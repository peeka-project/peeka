"""Tests for probe-context isolation and live probe discovery."""

import threading
from typing import Dict, Optional

import pytest

from peeka.core.agent_control.probes import AgentProbeControlMixin


class _StubProbeAgent(AgentProbeControlMixin):
    """Minimal stub that satisfies AgentProbeControlMixin requirements."""

    def __init__(
        self,
        probe_types: Optional[Dict[str, str]] = None,
        probe_contexts: Optional[Dict[str, object]] = None,
    ) -> None:
        self._probe_context_lock: threading.Lock = threading.Lock()
        self._probe_context_types: Dict[str, str] = dict(probe_types or {})
        self._probe_contexts: Dict[str, object] = dict(probe_contexts or {})


def test_list_tracked_probe_types_empty() -> None:
    """list_tracked_probe_types returns [] when nothing is tracked."""
    agent = _StubProbeAgent()

    result = agent.list_tracked_probe_types()

    assert result == []


def test_list_tracked_probe_types_dedup_sorted() -> None:
    """list_tracked_probe_types returns deduplicated, sorted types."""
    agent = _StubProbeAgent(probe_types={"s1": "watch", "s2": "watch", "s3": "trace"})

    result = agent.list_tracked_probe_types()

    assert result == ["trace", "watch"]


class _FailingExitContext:
    """Stub ProbeContext whose __exit__ always raises RuntimeError."""

    exited: bool = False

    def __exit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> None:
        self.exited = True
        raise RuntimeError("simulated __exit__ failure")


class _GoodExitContext:
    """Stub ProbeContext whose __exit__ succeeds silently."""

    exited: bool = False

    def __exit__(
        self,
        exc_type: object,
        exc_val: object,
        exc_tb: object,
    ) -> None:
        self.exited = True


def test_stop_probe_context_swallows_exit_failure_exc_info_none(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """stop_probe_context swallows __exit__ failure (exc_info=None path) and logs ERROR."""
    ctx = _FailingExitContext()
    agent = _StubProbeAgent(
        probe_types={"sk1": "watch"},
        probe_contexts={"sk1": ctx},  # type: ignore[arg-type]
    )

    with caplog.at_level("ERROR"):
        agent.stop_probe_context("sk1")

    assert agent.get_probe_context("sk1") is None
    assert agent.list_tracked_probe_types() == []
    assert ctx.exited is True
    assert any("probe_context.__exit__ failed" in r.message for r in caplog.records)


def test_stop_probe_context_swallows_exit_failure_with_exc_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """stop_probe_context swallows __exit__ failure (exc_info not-None path) and logs ERROR."""
    ctx = _FailingExitContext()
    agent = _StubProbeAgent(
        probe_types={"sk1": "trace"},
        probe_contexts={"sk1": ctx},  # type: ignore[arg-type]
    )
    exc = ValueError("original error")

    with caplog.at_level("ERROR"):
        agent.stop_probe_context("sk1", exc_info=(type(exc), exc, None))

    assert agent.get_probe_context("sk1") is None
    assert agent.list_tracked_probe_types() == []
    assert ctx.exited is True
    assert any("probe_context.__exit__ failed" in r.message for r in caplog.records)


def test_stop_probe_contexts_by_type_continues_after_one_failure() -> None:
    """stop_probe_contexts_by_type continues stopping remaining probes if one __exit__ fails."""
    failing_ctx = _FailingExitContext()
    good_ctx = _GoodExitContext()
    agent = _StubProbeAgent(
        probe_types={"sk1": "watch", "sk2": "watch"},
        probe_contexts={"sk1": failing_ctx, "sk2": good_ctx},  # type: ignore[arg-type]
    )

    agent.stop_probe_contexts_by_type(["watch"])

    assert agent.get_probe_context("sk1") is None
    assert agent.get_probe_context("sk2") is None
    assert agent.list_tracked_probe_types() == []
    assert failing_ctx.exited is True
    assert good_ctx.exited is True
