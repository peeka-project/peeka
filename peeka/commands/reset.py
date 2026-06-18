"""
Reset Command - Restore enhanced methods to original state
Similar to Arthas 'reset' command
"""

from typing import Any, ClassVar, Dict, TYPE_CHECKING

from peeka.commands.base import BaseCommand

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class ResetCommand(BaseCommand):
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

    def __init__(self, agent: "PeekaAgent"):
        super().__init__()
        self.agent = agent

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = params.get("action", "reset")

            if action == "reset":
                return self._reset(params)
            elif action == "list":
                return self._list_enhanced(params)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _reset(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Reset enhancements, optionally filtered by pattern."""
        import fnmatch

        pattern = params.get("pattern")

        stop_context = getattr(self.agent, "stop_probe_context", None)
        probe_context_lock = getattr(self.agent, "_probe_context_lock", None)
        probe_context_types = getattr(self.agent, "_probe_context_types", {})
        probe_contexts = getattr(self.agent, "_probe_contexts", {})

        if callable(stop_context) and probe_context_lock is not None:
            stream_keys = []
            with probe_context_lock:
                for stream_key in list(probe_context_types.keys()):
                    probe_context = probe_contexts.get(stream_key)
                    probe_run = getattr(probe_context, "probe", None)
                    probe_pattern = getattr(probe_run, "pattern", stream_key)
                    if pattern is None or fnmatch.fnmatch(probe_pattern or "", pattern):
                        stream_keys.append(stream_key)
            for stream_key in stream_keys:
                stop_context(stream_key)

        return self.agent.injector.reset(pattern)

    def _list_enhanced(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all current enhancements."""
        result = self.agent.injector.list_enhanced()

        probe_context_lock = getattr(self.agent, "_probe_context_lock", None)
        probe_context_types = getattr(self.agent, "_probe_context_types", {})
        probe_contexts = getattr(self.agent, "_probe_contexts", {})

        if probe_context_lock is not None:
            with probe_context_lock:
                for stream_key, probe_type in list(probe_context_types.items()):
                    probe_context = probe_contexts.get(stream_key)
                    probe_run = getattr(probe_context, "probe", None)
                    pattern = getattr(probe_run, "pattern", stream_key)
                    result["enhanced"].append(
                        {
                            "stream_id": stream_key,
                            "command": probe_type,
                            "pattern": pattern,
                        }
                    )

        result["total"] = len(result["enhanced"])
        return result
