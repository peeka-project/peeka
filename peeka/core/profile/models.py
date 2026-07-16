# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnnecessaryIsInstance=false
"""Profile system data models.

Provides schema-versioned, JSON-serializable dataclasses for profile
configuration, sampled stacks, and session summaries.
"""

import json
import time
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Optional


PROFILE_SESSION_SCHEMA_VERSION = 1
PROFILE_BACKENDS = frozenset(("sampling", "exact"))
PROFILE_STATUSES = frozenset(("running", "stopped"))


@dataclass
class ProfileConfig:
    """Profile runtime configuration."""

    backend: str = "sampling"
    interval_ms: int = 10
    duration_ms: Optional[int] = None
    max_samples: Optional[int] = 100000

    def __post_init__(self) -> None:
        if self.backend not in PROFILE_BACKENDS:
            raise ValueError("backend must be one of: sampling, exact")
        if self.interval_ms <= 0:
            raise ValueError("interval_ms must be greater than 0")
        if self.max_samples is None:
            self.max_samples = 100000
        if self.max_samples <= 0:
            raise ValueError("max_samples must be greater than 0")
        if self.duration_ms is not None and self.duration_ms <= 0:
            raise ValueError("duration_ms must be greater than 0 when provided")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the profile configuration into a JSON-safe dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProfileConfig":
        """Build a profile configuration from serialized data."""
        return cls(
            backend=str(data.get("backend", "sampling")),
            interval_ms=int(data.get("interval_ms", 10)),
            duration_ms=data.get("duration_ms"),
            max_samples=None if data.get("max_samples") is None else int(data.get("max_samples", 100000)),
        )


@dataclass
class StackRecord:
    """Represents one stack frame in a profile sample."""

    filename: str
    lineno: int
    name: str
    module: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the stack record into a JSON-safe dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StackRecord":
        """Build a stack record from serialized data."""
        return cls(
            filename=str(data.get("filename", "")),
            lineno=int(data.get("lineno", 0)),
            name=str(data.get("name", "")),
            module=data.get("module"),
        )


@dataclass
class SampleRecord:
    """Represents one profile sample."""

    timestamp: float
    thread_id: int
    thread_name: str
    stack: List[StackRecord]
    lane: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the sample record into a JSON-safe dictionary."""
        result = asdict(self)
        result["stack"] = [item.to_dict() for item in self.stack]
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SampleRecord":
        """Build a sample record from serialized data."""
        stack_data = data.get("stack", [])
        stack = [StackRecord.from_dict(item) for item in stack_data]
        return cls(
            timestamp=float(data.get("timestamp", 0.0)),
            thread_id=int(data.get("thread_id", 0)),
            thread_name=str(data.get("thread_name", "")),
            stack=stack,
            lane=data.get("lane"),
        )


@dataclass
class ProfileSummary:
    """Represents aggregated profile results."""

    sample_count: int
    duration_ms: float
    start_time: float
    top_functions: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the profile summary into a JSON-safe dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProfileSummary":
        """Build a profile summary from serialized data."""
        return cls(
            sample_count=int(data.get("sample_count", 0)),
            duration_ms=float(data.get("duration_ms", 0.0)),
            start_time=float(data.get("start_time", 0.0)),
            top_functions=list(data.get("top_functions", [])),
        )


@dataclass
class ProfileSession:
    """Represents one profiling session lifecycle."""

    profile_id: str
    backend: str
    config: ProfileConfig
    status: str = "running"
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    samples: List[SampleRecord] = field(default_factory=list)
    summary: Optional[ProfileSummary] = None
    version: int = PROFILE_SESSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.profile_id:
            raise ValueError("profile_id must not be empty")
        if self.backend not in PROFILE_BACKENDS:
            raise ValueError("backend must be one of: sampling, exact")
        if self.status not in PROFILE_STATUSES:
            raise ValueError("status must be one of: running, stopped")
        if not isinstance(self.config, ProfileConfig):
            raise ValueError("config must be a ProfileConfig")
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at must be greater than or equal to started_at")

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the profile session into a JSON-safe dictionary."""
        result = asdict(self)
        result["config"] = self.config.to_dict()
        result["samples"] = [sample.to_dict() for sample in self.samples]
        result["summary"] = self.summary.to_dict() if self.summary is not None else None
        return result

    def to_json(self) -> str:
        """Serialize the profile session into deterministic JSON."""
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProfileSession":
        """Build a profile session from serialized data."""
        config_data = data.get("config", {})
        summary_data = data.get("summary")
        samples_data = data.get("samples", [])
        return cls(
            profile_id=str(data.get("profile_id", "")),
            backend=str(data.get("backend", "sampling")),
            config=ProfileConfig.from_dict(config_data),
            status=str(data.get("status", "running")),
            started_at=float(data.get("started_at", time.time())),
            ended_at=data.get("ended_at"),
            samples=[SampleRecord.from_dict(item) for item in samples_data],
            summary=ProfileSummary.from_dict(summary_data) if summary_data is not None else None,
            version=int(data.get("version", PROFILE_SESSION_SCHEMA_VERSION)),
        )
