"""Data-plane compatibility policy for monkey-patched runtimes."""

from dataclasses import dataclass
from typing import Dict, Optional

from peeka.core.runtime.gevent_probe import GeventState


DECISION_SAFE = "safe"
DECISION_DEGRADED = "degraded"
DECISION_REFUSE = "refuse"

BACKEND_WRAPPER = "wrapper"
BACKEND_SETTRACE_OR_MONITORING = "settrace_or_monitoring"
BACKEND_WRAPPER_ONLY = "wrapper_only"
BACKEND_FRAME_WALK = "frame_walk"
BACKEND_INSPECT_STACK = "inspect_stack"


TRACE_GEVENT_REASON = (
    "sys.settrace under gevent can violate frame stack invariants; "
    "using wrapper-only tracing without recursive call tree"
)
TOP_GEVENT_REASON = (
    "frame-walk sampling under gevent sees only the active greenlet per OS thread"
)
STACK_GEVENT_REASON = (
    "stack inspection under gevent may only reflect the currently active greenlet"
)


@dataclass(frozen=True)
class Policy:
    """Compatibility decision for a command/backend pair."""

    decision: str
    backend: str
    reason: Optional[str]
    greenlet_blind: bool


_SAFE_WRAPPER = Policy(DECISION_SAFE, BACKEND_WRAPPER, None, False)
_SAFE_TRACE = Policy(DECISION_SAFE, BACKEND_SETTRACE_OR_MONITORING, None, False)
_SAFE_TOP = Policy(DECISION_SAFE, BACKEND_FRAME_WALK, None, False)
_SAFE_STACK = Policy(DECISION_SAFE, BACKEND_INSPECT_STACK, None, False)
_DEGRADED_TRACE = Policy(
    DECISION_DEGRADED,
    BACKEND_WRAPPER_ONLY,
    TRACE_GEVENT_REASON,
    False,
)
_DEGRADED_TOP = Policy(
    DECISION_DEGRADED,
    BACKEND_FRAME_WALK,
    TOP_GEVENT_REASON,
    True,
)
_DEGRADED_STACK = Policy(
    DECISION_DEGRADED,
    BACKEND_INSPECT_STACK,
    STACK_GEVENT_REASON,
    True,
)

_MATRIX: Dict[str, Dict[GeventState, Policy]] = {
    "watch": {
        GeventState.NONE: _SAFE_WRAPPER,
        GeventState.IMPORTED: _SAFE_WRAPPER,
        GeventState.PATCHED: _SAFE_WRAPPER,
        GeventState.ACTIVE_HUB: _SAFE_WRAPPER,
    },
    "monitor": {
        GeventState.NONE: _SAFE_WRAPPER,
        GeventState.IMPORTED: _SAFE_WRAPPER,
        GeventState.PATCHED: _SAFE_WRAPPER,
        GeventState.ACTIVE_HUB: _SAFE_WRAPPER,
    },
    "stack": {
        GeventState.NONE: _SAFE_STACK,
        GeventState.IMPORTED: _SAFE_STACK,
        GeventState.PATCHED: _DEGRADED_STACK,
        GeventState.ACTIVE_HUB: _DEGRADED_STACK,
    },
    "trace": {
        GeventState.NONE: _SAFE_TRACE,
        GeventState.IMPORTED: _SAFE_TRACE,
        GeventState.PATCHED: _DEGRADED_TRACE,
        GeventState.ACTIVE_HUB: _DEGRADED_TRACE,
    },
    "top": {
        GeventState.NONE: _SAFE_TOP,
        GeventState.IMPORTED: _SAFE_TOP,
        GeventState.PATCHED: _DEGRADED_TOP,
        GeventState.ACTIVE_HUB: _DEGRADED_TOP,
    },
}


def get_policy(command: str, state: GeventState) -> Policy:
    """Return compatibility policy for command under a gevent state.

    Args:
        command: Command name such as ``trace`` or ``top``.
        state: Current gevent runtime state.

    Returns:
        Policy: Frozen compatibility decision.

    Raises:
        KeyError: If command or state is not covered by the matrix.
    """
    return _MATRIX[command][state]


def policy_meta(state: GeventState, policy: Policy) -> Dict[str, Optional[object]]:
    """Serialize policy information for JSONL command metadata.

    Args:
        state: Current gevent runtime state.
        policy: Policy returned by ``get_policy``.

    Returns:
        Dict containing stable JSONL ``meta`` fields.
    """
    return {
        "gevent_state": state.value,
        "backend": policy.backend,
        "greenlet_blind": policy.greenlet_blind,
        "degraded_reason": policy.reason,
    }
