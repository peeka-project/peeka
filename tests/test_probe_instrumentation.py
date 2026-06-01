# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import re
import sys
from typing import Any, Dict, List

import pytest

import peeka.commands.top as top_module

from peeka.commands.top import TopCommand
from peeka.commands.trace import TraceCommand
from peeka.commands.watch import WatchCommand
from peeka.core import probes as probes_module
from peeka.core.agent import PeekaAgent
from peeka.core.probes import ProbeRegistry


EVENT_ID_PATTERN = re.compile(r"evt_[0-9a-f]{6}_\d+")
PROBE_ID_PATTERN = re.compile(r"prb_[0-9a-f]{8}")


class FakeThreadHandle:
    """Thread handle stub that captures thread targets without running them."""

    created: List["FakeThreadHandle"] = []

    def __init__(self, target, name: str):
        self.target = target
        self.name = name
        self.ident = 1000 + len(self.created)
        self._alive = True
        self.created.append(self)

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: Any = None) -> None:
        self._alive = False


@pytest.fixture(autouse=True)
def reset_probe_registry(monkeypatch: pytest.MonkeyPatch) -> ProbeRegistry:
    registry = ProbeRegistry()
    monkeypatch.setattr(probes_module, "probe_registry", registry)
    return registry


def _new_agent() -> PeekaAgent:
    return PeekaAgent(session_id="probe-instrumentation", attached_pid=12345)


def _install_module(module_name: str, **attrs: Any) -> Any:
    module = type(sys)(module_name)
    for name, value in attrs.items():
        setattr(module, name, value)
    sys.modules[module_name] = module
    return module


def _capture_record_event(
    monkeypatch: pytest.MonkeyPatch,
    agent: PeekaAgent,
) -> List[Dict[str, Any]]:
    recorded_payloads: List[Dict[str, Any]] = []
    original_record_event = agent.probe_registry.record_event

    def record_event(probe_id: str, payload: Dict[str, Any]):
        recorded_payloads.append(dict(payload))
        return original_record_event(probe_id, payload)

    monkeypatch.setattr(agent.probe_registry, "record_event", record_event)
    return recorded_payloads


def _capture_observations(
    monkeypatch: pytest.MonkeyPatch,
    agent: PeekaAgent,
) -> List[Dict[str, Any]]:
    observations: List[Dict[str, Any]] = []
    monkeypatch.setattr(agent, "_send_observation", lambda obs: observations.append(dict(obs)))
    return observations


def _assert_payload_tagged(
    observation: Dict[str, Any],
    recorded_payload: Dict[str, Any],
) -> None:
    assert EVENT_ID_PATTERN.fullmatch(observation["event_id"]) is not None
    assert PROBE_ID_PATTERN.fullmatch(observation["probe_id"]) is not None
    assert "event_id" not in recorded_payload
    assert "probe_id" not in recorded_payload

    for key, value in recorded_payload.items():
        assert observation[key] == value


