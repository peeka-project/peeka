"""Tests for watch CLI runtime metadata and limit semantics."""

# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false

import json
import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from peeka.cli.handlers import observe
from peeka.core.output import OutputFormatter


class _MockSessionContext:
    def __init__(self, session_id: str) -> None:
        self._session_id = session_id

    def __enter__(self) -> str:
        return self._session_id

    def __exit__(self, *args: Any) -> bool:
        return False


class _MockWatchStreamingClient:
    def __init__(
        self, socket_path: str, observations: List[Dict[str, Any]]
    ) -> None:
        self.socket_path = socket_path
        self.observations = observations
        self.commands_sent: List[Dict[str, Any]] = []
        self.connected = False

    def connect(self) -> Dict[str, Any]:
        self.connected = True
        return {"status": "success"}

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        self.commands_sent.append(command)
        if command.get("type") == "watch" and command.get("action") == "start":
            return {"status": "success", "watch_id": "watch_cli_123"}
        return {"status": "success"}

    def stream_observations(self):  # type: ignore[return]
        return iter(self.observations)

    def disconnect(self) -> None:
        self.connected = False


class _MockTraceStreamingClient:
    def __init__(
        self, socket_path: str, observations: List[Dict[str, Any]]
    ) -> None:
        self.socket_path = socket_path
        self.observations = observations
        self.commands_sent: List[Dict[str, Any]] = []
        self.connected = False

    def connect(self) -> Dict[str, Any]:
        self.connected = True
        return {"status": "success"}

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        self.commands_sent.append(command)
        if command.get("type") == "trace" and command.get("action") == "start":
            return {"status": "success", "watch_id": "trace_cli_789"}
        return {"status": "success"}

    def stream_observations(self):  # type: ignore[return]
        return iter(self.observations)

    def disconnect(self) -> None:
        self.connected = False


class _MockStackStreamingClient:
    def __init__(
        self, socket_path: str, observations: List[Dict[str, Any]]
    ) -> None:
        self.socket_path = socket_path
        self.observations = observations
        self.commands_sent: List[Dict[str, Any]] = []
        self.connected = False

    def connect(self) -> Dict[str, Any]:
        self.connected = True
        return {"status": "success"}

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        self.commands_sent.append(command)
        if command.get("type") == "stack" and command.get("action") == "start":
            return {"status": "success", "watch_id": "stack_cli_456"}
        return {"status": "success"}

    def stream_observations(self):  # type: ignore[return]
        return iter(self.observations)

    def disconnect(self) -> None:
        self.connected = False


def _watch_args(times: int) -> SimpleNamespace:
    return SimpleNamespace(
        pattern="mod.fn",
        depth=1,
        times=times,
        before=False,
        exception=False,
        success=True,
        finish=True,
        condition_express=None,
        client=None,
    )


def _trace_args(times: int) -> SimpleNamespace:
    return SimpleNamespace(
        pattern="mod.fn",
        depth=3,
        times=times,
        condition_express=None,
        skip_builtin=True,
        min_duration=0,
        client=None,
    )


def _stack_args(times: int) -> SimpleNamespace:
    return SimpleNamespace(
        pattern="mod.fn",
        depth=2,
        times=times,
        condition_express=None,
    )


def test_emit_watch_started_forwards_runtime_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """watch_started should expose runtime_meta as event metadata."""
    captured: Dict[str, Any] = {}

    def capture_event(
        event: str,
        data: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
        **_kwargs: Any,
    ) -> None:
        captured["event"] = event
        captured["data"] = data
        captured["meta"] = meta

    monkeypatch.setattr(OutputFormatter, "event", capture_event)

    args = SimpleNamespace(pattern="pkg.mod.func")
    runtime_meta = {
        "gevent_state": "patched",
        "backend": "wrapper_only",
        "greenlet_blind": False,
    }
    response = {
        "runtime_meta": runtime_meta,
        "target": {"is_coroutine_function": False},
    }

    observe._emit_watch_started(args, response, "watch_001")  # pyright: ignore[reportPrivateUsage]

    assert captured["event"] == "watch_started"
    assert captured["data"]["watch_id"] == "watch_001"
    assert captured["data"]["pattern"] == "pkg.mod.func"
    assert captured["data"]["target"] == {"is_coroutine_function": False}
    assert captured["meta"] == runtime_meta


