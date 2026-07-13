"""Profile Command - direct management of profile sessions in ProfileRegistry."""

import io
import json
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand
from peeka.core.profile.models import ProfileConfig
from peeka.core.profile.processors import ProcessedProfile
from peeka.core.profile.renderers import (
    JsonRenderer,
    PerfettoRenderer,
    SpeedscopeRenderer,
    TextRenderer,
)
from peeka.commands.top import _PROFILE_REGISTRY

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

    def __init__(self, agent: Optional["PeekaAgent"] = None):
        super().__init__(agent)

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
        return {"status": "success", "profile_id": profile_id}

    def _stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        profile_id = params.get("profile_id")
        if not profile_id:
            return {"status": "error", "error": "Missing profile_id"}
        try:
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
