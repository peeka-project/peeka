"""AgentCommandDispatchMixin implementation."""

import traceback
import time as _time
from typing import Any, Callable, Dict, Optional, cast

from peeka.core.jobs import JobCategory
from peeka.core.jobs import TERMINAL_STATUSES


class AgentCommandDispatchMixin:
    def _build_namespace_table(
        self,
    ) -> Dict[str, Dict[str, Any]]:
        """Return the namespace dispatch table.

        Each namespace maps action names to handler callables with signature
        ``(command: Dict[str, Any]) -> Dict[str, Any]``.  Two reserved keys
        control per-namespace behaviour:

        * ``"_pre"``: a zero-argument callable invoked before action dispatch.
        * ``"_unknown_error"``: a one-argument callable ``(action: str)``
          that returns the error dict for an unrecognised action.
        """
        return {
            "target": {
                "_unknown_error": lambda action: {
                    "status": "error",
                    "error_code": "UNSUPPORTED_CAPABILITY",
                    "message": f"Unknown target action: {action}",
                },
                "hello": lambda cmd: self._handle_target_hello(),
                "status": lambda cmd: self._handle_target_status(),
            },
            "client": {
                "_pre": lambda: self._get_client_registry().cleanup_idle(
                    idle_threshold_seconds=900
                ),
                "_unknown_error": lambda action: self._client_error(
                    "UNSUPPORTED_CAPABILITY", f"Unknown client action: {action}"
                ),
                "create": self._handle_client_create,
                "list": self._handle_client_list,
                "status": self._handle_client_status,
                "close": self._handle_client_close,
            },
            "job": {
                "_pre": lambda: self._job_registry().cleanup(retention_seconds=600),
                "_unknown_error": lambda action: self._job_error(
                    "UNSUPPORTED_CAPABILITY", f"Unknown job action: {action}"
                ),
                "list": self._handle_job_list,
                "status": self._handle_job_status,
                "inspect": self._handle_job_inspect,
                "interrupt": self._handle_job_interrupt,
                "cleanup": self._handle_job_cleanup,
            },
            "probe": {
                "_unknown_error": lambda action: self._probe_error(
                    "UNSUPPORTED_CAPABILITY", f"Unknown probe action: {action}"
                ),
                "list": self._handle_probe_list,
                "status": self._handle_probe_status,
                "inspect": self._handle_probe_inspect,
                "stop": self._handle_probe_stop,
                "pause": self._handle_probe_pause,
                "cleanup": self._handle_probe_cleanup,
            },
            "consumer": {
                "_unknown_error": lambda action: self._consumer_error(
                    "UNSUPPORTED_CAPABILITY", f"Unknown consumer action: {action}"
                ),
                "create": self._handle_consumer_create,
                "list": self._handle_consumer_list,
                "status": self._handle_consumer_status,
                "drain": self._handle_consumer_drain,
                "close": self._handle_consumer_close,
                "cleanup": self._handle_consumer_cleanup,
            },
            "dx": {
                "_unknown_error": lambda action: self._dx_error(
                    "UNSUPPORTED_CAPABILITY", f"Unknown dx action: {action}"
                ),
                "create": self._handle_dx_create,
                "list": self._handle_dx_list,
                "status": self._handle_dx_status,
                "add": self._handle_dx_add,
                "summary": self._handle_dx_summary,
                "export": self._handle_dx_export,
                "close": self._handle_dx_close,
            },
        }

    def _dispatch_namespace(
        self,
        cmd_type: str,
        action: str,
        command: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Dispatch *command* to its namespace handler.

        Returns ``None`` when *cmd_type* is not a recognised namespace, so the
        caller can fall through to the legacy ``_get_handler`` path.  For
        known namespaces an error dict is always returned for unknown actions
        (never ``None``).
        """
        ns_table = self._build_namespace_table()
        ns = ns_table.get(cmd_type)
        if ns is None:
            return None

        pre: Optional[Callable[[], None]] = ns.get("_pre")
        if pre is not None:
            pre()

        handler: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = ns.get(action)
        if handler is None:
            unknown_error: Optional[Callable[[str], Dict[str, Any]]] = ns.get(
                "_unknown_error"
            )
            if unknown_error is not None:
                return unknown_error(action)
            return {
                "status": "error",
                "error_code": "UNSUPPORTED_CAPABILITY",
                "message": f"Unknown action {action!r} for namespace {cmd_type!r}",
            }
        return handler(command)

    def _execute_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        cmd_type = command.get("type", "")

        # Handle legacy {"command":"ping"} as alias to target.hello
        if "command" in command and command.get("command") == "ping":
            return self._handle_target_hello()

        action = command.get("action") or ""
        if cmd_type == "probe" and not action:
            action = "start"

        result = self._dispatch_namespace(cmd_type, action, command)
        if result is not None:
            return result

        handler = self._get_handler(cmd_type)
        if handler:
            self._job_registry().cleanup(retention_seconds=600)

            client_session_id = str(command.get("client_session_id", ""))
            action = str(command.get("action", ""))
            foreground = not bool(command.get("background", False))
            params = {
                key: value
                for key, value in command.items()
                if key not in {"type", "action", "client_session_id", "background"}
            }
            category = getattr(type(handler), "category", "snapshot")
            allows_concurrent = bool(getattr(type(handler), "allows_concurrent", False))
            if category not in {"snapshot", "probe", "mutation"}:
                category = "snapshot"
            if category == "probe" and not action:
                action = "start"
            job_category = cast(JobCategory, category)

            client_registry = None
            client = None
            foreground_rule_applies = (
                (category != "snapshot" or not allows_concurrent)
                and foreground
                and bool(client_session_id)
            )
            if foreground_rule_applies:
                client_registry = self._get_client_registry()
                client = client_registry.get(client_session_id)
                if client is not None and client.foreground_job_id:
                    existing_job = self._job_registry().get(client.foreground_job_id)
                    if (
                        existing_job is not None
                        and existing_job.status not in TERMINAL_STATUSES
                    ):
                        message = (
                            f"Client {client_session_id} already has foreground job "
                            f"{client.foreground_job_id}"
                        )
                        return {
                            "status": "error",
                            "error_code": "JOB_ALREADY_RUNNING",
                            "message": message,
                            "error": f"JOB_ALREADY_RUNNING: {message}",
                        }

            mutation_lock_acquired = False
            if category == "mutation":
                mutation_lock_acquired = self._mutation_lock.acquire(timeout=5.0)
                if not mutation_lock_acquired:
                    message = "mutation in progress"
                    return {
                        "status": "error",
                        "error_code": "JOB_ALREADY_RUNNING",
                        "message": message,
                        "error": f"JOB_ALREADY_RUNNING: {message}",
                    }

            job = None
            try:
                if foreground and client_session_id and client is None:
                    client_registry = client_registry or self._get_client_registry()
                    client = client_registry.get(client_session_id)

                job = self._job_registry().create(
                    target_id=self._target_id_for_jobs(),
                    client_session_id=client_session_id,
                    command_type=str(cmd_type),
                    action=action,
                    params=params,
                    category=job_category,
                    foreground=foreground,
                )
                if (
                    job.foreground
                    and client_session_id
                    and client is not None
                    and client_registry is not None
                ):
                    client_registry.set_foreground_job(client_session_id, job.id)
                self._job_registry().set_status(job.id, "running")

                command["job_id"] = job.id
                result = handler.execute(command)

                if isinstance(result, dict) and result.get("status") == "error":
                    last_error = {
                        "code": str(result.get("error_code", "COMMAND_ERROR")),
                        "message": str(result.get("message") or result.get("error", "")),
                    }
                    self._job_registry().set_status(job.id, "failed", last_error=last_error)
                    self._get_consumer_registry().append_for_scope(
                        job.target_id,
                        source_type="job",
                        source_id=job.id,
                        record_type="error",
                        payload={
                            "job_id": job.id,
                            "command_type": cmd_type,
                            "action": action,
                            "error_code": last_error["code"],
                            "message": last_error["message"],
                        },
                    )
                    if (
                        job.foreground
                        and client_session_id
                        and client_registry is not None
                    ):
                        client_registry.clear_foreground_job(
                            client_session_id,
                            expected_job_id=job.id,
                        )
                    result["job_id"] = job.id
                    return result

                result_summary = result.get("data") if "data" in result else result
                final_status = "completed"
                if (
                    category == "probe"
                    and action == "start"
                    and result.get("status") == "success"
                ):
                    final_status = "streaming"
                    self._job_registry().set_status(
                        job.id,
                        final_status,
                        result_summary=result_summary,
                    )
                else:
                    self._job_registry().set_status(
                        job.id,
                        final_status,
                        result_summary=result_summary,
                    )
                self._get_consumer_registry().append_for_scope(
                    job.target_id,
                    source_type="job",
                    source_id=job.id,
                    record_type="summary" if final_status in TERMINAL_STATUSES else "result",
                    payload={
                        "job_id": job.id,
                        "command_type": cmd_type,
                        "action": action,
                        "status": final_status,
                        "data": result_summary,
                    },
                )
                if (
                    final_status in TERMINAL_STATUSES
                    and job.foreground
                    and client_session_id
                    and client_registry is not None
                ):
                    client_registry.clear_foreground_job(
                        client_session_id,
                        expected_job_id=job.id,
                    )

                result["job_id"] = job.id
                return result
            except Exception as e:
                error_entry = {
                    "timestamp": _time.time(),
                    "code": "COMMAND_EXECUTION_ERROR",
                    "message": str(e),
                }
                self._add_recent_error(error_entry)
                result = {
                    "status": "error",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
                if job is not None:
                    self._job_registry().set_status(
                        job.id,
                        "failed",
                        last_error={
                            "code": "COMMAND_EXECUTION_ERROR",
                            "message": str(e),
                        },
                    )
                    self._get_consumer_registry().append_for_scope(
                        job.target_id,
                        source_type="job",
                        source_id=job.id,
                        record_type="error",
                        payload={
                            "job_id": job.id,
                            "command_type": cmd_type,
                            "action": action,
                            "error_code": "COMMAND_EXECUTION_ERROR",
                            "message": str(e),
                        },
                    )
                    if (
                        job.foreground
                        and client_session_id
                        and client_registry is not None
                    ):
                        client_registry.clear_foreground_job(
                            client_session_id,
                            expected_job_id=job.id,
                        )
                    result["job_id"] = job.id
                return result
            finally:
                if mutation_lock_acquired:
                    self._mutation_lock.release()
        else:
            return {
                "status": "error",
                "error_code": "COMMAND_NOT_FOUND",
                "message": f"Unknown command type: {cmd_type}",
                "error": f"COMMAND_NOT_FOUND: Unknown command type: {cmd_type}",
            }
