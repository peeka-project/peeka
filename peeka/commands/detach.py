"""
Detach Command - Detach from the target process
"""

from typing import Any, ClassVar, Dict, List, Optional, TYPE_CHECKING, cast

from peeka.commands.base import BaseCommand

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent
    from peeka.commands.monitor import MonitorCommand
    from peeka.commands.top import TopCommand


class DetachCommand(BaseCommand):
    """
    Detach command - stops the agent and cleans up all resources

    Usage:
        detach

    This command:
    - Stops all active watches, monitors, and observations
    - Restores all instrumented functions
    - Closes the agent socket
    - Cleans up temporary files
    """

    category: ClassVar[str] = "mutation"
    allows_concurrent: ClassVar[bool] = False

    def __init__(self, agent: "PeekaAgent"):
        super().__init__()
        self.agent = agent

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            get_handler = getattr(self.agent, "_get_handler", None)

            monitor_cmd: Optional["MonitorCommand"] = None
            if callable(get_handler):
                monitor_cmd = cast(Optional["MonitorCommand"], get_handler("monitor"))
            if monitor_cmd is not None:
                monitor_ids: List[str] = []
                with monitor_cmd._lock:
                    monitor_ids = list(monitor_cmd._monitors.keys())
                for monitor_id in monitor_ids:
                    monitor_cmd._stop_monitor({"monitor_id": monitor_id})

            top_cmd: Optional["TopCommand"] = None
            if callable(get_handler):
                top_cmd = cast(Optional["TopCommand"], get_handler("top"))
            if top_cmd is not None:
                top_id: Optional[str] = None
                with top_cmd._lock:
                    if top_cmd._sampling_thread is not None and top_cmd._sampling_thread.is_alive():
                        top_id = top_cmd._top_id
                if top_id:
                    top_cmd._stop({"top_id": top_id})

            self.agent.injector.uninject_all()
            self.agent.observer.clear_all()

            attached_pid = self.agent.attached_pid
            self.agent.stop()

            return {
                "status": "success",
                "message": f"Detached from process {attached_pid}",
                "pid": attached_pid,
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}
