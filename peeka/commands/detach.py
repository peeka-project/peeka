"""
Detach Command - Detach from the target process
"""

# pyright: reportAny=false, reportDeprecated=false, reportExplicitAny=false, reportImplicitOverride=false, reportUnannotatedClassAttribute=false

import logging
from typing import Any, ClassVar, Dict

from peeka.core.agent_control.lifecycle import stop_resource_owners_for_detach
from peeka.commands.base import BaseCommand


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

    def __init__(self, agent: Any):
        super().__init__()
        self.agent = agent

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            logger = logging.getLogger(__name__)

            def log_cleanup_error(scope: str) -> None:
                logger.error("[peeka Detach] %s cleanup failed", scope, exc_info=True)

            _ = stop_resource_owners_for_detach(self.agent, logger)

            stop_by_type = getattr(self.agent, "stop_probe_contexts_by_type", None)
            if callable(stop_by_type):
                try:
                    _ = stop_by_type(["watch", "trace", "stack", "monitor", "top"])
                except Exception:
                    log_cleanup_error("probe contexts")
                    raise

            _ = self.agent.injector.uninject_all()
            _ = self.agent.observer.clear_all()

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
