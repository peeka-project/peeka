"""Tests for data-plane compatibility policy matrix."""

import pytest

from peeka.core.runtime.compat import (
    BACKEND_FRAME_WALK,
    BACKEND_INSPECT_STACK,
    BACKEND_SETTRACE_OR_MONITORING,
    BACKEND_WRAPPER,
    BACKEND_WRAPPER_ONLY,
    DECISION_DEGRADED,
    DECISION_REFUSE,
    DECISION_SAFE,
    get_policy,
    policy_meta,
)
from peeka.core.runtime.gevent_probe import GeventState


COMMANDS = ("trace", "top", "watch", "monitor", "stack")
STATES = (
    GeventState.NONE,
    GeventState.IMPORTED,
    GeventState.PATCHED,
    GeventState.ACTIVE_HUB,
)


@pytest.mark.unit
class TestRuntimeCompat:
    """Compatibility matrix contract tests."""

    def test_matrix_covers_all_required_cells(self):
        """Verify 5 commands x 4 gevent states are covered."""
        for command in COMMANDS:
            for state in STATES:
                policy = get_policy(command, state)
                assert policy.decision in {DECISION_SAFE, DECISION_DEGRADED}
                assert isinstance(policy.backend, str)
                assert isinstance(policy.greenlet_blind, bool)

    def test_unknown_command_raises_key_error(self):
        """Unknown commands are not silently classified."""
        with pytest.raises(KeyError):
            get_policy("unknown", GeventState.NONE)

    def test_trace_degrades_to_wrapper_only_when_patched(self):
        """trace avoids tracing APIs in patched gevent states."""
        for state in (GeventState.PATCHED, GeventState.ACTIVE_HUB):
            policy = get_policy("trace", state)
            assert policy.decision == DECISION_DEGRADED
            assert policy.backend == BACKEND_WRAPPER_ONLY
            assert policy.greenlet_blind is False
            assert policy.reason

    def test_trace_safe_for_none_and_imported_states(self):
        """trace keeps existing backend selection when gevent is not patched."""
        for state in (GeventState.NONE, GeventState.IMPORTED):
            policy = get_policy("trace", state)
            assert policy.decision == DECISION_SAFE
            assert policy.backend == BACKEND_SETTRACE_OR_MONITORING
            assert policy.reason is None

    def test_top_marks_frame_walk_greenlet_blind_when_patched(self):
        """top keeps frame walk but marks greenlet blindness under gevent."""
        for state in (GeventState.PATCHED, GeventState.ACTIVE_HUB):
            policy = get_policy("top", state)
            assert policy.decision == DECISION_DEGRADED
            assert policy.backend == BACKEND_FRAME_WALK
            assert policy.greenlet_blind is True
            assert policy.reason

    def test_watch_and_monitor_are_safe_in_all_states(self):
        """Wrapper-based commands are safe in all gevent states."""
        for command in ("watch", "monitor"):
            for state in STATES:
                policy = get_policy(command, state)
                assert policy.decision == DECISION_SAFE
                assert policy.backend == BACKEND_WRAPPER
                assert policy.greenlet_blind is False

    def test_stack_degrades_under_patched_states(self):
        """Stack inspection can run but is not fully greenlet-aware."""
        assert get_policy("stack", GeventState.NONE).backend == BACKEND_INSPECT_STACK
        for state in (GeventState.PATCHED, GeventState.ACTIVE_HUB):
            policy = get_policy("stack", state)
            assert policy.decision == DECISION_DEGRADED
            assert policy.backend == BACKEND_INSPECT_STACK
            assert policy.greenlet_blind is True

    def test_public_string_sets_are_frozen(self):
        """Verify decision/backend string contract."""
        decisions = set()
        backends = set()
        for command in COMMANDS:
            for state in STATES:
                policy = get_policy(command, state)
                decisions.add(policy.decision)
                backends.add(policy.backend)

        assert decisions == {DECISION_SAFE, DECISION_DEGRADED}
        assert DECISION_REFUSE == "refuse"
        assert backends == {
            BACKEND_FRAME_WALK,
            BACKEND_INSPECT_STACK,
            BACKEND_SETTRACE_OR_MONITORING,
            BACKEND_WRAPPER,
            BACKEND_WRAPPER_ONLY,
        }

    def test_policy_meta_shape(self):
        """Policy metadata serializes to stable JSONL keys."""
        policy = get_policy("top", GeventState.PATCHED)
        meta = policy_meta(GeventState.PATCHED, policy)

        assert set(meta) == {
            "gevent_state",
            "backend",
            "greenlet_blind",
            "degraded_reason",
        }
        assert meta["gevent_state"] == "patched"
        assert meta["backend"] == BACKEND_FRAME_WALK
        assert meta["greenlet_blind"] is True
        assert isinstance(meta["degraded_reason"], str)
