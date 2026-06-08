"""Tests for late-loaded gevent detection in trace wrapping."""

# pyright: reportAny=false, reportArgumentType=false, reportAttributeAccessIssue=false, reportImplicitOverride=false, reportMissingParameterType=false, reportMissingTypeArgument=false, reportPrivateUsage=false, reportUnannotatedClassAttribute=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnusedCallResult=false

import sys
import types
from pathlib import Path

import pytest

from peeka.core.injector import DecoratorInjector


class MockAgent:
    """Minimal injector agent."""

    def __init__(self):
        self._observations = []

    def _send_observation(self, observation):
        """Record observations."""
        self._observations.append(observation)


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
    module.helper = helper
    module.root = root
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


@pytest.mark.unit
class TestTraceLateGevent:
    """Late gevent detection regression tests."""

    def test_wrapper_downgrades_when_gevent_patched_at_runtime(self, monkeypatch):
        """Runtime gevent patching should force wrapper-only tracing."""
        agent = MockAgent()
        injector = DecoratorInjector(agent)
        module = _install_trace_module(monkeypatch, "late_gevent_runtime_module")

        watch_id = injector.inject_trace(
            "late_gevent_runtime_module.root", {"trace_depth": 3, "times": 1}
        )

        fake_monkey = types.ModuleType("gevent.monkey")

        def is_module_patched(_name: str) -> bool:
            return True

        fake_monkey.is_module_patched = is_module_patched
        monkeypatch.setitem(sys.modules, "gevent.monkey", fake_monkey)

        assert module.root() == "outer"
        assert len(agent._observations) == 1
        observation = agent._observations[0]
        assert observation["watch_id"] == watch_id
        assert observation["call_tree"][0]["children"] == []

    def test_wrapper_keeps_settrace_when_gevent_not_patched(self, monkeypatch):
        """Clean runtime should keep recursive trace collection."""
        agent = MockAgent()
        injector = DecoratorInjector(agent)
        module = _install_trace_module(monkeypatch, "late_gevent_clean_module")

        watch_id = injector.inject_trace(
            "late_gevent_clean_module.root", {"trace_depth": 3, "times": 1}
        )

        assert module.root() == "outer"
        assert len(agent._observations) == 1
        observation = agent._observations[0]
        assert observation["watch_id"] == watch_id
        assert len(observation["call_tree"][0]["children"]) > 0

    def test_gevent_check_cache_works(self, monkeypatch):
        """Runtime gevent detection should cache a patched state once seen."""
        agent = MockAgent()
        injector = DecoratorInjector(agent)
        module = _install_trace_module(monkeypatch, "late_gevent_cache_module")

        watch_id = injector.inject_trace(
            "late_gevent_cache_module.root", {"trace_depth": 3, "times": 2}
        )

        fake_monkey = types.ModuleType("gevent.monkey")

        def is_module_patched(_name: str) -> bool:
            return True

        fake_monkey.is_module_patched = is_module_patched
        counting_modules = dict(sys.modules)
        counting_modules["gevent.monkey"] = fake_monkey

        class CountingModules(dict):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.gevent_get_calls = 0

            def get(self, key, default=None):
                if key == "gevent.monkey":
                    self.gevent_get_calls += 1
                return super().get(key, default)

        counting_modules = CountingModules(counting_modules)
        monkeypatch.setattr(sys, "modules", counting_modules)

        assert module.root() == "outer"
        assert len(agent._observations) == 1
        observation = agent._observations[0]
        assert observation["watch_id"] == watch_id
        assert observation["call_tree"][0]["children"] == []
        assert counting_modules.gevent_get_calls == 1

        assert module.root() == "outer"
        assert counting_modules.gevent_get_calls == 1

    def test_gevent_check_no_lru_cache_dependency(self):
        """The future helper must not depend on functools.lru_cache."""
        from peeka.core.instrumentation import trace as trace_mod

        source = Path(trace_mod.__file__).read_text(encoding="utf-8")
        start = source.index("def _is_gevent_patched_now")
        end = source.find("\ndef ", start + 1)
        if end == -1:
            end = len(source)
        helper_body = source[start:end]

        wrapper_start = source.index("def _create_trace_wrapper")
        wrapper_end = source.index("def _count_nodes", wrapper_start)
        wrapper_body = source[wrapper_start:wrapper_end]

        assert "lru_cache" not in helper_body
        assert "_is_gevent_patched_now()" in wrapper_body
