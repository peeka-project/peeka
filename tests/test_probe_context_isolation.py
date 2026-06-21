"""Tests for probe-context isolation and live probe discovery."""

import threading
from typing import Any, Dict, Optional

from peeka.core.agent_control.probes import AgentProbeControlMixin


class _StubProbeAgent(AgentProbeControlMixin):
    """Minimal stub that satisfies AgentProbeControlMixin requirements."""

    def __init__(
        self,
        probe_types: Optional[Dict[str, str]] = None,
        probe_contexts: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._probe_context_lock = threading.Lock()
        self._probe_context_types: Dict[str, str] = dict(probe_types or {})
        self._probe_contexts: Dict[str, Any] = dict(probe_contexts or {})


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
