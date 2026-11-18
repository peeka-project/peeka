"""AgentCommandDispatchMixin implementation."""

import traceback
import time as _time
from typing import Any, Callable, Dict, List, Optional, cast

from peeka.core.jobs import JobCategory
from peeka.core.jobs import TERMINAL_STATUSES
from peeka.core.probes import ProbeContext
from peeka.core.probes import TERMINAL_STATUSES as PROBE_TERMINAL_STATUSES


class AgentCommandDispatchMixin:
    def _cleanup_idle_clients(self) -> List[str]:
        """Close idle client sessions and clean up their owned consumers."""
        closed_ids = self._get_client_registry().cleanup_idle(
            idle_threshold_seconds=900
        )
        if closed_ids:
            consumer_registry = self._get_consumer_registry()
            for client_session_id in closed_ids:
                consumer_registry.cleanup_for_client(client_session_id)
        return closed_ids

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
                "_pre": self._cleanup_idle_clients,
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
                "_pre": self._cleanup_idle_clients,
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
                "add_profile": self._handle_dx_add_profile,
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

    def _finish_streaming_job(
        self,
        job: Any,
        status: str,
        result_summary: Optional[Dict[str, Any]] = None,
        last_error: Optional[Dict[str, str]] = None,
    ) -> None:
        """Complete a non-terminal CommandJob and clear its foreground slot."""
        if job.status not in TERMINAL_STATUSES:
            transitioned = self._job_registry().set_status(
                job.id,
                status,  # type: ignore[arg-type]
                result_summary=result_summary,
                last_error=last_error,
            )
            if transitioned:
                try:
                    record_type = "error" if status == "failed" else "summary"
                    payload: Dict[str, Any] = {
                        "job_id": job.id,
                        "command_type": job.command_type,
                        "action": job.action,
                        "status": status,
                    }
                    if last_error is not None:
                        payload["error_code"] = last_error.get("code", "")
                        payload["message"] = last_error.get("message", "")
                    if result_summary is not None:
                        payload["data"] = result_summary
                    self._get_consumer_registry().append_for_scope(
                        job.target_id,
                        source_type="job",
                        source_id=job.id,
                        record_type=record_type,
                        payload=payload,
                    )
                except Exception:
                    pass
        if job.foreground and job.client_session_id:
            self._get_client_registry().clear_foreground_job(
                job.client_session_id,
                expected_job_id=job.id,
            )

    def _reconcile_post_reset_probes(self) -> None:
        """Stop orphaned injector probe contexts and finish terminal probe jobs after reset."""
        injector = getattr(self, "injector", None)
        with self._probe_context_lock:
            candidates = [
                stream_key
                for stream_key, probe_type in self._probe_context_types.items()
                if probe_type in ProbeContext.injector_managed_streaming_types()
            ]
        if injector is not None:
            for stream_key in candidates:
                if injector.get_watch_info(stream_key) is None:
                    self.stop_probe_context(stream_key)

        for job in self._job_registry().list(status="streaming"):
            probe = self._find_probe_by_job_id(job.id)
            if probe is not None and probe.status in PROBE_TERMINAL_STATUSES:
                self._finish_probe_job(
                    probe.id,
                    "failed" if probe.status == "failed" else "completed",
                    result_summary=dict(probe.summary),
                    last_error=probe.last_error if probe.status == "failed" else None,
                )

    def _reconcile_stopped_probe_jobs(
        self,
        cmd_type: str,
        command: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """Ensure stopped probe contexts, jobs, and foreground slots are finalized."""
        stream_key = (
            command.get("watch_id")
            or command.get("monitor_id")
            or command.get("top_id")
            or result.get("watch_id")
            or result.get("monitor_id")
            or result.get("top_id")
        )
        if stream_key:
            stream_key_str = str(stream_key)
            if self.get_probe_context(stream_key_str) is not None:
                self.stop_probe_context(stream_key_str)

            for job in self._job_registry().list(status="streaming"):
                summary = job.result_summary if isinstance(job.result_summary, dict) else {}
                if (
                    summary.get("watch_id") == stream_key_str
                    or summary.get("monitor_id") == stream_key_str
                    or summary.get("top_id") == stream_key_str
                ):
                    probe = self._find_probe_by_job_id(job.id)
                    if probe is not None and probe.status not in PROBE_TERMINAL_STATUSES:
                        self.probe_registry.set_status(probe.id, "stopped")
                        probe = self.probe_registry.get(probe.id)
                    job_status = (
                        "failed"
                        if probe is not None and probe.status == "failed"
                        else "completed"
                    )
                    last_error = (
                        probe.last_error
                        if probe is not None and probe.status == "failed"
                        else None
                    )
                    self._finish_streaming_job(
                        job,
                        job_status,
                        result_summary={"stopped_by": cmd_type, "stream_key": stream_key_str},
                        last_error=last_error,
                    )
            return

        injector_types = ProbeContext.injector_managed_streaming_types()
        for job in self._job_registry().list(status="streaming"):
            if job.command_type != cmd_type and not (
                cmd_type in injector_types and job.command_type in injector_types
            ):
                continue
            probe = self._find_probe_by_job_id(job.id)
            if probe is not None and probe.status not in PROBE_TERMINAL_STATUSES:
                self.probe_registry.set_status(probe.id, "stopped")
                probe = self.probe_registry.get(probe.id)
            job_status = (
                "failed"
                if probe is not None and probe.status == "failed"
                else "completed"
            )
            last_error = (
                probe.last_error
                if probe is not None and probe.status == "failed"
                else None
            )
            self._finish_streaming_job(
                job,
                job_status,
                result_summary={"stopped_by": cmd_type},
                last_error=last_error,
            )

    def _cleanup_after_stopped_command(
        self,
        handler: Any,
        job_id: str,
        result: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Teardown resources created by a command that finished after agent.stop()."""
        if (
            getattr(handler, "is_resource_owner", False) is True
            and callable(getattr(handler, "stop_active_resources", None))
        ):
            try:
                handler.stop_active_resources(pattern=None, reason="detach")
            except Exception:
                pass

        probe = self._find_probe_by_job_id(job_id)
        if probe is not None:
            context_ref = self._find_probe_context_by_probe_id(probe.id)
            if context_ref is not None:
                self.stop_probe_context(context_ref[0])
            refreshed = self.probe_registry.get(probe.id)
            if refreshed is not None and refreshed.status not in PROBE_TERMINAL_STATUSES:
                self.probe_registry.set_status(probe.id, "stopped")

        if isinstance(result, dict):
            watch_id = result.get("watch_id")
            if watch_id:
                injector = getattr(self, "injector", None)
                if injector is not None and injector.get_watch_info(str(watch_id)) is not None:
                    try:
                        injector.uninject(str(watch_id))
                    except Exception:
                        pass
                observer = getattr(self, "observer", None)
                if observer is not None:
                    try:
                        observer.unregister_watch(str(watch_id))
                    except Exception:
                        pass

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

            is_stop_command = action == "stop" and category in {"probe", "snapshot"}
            is_reset_command = cmd_type == "reset" and action in {"", "reset"}

            client_registry = None
            reserved_job_id: Optional[str] = None
            reserved_foreground = False
            foreground_rule_applies = (
                (category != "snapshot" or not allows_concurrent)
                and foreground
                and bool(client_session_id)
                and not is_stop_command
            )
            if foreground_rule_applies:
                client_registry = self._get_client_registry()
                candidate_job_id = self._job_registry().generate_job_id()

                def _is_job_active(existing_id: str) -> bool:
                    existing = self._job_registry().get(existing_id)
                    return existing is not None and existing.status not in TERMINAL_STATUSES

                reserved, blocking_job_id = client_registry.reserve_foreground_job(
                    client_session_id,
                    candidate_job_id,
                    is_job_active=_is_job_active,
                )
                if reserved:
                    reserved_job_id = candidate_job_id
                    reserved_foreground = True
                elif blocking_job_id is not None:
                    allow_reset_over_streaming = False
                    if is_reset_command:
                        blocking_job = self._job_registry().get(blocking_job_id)
                        if blocking_job is not None and blocking_job.status == "streaming":
                            allow_reset_over_streaming = True
                    if not allow_reset_over_streaming:
                        message = (
                            f"Client {client_session_id} already has foreground job "
                            f"{blocking_job_id}"
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
                    if (
                        reserved_foreground
                        and client_registry is not None
                        and reserved_job_id is not None
                    ):
                        client_registry.clear_foreground_job(
                            client_session_id,
                            expected_job_id=reserved_job_id,
                        )
                    message = "mutation in progress"
                    return {
                        "status": "error",
                        "error_code": "JOB_ALREADY_RUNNING",
                        "message": message,
                        "error": f"JOB_ALREADY_RUNNING: {message}",
                    }

            job = None
            try:
                job = self._job_registry().create(
                    target_id=self._target_id_for_jobs(),
                    client_session_id=client_session_id,
                    command_type=str(cmd_type),
                    action=action,
                    params=params,
                    category=job_category,
                    foreground=foreground,
                    job_id=reserved_job_id,
                )
                if reserved_foreground and client_registry is not None:
                    client_registry.confirm_foreground_job(client_session_id, job.id)
                self._job_registry().set_status(job.id, "running")

                command["job_id"] = job.id
                result = handler.execute(command)

                agent_stopped = bool(
                    getattr(self, "_stopping", False)
                    or getattr(self, "_stopped", False)
                    or not getattr(self, "running", True)
                )
                if agent_stopped:
                    self._cleanup_after_stopped_command(handler, job.id, result)

                if isinstance(result, dict) and result.get("status") == "error":
                    probe = self._find_probe_by_job_id(job.id)
                    if probe is not None and probe.status not in PROBE_TERMINAL_STATUSES:
                        self.probe_registry.set_status(
                            probe.id,
                            "failed",
                            error=str(result.get("message") or result.get("error", "")),
                        )
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
                    if reserved_foreground and client_registry is not None:
                        client_registry.clear_foreground_job(
                            client_session_id,
                            expected_job_id=job.id,
                        )
                    result["job_id"] = job.id
                    return result

                if is_reset_command:
                    self._reconcile_post_reset_probes()
                if is_stop_command:
                    self._reconcile_stopped_probe_jobs(cmd_type, command, result)

                result_summary = result.get("data") if "data" in result else result
                final_status = "completed"
                probe = None
                last_error_for_job: Optional[Dict[str, str]] = None
                if (
                    category == "probe"
                    and action == "start"
                    and result.get("status") == "success"
                ):
                    probe = self._find_probe_by_job_id(job.id)
                    if probe is not None and probe.status == "failed":
                        final_status = "failed"
                        last_error_for_job = probe.last_error
                    elif (
                        agent_stopped
                        or (probe is not None and probe.status == "stopped")
                    ):
                        final_status = "completed"
                    else:
                        final_status = "streaming"

                transitioned = self._job_registry().set_status(
                    job.id,
                    final_status,
                    result_summary=result_summary,
                    last_error=last_error_for_job,
                )
                if not transitioned:
                    refreshed_job = self._job_registry().get(job.id)
                    if refreshed_job is not None:
                        final_status = refreshed_job.status

                if transitioned:
                    record_type = (
                        "error"
                        if final_status == "failed"
                        else "summary"
                        if final_status in TERMINAL_STATUSES
                        else "result"
                    )
                    self._get_consumer_registry().append_for_scope(
                        job.target_id,
                        source_type="job",
                        source_id=job.id,
                        record_type=record_type,
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
                    and reserved_foreground
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
                    if reserved_foreground and client_registry is not None:
                        client_registry.clear_foreground_job(
                            client_session_id,
                            expected_job_id=job.id,
                        )
                    result["job_id"] = job.id
                elif (
                    reserved_foreground
                    and client_registry is not None
                    and reserved_job_id is not None
                ):
                    client_registry.clear_foreground_job(
                        client_session_id,
                        expected_job_id=reserved_job_id,
                    )
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
