"""RED-phase contracts for runtime watch metadata."""

# pyright: reportAny=false, reportArgumentType=false, reportAttributeAccessIssue=false, reportImplicitOverride=false, reportMissingParameterType=false, reportMissingTypeArgument=false, reportPrivateUsage=false, reportUnannotatedClassAttribute=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnusedCallResult=false

import sys
import types

import pytest

from peeka.commands.watch import WatchCommand
from peeka.core.injector import DecoratorInjector
from peeka.core.instrumentation import watch as watch_mod
from peeka.core.runtime import gevent_probe
from peeka.core.runtime.gevent_probe import GeventState


class MockAgent:
    """Minimal injector agent."""

    def __init__(self):
        self._observations = []

    def _send_observation(self, observation):
        """Record observations."""
        self._observations.append(observation)


class FakeInjector:
    """Record watch injection calls."""

    def __init__(self):
        self.calls = []
        self._watch_info = {
            "is_coroutine_function": False,
            "alias_count": 0,
            "aliases": [],
        }

    def inject(self, pattern, watch_config):
        """Return a stable watch id and record the config."""
        self.calls.append(
            {
                "pattern": pattern,
                "watch_config": watch_config,
            }
        )
        return "watch_test"

    def get_watch_info(self, watch_id):
        """Return a stable watch info payload."""
        if watch_id != "watch_test":
            return None
        return self._watch_info


class FakeObserver:
    """Record watch registrations."""

    def __init__(self):
        self.registrations = []

    def register_watch(self, watch_id, pattern, config):
        """Record registration calls."""
        self.registrations.append((watch_id, pattern, config))


class FakeAgent:
    """WatchCommand test agent."""

    def __init__(self):
        self.injector = FakeInjector()
        self.observer = FakeObserver()


def _install_watch_module(monkeypatch, module_name):
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
def reset_watch_probe_cache():
    """Reset cached watch probe helpers between tests."""
    original_probe = gevent_probe.probe
    original_cache = getattr(watch_mod, "_GEVENT_PATCHED_CACHE", None)
    try:
        if hasattr(watch_mod, "_GEVENT_PATCHED_CACHE"):
            watch_mod._GEVENT_PATCHED_CACHE = None
        yield
    finally:
        gevent_probe.probe = original_probe
        if hasattr(watch_mod, "_GEVENT_PATCHED_CACHE"):
            watch_mod._GEVENT_PATCHED_CACHE = original_cache


@pytest.mark.unit
class TestWatchRuntimeMeta:
    """Runtime metadata contract tests for watch."""

    def test_watch_observation_includes_runtime_meta_when_gevent_patched(self, monkeypatch):
        """Patched gevent should surface runtime watch metadata."""
        agent = MockAgent()
        injector = DecoratorInjector(agent)
        module = _install_watch_module(monkeypatch, "watch_runtime_meta_patched")
        monkeypatch.setattr(gevent_probe, "probe", lambda: GeventState.PATCHED)

        injector.inject("watch_runtime_meta_patched.root", {"depth": 3, "times": 1})

        assert module.root() == "outer"
        observation = agent._observations[0]

        assert observation["runtime_meta"]["gevent_state"] == GeventState.PATCHED.value
        assert observation["runtime_meta"]["backend"] == "wrapper_only"
        assert observation["runtime_meta"]["greenlet_blind"] is False
        assert observation["runtime_meta"]["degraded_reason"] is not None

    def test_watch_observation_no_runtime_meta_when_clean_runtime(self, monkeypatch):
        """Clean runtime should not report watch metadata."""
        agent = MockAgent()
        injector = DecoratorInjector(agent)
        module = _install_watch_module(monkeypatch, "watch_runtime_meta_clean")
        monkeypatch.setattr(gevent_probe, "probe", lambda: GeventState.NONE)

        injector.inject("watch_runtime_meta_clean.root", {"depth": 3, "times": 1})

        assert module.root() == "outer"
        observation = agent._observations[0]

        assert observation["runtime_meta"] is None

    def test_watch_start_response_includes_runtime_meta(self, monkeypatch):
        """Startup response should expose runtime watch metadata."""
        _install_watch_module(monkeypatch, "watch_runtime_meta_start")
        monkeypatch.setattr(gevent_probe, "probe", lambda: GeventState.PATCHED)
        agent = FakeAgent()
        command = WatchCommand(agent)

        result = command.execute({"action": "start", "pattern": "watch_runtime_meta_start.root"})

        assert result["status"] == "success"
        assert result["runtime_meta"]["gevent_state"] == GeventState.PATCHED.value
        assert result["runtime_meta"]["backend"] == "wrapper_only"
        assert result["runtime_meta"]["greenlet_blind"] is False
        assert result["runtime_meta"]["degraded_reason"] is not None
