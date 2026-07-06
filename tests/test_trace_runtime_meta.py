"""RED-phase contracts for runtime trace downgrade metadata."""

# pyright: reportAny=false, reportArgumentType=false, reportAttributeAccessIssue=false, reportImplicitOverride=false, reportMissingParameterType=false, reportMissingTypeArgument=false, reportPrivateUsage=false, reportUnannotatedClassAttribute=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnusedCallResult=false

import sys
import types

import pytest

from peeka.commands.trace import TraceCommand
from peeka.core.instrumentation import trace as trace_mod
from peeka.core.injector import DecoratorInjector
from peeka.core.runtime.gevent_probe import GeventState


class MockAgent:
    """Minimal injector agent."""

    def __init__(self):
        self._observations = []

    def _send_observation(self, observation):
        """Record observations."""
        self._observations.append(observation)


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


def _install_trace_module(monkeypatch, module_name):
    """Create a tiny module with a helper call chain."""
    module = types.ModuleType(module_name)

    def helper():
        return "inner"

    def root():
        helper()
        return "outer"

    helper.__module__ = module_name
    root.__module__ = module_name
    setattr(module, "helper", helper)
    setattr(module, "root", root)
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


@pytest.fixture(autouse=True)
def reset_gevent_cache():
    """Reset cached gevent patch state between tests."""
    original = trace_mod._GEVENT_PATCHED_CACHE
    trace_mod._GEVENT_PATCHED_CACHE = None
    try:
        yield
    finally:
        trace_mod._GEVENT_PATCHED_CACHE = original


