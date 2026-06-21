"""AgentProbeControlMixin implementation."""

import traceback
from typing import Any, Dict, List, Optional, Tuple

from peeka.core.jobs import TERMINAL_STATUSES
from peeka.core.probes import ProbeContext


class AgentProbeControlMixin:
    def track_probe_context(
        self,
        stream_key: str,
        probe_context: ProbeContext,
        probe_type: str,
    ) -> None:
        """Track an active probe context by stream identifier."""
        with self._probe_context_lock:
            self._probe_contexts[stream_key] = probe_context
            self._probe_context_types[stream_key] = probe_type

    def get_probe_context(self, stream_key: str) -> Optional[ProbeContext]:
        """Return an active probe context for a stream key."""
        with self._probe_context_lock:
            return self._probe_contexts.get(stream_key)

    def stop_probe_context(
        self,
        stream_key: str,
        exc_info: Optional[Tuple[Any, Any, Any]] = None,
    ) -> None:
        """Stop and forget an active probe context."""
        with self._probe_context_lock:
            probe_context = self._probe_contexts.pop(stream_key, None)
            self._probe_context_types.pop(stream_key, None)

        if probe_context is None:
            return

        if exc_info is None:
            probe_context.__exit__(None, None, None)
            return

        probe_context.__exit__(exc_info[0], exc_info[1], exc_info[2])

    def untrack_probe_context(self, stream_key: str) -> None:
        """Forget an active probe context without closing it."""
        with self._probe_context_lock:
            self._probe_contexts.pop(stream_key, None)
            self._probe_context_types.pop(stream_key, None)

    def _find_probe_context_by_probe_id(
        self, probe_id: str
    ) -> Optional[Tuple[str, str]]:
        """Return the tracked stream key and probe type for a probe id."""
        with self._probe_context_lock:
            for stream_key, probe_context in self._probe_contexts.items():
                if probe_context.probe_id == probe_id:
                    probe_type = self._probe_context_types.get(stream_key, "")
                    return stream_key, probe_type
        return None

    def stop_probe_contexts_by_type(self, probe_types: List[str]) -> None:
        """Stop all tracked probe contexts whose type matches *probe_types*."""
        with self._probe_context_lock:
            stream_keys = [
                stream_key
                for stream_key, probe_type in self._probe_context_types.items()
                if probe_type in probe_types
            ]

        for stream_key in stream_keys:
            self.stop_probe_context(stream_key)

    def list_tracked_probe_types(self) -> List[str]:
        """Return a snapshot of currently tracked probe-context types.

        Returns a deduplicated, sorted list. The lock is held only during
        snapshot; result is a new list, not a live view. Empty list is a
        valid no-op for callers (nothing to stop).

        Note: A probe type registered after this snapshot is taken will not
        appear in the result. This matches the existing
        stop_probe_contexts_by_type snapshot semantics and is an accepted
        limitation.
        """
        with self._probe_context_lock:
            return sorted(set(self._probe_context_types.values()))

    def _stop_probe_resources(self, probe_id: str) -> Dict[str, Any]:
        """Stop runtime resources backing an active ProbeRun."""
        context_ref = self._find_probe_context_by_probe_id(probe_id)
        if context_ref is None:
            return {"status": "success", "data": {"resource_stopped": False}}

        stream_key, probe_type = context_ref
        if probe_type in ("watch", "trace", "stack", "monitor"):
            handler = self._get_handler(probe_type)
            if handler is None:
                return {
                    "status": "error",
                    "error": f"Handler not found for probe type {probe_type!r}",
                }
            return handler.execute({"action": "stop", "watch_id": stream_key})

        if probe_type == "top":
            handler = self._get_handler("top")
            if handler is None:
                return {"status": "error", "error": "Handler not found for probe type 'top'"}
            return handler.execute({"action": "stop", "top_id": stream_key})

        self.stop_probe_context(stream_key)
        return {
            "status": "success",
            "data": {"resource_stopped": True, "probe_type": probe_type},
        }

    def _find_probe_by_job_id(self, job_id: str) -> Optional[Any]:
        """Return the first ProbeRun associated with a command job."""
        for probe in self.probe_registry.list():
            if probe.job_id == job_id:
                return probe
        return None

    def _finish_probe_job(
        self,
        probe_id: str,
        status: str,
        result_summary: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Move the CommandJob associated with a probe to a terminal state."""
        probe = self.probe_registry.get(probe_id)
        if probe is None or not probe.job_id:
            return

        job = self._job_registry().get(probe.job_id)
        if job is None or job.status in TERMINAL_STATUSES:
            return

        if not self._job_registry().set_status(
            probe.job_id,
            status,  # type: ignore[arg-type]
            result_summary=result_summary,
        ):
            return

        if job.foreground and job.client_session_id:
            client_registry = self._get_client_registry()
            client_registry.clear_foreground_job(
                job.client_session_id,
                expected_job_id=job.id,
            )


    def _handle_probe_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            target_id = params.get("target_id")
            status = params.get("status")
            probe_type = params.get("probe_type")

            probes = self.probe_registry.list(
                target_id=target_id,
                status=status,
                type=probe_type,
            )

            return {
                "status": "success",
                "data": {"probes": [probe.to_dict() for probe in probes]},
            }
        except Exception as e:
            result = self._probe_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_probe_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            probe_id = params.get("probe_id", "")
            if not probe_id:
                return self._probe_error("PROBE_NOT_FOUND", "probe_id is required")

            probe = self.probe_registry.get(probe_id)
            if probe is None:
                return self._probe_error("PROBE_NOT_FOUND", f"Probe {probe_id!r} not found")

            return {
                "status": "success",
                "data": {"probe": probe.to_dict()},
            }
        except Exception as e:
            result = self._probe_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_probe_inspect(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            probe_id = params.get("probe_id", "")
            if not probe_id:
                return self._probe_error("PROBE_NOT_FOUND", "probe_id is required")

            probe = self.probe_registry.get(probe_id)
            if probe is None:
                return self._probe_error("PROBE_NOT_FOUND", f"Probe {probe_id!r} not found")

            events_limit = int(params.get("events_limit", 100))
            if events_limit > 100:
                events_limit = 100

            recent_events = self.probe_registry.get_recent_events(probe_id, limit=events_limit)

            return {
                "status": "success",
                "data": {
                    "probe": probe.to_dict(),
                    "events": [
                        {
                            "event_id": event.event_id,
                            "probe_id": event.probe_id,
                            "target_id": event.target_id,
                            "sequence": event.sequence,
                            "timestamp": event.timestamp,
                            "payload": event.payload,
                        }
                        for event in recent_events
                    ],
                },
            }
        except Exception as e:
            result = self._probe_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_probe_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from peeka.core.probes import TERMINAL_STATUSES as PROBE_TERMINAL_STATUSES

            probe_id = params.get("probe_id", "")
            if not probe_id:
                return self._probe_error("PROBE_NOT_FOUND", "probe_id is required")

            probe = self.probe_registry.get(probe_id)
            if probe is None:
                return self._probe_error("PROBE_NOT_FOUND", f"Probe {probe_id!r} not found")

            if probe.status in PROBE_TERMINAL_STATUSES:
                self._finish_probe_job(
                    probe_id,
                    "completed",
                    result_summary={
                        "probe_id": probe_id,
                        "status": probe.status,
                        "summary": f"Probe already in terminal state {probe.status}",
                    },
                )
                return {
                    "status": "success",
                    "data": {
                        "probe_id": probe_id,
                        "status": probe.status,
                        "summary": f"Probe already in terminal state {probe.status}",
                    },
                }

            stop_result = self._stop_probe_resources(probe_id)
            if stop_result.get("status") != "success":
                return self._probe_error(
                    "COMMAND_EXECUTION_ERROR",
                    self._response_message(stop_result, "Failed to stop probe resources"),
                )

            refreshed = self.probe_registry.get(probe_id)
            if refreshed is not None and refreshed.status not in PROBE_TERMINAL_STATUSES:
                success = self.probe_registry.set_status(
                    probe_id,
                    "stopped",
                    summary={"stop_result": stop_result},
                )
            else:
                success = True
            if not success:
                return self._probe_error(
                    "COMMAND_EXECUTION_ERROR",
                    f"Failed to transition probe from {probe.status} to stopped",
                )

            self._finish_probe_job(
                probe_id,
                "completed",
                result_summary={"probe_id": probe_id, "stop_result": stop_result},
            )

            return {
                "status": "success",
                "data": {"probe_id": probe_id, "status": "stopped"},
            }
        except Exception as e:
            result = self._probe_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_probe_pause(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._probe_error(
            "UNSUPPORTED_CAPABILITY",
            "pause is not yet implemented",
        )

    def _handle_probe_cleanup(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            older_than_seconds = float(params.get("older_than_seconds", 600))
            completed_only = bool(params.get("completed_only", True))
            target_id = params.get("target_id")

            removed_ids = self.probe_registry.cleanup(
                older_than_seconds=older_than_seconds,
                target_id=target_id,
                completed_only=completed_only,
            )

            return {
                "status": "success",
                "data": {"removed_ids": removed_ids},
            }
        except Exception as e:
            result = self._probe_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result
