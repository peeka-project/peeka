"""
Reset Command - Restore enhanced methods to original state
Similar to Arthas 'reset' command
"""

from __future__ import annotations

import logging
from typing import ClassVar, TYPE_CHECKING, cast

from peeka.commands.base import BaseCommand
from peeka.core.agent_control.lifecycle import (
    _is_resource_owner,
    stop_resource_owners_for_reset,
)

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class ResetCommand(BaseCommand):
    is_resource_owner = False  # explicit; not a resource owner
    """
    Reset command - removes instrumentation and restores original functions

    Usage:
        reset                 # Reset all enhancements
        reset <pattern>       # Reset matching pattern (wildcards: *, ?)
        reset --list          # List current enhancements

    Actions:
        reset: Remove instrumentation, restore original functions
        list: Show all current enhancements

    Examples:
        reset                           # Reset all
        reset myapp.service.*          # Reset myapp.service module
        reset myapp.service.UserService.query  # Reset specific method
        reset --list                    # List enhancements
    """

    category: ClassVar[str] = "mutation"
    allows_concurrent: ClassVar[bool] = False
    agent: "PeekaAgent"

    def __init__(self, agent: "PeekaAgent"):
        super().__init__()
        self.agent = agent

    def execute(self, params: dict[str, object]) -> dict[str, object]:
        try:
            action = str(params.get("action", "reset"))

            if action == "reset":
                return self._reset(params)
            elif action == "list":
                return self._list_enhanced(params)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _reset(self, params: dict[str, object]) -> dict[str, object]:
        import fnmatch

        pattern_obj = params.get("pattern")
        pattern = pattern_obj if isinstance(pattern_obj, str) else None

        # CLEANUP CONTRACT:
        # 1) Command-level monitor resources own real runtime state and must be cleaned first.
        # 2) Probe-context bookkeeping follows so registry state matches reset teardown.
        # Both layers must complete before injector teardown.
        # REGRESSION GUARD: c03971e
        logger = logging.getLogger(__name__)
        resource_owners_summary = stop_resource_owners_for_reset(self.agent, pattern, logger)

        stop_context = getattr(self.agent, "stop_probe_context", None)
        probe_context_lock = getattr(self.agent, "_probe_context_lock", None)
        probe_context_types = cast(dict[str, object], getattr(self.agent, "_probe_context_types", {}))
        probe_contexts = cast(dict[str, object], getattr(self.agent, "_probe_contexts", {}))

        probe_context_stopped: list[str] = []
        probe_context_errors: list[dict[str, object]] = []

        if callable(stop_context) and probe_context_lock is not None:
            command_handlers = getattr(self.agent, "command_handlers", {}) or {}
            stream_keys: list[str] = []
            with probe_context_lock:
                for stream_key in list(probe_context_types.keys()):
                    probe_type = probe_context_types.get(stream_key)
                    if isinstance(probe_type, str):
                        handler = command_handlers.get(probe_type)
                        scope = getattr(handler, "cleanup_scope", None)
                        if (
                            _is_resource_owner(handler)
                            and getattr(scope, "value", None) == "detach_only"
                        ):
                            continue
                    probe_context = probe_contexts.get(stream_key)
                    probe_run = getattr(probe_context, "probe", None)
                    probe_pattern = getattr(probe_run, "pattern", stream_key)
                    if pattern is None or fnmatch.fnmatch(probe_pattern or "", pattern):
                        stream_keys.append(stream_key)
            for stream_key in stream_keys:
                try:
                    stop_result = stop_context(stream_key)
                    exit_error = stop_result.get("exit_error") if isinstance(stop_result, dict) else None
                    if exit_error is not None:
                        probe_context_errors.append(exit_error)
                    else:
                        probe_context_stopped.append(stream_key)
                except Exception as exc:
                    probe_context_errors.append({"stream_key": stream_key, "error": str(exc)})

        injector_errors: list[dict[str, object]] = []
        result: dict[str, object]
        try:
            result = cast(dict[str, object], self.agent.injector.reset(pattern))
        except Exception as exc:
            injector_errors.append({"error": str(exc)})
            result = {"status": "error", "error": str(exc)}

        result["cleanup_summary"] = {
            "resource_owners": resource_owners_summary,
            "probe_contexts": {
                "stopped_count": len(probe_context_stopped),
                "errors": probe_context_errors,
            },
            "injector": {"errors": injector_errors},
        }
        return result

    def _list_enhanced(self, _params: dict[str, object]) -> dict[str, object]:
        """List all current enhancements (deduplicated)."""
        result = self.agent.injector.list_enhanced()
        enhanced = cast(list[dict[str, object]], result["enhanced"])

        # Build seen set from injector entries to dedupe watch/trace/stack
        # (those commands register in BOTH injector AND probe_context_types with same watch_id)
        seen_watch_ids = {
            str(entry["watch_id"])
            for entry in enhanced
            if isinstance(entry, dict) and "watch_id" in entry
        }

        probe_context_lock = getattr(self.agent, "_probe_context_lock", None)
        probe_context_types = cast(dict[str, object], getattr(self.agent, "_probe_context_types", {}))
        probe_contexts = cast(dict[str, object], getattr(self.agent, "_probe_contexts", {}))

        if probe_context_lock is not None:
            with probe_context_lock:
                for stream_key, probe_type in list(probe_context_types.items()):
                    if stream_key in seen_watch_ids:
                        continue  # already represented in injector output
                    probe_context = probe_contexts.get(stream_key)
                    probe_run = getattr(probe_context, "probe", None)
                    pattern = getattr(probe_run, "pattern", stream_key)
                    enhanced.append(
                        {
                            "stream_id": stream_key,
                            "command": probe_type,
                            "pattern": pattern,
                        }
                    )

        result["total"] = len(enhanced)
        return result
