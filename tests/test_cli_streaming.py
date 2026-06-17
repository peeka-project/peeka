# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false

import json
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Type, cast

import pytest

from peeka.cli.handlers import observe
from peeka.cli.streaming_config import STREAMING_COMMANDS
from peeka.cli.streaming_config import StreamingCommandConfig


@dataclass
class _TestConfig:
    args_factory: Callable[[int], SimpleNamespace]
    observation_factory: Callable[[str, int], Dict[str, Any]]


def _watch_args(n: int) -> SimpleNamespace:
    return SimpleNamespace(
        pattern="mod.fn",
        depth=1,
        times=n,
        before=False,
        exception=False,
        success=True,
        finish=True,
        condition_express=None,
        client=None,
    )


def _trace_args(n: int) -> SimpleNamespace:
    return SimpleNamespace(
        pattern="mod.fn",
        depth=3,
        times=n,
        condition_express=None,
        skip_builtin=True,
        min_duration=0,
        client=None,
    )


def _stack_args(n: int) -> SimpleNamespace:
    return SimpleNamespace(
        pattern="mod.fn",
        depth=2,
        times=n,
        condition_express=None,
    )


def _monitor_args(n: int) -> SimpleNamespace:
    return SimpleNamespace(
        pattern="mod.fn",
        interval=1,
        cycles=n,
    )


def _top_args(n: int) -> SimpleNamespace:
    return SimpleNamespace(
        interval=1,
        cycles=n,
        no_filter_peeka=False,
    )


def _watch_obs(stream_id: str, idx: int) -> Dict[str, Any]:
    return {"watch_id": stream_id, "count": idx, "location": "AtReturn"}


def _monitor_obs(stream_id: str, idx: int) -> Dict[str, Any]:
    return {"monitor_id": stream_id, "cycles": idx, "stats": {}}


def _top_obs(stream_id: str, idx: int) -> Dict[str, Any]:
    return {"top_id": stream_id, "cycles": idx, "functions": []}


_TEST_HELPERS: Dict[str, _TestConfig] = {
    "watch": _TestConfig(args_factory=_watch_args, observation_factory=_watch_obs),
    "trace": _TestConfig(args_factory=_trace_args, observation_factory=_watch_obs),
    "stack": _TestConfig(args_factory=_stack_args, observation_factory=_watch_obs),
    "monitor": _TestConfig(
        args_factory=_monitor_args, observation_factory=_monitor_obs
    ),
    "top": _TestConfig(args_factory=_top_args, observation_factory=_top_obs),
}

assert set(_TEST_HELPERS.keys()) == set(STREAMING_COMMANDS.keys()), (
    f"_TEST_HELPERS must cover all STREAMING_COMMANDS. Missing: "
    f"{set(STREAMING_COMMANDS.keys()) - set(_TEST_HELPERS.keys())}"
)


_CMD_FUNCS: Dict[str, Callable[..., int]] = {
    "watch": cast(Callable[..., int], observe.cmd_watch),
    "trace": cast(Callable[..., int], observe.cmd_trace),
    "stack": cast(Callable[..., int], observe.cmd_stack),
    "monitor": cast(Callable[..., int], observe.cmd_monitor),
    "top": cast(Callable[..., int], observe.cmd_top),
}
assert set(_CMD_FUNCS.keys()) == set(STREAMING_COMMANDS.keys())


def _stop_has_id(cfg: StreamingCommandConfig) -> bool:
    """True if the stop command includes a stream-id field."""

    test_id = "test_id_check"
    stop = cfg.stop_command_builder(test_id)
    return stop is not None and any(value == test_id for value in stop.values())


_CMDS_WITH_STOP_ID: List[str] = [
    name for name, cfg in STREAMING_COMMANDS.items() if _stop_has_id(cfg)
]


class _MockSessionContext:
    def __init__(self, session_id: str) -> None:
        self._session_id: str = session_id

    def __enter__(self) -> str:
        return self._session_id

    def __exit__(self, *args: Any) -> bool:
        return False


def _make_mock_client_class(
    cfg: StreamingCommandConfig,
    stream_id: str,
    observations: List[Dict[str, Any]],
) -> Type[Any]:
    _response_id_key = cfg.response_id_key
    _command_type = cfg.command_type
    _stream_id = stream_id
    _observations = observations

    class _MockClient:
        commands_sent: List[Dict[str, Any]]
        connected: bool

        def __init__(self, socket_path: str) -> None:
            self.socket_path: str = socket_path
            self.commands_sent = []
            self.connected = False

        def connect(self) -> Dict[str, Any]:
            self.connected = True
            return {"status": "success"}

        def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
            self.commands_sent.append(command)
            if (
                command.get("type") == _command_type
                and command.get("action") == "start"
            ):
                return {"status": "success", _response_id_key: _stream_id}
            return {"status": "success"}

        def stream_observations(self):  # type: ignore[return]
            return iter(_observations)

        def disconnect(self) -> None:
            self.connected = False

    return _MockClient


