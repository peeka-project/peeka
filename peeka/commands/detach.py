"""
Detach Command - Detach from the target process
"""

# pyright: reportAny=false, reportDeprecated=false, reportExplicitAny=false, reportImplicitOverride=false, reportUnannotatedClassAttribute=false

import logging
from typing import Any, ClassVar, Dict

from peeka.commands.base import BaseCommand


class DetachCommand(BaseCommand):
    is_resource_owner = False  # explicit; not a resource owner
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

    def __init__(self, agent: Any):
        super().__init__()
        self.agent = agent

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            attached_pid = self.agent.attached_pid
            self.agent.stop()
            cleanup_summary = getattr(self.agent, "_last_cleanup_summary", {})

            return {
                "status": "success",
                "message": f"Detached from process {attached_pid}",
                "pid": attached_pid,
                "cleanup_summary": cleanup_summary,
            }

        except Exception as e:
            logging.getLogger(__name__).exception("[peeka Detach] detach failed")
            return {"status": "error", "error": str(e)}
