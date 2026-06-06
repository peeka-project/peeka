"""AgentCommandDispatchMixin implementation."""

import traceback
import time as _time
from typing import Any, Dict, cast

from peeka.core.jobs import JobCategory
from peeka.core.jobs import TERMINAL_STATUSES


class AgentCommandDispatchMixin:
    def _execute_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        cmd_type = command.get("type", "")

        # Handle legacy {"command":"ping"} as alias to target.hello
        if "command" in command and command.get("command") == "ping":
            return self._handle_target_hello()

        # Handle new target namespace
        if cmd_type == "target":
            action = command.get("action", "")
            if action == "hello":
                return self._handle_target_hello()
            elif action == "status":
                return self._handle_target_status()
            else:
                return {"status": "error", "error": f"Unknown target action: {action}"}

        if cmd_type == "client":
            action = command.get("action", "")
            registry = self._get_client_registry()
            registry.cleanup_idle(idle_threshold_seconds=900)
            if action == "create":
                return self._handle_client_create(command)
            elif action == "list":
                return self._handle_client_list(command)
            elif action == "status":
                return self._handle_client_status(command)
            elif action == "close":
                return self._handle_client_close(command)
            else:
                return self._client_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown client action: {action}",
                )

        if cmd_type == "job":
            action = command.get("action", "")
            self._job_registry().cleanup(retention_seconds=600)
            if action == "list":
                return self._handle_job_list(command)
            elif action == "status":
                return self._handle_job_status(command)
            elif action == "inspect":
                return self._handle_job_inspect(command)
            elif action == "interrupt":
                return self._handle_job_interrupt(command)
            elif action == "cleanup":
                return self._handle_job_cleanup(command)
            else:
                return self._job_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown job action: {action}",
                )

        if cmd_type == "probe":
            action = command.get("action", "")
            if action == "list":
                return self._handle_probe_list(command)
            elif action == "status":
                return self._handle_probe_status(command)
            elif action == "inspect":
                return self._handle_probe_inspect(command)
            elif action == "stop":
                return self._handle_probe_stop(command)
            elif action == "pause":
                return self._handle_probe_pause(command)
            elif action == "cleanup":
                return self._handle_probe_cleanup(command)
            else:
                return self._probe_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown probe action: {action}",
                )

        if cmd_type == "consumer":
            action = command.get("action", "")
            if action == "create":
                return self._handle_consumer_create(command)
            elif action == "list":
                return self._handle_consumer_list(command)
            elif action == "status":
                return self._handle_consumer_status(command)
            elif action == "drain":
                return self._handle_consumer_drain(command)
            elif action == "close":
                return self._handle_consumer_close(command)
            elif action == "cleanup":
                return self._handle_consumer_cleanup(command)
            else:
                return self._consumer_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown consumer action: {action}",
                )

        if cmd_type == "dx":
            action = command.get("action", "")
            if action == "create":
                return self._handle_dx_create(command)
            elif action == "list":
                return self._handle_dx_list(command)
            elif action == "status":
                return self._handle_dx_status(command)
            elif action == "add":
                return self._handle_dx_add(command)
            elif action == "summary":
                return self._handle_dx_summary(command)
            elif action == "export":
                return self._handle_dx_export(command)
            elif action == "close":
                return self._handle_dx_close(command)
            else:
                return self._dx_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown dx action: {action}",
                )

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
