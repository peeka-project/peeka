"""
Detach Command - Detach from the target process
"""

from typing import Any, Dict, TYPE_CHECKING

from peeka.commands.base import BaseCommand

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


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

    def __init__(self, agent: "PeekaAgent"):
        super().__init__()
        self.agent = agent

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
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
