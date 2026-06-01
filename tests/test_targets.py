# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportPrivateLocalImportUsage=false, reportUnusedParameter=false

import json
import shutil
import socket
import tempfile
import threading
from dataclasses import fields
from pathlib import Path
from typing import Any
from typing import Dict
from typing import Optional
from typing import Tuple

import pytest

from peeka.core import targets
from peeka.core.targets import TARGET_SCHEMA_VERSION
from peeka.core.targets import TargetAgent


EXPECTED_KEYS = [
    "schema_version",
    "target_id",
    "legacy_session_id",
    "pid",
    "socket_path",
    "state",
    "agent_mode",
    "injection_mode",
    "python_version",
    "peeka_version",
    "capabilities",
    "runtime",
    "created_at",
    "last_seen_at",
    "recent_errors",
    "next_valid_actions",
]


def _build_target() -> TargetAgent:
    return TargetAgent(
        target_id="target_12345678",
        legacy_session_id="12345678-1234-5678-1234-567812345678",
        pid=4321,
        socket_path="/tmp/peeka_12345678-1234-5678-1234-567812345678.sock",
        state="alive",
        agent_mode="injected",
        injection_mode="pep768",
        python_version="3.12.4",
        peeka_version="0.1.15",
        capabilities={},
        runtime={},
        created_at=10.5,
        last_seen_at=20.5,
        recent_errors=[
            {
                "timestamp": 11.5,
                "code": "TARGET_STALE",
                "message": "example error",
            }
        ],
        next_valid_actions=["inspect", "detach"],
    )


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            return b""
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _start_hello_server(
    socket_path: Path, response: Dict[str, Any]
) -> Tuple[threading.Event, threading.Thread, socket.socket]:
    stop_event = threading.Event()
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(socket_path))
    server.listen(5)
    server.settimeout(0.1)

    def serve() -> None:
        try:
            while not stop_event.is_set():
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
                except OSError:
                    break

                with conn:
                    payload_length = _recv_exact(conn, 4)
                    if not payload_length:
                        continue
                    payload_size = int.from_bytes(payload_length, "big")
                    _ = _recv_exact(conn, payload_size)
                    data = json.dumps(response).encode("utf-8")
                    conn.sendall(len(data).to_bytes(4, "big"))
                    conn.sendall(data)
        finally:
            server.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return stop_event, thread, server


def _stop_server(
    stop_event: threading.Event, thread: threading.Thread, server: socket.socket
) -> None:
    stop_event.set()
    server.close()
    thread.join(timeout=1.0)


def _write_pid(base_dir: Path, session_id: str, pid: int) -> None:
    _ = (base_dir / "peeka_{0}.pid".format(session_id)).write_text(
        str(pid), encoding="utf-8"
    )


def _write_ready(base_dir: Path, session_id: str, payload: Optional[Dict[str, Any]]) -> None:
    ready_path = base_dir / "peeka_{0}.ready".format(session_id)
    if payload is None:
        _ = ready_path.write_text("", encoding="utf-8")
        return
    _ = ready_path.write_text(json.dumps(payload), encoding="utf-8")


def _make_unlistened_socket(socket_path: Path) -> socket.socket:
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(socket_path))
    return sock


def _make_socket_dir() -> Path:
    return Path(tempfile.mkdtemp(prefix="pk-"))


def test_target_agent_fields_match_spec() -> None:
    assert [field.name for field in fields(TargetAgent)] == EXPECTED_KEYS[1:]


