"""Resource-owning command abstractions."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, Optional  # pyright: ignore[reportDeprecated]

from peeka.commands.base import BaseCommand


class CleanupScope(str, Enum):
    """Cleanup scope for resource-owning commands."""

    DETACH_ONLY = "detach_only"
    DETACH_AND_RESET = "detach_and_reset"


class ResourceOwningCommand(BaseCommand, ABC):
    """Base class for commands that own injected runtime resources.

    Subclasses must implement resource cleanup and reporting.
    stop_active_resources() must return at minimum::

        {"stopped": list, "errors": list}

    Subclasses may include extra keys such as "skipped".

    list_active_resources() must return at minimum::

        {"active": list}

    Subclasses may include extra keys as needed.
    """

    is_resource_owner: bool = True
    cleanup_scope: CleanupScope

    @abstractmethod
    def stop_active_resources(
        self, pattern: Optional[str], reason: str  # pyright: ignore[reportDeprecated]
    ) -> Dict[str, Any]:  # pyright: ignore[reportDeprecated, reportExplicitAny]
        """Stop active resources, optionally filtered by pattern."""

    @abstractmethod
    def list_active_resources(self) -> Dict[str, Any]:  # pyright: ignore[reportDeprecated, reportExplicitAny]
        """List active resources currently owned by the command."""
