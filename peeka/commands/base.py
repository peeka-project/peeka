"""
Base Command Interface
All diagnostic commands inherit from BaseCommand
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class BaseCommand(ABC):
    """Base class for all diagnostic commands.

    All concrete command subclasses must declare:
    - category: Command concurrency category (snapshot | probe | mutation)
    - allows_concurrent: Whether multiple clients may run this command simultaneously

    Command Categories:
    - snapshot: One-shot inspection commands (e.g., memory, thread, stack, search, inspect, top).
                Returns a single result and exits. Minimal state mutation.
                Can be concurrent if allows_concurrent=True.

    - probe: Long-lived observation commands (e.g., watch, trace, monitor, logger).
             Streams events over time. Injection persists until explicitly stopped.
             Typically not concurrent (allows_concurrent=False).

    - mutation: Commands that modify agent state (e.g., reset, detach).
                Injects/uninstalls/modifies global state in target process.
                Never concurrent (allows_concurrent=False) — serialized via mutation lock.

    Note: WatchCommand is classified as probe (injection is a brief opening phase;
    streaming dominates). Reset and Detach remain mutation.

    Concurrency Semantics:
    - allows_concurrent=True: Multiple clients may invoke simultaneously (snapshot only).
    - allows_concurrent=False: Enforced per-session foreground rule; mutation lock for mutation category.
    """

    category: ClassVar[str] = "snapshot"
    allows_concurrent: ClassVar[bool] = False

    def __init__(self, agent: Optional["PeekaAgent"] = None):
        self.name = self.__class__.__name__
        self.agent = agent

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the command

        Args:
            params: Command parameters

        Returns:
            Dict containing execution results
        """
        pass

    def validate_params(self, params: Dict[str, Any], required: list) -> None:
        """
        Validate required parameters

        Args:
            params: Parameters to validate
            required: List of required parameter names

        Raises:
            ValueError: If required parameters are missing
        """
        missing = [p for p in required if p not in params]
        if missing:
            raise ValueError(f"Missing required parameters: {', '.join(missing)}")
