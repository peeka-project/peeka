"""AgentJobControlMixin implementation."""

import traceback
import time as _time
from typing import Any, Dict

from peeka.core.jobs import TERMINAL_STATUSES


class AgentJobControlMixin:
    def _handle_job_list(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle job.list command - list jobs with optional filters."""
        try:
            from peeka.core.jobs import to_dict as job_to_dict

            target_id = command.get("target_id")
            client_session_id = command.get("client_session_id")
            status = command.get("status")

            jobs = self._job_registry().list(
                target=target_id if target_id else None,
                client=client_session_id if client_session_id else None,
                status=status if status else None,
            )

            return {
                "status": "success",
                "data": {"jobs": [job_to_dict(j) for j in jobs]},
            }
        except Exception as e:
            result = self._job_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_job_status(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle job.status command - get job summary by ID."""
        try:
            job_id = command.get("job_id", "")
            if not job_id:
                return self._job_error("JOB_NOT_FOUND", "job_id is required")

            job = self._job_registry().get(job_id)
            if job is None:
                return self._job_error("JOB_NOT_FOUND", f"Job {job_id!r} not found")

            return {
                "status": "success",
                "data": {
                    "job": {
                        "id": job.id,
                        "status": job.status,
                        "category": job.category,
                        "updated_at": job.updated_at,
                        "completed_at": job.completed_at,
                        "last_error": job.last_error,
                    }
                },
            }
        except Exception as e:
            result = self._job_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_job_inspect(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle job.inspect command - get full job details by ID."""
        try:
            from peeka.core.jobs import to_dict as job_to_dict

            job_id = command.get("job_id", "")
            if not job_id:
                return self._job_error("JOB_NOT_FOUND", "job_id is required")

            job = self._job_registry().get(job_id)
            if job is None:
                return self._job_error("JOB_NOT_FOUND", f"Job {job_id!r} not found")

            return {
                "status": "success",
                "data": {"job": job_to_dict(job)},
            }
        except Exception as e:
            result = self._job_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_job_interrupt(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle job.interrupt command - attempt to interrupt a job."""
        try:
            job_id = command.get("job_id", "")
            if not job_id:
                return self._job_error("JOB_NOT_FOUND", "job_id is required")

            job = self._job_registry().get(job_id)
            if job is None:
                return self._job_error("JOB_NOT_FOUND", f"Job {job_id!r} not found")

            if job.status in TERMINAL_STATUSES:
                return self._job_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Job is already in terminal state {job.status!r}",
                )

            if job.category == "probe":
                probe = self._find_probe_by_job_id(job.id)
                if probe is not None:
                    stop_result = self._stop_probe_resources(probe.id)
                    if stop_result.get("status") != "success":
                        return self._job_error(
                            "COMMAND_EXECUTION_ERROR",
                            self._response_message(
                                stop_result,
                                "Failed to stop probe resources",
                            ),
                        )
                    refreshed_probe = self.probe_registry.get(probe.id)
                    if (
                        refreshed_probe is not None
                        and refreshed_probe.status not in {"stopped", "failed"}
                    ):
                        self.probe_registry.set_status(
                            probe.id,
                            "stopped",
                            summary={"stop_result": stop_result},
                        )

                success = self._job_registry().set_status(job_id, "interrupted")
                if not success:
                    return self._job_error(
                        "UNSUPPORTED_CAPABILITY",
                        f"Cannot transition from {job.status} to interrupted",
                    )

                if job.client_session_id:
                    client_registry = self._get_client_registry()
                    client_registry.clear_foreground_job(
                        job.client_session_id, expected_job_id=job.id
                    )

                return {
                    "status": "success",
                    "data": {"job_id": job_id, "status": "interrupted"},
                }
            elif job.category in ("snapshot", "mutation"):
                return self._job_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Interrupt not supported for {job.category} jobs",
                )
            else:
                return self._job_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown job category: {job.category}",
                )
        except Exception as e:
            result = self._job_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_job_cleanup(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle job.cleanup command - remove old terminal jobs."""
        try:
            target_id = command.get("target_id")
            completed_only = bool(command.get("completed_only", False))
            older_than_seconds = int(command.get("older_than_seconds", 600))

            now = _time.time()
            candidate_jobs = self._job_registry().list(
                target=target_id if target_id else None
            )

            to_remove = []
            for job in candidate_jobs:
                if job.status not in TERMINAL_STATUSES:
                    continue
                if completed_only and job.status != "completed":
                    continue
                terminal_at = job.completed_at if job.completed_at is not None else job.updated_at
                age = now - terminal_at
                if age > older_than_seconds:
                    to_remove.append(job.id)

            removed_ids = []
            for job_id in to_remove:
                if self._job_registry().remove(job_id):
                    removed_ids.append(job_id)

            return {
                "status": "success",
                "data": {"removed": removed_ids},
            }
        except Exception as e:
            result = self._job_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result