def test_target_agent_to_dict_round_trips_and_writes_evidence() -> None:
    target = _build_target()
    serialized = target.to_dict()

    assert list(serialized.keys()) == EXPECTED_KEYS
    assert serialized["schema_version"] == TARGET_SCHEMA_VERSION
    assert json.loads(json.dumps(serialized)) == serialized

    evidence_path = Path(
        ".sisyphus/evidence/target-discovery-task-1-serialize.json"
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    _ = evidence_path.write_text(json.dumps(serialized, indent=2), encoding="utf-8")

    assert json.loads(evidence_path.read_text(encoding="utf-8")) == serialized


def test_target_agent_mutable_defaults_are_isolated() -> None:
    first_target = _build_target()
    second_target = _build_target()

    first_target.capabilities["target_status"] = True
    first_target.runtime["asyncio_loop"] = "running"
    first_target.recent_errors.append(
        {"timestamp": 12.5, "code": "X", "message": "another"}
    )
    first_target.next_valid_actions.append("cleanup")

    assert second_target.capabilities == {}
    assert second_target.runtime == {}
    assert len(second_target.recent_errors) == 1
    assert second_target.next_valid_actions == ["inspect", "detach"]


def test_discover_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_dir = _make_socket_dir()
    monkeypatch.setattr(targets, "SOCKET_DIR", socket_dir)

    alive_sid = "11111111-1111-1111-1111-111111111111"
    stale_sid = "22222222-2222-2222-2222-222222222222"
    unknown_sid = "33333333-3333-3333-3333-333333333333"

    alive_sock_path = socket_dir / f"peeka_{alive_sid}.sock"
    alive_stop, alive_thread, alive_server = _start_hello_server(
        alive_sock_path,
        {
            "status": "success",
            "agent_mode": "injected",
            "injection_mode": "pep768",
            "python_version": "3.12.4",
            "peeka_version": "0.1.15",
            "capabilities": {"hello": True},
            "runtime": {"platform": "linux"},
        },
    )

    stale_socket = _make_unlistened_socket(socket_dir / f"peeka_{stale_sid}.sock")
    unknown_socket = _make_unlistened_socket(socket_dir / f"peeka_{unknown_sid}.sock")

    try:
        _write_pid(socket_dir, alive_sid, 101)
        _write_ready(socket_dir, alive_sid, {})
        _write_pid(socket_dir, stale_sid, 202)
        _write_ready(socket_dir, stale_sid, None)

        def fake_kill(pid: int, sig: int) -> None:
            if pid == 101:
                return
            if pid == 202:
                raise ProcessLookupError()
            raise AssertionError(f"unexpected pid {pid}")

        monkeypatch.setattr(targets.os, "kill", fake_kill)

        discovered = targets.discover_targets()
    finally:
        _stop_server(alive_stop, alive_thread, alive_server)
        stale_socket.close()
        unknown_socket.close()
        shutil.rmtree(socket_dir)

    assert [target.target_id for target in discovered] == [
        "target_11111111",
        "target_22222222",
        "target_33333333",
    ]

    alive_target = discovered[0]
    stale_target = discovered[1]
    unknown_target = discovered[2]

    assert alive_target.state == "alive"
    assert alive_target.pid == 101
    assert alive_target.python_version == "3.12.4"
    assert alive_target.peeka_version == "0.1.15"
    assert alive_target.capabilities == {"hello": True}
    assert alive_target.runtime == {"platform": "linux"}

    assert stale_target.state == "stale"
    assert stale_target.pid == 202

    assert unknown_target.state == "unknown"
    assert unknown_target.pid == 0


def test_cleanup_race_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_dir = _make_socket_dir()
    monkeypatch.setattr(targets, "SOCKET_DIR", socket_dir)

    session_id = "44444444-4444-4444-4444-444444444444"
    socket_holder = _make_unlistened_socket(socket_dir / f"peeka_{session_id}.sock")
    _write_pid(socket_dir, session_id, 404)
    _write_ready(socket_dir, session_id, None)

    calls = {"count": 0}

    def fake_kill(pid: int, sig: int) -> None:
        assert pid == 404
        calls["count"] += 1
        if calls["count"] == 1:
            raise ProcessLookupError()
        return

    monkeypatch.setattr(targets.os, "kill", fake_kill)

    try:
        result = targets.cleanup_stale_targets()
    finally:
        socket_holder.close()

    assert result == {
        "removed": [],
        "skipped": [{"target_id": "target_44444444", "reason": "race_alive"}],
        "errors": [],
    }
    assert (socket_dir / f"peeka_{session_id}.sock").exists()
    assert (socket_dir / f"peeka_{session_id}.pid").exists()
    assert (socket_dir / f"peeka_{session_id}.ready").exists()
    shutil.rmtree(socket_dir)


def test_cleanup_dry_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_dir = _make_socket_dir()
    monkeypatch.setattr(targets, "SOCKET_DIR", socket_dir)

    session_id = "55555555-5555-5555-5555-555555555555"
    socket_holder = _make_unlistened_socket(socket_dir / f"peeka_{session_id}.sock")
    _write_pid(socket_dir, session_id, 505)
    _write_ready(socket_dir, session_id, None)
    _ = (socket_dir / f"peeka_{session_id}.log").write_text(
        "log", encoding="utf-8"
    )

    def fake_kill(pid: int, sig: int) -> None:
        assert pid == 505
        raise ProcessLookupError()

    monkeypatch.setattr(targets.os, "kill", fake_kill)

    try:
        result = targets.cleanup_stale_targets(dry_run=True)
    finally:
        socket_holder.close()

    assert result == {"removed": ["target_55555555"], "skipped": [], "errors": []}
    assert (socket_dir / f"peeka_{session_id}.sock").exists()
    assert (socket_dir / f"peeka_{session_id}.pid").exists()
    assert (socket_dir / f"peeka_{session_id}.ready").exists()
    assert (socket_dir / f"peeka_{session_id}.log").exists()
    shutil.rmtree(socket_dir)


def test_get_target_returns_none_for_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_dir = _make_socket_dir()
    monkeypatch.setattr(targets, "SOCKET_DIR", socket_dir)

    session_id = "66666666-6666-6666-6666-666666666666"
    socket_holder = _make_unlistened_socket(socket_dir / f"peeka_{session_id}.sock")

    try:
        assert targets.get_target("target_missing") is None
    finally:
        socket_holder.close()
        shutil.rmtree(socket_dir)


def test_discover_deterministic_sort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    socket_dir = _make_socket_dir()
    monkeypatch.setattr(targets, "SOCKET_DIR", socket_dir)

    first_sid = "77777777-7777-7777-7777-777777777777"
    second_sid = "11111111-8888-8888-8888-888888888888"
    third_sid = "99999999-9999-9999-9999-999999999999"

    sockets = [
        _make_unlistened_socket(socket_dir / f"peeka_{first_sid}.sock"),
        _make_unlistened_socket(socket_dir / f"peeka_{second_sid}.sock"),
        _make_unlistened_socket(socket_dir / f"peeka_{third_sid}.sock"),
    ]

    created_times = {
        str(socket_dir / f"peeka_{first_sid}.sock"): 20.0,
        str(socket_dir / f"peeka_{second_sid}.sock"): 10.0,
        str(socket_dir / f"peeka_{third_sid}.sock"): 10.0,
    }

    def fake_getctime(path: Path) -> float:
        return created_times[str(path)]

    monkeypatch.setattr(targets.os.path, "getctime", fake_getctime)

    try:
        discovered = targets.discover_targets()
    finally:
        for sock in sockets:
            sock.close()
        shutil.rmtree(socket_dir)

    assert [target.target_id for target in discovered] == [
        "target_11111111",
        "target_99999999",
        "target_77777777",
    ]
