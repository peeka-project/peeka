"""Tests for policy-driven trace backend dispatch in DecoratorInjector."""

import sys

import pytest

from peeka.core.injector import DecoratorInjector


class MockAgent:
    """Minimal injector agent."""

    def __init__(self):
        self._observations = []

    def _send_observation(self, observation):
        """Record observations."""
        self._observations.append(observation)


@pytest.mark.unit
class TestInjectorForceBackend:
    """force_backend behavior tests."""

    def test_wrapper_only_does_not_call_sys_settrace(self, monkeypatch):
        """wrapper_only avoids global tracing APIs."""
        agent = MockAgent()
        injector = DecoratorInjector(agent)

        def sample(value):
            return value * 2

        module = type(sys)("test_force_backend_module")
        module.sample = sample
        monkeypatch.setitem(sys.modules, "test_force_backend_module", module)

        def fail_settrace(_trace):
            raise AssertionError("sys.settrace should not be called")

        monkeypatch.setattr(sys, "settrace", fail_settrace)

        watch_id = injector.inject_trace(
            "test_force_backend_module.sample",
            {"trace_depth": 3, "times": 1},
            force_backend="wrapper_only",
        )

        assert watch_id.startswith("trace_")
        assert module.sample(4) == 8
        assert len(agent._observations) == 1
        observation = agent._observations[0]
        assert observation["watch_id"] == watch_id
        assert observation["call_tree"][0]["children"] == []
        assert "sample" in observation["call_tree"][0]["function"]

    def test_default_backend_preserves_config(self, monkeypatch):
        """Default trace injection remains backward compatible."""
        agent = MockAgent()
        injector = DecoratorInjector(agent)

        def sample():
            return "ok"

        module = type(sys)("test_default_backend_module")
        module.sample = sample
        monkeypatch.setitem(sys.modules, "test_default_backend_module", module)

        watch_id = injector.inject_trace(
            "test_default_backend_module.sample", {"trace_depth": 3, "times": 1}
        )

        assert "_force_backend" not in injector.instrumented[watch_id]["config"]
        assert module.sample() == "ok"
        assert len(agent._observations) == 1
