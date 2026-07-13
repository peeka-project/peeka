"""Profile processor contracts."""

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Optional

from peeka.core.profile.models import ProfileSession


@dataclass
class ProcessorContext:
    """Configuration shared by profile processors."""

    hide_stdlib: bool = False
    hide_site_packages: bool = False
    min_threshold_pct: float = 0.0


@dataclass
class ProcessedProfile:
    """Normalized profile output produced by processors."""

    profile_id: str
    backend: str
    session: ProfileSession
    top_list: List[Dict[str, Any]] = field(default_factory=list)
    call_tree: Optional[Dict[str, Any]] = None
    flamegraph: Optional[Dict[str, Any]] = None
    timeline: Optional[List[Dict[str, Any]]] = None


class ProfileProcessor(ABC):
    """Contract for turning a profile session into rendered profile data."""

    @abstractmethod
    def process(self, session: ProfileSession) -> "ProcessedProfile":
        """Transform a profile session into a processed profile payload."""
