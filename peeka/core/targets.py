# pyright: reportDeprecated=false, reportExplicitAny=false, reportUnusedParameter=false
"""Target discovery domain objects.

Implements the ``TargetAgent`` object contract from
``.sisyphus/plans/session-optimize.md`` §TargetAgent.

Target state machine:
    alive: hello probe succeeds for a live PID.
    stale: marker files or socket remain, but the PID is gone or probe fails.
    unknown: there is not enough information to classify safely.
    attaching: attach is in progress.
    failed: the latest attach attempt failed.
    detached: the target was explicitly detached.
"""

from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Literal
from typing import Optional


TARGET_SCHEMA_VERSION = "1"

TargetState = Literal[
    "alive",
    "stale",
    "unknown",
    "attaching",
    "failed",
    "detached",
]
AgentMode = Literal["injected", "preinstalled"]
InjectionMode = Literal[
    "gdb_dlopen",
    "lldb_dlopen",
    "pep768",
    "preinstalled",
]


@dataclass
class TargetAgent:
    """Represents one Peeka-managed target process.

    Attributes:
        target_id: Public target identifier.
        legacy_session_id: Legacy session identifier used by /tmp/peeka_* files.
        pid: Target process PID.
        socket_path: Unix socket path for the target agent.
        state: Current target lifecycle state.
        agent_mode: Whether the agent is injected or preinstalled.
        injection_mode: Attach mechanism used for the target agent.
        python_version: Target interpreter version string.
        peeka_version: Peeka version reported by the target.
        capabilities: Free-form capability map for target features.
        runtime: Free-form runtime metadata map.
        created_at: Target creation timestamp in epoch seconds.
        last_seen_at: Last successful observation timestamp in epoch seconds.
        recent_errors: Recent error records shaped like
            {"timestamp": float, "code": str, "message": str}.
        next_valid_actions: Allowed next actions for the target.
    """

    target_id: str
    legacy_session_id: str
    pid: int
    socket_path: str
    state: TargetState
    agent_mode: AgentMode
    injection_mode: InjectionMode
    python_version: str
    peeka_version: str
    capabilities: Dict[str, Any] = field(default_factory=dict)
    runtime: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    last_seen_at: float = 0.0
    recent_errors: List[Dict[str, Any]] = field(default_factory=list)
    next_valid_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the target into a JSON-safe dictionary."""
        result = {"schema_version": TARGET_SCHEMA_VERSION}
        result.update(asdict(self))
        return result


def discover_targets() -> List[TargetAgent]:
    """Discover Peeka target agents on the current host."""
    raise NotImplementedError("discover_targets() is implemented in T3")


def get_target(target_id: str) -> Optional[TargetAgent]:
    """Return a target by public identifier if it exists."""
    raise NotImplementedError("get_target() is implemented in T3")


def cleanup_stale_targets(dry_run: bool = False) -> Dict[str, Any]:
    """Plan or perform stale target cleanup."""
    raise NotImplementedError("cleanup_stale_targets() is implemented in T3")


def detach_target(target_id: str, force: bool = False) -> Dict[str, Any]:
    """Detach a target from Peeka management."""
    raise NotImplementedError("detach_target() is implemented in T3")