def _make_session_context_factory(cmd_name: str) -> Callable[[Any], _MockSessionContext]:
    def _factory(_tid: Any) -> _MockSessionContext:
        return _MockSessionContext(f"{cmd_name}_session")

    return _factory


def _patch_observe(
    monkeypatch: pytest.MonkeyPatch,
    cmd_name: str,
    client_factory: Any,
) -> None:
    monkeypatch.setattr(
        observe,
        "_check_agent_attached",
        lambda: (f"/tmp/peeka_{cmd_name}.sock", 1234),
    )
    monkeypatch.setattr(observe, "StreamingAgentClient", client_factory)
    monkeypatch.setattr(
        observe,
        "ephemeral_client",
        _make_session_context_factory(cmd_name),
    )


@pytest.mark.parametrize("cmd_name", list(STREAMING_COMMANDS.keys()))
def test_stream_id_filter_excludes_unrelated_observations(
    cmd_name: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: "pytest.CaptureFixture[str]",
) -> None:
    cfg = STREAMING_COMMANDS[cmd_name]
    helpers = _TEST_HELPERS[cmd_name]
    stream_id = f"{cmd_name}_test_001"
    unrelated_id = f"{cmd_name}_unrelated_999"

    unrelated_obs = {cfg.stream_id_key: unrelated_id, "count": 1, "data": "noise"}
    log_frame = {"type": "log", "level": "INFO", "msg": "background noise"}
    matching_obs = [helpers.observation_factory(stream_id, i + 1) for i in range(2)]
    observations: List[Dict[str, Any]] = [unrelated_obs, log_frame] + matching_obs

    built_clients: List[Any] = []
    MockClient = _make_mock_client_class(cfg, stream_id, observations)

    def build_client(socket_path: str) -> Any:
        client = MockClient(socket_path)
        built_clients.append(client)
        return client

    _patch_observe(monkeypatch, cmd_name, build_client)

    args = helpers.args_factory(2)
    assert _CMD_FUNCS[cmd_name](args) == 0

    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    active_records = [r for r in records if r.get(cfg.stream_id_key) == stream_id]
    assert len(active_records) == 2, (
        f"[{cmd_name}] Expected 2 matching observations, got {len(active_records)}; "
        "unrelated stream IDs and log frames must not count toward the limit"
    )


@pytest.mark.parametrize("cmd_name", list(STREAMING_COMMANDS.keys()))
def test_limit_stops_after_n_matching_observations(
    cmd_name: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: "pytest.CaptureFixture[str]",
) -> None:
    cfg = STREAMING_COMMANDS[cmd_name]
    helpers = _TEST_HELPERS[cmd_name]
    stream_id = f"{cmd_name}_test_002"
    n = 3

    observations = [helpers.observation_factory(stream_id, i + 1) for i in range(n + 10)]

    built_clients: List[Any] = []
    MockClient = _make_mock_client_class(cfg, stream_id, observations)

    def build_client(socket_path: str) -> Any:
        client = MockClient(socket_path)
        built_clients.append(client)
        return client

    _patch_observe(monkeypatch, cmd_name, build_client)

    args = helpers.args_factory(n)
    assert _CMD_FUNCS[cmd_name](args) == 0

    records = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip().startswith("{")
    ]
    active_records = [r for r in records if r.get(cfg.stream_id_key) == stream_id]
    assert len(active_records) == n, (
        f"[{cmd_name}] Expected exactly {n} observations, got {len(active_records)}"
    )


@pytest.mark.parametrize("cmd_name", _CMDS_WITH_STOP_ID)
def test_cleanup_sends_type_specific_stop_command(
    cmd_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = STREAMING_COMMANDS[cmd_name]
    helpers = _TEST_HELPERS[cmd_name]
    stream_id = f"{cmd_name}_test_003"

    observations = [helpers.observation_factory(stream_id, i + 1) for i in range(2)]

    built_clients: List[Any] = []
    MockClient = _make_mock_client_class(cfg, stream_id, observations)

    def build_client(socket_path: str) -> Any:
        client = MockClient(socket_path)
        built_clients.append(client)
        return client

    _patch_observe(monkeypatch, cmd_name, build_client)

    args = helpers.args_factory(1)
    assert _CMD_FUNCS[cmd_name](args) == 0

    assert built_clients, f"[{cmd_name}] No streaming client was constructed"
    client = built_clients[0]

    stop_cmds = [
        cmd
        for cmd in client.commands_sent
        if cmd.get("type") == cmd_name and cmd.get("action") == "stop"
    ]
    assert stop_cmds, (
        f"[{cmd_name}] No type-specific stop command (type={cmd_name!r}, action='stop') "
        "was sent after the limit was reached"
    )

    stop_id_key = cfg.stream_id_key
    assert stop_cmds[0].get(stop_id_key) == stream_id, (
        f"[{cmd_name}] Stop command {stop_id_key!r} must be {stream_id!r}, "
        f"got {stop_cmds[0].get(stop_id_key)!r}"
    )
