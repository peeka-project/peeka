"""
Detach Command - Detach from the target process
"""

# pyright: reportAny=false, reportDeprecated=false, reportExplicitAny=false, reportImplicitOverride=false, reportUnannotatedClassAttribute=false

import logging
from typing import Any, ClassVar, Dict

from peeka.core.agent_control.lifecycle import shutdown_agent_resources
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
            logger = logging.getLogger(__name__)
            list_probe_types = getattr(
                self.agent, "list_tracked_probe_types", lambda: []
            )

            _ = shutdown_agent_resources(
                self.agent, logger, list_probe_types()
            )

            attached_pid = self.agent.attached_pid
            self.agent.stop()

            return {
                "status": "success",
                "message": f"Detached from process {attached_pid}",
                "pid": attached_pid,
            }

        except Exception as e:
            logging.getLogger(__name__).exception("[peeka Detach] detach failed")
            return {"status": "error", "error": str(e)}