def test_watch_times_help_current_wording_mentions_print_observations() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "watch", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    help_text = result.stdout.lower()
    assert "-n" in result.stdout and "--times" in result.stdout
    assert "observations" in help_text
    assert "print" in help_text or "emit" in help_text


def test_watch_times_help_does_not_say_capture() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "watch", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    help_text = result.stdout.lower()
    assert "number of times to capture" not in help_text


def test_watch_n_counts_only_watch_observations(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    active_id = "watch_cli_123"
    unrelated_obs = {"watch_id": "watch_other_999", "count": 1, "data": "unrelated"}
    active_obs_1 = {"watch_id": active_id, "count": 5, "location": "AtReturn"}
    active_obs_2 = {"watch_id": active_id, "count": 6, "location": "AtReturn"}
    observations = [unrelated_obs, active_obs_1, active_obs_2]
    streaming_clients: List[_MockWatchStreamingClient] = []

    def build_streaming_client(socket_path: str) -> _MockWatchStreamingClient:
        client = _MockWatchStreamingClient(socket_path, observations)
        streaming_clients.append(client)
        return client

    monkeypatch.setattr(observe, "_check_agent_attached", lambda: ("/tmp/peeka_watch.sock", 1234))
    monkeypatch.setattr(observe, "StreamingAgentClient", build_streaming_client)
    monkeypatch.setattr(observe, "ephemeral_client", lambda _tid: _MockSessionContext("w_session"))

    assert observe.cmd_watch(_watch_args(times=2)) == 0

    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    active_records = [r for r in records if r.get("watch_id") == active_id]
    assert len(active_records) == 2, (
        f"Expected 2 active watch observations, got {len(active_records)}; "
        "unrelated probe observations must not count toward the local -n limit"
    )
    assert [r["count"] for r in active_records] == [5, 6]


def test_unrelated_log_frames_do_not_decrement_watch_n(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    active_id = "watch_cli_123"
    log_frame_1 = {"type": "log", "level": "INFO", "msg": "background log"}
    log_frame_2 = {"type": "log", "level": "DEBUG", "msg": "another log"}
    active_obs_1 = {"watch_id": active_id, "count": 1, "location": "AtReturn"}
    active_obs_2 = {"watch_id": active_id, "count": 2, "location": "AtReturn"}
    observations = [log_frame_1, log_frame_2, active_obs_1, active_obs_2]
    streaming_clients: List[_MockWatchStreamingClient] = []

    def build_streaming_client(socket_path: str) -> _MockWatchStreamingClient:
        client = _MockWatchStreamingClient(socket_path, observations)
        streaming_clients.append(client)
        return client

    monkeypatch.setattr(observe, "_check_agent_attached", lambda: ("/tmp/peeka_watch.sock", 1234))
    monkeypatch.setattr(observe, "StreamingAgentClient", build_streaming_client)
    monkeypatch.setattr(observe, "ephemeral_client", lambda _tid: _MockSessionContext("w_session"))

    assert observe.cmd_watch(_watch_args(times=2)) == 0

    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    active_records = [r for r in records if r.get("watch_id") == active_id]
    assert len(active_records) == 2, (
        f"Expected 2 active watch observations, got {len(active_records)}; "
        "log frames must not count toward the local -n limit"
    )
    assert [r["count"] for r in active_records] == [1, 2]


def test_trace_n_counts_only_trace_observations(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    active_id = "trace_cli_789"
    unrelated_obs = {"watch_id": "watch_other_999", "count": 1, "data": "unrelated"}
    log_frame = {"type": "log", "level": "INFO", "msg": "bg log"}
    active_obs_1 = {"watch_id": active_id, "count": 5, "call_tree": []}
    active_obs_2 = {"watch_id": active_id, "count": 6, "call_tree": []}
    observations = [unrelated_obs, log_frame, active_obs_1, active_obs_2]
    streaming_clients: List[_MockTraceStreamingClient] = []

    def build_streaming_client(socket_path: str) -> _MockTraceStreamingClient:
        client = _MockTraceStreamingClient(socket_path, observations)
        streaming_clients.append(client)
        return client

    monkeypatch.setattr(observe, "_check_agent_attached", lambda: ("/tmp/peeka_trace.sock", 1234))
    monkeypatch.setattr(observe, "StreamingAgentClient", build_streaming_client)
    monkeypatch.setattr(observe, "ephemeral_client", lambda _tid: _MockSessionContext("t_session"))

    assert observe.cmd_trace(_trace_args(times=2)) == 0

    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    active_records = [r for r in records if r.get("watch_id") == active_id]
    assert len(active_records) == 2, (
        f"Expected 2 active trace observations, got {len(active_records)}; "
        "unrelated frames must not count toward the local -n limit"
    )
    assert [r["count"] for r in active_records] == [5, 6]


def test_stack_n_counts_only_stack_observations(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    active_id = "stack_cli_456"
    unrelated_obs = {"watch_id": "watch_other_999", "count": 1, "data": "unrelated"}
    log_frame = {"type": "log", "level": "WARNING", "msg": "bg warning"}
    active_obs_1 = {"watch_id": active_id, "count": 3, "frames": []}
    active_obs_2 = {"watch_id": active_id, "count": 4, "frames": []}
    observations = [unrelated_obs, log_frame, active_obs_1, active_obs_2]
    streaming_clients: List[_MockStackStreamingClient] = []

    def build_streaming_client(socket_path: str) -> _MockStackStreamingClient:
        client = _MockStackStreamingClient(socket_path, observations)
        streaming_clients.append(client)
        return client

    monkeypatch.setattr(observe, "_check_agent_attached", lambda: ("/tmp/peeka_stack.sock", 1234))
    monkeypatch.setattr(observe, "StreamingAgentClient", build_streaming_client)
    monkeypatch.setattr(observe, "ephemeral_client", lambda _tid: _MockSessionContext("s_session"))

    assert observe.cmd_stack(_stack_args(times=2)) == 0

    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    active_records = [r for r in records if r.get("watch_id") == active_id]
    assert len(active_records) == 2, (
        f"Expected 2 active stack observations, got {len(active_records)}; "
        "unrelated frames must not count toward the local -n limit"
    )
    assert [r["count"] for r in active_records] == [3, 4]


class _MockMonitorStreamingClient:
    def __init__(
        self, socket_path: str, observations: List[Dict[str, Any]]
    ) -> None:
        self.socket_path = socket_path
        self.observations = observations
        self.commands_sent: List[Dict[str, Any]] = []
        self.connected = False

    def connect(self) -> Dict[str, Any]:
        self.connected = True
        return {"status": "success"}

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        self.commands_sent.append(command)
        if command.get("type") == "monitor" and command.get("action") == "start":
            return {"status": "success", "monitor_id": "monitor_cli_111"}
        return {"status": "success"}

    def stream_observations(self):  # type: ignore[return]
        return iter(self.observations)

    def disconnect(self) -> None:
        self.connected = False


class _MockTopStreamingClient:
    def __init__(
        self, socket_path: str, observations: List[Dict[str, Any]]
    ) -> None:
        self.socket_path = socket_path
        self.observations = observations
        self.commands_sent: List[Dict[str, Any]] = []
        self.connected = False

    def connect(self) -> Dict[str, Any]:
        self.connected = True
        return {"status": "success"}

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        self.commands_sent.append(command)
        if command.get("type") == "top" and command.get("action") == "start":
            return {"status": "success", "top_id": "top_cli_222"}
        return {"status": "success"}

    def stream_observations(self):  # type: ignore[return]
        return iter(self.observations)

    def disconnect(self) -> None:
        self.connected = False


def _monitor_args(cycles: int) -> SimpleNamespace:
    return SimpleNamespace(
        pattern="mod.fn",
        interval=1,
        cycles=cycles,
    )


def _top_args(cycles: int) -> SimpleNamespace:
    return SimpleNamespace(
        interval=1,
        cycles=cycles,
        no_filter_peeka=False,
    )


def test_monitor_n_counts_only_monitor_observations(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    active_id = "monitor_cli_111"
    log_frame = {"type": "LOG", "level": "INFO", "msg": "background log"}
    unrelated_obs = {"monitor_id": "monitor_other_999", "cycles": 1, "data": "unrelated"}
    active_obs = {"monitor_id": active_id, "cycles": 1, "stats": {}}
    observations = [log_frame, unrelated_obs, active_obs]
    streaming_clients: List[_MockMonitorStreamingClient] = []

    def build_streaming_client(socket_path: str) -> _MockMonitorStreamingClient:
        client = _MockMonitorStreamingClient(socket_path, observations)
        streaming_clients.append(client)
        return client

    monkeypatch.setattr(observe, "_check_agent_attached", lambda: ("/tmp/peeka_monitor.sock", 1234))
    monkeypatch.setattr(observe, "StreamingAgentClient", build_streaming_client)
    monkeypatch.setattr(observe, "ephemeral_client", lambda _tid: _MockSessionContext("m_session"))

    assert observe.cmd_monitor(_monitor_args(cycles=1)) == 0

    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    active_records = [r for r in records if r.get("monitor_id") == active_id]
    assert len(active_records) == 1, (
        f"Expected 1 active monitor observation, got {len(active_records)}; "
        "LOG frames and unrelated OBS frames must not count toward the --cycles limit"
    )


def test_top_n_counts_only_top_observations(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    active_id = "top_cli_222"
    log_frame = {"type": "LOG", "level": "INFO", "msg": "background log"}
    unrelated_obs = {"top_id": "top_other_999", "cycles": 1, "data": "unrelated"}
    active_obs = {"top_id": active_id, "cycles": 1, "functions": []}
    observations = [log_frame, unrelated_obs, active_obs]
    streaming_clients: List[_MockTopStreamingClient] = []

    def build_streaming_client(socket_path: str) -> _MockTopStreamingClient:
        client = _MockTopStreamingClient(socket_path, observations)
        streaming_clients.append(client)
        return client

    monkeypatch.setattr(observe, "_check_agent_attached", lambda: ("/tmp/peeka_top.sock", 1234))
    monkeypatch.setattr(observe, "StreamingAgentClient", build_streaming_client)
    monkeypatch.setattr(observe, "ephemeral_client", lambda _tid: _MockSessionContext("top_session"))

    assert observe.cmd_top(_top_args(cycles=1)) == 0

    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    active_records = [r for r in records if r.get("top_id") == active_id]
    assert len(active_records) == 1, (
        f"Expected 1 active top observation, got {len(active_records)}; "
        "LOG frames and unrelated OBS frames must not count toward the --cycles limit"
    )


def test_stack_start_returns_watch_id_and_cleanup_uses_watch_id(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    active_id = "stack_cli_456"
    active_obs_1 = {"watch_id": active_id, "count": 1, "frames": []}
    active_obs_2 = {"watch_id": active_id, "count": 2, "frames": []}
    unrelated_obs = {"watch_id": "watch_other_999", "count": 9}
    observations = [active_obs_1, unrelated_obs, active_obs_2]
    streaming_clients: List[_MockStackStreamingClient] = []

    def build_streaming_client(socket_path: str) -> _MockStackStreamingClient:
        client = _MockStackStreamingClient(socket_path, observations)
        streaming_clients.append(client)
        return client

    monkeypatch.setattr(observe, "_check_agent_attached", lambda: ("/tmp/peeka_stack.sock", 1234))
    monkeypatch.setattr(observe, "StreamingAgentClient", build_streaming_client)
    monkeypatch.setattr(observe, "ephemeral_client", lambda _tid: _MockSessionContext("s_session"))

    assert observe.cmd_stack(_stack_args(times=2)) == 0

    client = streaming_clients[0]
    stop_commands = [
        cmd for cmd in client.commands_sent
        if cmd.get("type") == "stack" and cmd.get("action") == "stop"
    ]
    assert stop_commands, "cmd_stack must send a stack stop command on cleanup"
    assert stop_commands[0]["watch_id"] == active_id, (
        f"stop command watch_id must be {active_id!r}, got {stop_commands[0].get('watch_id')!r}"
    )

    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    active_records = [r for r in records if r.get("watch_id") == active_id]
    assert len(active_records) == 2, (
        f"Expected 2 active stack observations with times=2, got {len(active_records)}"
    )
    assert [r["count"] for r in active_records] == [1, 2]
