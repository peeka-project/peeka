# pyright: reportDeprecated=false, reportUnannotatedClassAttribute=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportAny=false, reportExplicitAny=false, reportUnknownVariableType=false, reportUnknownLambdaType=false, reportUnusedVariable=false

"""Tests for trace observation cleanup in wrapper-only backend."""

import json
import sys
from typing import Any, Callable, Dict, Tuple, cast

import pytest

from peeka.core.injector import DecoratorInjector


class MockAgent:
    """Minimal injector agent."""

    def __init__(self):
        self._observations = []

    def _send_observation(self, observation):
        """Record observations."""
        self._observations.append(observation)


def _install_module(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    func_name: str,
    func: Callable[..., Any],
) -> Any:
    module: Any = type(sys)(module_name)
    setattr(module, func_name, func)
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


def _inject_trace(
    monkeypatch: pytest.MonkeyPatch,
    module_name: str,
    func_name: str,
    func: Callable[..., Any],
) -> Tuple[Any, DecoratorInjector, str]:
    _install_module(monkeypatch, module_name, func_name, func)
    agent = cast(Any, MockAgent())
    injector = DecoratorInjector(agent)
    watch_id = injector.inject_trace(
        f"{module_name}.{func_name}",
        {"trace_depth": 1, "times": 1},
        force_backend="wrapper_only",
    )
    return agent, injector, watch_id


@pytest.mark.unit
class TestTraceObservationClean:
    def test_observation_contains_no_internal_result_field(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module_name = "test_trace_observation_clean_result_module"

        def sample():
            return 7

        sample.__module__ = module_name
        agent, _injector, _watch_id = _inject_trace(
            monkeypatch, module_name, "sample", sample
        )

        module = sys.modules[module_name]
        assert module.sample() == 7

        observation = agent._observations[0]
        node = observation["call_tree"][0]
        assert not any(key.startswith("_") for key in node)

    def test_observation_json_serializable_with_complex_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module_name = "test_trace_observation_clean_json_module"

        def sample():
            return lambda value: value + 1

        sample.__module__ = module_name
        agent, _injector, _watch_id = _inject_trace(
            monkeypatch, module_name, "sample", sample
        )

        module = sys.modules[module_name]
        assert callable(module.sample())

        observation = agent._observations[0]
        serialized = json.dumps(observation)
        assert serialized

    def test_observation_exception_serialized_as_dict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module_name = "test_trace_observation_clean_exception_module"

        def sample():
            raise ValueError("test error")

        sample.__module__ = module_name
        agent, _injector, _watch_id = _inject_trace(
            monkeypatch, module_name, "sample", sample
        )

        module = sys.modules[module_name]
        with pytest.raises(ValueError, match="test error"):
            module.sample()

        observation: Dict[str, Any] = agent._observations[0]
        node: Dict[str, Any] = observation["call_tree"][0]
        assert node["exception"] == {
            "type": "ValueError",
            "message": "test error",
        }
        assert "_exception" not in node

    def test_return_value_preserved_after_cleanup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module_name = "test_trace_observation_clean_return_module"

        def sample():
            return 42

        sample.__module__ = module_name
        _agent, _injector, _watch_id = _inject_trace(
            monkeypatch, module_name, "sample", sample
        )

        module = sys.modules[module_name]
        assert module.sample() == 42

    def test_exception_reraised_after_cleanup(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        module_name = "test_trace_observation_clean_reraise_module"

        def sample():
            raise RuntimeError("boom")

        sample.__module__ = module_name
        _agent, _injector, _watch_id = _inject_trace(
            monkeypatch, module_name, "sample", sample
        )

        module = sys.modules[module_name]
        with pytest.raises(RuntimeError, match="boom"):
            module.sample()
