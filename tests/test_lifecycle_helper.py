import importlib.util
import logging
import os

import pytest

from peeka.core.agent_control.lifecycle import (
    stop_resource_owners_for_detach,
    stop_resource_owners_for_reset,
)

_LOG = logging.getLogger("test")


class _FakeHandler:
    def __init__(self):
        self.called_with = []

    def stop_active_resources(self, pattern, reason):
        self.called_with.append((pattern, reason))
        return {"stopped": [], "errors": []}


class _FailingHandler:
    def stop_active_resources(self, pattern, reason):
        raise RuntimeError("boom")


class _FakeAgent:
    def __init__(self, handlers=None):
        self.command_handlers = handlers or {}


class _AgentWithNoHandlers:
    pass


@pytest.mark.unit
def test_detach_stops_monitor_and_top_handlers():
    monitor = _FakeHandler()
    top = _FakeHandler()
    agent = _FakeAgent({"monitor": monitor, "top": top})

    result = stop_resource_owners_for_detach(agent, _LOG)

    assert result["errors"] == []
    assert set(result["handlers_stopped"]) == {"monitor", "top"}
    assert monitor.called_with == [(None, "detach")]
    assert top.called_with == [(None, "detach")]


@pytest.mark.unit
def test_reset_stops_only_monitor_handler():
    monitor = _FakeHandler()
    top = _FakeHandler()
    agent = _FakeAgent({"monitor": monitor, "top": top})

    result = stop_resource_owners_for_reset(agent, "some_pattern", _LOG)

    assert result["errors"] == []
    assert result["handlers_stopped"] == ["monitor"]
    assert monitor.called_with == [("some_pattern", "reset")]
    assert top.called_with == []


@pytest.mark.unit
def test_detach_tolerates_absent_command_handlers():
    agent = _AgentWithNoHandlers()

    result = stop_resource_owners_for_detach(agent, _LOG)

    assert result["handlers_stopped"] == []
    assert result["errors"] == []


@pytest.mark.unit
def test_detach_tolerates_none_handler_value():
    agent = _FakeAgent({"monitor": None, "top": None})

    result = stop_resource_owners_for_detach(agent, _LOG)

    assert result["handlers_stopped"] == []
    assert result["errors"] == []


@pytest.mark.unit
def test_detach_tolerates_handler_without_cleanup_method():
    class _BareHandler:
        pass

    agent = _FakeAgent({"monitor": _BareHandler(), "top": _BareHandler()})

    result = stop_resource_owners_for_detach(agent, _LOG)

    assert result["handlers_stopped"] == []
    assert result["errors"] == []


@pytest.mark.unit
def test_detach_error_in_one_handler_does_not_abort_other():
    failing = _FailingHandler()
    good = _FakeHandler()
    agent = _FakeAgent({"monitor": failing, "top": good})

    result = stop_resource_owners_for_detach(agent, _LOG)

    assert len(result["errors"]) == 1
    assert result["errors"][0]["handler"] == "monitor"
    assert "boom" in result["errors"][0]["error"]
    assert result["handlers_stopped"] == ["top"]
    assert good.called_with == [(None, "detach")]


@pytest.mark.unit
def test_lifecycle_helper_does_not_use_get_handler():
    spec = importlib.util.find_spec("peeka.core.agent_control.lifecycle")
    assert spec is not None
    source_path = spec.origin
    assert source_path is not None and os.path.isfile(source_path)
    assert "_get_handler(" not in open(source_path).read()


@pytest.mark.unit
def test_repeated_detach_calls_are_safe():
    monitor = _FakeHandler()
    top = _FakeHandler()
    agent = _FakeAgent({"monitor": monitor, "top": top})

    result1 = stop_resource_owners_for_detach(agent, _LOG)
    result2 = stop_resource_owners_for_detach(agent, _LOG)

    assert result1["errors"] == []
    assert result2["errors"] == []
    assert monitor.called_with == [(None, "detach"), (None, "detach")]
    assert top.called_with == [(None, "detach"), (None, "detach")]
    assert set(result1["handlers_stopped"]) == {"monitor", "top"}
    assert set(result2["handlers_stopped"]) == {"monitor", "top"}
