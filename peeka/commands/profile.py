"""Profile Command - direct management of profile sessions in ProfileRegistry."""

import io
import json
import logging
import threading
from typing import Any, ClassVar, Dict, List, Optional, TYPE_CHECKING

from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand
from peeka.commands.top import _PROFILE_REGISTRY
from peeka.core.profile.exact import ExactProfileSampler
from peeka.core.profile.models import ProfileConfig
from peeka.core.profile.processors import ProcessedProfile
from peeka.core.profile.renderers import (
    JsonRenderer,
    PerfettoRenderer,
    SpeedscopeRenderer,
    TextRenderer,
)

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent

logger = logging.getLogger(__name__)

_RENDERER_MAP = {
    "json": JsonRenderer,
    "text": TextRenderer,
    "speedscope": SpeedscopeRenderer,
    "perfetto": PerfettoRenderer,
}


class ProfileCommand(ResourceOwningCommand):
    """Manage profile sessions in the shared ProfileRegistry.

    Actions:
    - start: Create a new profiling session and return its profile_id.
    - stop: Stop a running session and return its summary.
    - snapshot: Return a point-in-time JSON snapshot of a session.
    - list: List all tracked sessions with metadata.
    - cleanup: Remove old stopped sessions from the registry.
    - export: Render a session to a chosen output format (json/text/speedscope/perfetto).
    """

    is_resource_owner: bool = True
    cleanup_scope: CleanupScope = CleanupScope.DETACH_ONLY
    category: ClassVar[str] = "snapshot"
    allows_concurrent: ClassVar[bool] = False

    def __init__(self, agent: Optional["PeekaAgent"] = None):
        super().__init__(agent)
        self._exact_sampler: Optional[ExactProfileSampler] = None
        self._exact_stop_timer: Optional[threading.Timer] = None

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = params.get("action", "list")

            if action == "start":
                return self._start(params)
            elif action == "stop":
                return self._stop(params)
            elif action == "snapshot":
                return self._snapshot(params)
            elif action == "list":
                return self._list(params)
            elif action == "cleanup":
                return self._cleanup(params)
            elif action == "export":
                return self._export(params)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        config = ProfileConfig(
            backend=params.get("backend", "sampling"),
            interval_ms=params.get("interval_ms", 10),
            duration_ms=params.get("duration_ms"),
            max_samples=params.get("max_samples", 100000),
        )
        profile_id = _PROFILE_REGISTRY.start(config)
        if config.backend == "exact":
            sampler = ExactProfileSampler(
                profile_id,
                _PROFILE_REGISTRY,
                max_events=params.get("max_events", 10000),
            )
            capability = sampler.check_capability()
            if not capability["available"]:
                _PROFILE_REGISTRY.stop(profile_id)
                return {
                    "status": "error",
                    "error": capability["reason"],
                    "capability": capability,
                }
            sampler.start()
            self._exact_sampler = sampler
            if config.duration_ms is not None:
                self._exact_stop_timer = threading.Timer(
                    config.duration_ms / 1000.0,
                    sampler.stop,
                )
                self._exact_stop_timer.daemon = True
                self._exact_stop_timer.start()
        return {"status": "success", "profile_id": profile_id}

    def _stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        profile_id = params.get("profile_id")
        if not profile_id:
            return {"status": "error", "error": "Missing profile_id"}
        try:
            if self._exact_sampler is not None:
                self._exact_sampler.stop()
                self._exact_sampler = None
            if self._exact_stop_timer is not None:
                self._exact_stop_timer.cancel()
                self._exact_stop_timer = None
            session = _PROFILE_REGISTRY.stop(profile_id)
            return {
                "status": "success",
                "profile_id": profile_id,
                "summary": session.summary.to_dict() if session.summary else {},
            }
        except KeyError:
            return {"status": "error", "error": "profile not found"}

    def _snapshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        profile_id = params.get("profile_id")
        if not profile_id:
            return {"status": "error", "error": "Missing profile_id"}
        try:
            session = _PROFILE_REGISTRY.snapshot(profile_id)
        except KeyError:
            return {"status": "error", "error": "profile not found"}

        processed = ProcessedProfile(
            profile_id=session.profile_id,
            backend=session.backend,
            session=session,
        )
        buf = io.StringIO()
        JsonRenderer().render(processed, buf)
        result = json.loads(buf.getvalue())
        return {"status": "success", "profile_id": profile_id, "snapshot": result}

    def _list(self, params: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG002
        sessions = _PROFILE_REGISTRY.list_sessions()
        return {
            "status": "success",
            "sessions": [
                {
                    "profile_id": s.profile_id,
                    "backend": s.backend,
                    "status": s.status,
                    "started_at": s.started_at,
                    "sample_count": len(s.samples),
                }
                for s in sessions
            ],
        }

    def _cleanup(self, params: Dict[str, Any]) -> Dict[str, Any]:
        count = _PROFILE_REGISTRY.cleanup(
            older_than_secs=params.get("older_than_secs"),
            max_sessions=params.get("max_sessions"),
        )
        return {"status": "success", "removed": count}

    def _export(self, params: Dict[str, Any]) -> Dict[str, Any]:
        profile_id = params.get("profile_id")
        if not profile_id:
            return {"status": "error", "error": "Missing profile_id"}

        format_name = params.get("format", "json")
        renderer_cls = _RENDERER_MAP.get(format_name)
        if renderer_cls is None:
            return {"status": "error", "error": f"Unknown format: {format_name}"}

        try:
            session = _PROFILE_REGISTRY.snapshot(profile_id)
        except KeyError:
            return {"status": "error", "error": "profile not found"}

        processed = ProcessedProfile(
            profile_id=session.profile_id,
            backend=session.backend,
            session=session,
        )
        buf = io.StringIO()
        renderer_cls().render(processed, buf)
        return {
            "status": "success",
            "content": buf.getvalue(),
            "format": format_name,
        }

    def stop_active_resources(
        self, pattern: Optional[str], reason: str
    ) -> Dict[str, Any]:
        sessions = _PROFILE_REGISTRY.list_sessions()
        stopped: List[str] = []
        errors: List[Dict[str, Any]] = []

        if self._exact_sampler is not None:
            try:
                self._exact_sampler.stop()
                self._exact_sampler = None
                if self._exact_stop_timer is not None:
                    self._exact_stop_timer.cancel()
                    self._exact_stop_timer = None
            except Exception as exc:
                logger.error(
                    "[peeka Profile] exact sampler cleanup failed (%s)",
                    reason,
                    exc_info=True,
                )
                errors.append({"profile_id": "exact", "error": str(exc)})

        for session in sessions:
            if session.status != "running":
                continue
            try:
                _PROFILE_REGISTRY.stop(session.profile_id)
                stopped.append(session.profile_id)
            except Exception as exc:
                logger.error(
                    "[peeka Profile] stop_active_resources failed for %s (%s)",
                    session.profile_id,
                    reason,
                    exc_info=True,
                )
                errors.append({"profile_id": session.profile_id, "error": str(exc)})

        return {"stopped": stopped, "errors": errors}

    def list_active_resources(self) -> Dict[str, Any]:
        sessions = _PROFILE_REGISTRY.list_sessions()
        active = [
            {
                "profile_id": s.profile_id,
                "backend": s.backend,
                "started_at": s.started_at,
            }
            for s in sessions
            if s.status == "running"
        ]
        return {"active": active}