@pytest.mark.unit
class TestTraceRuntimeMeta:
    """Runtime downgrade metadata contract tests."""

    def test_observation_includes_runtime_meta_on_downgrade(self, monkeypatch):
        """Late gevent patching should surface runtime trace metadata."""
        agent = MockAgent()
        injector = DecoratorInjector(agent)
        module = _install_trace_module(monkeypatch, "trace_runtime_meta_downgrade")

        injector.inject_trace(
            "trace_runtime_meta_downgrade.root", {"trace_depth": 3, "times": 1}
        )

        fake_monkey = types.ModuleType("gevent.monkey")

        def is_module_patched(_name):
            return True

        setattr(fake_monkey, "is_module_patched", is_module_patched)
        monkeypatch.setitem(sys.modules, "gevent.monkey", fake_monkey)

        assert module.root() == "outer"
        observation = agent._observations[0]

        if sys.version_info >= (3, 12):
            runtime_meta = observation.get("runtime_meta")
            assert runtime_meta is None or not runtime_meta.get("trace", {}).get("downgraded", False)
        else:
            assert observation["runtime_meta"]["trace"]["downgraded"] is True
            assert observation["runtime_meta"]["trace"]["effective_backend"] == "wrapper_only"
            assert observation["runtime_meta"]["trace"]["gevent_patched_now"] is True

    def test_observation_runtime_meta_absent_when_no_downgrade(self, monkeypatch):
        """Clean runtime should not report downgrade metadata."""
        agent = MockAgent()
        injector = DecoratorInjector(agent)
        module = _install_trace_module(monkeypatch, "trace_runtime_meta_clean")

        injector.inject_trace(
            "trace_runtime_meta_clean.root", {"trace_depth": 3, "times": 1}
        )

        assert module.root() == "outer"
        observation = agent._observations[0]

        runtime_meta = observation.get("runtime_meta")
        assert runtime_meta is None or not runtime_meta.get("trace", {}).get("downgraded", False)

    def test_trace_start_response_has_no_runtime_meta_initially(self, monkeypatch):
        """Startup response should stay unchanged before any downgrade."""
        monkeypatch.setattr("peeka.commands.trace.probe", lambda: GeventState.NONE)
        agent = FakeAgent()
        command = TraceCommand(agent)

        result = command.execute({"action": "start", "pattern": "module.func"})

        assert result["status"] == "success"
        assert "runtime_meta" not in result or result["runtime_meta"] in (None, False)

    def test_trace_start_response_exposes_runtime_meta_after_downgrade(self, monkeypatch):
        """Patched gevent startup should include downgrade metadata in response."""
        monkeypatch.setattr("peeka.commands.trace.probe", lambda: GeventState.PATCHED)
        agent = FakeAgent()
        command = TraceCommand(agent)

        result = command.execute({"action": "start", "pattern": "module.func"})

        assert result["status"] == "success"
        if sys.version_info >= (3, 12):
            assert "runtime_meta" not in result or result["runtime_meta"] in (None, False)
        else:
            assert result["runtime_meta"]["trace"]["downgraded"] is True
            assert result["runtime_meta"]["trace"]["effective_backend"] == "wrapper_only"
            assert result["runtime_meta"]["trace"]["gevent_patched_now"] is True

    def test_observation_runtime_meta_present_when_prepatched_at_startup(self, monkeypatch):
        """Pre-patched gevent startup should still emit trace observation runtime meta."""
        monkeypatch.setattr("peeka.commands.trace.probe", lambda: GeventState.PATCHED)
        fake_monkey = types.ModuleType("gevent.monkey")

        def is_module_patched(_name):
            return True

        setattr(fake_monkey, "is_module_patched", is_module_patched)
        monkeypatch.setitem(sys.modules, "gevent.monkey", fake_monkey)

        agent = MockAgent()
        agent.injector = DecoratorInjector(agent)
        agent.observer = FakeObserver()
        module = _install_trace_module(monkeypatch, "trace_runtime_meta_prepatched")
        command = TraceCommand(agent)

        result = command.execute(
            {"action": "start", "pattern": "trace_runtime_meta_prepatched.root"}
        )

        assert result["status"] == "success"
        if sys.version_info >= (3, 12):
            assert "runtime_meta" not in result or result["runtime_meta"] in (None, False)
        else:
            assert result["runtime_meta"]["trace"]["effective_backend"] == "wrapper_only"

        assert module.root() == "outer"
        observation = agent._observations[0]

        if sys.version_info >= (3, 12):
            runtime_meta = observation.get("runtime_meta")
            assert runtime_meta is None or not runtime_meta.get("trace", {}).get("downgraded", False)
        else:
            assert observation["runtime_meta"]["trace"]["effective_backend"] == "wrapper_only"

    def test_observation_runtime_meta_schema(self, monkeypatch):
        """Runtime trace metadata should expose the full schema on downgrade."""
        agent = MockAgent()
        injector = DecoratorInjector(agent)
        module = _install_trace_module(monkeypatch, "trace_runtime_meta_schema")

        injector.inject_trace(
            "trace_runtime_meta_schema.root", {"trace_depth": 3, "times": 1}
        )

        fake_monkey = types.ModuleType("gevent.monkey")

        def is_module_patched(_name):
            return True

        setattr(fake_monkey, "is_module_patched", is_module_patched)
        monkeypatch.setitem(sys.modules, "gevent.monkey", fake_monkey)

        assert module.root() == "outer"

        if sys.version_info >= (3, 12):
            runtime_meta = agent._observations[0].get("runtime_meta")
            assert runtime_meta is None or not runtime_meta.get("trace", {}).get("downgraded", False)
        else:
            trace_meta = agent._observations[0]["runtime_meta"]["trace"]

            assert isinstance(trace_meta, dict)
            assert set(trace_meta) >= {
                "startup_backend",
                "effective_backend",
                "downgraded",
                "downgrade_reason",
                "gevent_patched_now",
            }
            assert isinstance(trace_meta["startup_backend"], str)
            assert isinstance(trace_meta["effective_backend"], str)
            assert isinstance(trace_meta["downgraded"], bool)
            assert trace_meta["downgrade_reason"] is None or isinstance(trace_meta["downgrade_reason"], str)
            assert isinstance(trace_meta["gevent_patched_now"], bool)
