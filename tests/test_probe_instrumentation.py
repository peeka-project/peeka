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


@pytest.mark.parametrize("kind", ["staticmethod", "classmethod"])
@pytest.mark.parametrize("inherited", [False, True])
@pytest.mark.parametrize("stop_order", [(0, 1), (1, 0), None])
def test_descriptor_watch_restoration(monkeypatch, kind, inherited, stop_order):
    import inspect

    from peeka.core.injector import DecoratorInjector

    def static(value):
        return value + 1

    def class_method(cls, value):
        assert cls is target
        return value + 1

    descriptor = staticmethod(static) if kind == "staticmethod" else classmethod(class_method)
    base = type("Base", (), {"method": descriptor})
    target = type("Child", (base,), {}) if inherited else base
    module = _install_module("descriptor_watch_module", Target=target)
    agent = _new_agent()
    observations = _capture_observations(monkeypatch, agent)
    injector = DecoratorInjector(agent)
    try:
        ids = [injector.inject("descriptor_watch_module.Target.method", {}) for _ in range(2)]
        assert module.Target.method(10) == 11
        assert module.Target().method(20) == 21
        assert [obs["params"] for obs in observations] == [[10], [10], [20], [20]]
        if kind == "staticmethod":
            assert all(obs["target"] is None for obs in observations)
        if stop_order is None:
            assert injector.uninject_all() == 2
        else:
            injector.uninject(ids[stop_order[0]])
            observations.clear()
            assert target.method(30) == 31
            assert target().method(40) == 41
            assert len(observations) == 2
            injector.uninject(ids[stop_order[1]])
        assert inspect.getattr_static(target, "method") is descriptor
        assert ("method" in target.__dict__) is (not inherited)
        assert target.method(50) == 51
        assert target().method(60) == 61
    finally:
        injector.uninject_all()
        sys.modules.pop(module.__name__, None)


@pytest.mark.parametrize("trace", [False, True])
def test_concurrent_inject_is_atomic(monkeypatch, trace):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    from peeka.core.injector import DecoratorInjector

    module = _install_module("atomic_watch_module", watched=lambda value: value)
    injector = DecoratorInjector(_new_agent())
    original = module.watched
    entered = threading.Event()
    release = threading.Event()
    second_started = threading.Event()
    second_committed = threading.Event()
    read_binding = injector._read_target_binding
    calls = []

    def blocking_commit_read(parent_obj, attr_name):
        calls.append((parent_obj, attr_name))
        if len(calls) == 1:
            entered.set()
            assert release.wait(5)
        else:
            second_committed.set()
        return read_binding(parent_obj, attr_name)

    monkeypatch.setattr(injector, "_read_target_binding", blocking_commit_read)

    def install(second=False):
        if second:
            second_started.set()
        if trace:
            return injector.inject_trace("atomic_watch_module.watched", {}, force_backend="wrapper_only")
        return injector.inject("atomic_watch_module.watched", {})

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(install)
            assert entered.wait(5)
            second = pool.submit(install, True)
            assert second_started.wait(5)
            try:
                assert not second_committed.wait(0.1)
            finally:
                release.set()
            ids = [first.result(timeout=5), second.result(timeout=5)]
        assert injector.instrumented[ids[1]]["original"] is injector.instrumented[ids[0]]["wrapper"]
        assert module.watched(42) == 42
        injector.uninject(ids[0])
        injector.uninject(ids[1])
        assert module.watched is original
    finally:
        release.set()
        injector.uninject_all()
        sys.modules.pop(module.__name__, None)


def test_concurrent_watch_conditions_are_isolated(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import threading

    from peeka.core.injector import DecoratorInjector
    from peeka.core.safeeval.simpleeval import SimpleEval

    module = _install_module("isolated_watch_module", watched=lambda value: value)
    agent = _new_agent()
    observations = _capture_observations(monkeypatch, agent)
    injector = DecoratorInjector(agent)
    barrier = threading.Barrier(2)
    original_eval = SimpleEval.eval

    def synchronized_eval(self, expr, previously_parsed=None):
        barrier.wait(timeout=5)
        return original_eval(self, expr, previously_parsed)

    monkeypatch.setattr(SimpleEval, "eval", synchronized_eval)
    try:
        injector.inject("isolated_watch_module.watched", {"condition": "params[0] == 1"})
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(module.watched, [1, 2]))
        assert results == [1, 2]
        assert [obs["params"] for obs in observations] == [[1]]
    finally:
        injector.uninject_all()
        sys.modules.pop(module.__name__, None)


def test_shared_simpleeval_expression_context_is_isolated():
    from concurrent.futures import ThreadPoolExecutor
    import threading

    from peeka.core.safeeval.simpleeval import NameNotDefined, SimpleEval

    barrier = threading.Barrier(2)

    def rendezvous():
        barrier.wait(timeout=5)
        return True

    evaluator = SimpleEval(functions={"rendezvous": rendezvous})

    def evaluate(name):
        expression = "rendezvous() and " + name
        with pytest.raises(NameNotDefined) as error:
            evaluator.eval(expression)
        return error.value.expression

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(evaluate, ["missing_a", "missing_b"])) == [
            "rendezvous() and missing_a", "rendezvous() and missing_b"
        ]
