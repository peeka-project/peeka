"""Tests for trace command gevent compatibility policy integration."""

import pytest

from peeka.commands.trace import TraceCommand
from peeka.core.runtime.gevent_probe import GeventState


class FakeInjector:
    """Record trace injection calls."""

    def __init__(self):
        self.calls = []

    def inject_trace(self, pattern, trace_config, force_backend=None):
        """Return a stable trace id and record the backend."""
        self.calls.append(
            {
                "pattern": pattern,
                "trace_config": trace_config,
                "force_backend": force_backend,
            }
        )
        return "trace_test"


class FakeObserver:
    """Record watch registrations."""

    def __init__(self):
        self.registrations = []

    def register_watch(self, watch_id, pattern, config):
        """Record registration calls."""
        self.registrations.append((watch_id, pattern, config))


class FakeAgent:
    """TraceCommand test agent."""

    def __init__(self):
        self.injector = FakeInjector()
        self.observer = FakeObserver()


@pytest.mark.unit
class TestTraceCommandPolicy:
    """Trace command policy tests."""

    def test_clean_runtime_uses_existing_backend_selection(self, monkeypatch):
        """Clean runtime passes settrace_or_monitoring to injector."""
        monkeypatch.setattr("peeka.commands.trace.probe", lambda: GeventState.NONE)
        agent = FakeAgent()
        command = TraceCommand(agent)

        result = command.execute(
            {"action": "start", "pattern": "module.func", "depth": 3}
        )

        assert result["status"] == "success"
        assert agent.injector.calls[0]["force_backend"] == "settrace_or_monitoring"
        assert result["meta"] == {
            "gevent_state": "none",
            "backend": "settrace_or_monitoring",
            "greenlet_blind": False,
            "degraded_reason": None,
        }

    def test_patched_runtime_uses_wrapper_only(self, monkeypatch):
        """Patched gevent runtime degrades trace to wrapper_only."""
        monkeypatch.setattr("peeka.commands.trace.probe", lambda: GeventState.PATCHED)
        agent = FakeAgent()
        command = TraceCommand(agent)

        result = command.execute({"action": "start", "pattern": "module.func"})

        assert result["status"] == "success"
        assert agent.injector.calls[0]["force_backend"] == "wrapper_only"
        assert result["meta"]["gevent_state"] == "patched"
        assert result["meta"]["backend"] == "wrapper_only"
        assert result["meta"]["greenlet_blind"] is False
        assert isinstance(result["meta"]["degraded_reason"], str)

    def test_active_hub_runtime_uses_wrapper_only(self, monkeypatch):
        """Active gevent hub gets the same wrapper-only degradation."""
        monkeypatch.setattr(
            "peeka.commands.trace.probe", lambda: GeventState.ACTIVE_HUB
        )
        agent = FakeAgent()
        command = TraceCommand(agent)

        result = command.execute({"action": "start", "pattern": "module.func"})

        assert result["status"] == "success"
        assert agent.injector.calls[0]["force_backend"] == "wrapper_only"
        assert result["meta"]["gevent_state"] == "active_hub"
        assert result["meta"]["backend"] == "wrapper_only"
