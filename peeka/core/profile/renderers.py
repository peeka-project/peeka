"""Profile renderer contracts."""

from abc import ABC
from abc import abstractmethod
from typing import TextIO

from peeka.core.profile.processors import ProcessedProfile


class ProfileRenderer(ABC):
    """Contract for rendering processed profile data to a text stream."""

    @abstractmethod
    def render(self, processed: "ProcessedProfile", output: TextIO) -> None:
        """Render a processed profile into the provided text output stream."""
