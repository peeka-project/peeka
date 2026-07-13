"""Profile processor contracts and concrete implementations."""

from abc import ABC
from abc import abstractmethod
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Optional
from typing import Set

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


class AggregateRepeatedCallsProcessor(ProfileProcessor):
    """Collapse consecutive identical frames within each sample's stack in-place."""

    def process(self, session: ProfileSession) -> ProcessedProfile:
        """Remove consecutive duplicate StackRecord entries from each sample stack."""
        for sample in session.samples:
            if len(sample.stack) < 2:
                continue
            deduped = [sample.stack[0]]
            for frame in sample.stack[1:]:
                prev = deduped[-1]
                if not (
                    frame.name == prev.name
                    and frame.filename == prev.filename
                    and frame.lineno == prev.lineno
                ):
                    deduped.append(frame)
            sample.stack = deduped
        return ProcessedProfile(
            profile_id=session.profile_id,
            backend=session.backend,
            session=session,
        )


class BuildTopListProcessor(ProfileProcessor):
    """Build a sorted top-functions list from profile samples.

    stack[-1] is the leaf frame and contributes own_count.  All frames
    contribute total_count (deduplicated per sample).  Percentages are
    rounded to 2 decimal places.
    """

    def process(self, session: ProfileSession) -> ProcessedProfile:
        """Return ProcessedProfile with top_list sorted by own_count descending."""
        own_counts: Dict[str, int] = {}
        total_counts: Dict[str, int] = {}
        frame_meta: Dict[str, Dict[str, Any]] = {}

        total_samples = len(session.samples)

        for sample in session.samples:
            if not sample.stack:
                continue

            # Leaf is stack[-1]; give it own credit.
            leaf = sample.stack[-1]
            leaf_key = _frame_key(leaf.name, leaf.filename, leaf.lineno)
            own_counts[leaf_key] = own_counts.get(leaf_key, 0) + 1
            if leaf_key not in frame_meta:
                frame_meta[leaf_key] = {
                    "name": leaf.name,
                    "filename": leaf.filename,
                    "lineno": leaf.lineno,
                }

            # All frames contribute to total_count (once per sample).
            seen_in_sample: Set[str] = set()
            for frame in sample.stack:
                key = _frame_key(frame.name, frame.filename, frame.lineno)
                if key not in seen_in_sample:
                    total_counts[key] = total_counts.get(key, 0) + 1
                    seen_in_sample.add(key)
                    if key not in frame_meta:
                        frame_meta[key] = {
                            "name": frame.name,
                            "filename": frame.filename,
                            "lineno": frame.lineno,
                        }

        all_keys = set(total_counts.keys()) | set(own_counts.keys())
        top_list: List[Dict[str, Any]] = []
        for key in all_keys:
            own_count = own_counts.get(key, 0)
            total_count = total_counts.get(key, 0)
            own_pct = round(own_count / total_samples * 100, 2) if total_samples > 0 else 0.0
            total_pct = (
                round(total_count / total_samples * 100, 2) if total_samples > 0 else 0.0
            )
            meta = frame_meta[key]
            top_list.append(
                {
                    "name": meta["name"],
                    "filename": meta["filename"],
                    "lineno": meta["lineno"],
                    "own_count": own_count,
                    "total_count": total_count,
                    "own_pct": own_pct,
                    "total_pct": total_pct,
                }
            )

        top_list.sort(key=lambda x: x["own_count"], reverse=True)

        processed = ProcessedProfile(
            profile_id=session.profile_id,
            backend=session.backend,
            session=session,
        )
        processed.top_list = top_list
        return processed


class BuildCallTreeProcessor(ProfileProcessor):
    """Build a nested call tree from profile samples (root=stack[0], leaf=stack[-1])."""

    def process(self, session: ProfileSession) -> ProcessedProfile:
        """Return ProcessedProfile with call_tree set to ``{"roots": [node, ...]}``."""
        roots: List[Dict[str, Any]] = []
        # Map frame_key -> node dict for each tree level
        root_index: Dict[str, Dict[str, Any]] = {}
        # Map id(node) -> children index for that node
        children_index: Dict[int, Dict[str, Dict[str, Any]]] = {}

        for sample in session.samples:
            if not sample.stack:
                continue

            current_list = roots
            current_index = root_index

            for frame in sample.stack:
                key = _frame_key(frame.name, frame.filename, frame.lineno)
                if key not in current_index:
                    node: Dict[str, Any] = {
                        "name": frame.name,
                        "filename": frame.filename,
                        "lineno": frame.lineno,
                        "count": 0,
                        "children": [],
                    }
                    current_list.append(node)
                    current_index[key] = node
                    children_index[id(node)] = {}

                node = current_index[key]
                node["count"] += 1

                current_list = node["children"]
                current_index = children_index[id(node)]

        processed = ProcessedProfile(
            profile_id=session.profile_id,
            backend=session.backend,
            session=session,
        )
        processed.call_tree = {"roots": roots}
        return processed


class BuildFlamegraphTreeProcessor(ProfileProcessor):
    """Build a flamegraph-compatible folded tree; node value = sample count through that frame."""

    def process(self, session: ProfileSession) -> ProcessedProfile:
        """Return ProcessedProfile with flamegraph = ``{"name":"root","value":N,"children":[...]}``."""
        total_samples = len(session.samples)
        root: Dict[str, Any] = {
            "name": "root",
            "value": total_samples,
            "children": [],
        }
        root_index: Dict[str, Dict[str, Any]] = {}
        children_index: Dict[int, Dict[str, Dict[str, Any]]] = {}

        for sample in session.samples:
            if not sample.stack:
                continue

            current_list = root["children"]
            current_index = root_index

            for frame in sample.stack:
                key = _frame_key(frame.name, frame.filename, frame.lineno)
                if key not in current_index:
                    node: Dict[str, Any] = {
                        "name": frame.name,
                        "value": 0,
                        "children": [],
                    }
                    current_list.append(node)
                    current_index[key] = node
                    children_index[id(node)] = {}

                node = current_index[key]
                node["value"] += 1

                current_list = node["children"]
                current_index = children_index[id(node)]

        processed = ProcessedProfile(
            profile_id=session.profile_id,
            backend=session.backend,
            session=session,
        )
        processed.flamegraph = root
        return processed


def _frame_key(name: str, filename: str, lineno: int) -> str:
    return f"{name}::{filename}::{lineno}"


__all__ = [
    "AggregateRepeatedCallsProcessor",
    "BuildCallTreeProcessor",
    "BuildFlamegraphTreeProcessor",
    "BuildTopListProcessor",
    "ProcessedProfile",
    "ProcessorContext",
    "ProfileProcessor",
]
