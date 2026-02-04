"""
Base Command Interface
All diagnostic commands inherit from BaseCommand
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class BaseCommand(ABC):
    """Base class for all diagnostic commands"""

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
