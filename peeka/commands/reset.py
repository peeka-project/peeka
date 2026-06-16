"""
Reset Command - Restore enhanced methods to original state
Similar to Arthas 'reset' command
"""

from typing import Any, ClassVar, Dict, Optional, Protocol, TYPE_CHECKING, cast

from peeka.commands.base import BaseCommand

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class _MonitorCommandProtocol(Protocol):
    _lock: Any
    _monitors: Dict[str, Dict[str, Any]]

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        ...


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

        monitor_cmd = self._get_monitor_command()
        if monitor_cmd is not None:
            monitors_to_stop = []
            with monitor_cmd._lock:
                for wid, info in list(monitor_cmd._monitors.items()):
                    if pattern is None or fnmatch.fnmatch(info.get("pattern", ""), pattern):
                        monitors_to_stop.append(wid)
            for wid in monitors_to_stop:
                monitor_cmd.execute({"action": "stop", "watch_id": wid})

        return self.agent.injector.reset(pattern)

    def _list_enhanced(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all current enhancements."""
        result = self.agent.injector.list_enhanced()

        monitor_cmd = self._get_monitor_command()

        if monitor_cmd is not None:
            with monitor_cmd._lock:
                for monitor_id, info in list(monitor_cmd._monitors.items()):
                    result["enhanced"].append(
                        {
                            "monitor_id": monitor_id,
                            "pattern": info.get("pattern", "unknown"),
                            "command": "monitor",
                            "cycle": info.get("cycle", 0),
                            "cycles": info.get("cycles", -1),
                            "cycle_count": info.get("cycle_count", 0),
                        }
                    )

        result["total"] = len(result["enhanced"])
        return result

    def _get_monitor_command(self) -> Optional[_MonitorCommandProtocol]:
        """Resolve the active monitor command handler, if available."""
        monitor_cmd = getattr(self.agent, "monitor_cmd", None)
        if monitor_cmd is None:
            get_handler = getattr(self.agent, "_get_handler", None)
            if callable(get_handler):
                monitor_cmd = get_handler("monitor")
            if monitor_cmd is None:
                monitor_cmd = getattr(self.agent, "command_handlers", {}).get("monitor")

        if monitor_cmd is None:
            return None

        return cast(_MonitorCommandProtocol, monitor_cmd)