class TestProbeInstrumentation:
    def test_watch_records_and_tags_each_observation(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        agent = _new_agent()
        command = WatchCommand(agent)
        observations = _capture_observations(monkeypatch, agent)
        recorded_payloads = _capture_record_event(monkeypatch, agent)
        result: Dict[str, Any] = {}

        def watched(value: int) -> int:
            return value + 1

        _ = _install_module("probe_watch_module", watched=watched)

        try:
            result = command.execute(
                {
                    "action": "start",
                    "pattern": "probe_watch_module.watched",
                    "client_session_id": "client_watch",
                    "job_id": "job_watch",
                }
            )

            assert result["status"] == "success"

            sys.modules["probe_watch_module"].watched(41)

            assert len(recorded_payloads) == 1
            assert len(observations) == 1
            _assert_payload_tagged(observations[0], recorded_payloads[0])
            assert recorded_payloads[0]["func_name"].endswith("watched")
            assert recorded_payloads[0]["watch_id"] == result["watch_id"]
        finally:
            if "watch_id" in locals().get("result", {}):
                command.execute({"action": "stop", "watch_id": result["watch_id"]})
            sys.modules.pop("probe_watch_module", None)

    def test_trace_records_and_tags_each_observation(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        agent = _new_agent()
        command = TraceCommand(agent)
        observations = _capture_observations(monkeypatch, agent)
        recorded_payloads = _capture_record_event(monkeypatch, agent)
        result: Dict[str, Any] = {}

        def leaf(value: int) -> int:
            return value * 2

        def traced(value: int) -> int:
            return leaf(value) + 1

        module = _install_module("probe_trace_module", traced=traced, leaf=leaf)

        try:
            result = command.execute(
                {
                    "action": "start",
                    "pattern": "probe_trace_module.traced",
                    "client_session_id": "client_trace",
                    "job_id": "job_trace",
                }
            )

            assert result["status"] == "success"

            module.traced(7)

            assert len(recorded_payloads) == 1
            assert len(observations) == 1
            _assert_payload_tagged(observations[0], recorded_payloads[0])
            assert recorded_payloads[0]["watch_id"] == result["watch_id"]
            assert "call_tree" in recorded_payloads[0]
            assert recorded_payloads[0]["func_name"].endswith("traced")
        finally:
            if "watch_id" in locals().get("result", {}):
                command.execute({"action": "stop", "watch_id": result["watch_id"]})
            sys.modules.pop("probe_trace_module", None)

    def test_top_stream_records_and_tags_each_snapshot(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        FakeThreadHandle.created = []
        agent = _new_agent()
        command = TopCommand(agent)
        observations = _capture_observations(monkeypatch, agent)
        recorded_payloads = _capture_record_event(monkeypatch, agent)

        monkeypatch.setattr(top_module, "_NativeThreadHandle", FakeThreadHandle)

        def build_snapshot() -> Dict[str, Any]:
            command._stop_event.set()
            return {
                "type": "top_snapshot",
                "top_id": command._top_id,
                "total_samples": 3,
                "sample_interval": command._interval,
                "functions": [{"name": "busy", "own_count": 3, "total_count": 3}],
                "meta": dict(command._meta),
            }

        monkeypatch.setattr(command, "_build_snapshot", build_snapshot)

        result = command.execute(
            {
                "action": "start",
                "interval": 0.01,
                "stream": True,
                "client_session_id": "client_top",
                "job_id": "job_top",
            }
        )

        assert result["status"] == "success"
        assert len(FakeThreadHandle.created) == 2

        try:
            FakeThreadHandle.created[1].target()

            assert len(recorded_payloads) == 1
            assert len(observations) == 1
            _assert_payload_tagged(observations[0], recorded_payloads[0])
            assert recorded_payloads[0]["top_id"] == result["top_id"]
            assert recorded_payloads[0]["functions"][0]["name"] == "busy"
        finally:
            command.execute({"action": "stop"})

    def test_top_stream_exception_marks_probe_failed(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        FakeThreadHandle.created = []
        agent = _new_agent()
        command = TopCommand(agent)

        monkeypatch.setattr(top_module, "_NativeThreadHandle", FakeThreadHandle)
        monkeypatch.setattr(command, "_build_snapshot", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

        result = command.execute(
            {
                "action": "start",
                "interval": 0.01,
                "stream": True,
                "client_session_id": "client_top_fail",
                "job_id": "job_top_fail",
            }
        )

        assert result["status"] == "success"

        try:
            with pytest.raises(RuntimeError, match="boom"):
                FakeThreadHandle.created[1].target()

            probes = agent.probe_registry.list(type="top")
            assert len(probes) == 1
            assert probes[0].status == "failed"
            assert probes[0].last_error == {
                "code": "COMMAND_EXECUTION_ERROR",
                "message": "boom",
            }
            assert probes[0].summary["last_error"] == "boom"
        finally:
            command.execute({"action": "stop"})
