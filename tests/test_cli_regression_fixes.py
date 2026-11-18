# pyright: reportPrivateUsage=false, reportDeprecated=false

"""Regression tests for CLI target ambiguity, permission preservation, stream filtering, and run command."""

import argparse
import errno
import json
import os
import signal
import socket
import sys
import tempfile
import threading
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from peeka.cli import connection as cli_connection
from peeka.cli import sessions as cli_sessions
from peeka.cli import streaming as cli_streaming
from peeka.cli import targets as cli_targets
from peeka.cli.handlers import run as cli_run


class _FakeStreamClient:
    """Fake streaming client emitting predefined observations and recording commands."""

    def __init__(
        self,
        start_response: Dict[str, Any],
        observations: List[Dict[str, Any]],
        stop_response: Dict[str, Any] = None,
    ) -> None:
        self.start_response = start_response
        self.observations = list(observations)
        self.stop_response = stop_response or {"status": "success"}
        self.commands_received: List[Dict[str, Any]] = []
        self.disconnected = False

    def connect(self) -> Dict[str, Any]:
        return {"status": "success"}

    def send_command(self, cmd: Dict[str, Any]) -> Dict[str, Any]:
        self.commands_received.append(cmd)
        if cmd.get("action") == "stop":
            return self.stop_response
        if cmd.get("type") == "detach":
            return {"status": "success"}
        return self.start_response

    def stream_observations(self):
        yield from self.observations

    def disconnect(self) -> None:
        self.disconnected = True


def _patch_tmp_dir_and_sockets(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Redirect Path('/tmp') in peeka.cli.sessions and treat *.sock files as sockets."""
    real_path = cli_sessions.Path

    def _fake_path(arg: Any) -> Path:
        if arg == "/tmp":
            return tmp_path
        return real_path(arg)

    monkeypatch.setattr(cli_sessions, "Path", _fake_path)
    monkeypatch.setattr(
        Path,
        "is_socket",
        lambda self: self.suffix == ".sock" and self.exists(),
    )


class TestMultiTargetAndPermissionPreservation:
    """Ensure multi-PID/multi-session ambiguity fails loudly and EPERM preserves sessions."""

    def test_exception_class_shared_between_sessions_and_connection(self) -> None:
        assert cli_connection.TargetResolutionError is cli_sessions.TargetResolutionError
        assert issubclass(cli_sessions.TargetResolutionError, ValueError)

    def test_find_pid_by_name_raises_on_multiple_matches(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        proc_dir = tmp_path / "proc"
        proc_dir.mkdir()
        for pid in ("101", "202"):
            d = proc_dir / pid
            d.mkdir()
            (d / "cmdline").write_bytes(b"python3\x00worker.py\x00")
        (proc_dir / "303").mkdir()
        (proc_dir / "303" / "cmdline").write_bytes(b"nginx\x00master\x00")

        real_path = cli_targets.Path

        def _fake_path(arg: Any) -> Path:
            if arg == "/proc":
                return proc_dir
            return real_path(arg)

        monkeypatch.setattr(cli_targets, "Path", _fake_path)

        with pytest.raises(cli_targets.TargetResolutionError) as exc_info:
            cli_targets._find_pid_by_name("worker.py")

        assert exc_info.value.error_code == "TARGET_AMBIGUOUS"
        assert "101" in str(exc_info.value)
        assert "202" in str(exc_info.value)

    def test_find_active_sessions_preserves_eperm_and_cleans_esrch(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _patch_tmp_dir_and_sockets(monkeypatch, tmp_path)

        sock_a = tmp_path / "peeka_aaa.sock"
        sock_b = tmp_path / "peeka_bbb.sock"
        sock_a.write_text("")
        sock_b.write_text("")

        # Session 1: EPERM (owned by another user / privileged process) -> preserve!
        (tmp_path / "peeka_aaa.pid").write_text("1111")
        # Session 2: ESRCH (dead process) -> unlink!
        (tmp_path / "peeka_bbb.pid").write_text("2222")

        def _fake_kill(pid: int, sig: int) -> None:
            if pid == 1111:
                raise PermissionError(errno.EPERM, "Operation not permitted")
            if pid == 2222:
                raise ProcessLookupError(errno.ESRCH, "No such process")

        monkeypatch.setattr(cli_sessions.os, "kill", _fake_kill)

        sessions = cli_sessions._find_active_sessions()

        assert len(sessions) == 1
        assert sessions[0][1] == 1111
        assert (tmp_path / "peeka_aaa.pid").exists()
        assert sock_a.exists()
        assert not (tmp_path / "peeka_bbb.pid").exists()
        assert not sock_b.exists()

    def test_find_active_session_raises_ambiguous_on_multiple_alive_sessions(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _patch_tmp_dir_and_sockets(monkeypatch, tmp_path)
        for sid, pid in (("sess1", 1111), ("sess2", 2222)):
            (tmp_path / f"peeka_{sid}.pid").write_text(str(pid))
            (tmp_path / f"peeka_{sid}.sock").write_text("")

        monkeypatch.setattr(cli_sessions.os, "kill", lambda pid, sig: None)

        with pytest.raises(cli_sessions.TargetResolutionError) as exc_info:
            cli_sessions._find_active_session()

        assert exc_info.value.error_code == "TARGET_AMBIGUOUS"

    def test_connect_streaming_agent_also_rejects_multiple_default_sessions(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        _patch_tmp_dir_and_sockets(monkeypatch, tmp_path)
        for sid, pid in (("sess1", 1111), ("sess2", 2222)):
            (tmp_path / f"peeka_{sid}.pid").write_text(str(pid))
            (tmp_path / f"peeka_{sid}.sock").write_text("")

        monkeypatch.setattr(cli_sessions.os, "kill", lambda pid, sig: None)

        assert cli_connection._connect_streaming_agent("watch") is None
        assert json.loads(capsys.readouterr().out)["error_code"] == "TARGET_AMBIGUOUS"

    def test_check_agent_attached_propagates_target_ambiguous_error(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        _patch_tmp_dir_and_sockets(monkeypatch, tmp_path)
        for sid, pid in (("sess1", 1111), ("sess2", 2222)):
            (tmp_path / f"peeka_{sid}.pid").write_text(str(pid))
            (tmp_path / f"peeka_{sid}.sock").write_text("")

        monkeypatch.setattr(cli_sessions.os, "kill", lambda pid, sig: None)

        with pytest.raises(cli_sessions.TargetResolutionError) as exc_info:
            cli_sessions._check_agent_attached()
        assert exc_info.value.error_code == "TARGET_AMBIGUOUS"


class TestCLIStreamFilteringAndRunConfigReuse:
    """Verify log/foreign probe filtering and run command config reuse with real payloads."""

    @pytest.mark.parametrize(
        "stream_id_key,stream_id,foreign_obs,valid_obs",
        [
            (
                "watch_id",
                "watch_mine",
                {
                    "watch_id": "watch_other",
                    "timestamp": 1752096181.0,
                    "location": "AtReturn",
                    "func_name": "other.fn",
                    "params": [999],
                    "kwargs": {},
                    "target": None,
                    "returnObj": 1000,
                    "success": True,
                    "throwExp": None,
                    "cost": 0.2,
                },
                {
                    "watch_id": "watch_mine",
                    "timestamp": 1752096182.0,
                    "location": "AtReturn",
                    "func_name": "pkg.Counter.inc",
                    "params": [5],
                    "kwargs": {"step": 1},
                    "target": {"type": "Counter", "value": "<Counter>"},
                    "returnObj": 6,
                    "success": True,
                    "throwExp": None,
                    "cost": 0.4,
                    "runtime_meta": None,
                },
            ),
            (
                "monitor_id",
                "mon_mine",
                {
                    "monitor_id": "mon_other",
                    "watch_id": "mon_other",
                    "total": 99,
                    "success": 99,
                    "fail": 0,
                    "rt_avg": 1.0,
                },
                {
                    "monitor_id": "mon_mine",
                    "watch_id": "mon_mine",
                    "cycle": 1,
                    "total": 10,
                    "success": 9,
                    "fail": 1,
                    "rt_avg": 3.5,
                    "rt_min": 1.0,
                    "rt_max": 8.0,
                    "rt_p95": 7.5,
                },
            ),
            (
                "top_id",
                "top_mine",
                {"top_id": "top_other", "functions": [{"name": "noise"}]},
                {
                    "top_id": "top_mine",
                    "total_samples": 42,
                    "sample_interval": 0.01,
                    "functions": [{"name": "target_fn", "own_pct": 50.0}],
                },
            ),
        ],
    )
    def test_run_streaming_command_filters_logs_and_foreign_probes_before_counting(
        self,
        tmp_path: Path,
        capsys,
        stream_id_key: str,
        stream_id: str,
        foreign_obs: Dict[str, Any],
        valid_obs: Dict[str, Any],
    ) -> None:
        stream = [
            {"type": "log", "level": "INFO", "message": "[peeka Agent] noise"},
            foreign_obs,
            dict(valid_obs),
            {"type": "log", "level": "WARN", "message": "[peeka Agent] more noise"},
            foreign_obs,
            dict(valid_obs),
            dict(valid_obs),  # Should not be reached after -n 2 stops the loop
        ]
        client = _FakeStreamClient(
            start_response={"status": "success", stream_id_key: stream_id},
            observations=stream,
        )

        printed_count = [0]

        def _limit(obs: Dict[str, Any]) -> bool:
            printed_count[0] += 1
            return printed_count[0] >= 2

        exit_code = cli_streaming.run_streaming_command(
            args=SimpleNamespace(times=2),
            command_name="watch",
            start_error="Failed",
            command_builder=lambda _args, _sid: {"type": "test", "action": "start"},
            response_id_key=stream_id_key,
            stop_command_builder=lambda sid: {
                "type": "test",
                "action": "stop",
                stream_id_key: sid,
            },
            emit_started=lambda _args, _resp, _sid: None,
            limit_reached=lambda _args, obs: _limit(obs),
            check_agent_attached=lambda: (str(tmp_path / "s.sock"), 1234),
            client_factory=lambda _sock: client,
            ephemeral_client_factory=lambda _tid: nullcontext("ephem-1"),
            target_id_resolver=lambda _sock: "target_1",
            stream_id_key=stream_id_key,
        )

        assert exit_code == 0
        lines = [line for line in capsys.readouterr().out.strip().splitlines() if line]
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert parsed.get("type") != "log"
            assert parsed.get(stream_id_key) == stream_id

        stop_cmds = [c for c in client.commands_received if c.get("action") == "stop"]
        assert stop_cmds == [{"type": "test", "action": "stop", stream_id_key: stream_id}]
        assert client.disconnected is True

    @pytest.mark.parametrize(
        "cmd_type,obs_argv,extra_obs",
        [
            (
                "trace",
                ["trace", "mod.work", "-n", "2", "--min-duration", "1.5"],
                lambda wid: {
                    "watch_id": wid,
                    "func_name": "mod.work",
                    "total_duration_ms": 5.2,
                    "self_time_ms": 1.2,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [{"function": "mod.helper", "total_ms": 4.0}],
                },
            ),
            (
                "stack",
                ["stack", "mod.work", "-n", "2", "--depth", "4"],
                lambda wid: {
                    "watch_id": wid,
                    "location": "AtEnter",
                    "func_name": "mod.work",
                    "stack": [
                        {
                            "filename": "app.py",
                            "lineno": 12,
                            "function": "work",
                            "code_context": "return 1",
                        }
                    ],
                },
            ),
        ],
    )
    def test_cmd_run_reuses_streaming_config_times_minus_one_and_filters_stream(
        self, tmp_path: Path, capsys, monkeypatch, cmd_type: str, obs_argv: List[str], extra_obs
    ) -> None:
        script = tmp_path / "target.py"
        script.write_text("print('hi')\n")

        prepared = cli_run._prepare_run_command(cmd_type, obs_argv)
        assert prepared is not None
        cfg, start_cmd, limit_args = prepared
        # Agent receives unlimited times=-1 so CLI filters logs/foreign probes locally first.
        assert start_cmd["times"] == -1
        assert limit_args.times == 2

        observations = [
            {"type": "log", "level": "INFO", "message": "startup log"},
            {"watch_id": "foreign_probe", "func_name": "other.fn"},
            extra_obs("probe_run_1"),
            {"watch_id": "foreign_probe", "func_name": "other.fn"},
            extra_obs("probe_run_1"),
            extra_obs("probe_run_1"),
        ]
        fake_client = _FakeStreamClient(
            start_response={"status": "success", "watch_id": "probe_run_1"},
            observations=observations,
        )

        class _FakeProc:
            pid = 4242

            def poll(self):
                return 0

            def wait(self, timeout=None):
                return 0

            def terminate(self):
                pass

            def kill(self):
                pass

        class _FakeAttacher:
            def __init__(self, pid: int, **kwargs: Any) -> None:
                self.pid = pid

            def attach(self) -> bool:
                return True

            def get_socket_path(self) -> str:
                return str(tmp_path / "run.sock")

            def cleanup(self) -> None:
                pass

        real_exists = cli_run.os.path.exists
        monkeypatch.setattr(cli_run.uuid, "uuid4", lambda: "test-run-sid")
        monkeypatch.setattr(
            cli_run.os.path,
            "exists",
            lambda p: True if str(p).endswith(".import-ready") else real_exists(p),
        )
        monkeypatch.setattr(cli_run.subprocess, "Popen", lambda *a, **kw: _FakeProc())
        monkeypatch.setattr(cli_run, "ProcessAttacher", _FakeAttacher)
        monkeypatch.setattr(cli_run, "StreamingAgentClient", lambda *a, **kw: fake_client)
        monkeypatch.setattr(cli_run.os, "kill", lambda pid, sig: None)
        monkeypatch.setattr(cli_run.os, "waitpid", lambda pid, opts: (0, 0) if opts == os.WNOHANG else (pid, 0))
        monkeypatch.setattr(
            sys,
            "argv",
            ["peeka-cli", "run", str(script), "--", *obs_argv],
        )

        args = argparse.Namespace(script_path=str(script), remaining=None)
        exit_code = cli_run.cmd_run(args)
        assert exit_code == 0

        printed = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines() if line]
        assert len(printed) == 2
        assert all(obs["watch_id"] == "probe_run_1" for obs in printed)

        start_cmds = [c for c in fake_client.commands_received if c.get("action") == "start"]
        stop_cmds = [c for c in fake_client.commands_received if c.get("action") == "stop"]
        assert start_cmds[0]["times"] == -1
        assert stop_cmds == [{"type": cmd_type, "action": "stop", "watch_id": "probe_run_1"}]


def _encode_wire_frame(payload: Dict[str, Any], prefix: bytes = b"") -> bytes:
    """Encode a JSON message in the Peeka agent wire protocol."""
    body = json.dumps(payload).encode("utf-8")
    return prefix + len(body).to_bytes(4, "big") + body


class _RealProtocolRunServer:
    """In-process AF_UNIX agent server implementing the Peeka wire protocol."""

    def __init__(
        self,
        sock_path: str,
        watch_id: str,
        stream_chunks: List[bytes],
        close_after_frames: bool = True,
        on_frames_sent: Optional[Callable[[], None]] = None,
        on_stop_received: Optional[Callable[[], None]] = None,
    ) -> None:
        self.sock_path = sock_path
        self.watch_id = watch_id
        self.stream_chunks = stream_chunks
        self.close_after_frames = close_after_frames
        self.on_frames_sent = on_frames_sent
        self.on_stop_received = on_stop_received
        self.stop_commands: List[Dict[str, Any]] = []
        self.stop_event = threading.Event()
        self._listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._listener.bind(sock_path)
        self._listener.listen(8)
        self._listener.settimeout(0.05)
        self._conns: List[socket.socket] = []
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self) -> None:
        self.stop_event.set()
        try:
            self._listener.close()
        except OSError:
            pass
        with self._lock:
            conns = list(self._conns)
        for conn in conns:
            try:
                conn.close()
            except OSError:
                pass
        self._thread.join(timeout=2.0)

    def _serve(self) -> None:
        while not self.stop_event.is_set():
            try:
                conn, _ = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                self._conns.append(conn)
            threading.Thread(
                target=self._handle_conn, args=(conn,), daemon=True
            ).start()

    @staticmethod
    def _recv_exact(conn: socket.socket, size: int) -> bytes:
        buf = bytearray()
        while len(buf) < size:
            chunk = conn.recv(size - len(buf))
            if not chunk:
                return b""
            buf.extend(chunk)
        return bytes(buf)

    def _handle_conn(self, conn: socket.socket) -> None:
        try:
            len_bytes = self._recv_exact(conn, 4)
            if not len_bytes:
                return
            req_len = int.from_bytes(len_bytes, "big")
            raw_req = self._recv_exact(conn, req_len)
            if not raw_req:
                return
            cmd = json.loads(raw_req.decode("utf-8"))
            action = cmd.get("action")

            if action == "start":
                conn.sendall(
                    _encode_wire_frame(
                        {"status": "success", "watch_id": self.watch_id}
                    )
                )
                for chunk in self.stream_chunks:
                    conn.sendall(chunk)
                if self.close_after_frames:
                    conn.shutdown(socket.SHUT_WR)
                    conn.close()
                if self.on_frames_sent is not None:
                    self.on_frames_sent()
                if not self.close_after_frames:
                    self.stop_event.wait(timeout=5.0)
            elif action == "stop":
                with self._lock:
                    self.stop_commands.append(cmd)
                conn.sendall(_encode_wire_frame({"status": "success"}))
                if self.on_stop_received is not None:
                    self.on_stop_received()
                conn.close()
            else:
                conn.sendall(_encode_wire_frame({"status": "success"}))
                conn.close()
        except OSError:
            pass


class TestCmdRunStreamLifecycleRegressions:
    """Regression tests for cmd_run buffered frames, waitpid, exit codes, and EOF/no-EOF."""

    @staticmethod
    def _run_with_real_protocol(
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
        obs_argv: List[str],
        stream_chunks: List[bytes],
        *,
        close_after_frames: bool,
        child_exit_event: threading.Event,
        child_status: int,
        release_exit_on_frames: bool = False,
        release_exit_on_stop: bool = False,
    ) -> Tuple[int, List[Dict[str, Any]], List[Tuple[int, int]]]:
        script = tmp_path / "target.py"
        script.write_text("def work():\n    return 1\n")

        waitpid_calls: List[Tuple[int, int]] = []
        reap_count = [0]
        wait_lock = threading.Lock()
        child_pid = 4242

        def _fake_waitpid(pid: int, options: int) -> Tuple[int, int]:
            with wait_lock:
                waitpid_calls.append((pid, options))
                assert reap_count[0] == 0, (
                    f"Duplicate os.waitpid({pid}, {options}) after child already reaped: {waitpid_calls}"
                )
            if options == os.WNOHANG:
                if not child_exit_event.is_set():
                    return (0, 0)
            else:
                assert child_exit_event.wait(timeout=3.0), "Timed out waiting for child exit event"
            with wait_lock:
                assert reap_count[0] == 0, (
                    f"Duplicate os.waitpid({pid}, {options}) after child already reaped: {waitpid_calls}"
                )
                reap_count[0] += 1
                return (pid, child_status)

        with tempfile.TemporaryDirectory(dir="/tmp") as sock_dir:
            sock_path = os.path.join(sock_dir, "peeka_testrun.sock")
            server = _RealProtocolRunServer(
                sock_path=sock_path,
                watch_id="probe_run_1",
                stream_chunks=stream_chunks,
                close_after_frames=close_after_frames,
                on_frames_sent=(
                    child_exit_event.set if release_exit_on_frames else None
                ),
                on_stop_received=(
                    child_exit_event.set if release_exit_on_stop else None
                ),
            )
            server.start()

            class _FakeProc:
                pid = child_pid

                def poll(self) -> Optional[int]:
                    return os.WEXITSTATUS(child_status) if child_exit_event.is_set() else None

            class _FakeAttacher:
                def __init__(self, pid: int, **kwargs: Any) -> None:
                    self.pid = pid

                def attach(self) -> bool:
                    return True

                def get_socket_path(self) -> str:
                    return sock_path

                def cleanup(self) -> None:
                    pass

            real_exists = cli_run.os.path.exists
            monkeypatch.setattr(cli_run.uuid, "uuid4", lambda: "test-run-proto")
            monkeypatch.setattr(
                cli_run.os.path,
                "exists",
                lambda p: True if str(p).endswith(".import-ready") else real_exists(p),
            )
            monkeypatch.setattr(cli_run.subprocess, "Popen", lambda *a, **kw: _FakeProc())
            monkeypatch.setattr(cli_run, "ProcessAttacher", _FakeAttacher)
            monkeypatch.setattr(cli_run.os, "kill", lambda pid, sig: None)
            monkeypatch.setattr(cli_run.os, "waitpid", _fake_waitpid)
            monkeypatch.setattr(
                sys,
                "argv",
                ["peeka-cli", "run", str(script), "--", *obs_argv],
            )

            try:
                args = argparse.Namespace(script_path=str(script), remaining=None)
                exit_code = cli_run.cmd_run(args)
            finally:
                server.close()

        assert reap_count[0] == 1, f"Expected exactly 1 reap, got {reap_count[0]}: {waitpid_calls}"
        return exit_code, server.stop_commands, waitpid_calls

    @pytest.mark.parametrize("cmd_type", ["trace", "stack"])
    @pytest.mark.parametrize("close_after_frames", [True, False], ids=["eof", "no-eof"])
    def test_buffered_observations_not_dropped_when_child_exits_after_first_log(
        self,
        tmp_path: Path,
        capsys,
        monkeypatch: pytest.MonkeyPatch,
        cmd_type: str,
        close_after_frames: bool,
    ) -> None:
        """2bbee72 regression: WNOHANG exit after first LOG frame must still emit buffered OBS frames."""
        log_frame = _encode_wire_frame(
            {"type": "log", "level": "INFO", "message": "[peeka Agent] started"},
            prefix=b"LOG:",
        )
        obs1 = _encode_wire_frame(
            {"watch_id": "probe_run_1", "seq": 1, "func_name": "mod.work"},
            prefix=b"OBS:",
        )
        obs2 = _encode_wire_frame(
            {"watch_id": "probe_run_1", "seq": 2, "func_name": "mod.work"},
            prefix=b"OBS:",
        )

        # Child reports exited immediately once frames are sent, while LOG + 2 OBS are buffered.
        child_exit_event = threading.Event()
        exit_code, _, _ = self._run_with_real_protocol(
            monkeypatch,
            tmp_path,
            [cmd_type, "mod.work"],
            [log_frame + obs1 + obs2],
            close_after_frames=close_after_frames,
            child_exit_event=child_exit_event,
            child_status=(7 << 8),
            release_exit_on_frames=True,
        )

        printed = [
            json.loads(line)
            for line in capsys.readouterr().out.strip().splitlines()
            if line
        ]
        assert [obs["seq"] for obs in printed] == [1, 2]
        assert exit_code == 7

    @pytest.mark.parametrize(
        "child_status,expected_exit_code",
        [
            (42 << 8, 42),
            (signal.SIGTERM, 128 + signal.SIGTERM),
        ],
        ids=["nonzero-exit", "signaled-exit"],
    )
    def test_normal_eof_reaps_once_and_preserves_exit_code(
        self,
        tmp_path: Path,
        capsys,
        monkeypatch: pytest.MonkeyPatch,
        child_status: int,
        expected_exit_code: int,
    ) -> None:
        """Normal EOF drains observations, reaps once, and preserves original exit/signal code."""
        obs1 = _encode_wire_frame(
            {"watch_id": "probe_run_1", "seq": 1, "func_name": "mod.work"},
            prefix=b"OBS:",
        )
        obs2 = _encode_wire_frame(
            {"watch_id": "probe_run_1", "seq": 2, "func_name": "mod.work"},
            prefix=b"OBS:",
        )

        child_exit_event = threading.Event()
        # Child finishes shortly after stream EOF (blocking waitpid observes exit).
        timer = threading.Timer(0.05, child_exit_event.set)
        timer.daemon = True
        timer.start()
        try:
            exit_code, _, waitpid_calls = self._run_with_real_protocol(
                monkeypatch,
                tmp_path,
                ["trace", "mod.work"],
                [obs1, obs2],
                close_after_frames=True,
                child_exit_event=child_exit_event,
                child_status=child_status,
            )
        finally:
            timer.cancel()

        printed = [
            json.loads(line)
            for line in capsys.readouterr().out.strip().splitlines()
            if line
        ]
        assert [obs["seq"] for obs in printed] == [1, 2]
        assert exit_code == expected_exit_code
        assert waitpid_calls[-1] == (4242, 0)

    @pytest.mark.parametrize("close_after_frames", [True, False], ids=["eof", "no-eof"])
    def test_zero_frames_exits_without_hang_and_preserves_exit_code(
        self,
        tmp_path: Path,
        capsys,
        monkeypatch: pytest.MonkeyPatch,
        close_after_frames: bool,
    ) -> None:
        """Zero matching frames exits cleanly on EOF or child exit without overwriting exit code."""
        noise_log = _encode_wire_frame(
            {"type": "log", "level": "INFO", "message": "startup"},
            prefix=b"LOG:",
        )
        foreign_obs = _encode_wire_frame(
            {"watch_id": "foreign_probe", "seq": 99},
            prefix=b"OBS:",
        )

        child_exit_event = threading.Event()
        timer = threading.Timer(0.05, child_exit_event.set)
        timer.daemon = True
        timer.start()
        try:
            exit_code, _, _ = self._run_with_real_protocol(
                monkeypatch,
                tmp_path,
                ["stack", "mod.work"],
                [noise_log, foreign_obs],
                close_after_frames=close_after_frames,
                child_exit_event=child_exit_event,
                child_status=(5 << 8),
            )
        finally:
            timer.cancel()

        assert capsys.readouterr().out.strip() == ""
        assert exit_code == 5

    @pytest.mark.parametrize("cmd_type", ["trace", "stack"])
    def test_limit_hit_sends_stop_and_preserves_original_exit_code(
        self,
        tmp_path: Path,
        capsys,
        monkeypatch: pytest.MonkeyPatch,
        cmd_type: str,
    ) -> None:
        """Hitting -n stops after N matching frames, sends stop RPC, and keeps child exit code."""
        frames = (
            _encode_wire_frame({"type": "log", "message": "boot"}, prefix=b"LOG:")
            + _encode_wire_frame({"watch_id": "other", "seq": 0}, prefix=b"OBS:")
            + _encode_wire_frame({"watch_id": "probe_run_1", "seq": 1}, prefix=b"OBS:")
            + _encode_wire_frame({"watch_id": "probe_run_1", "seq": 2}, prefix=b"OBS:")
            + _encode_wire_frame({"watch_id": "probe_run_1", "seq": 3}, prefix=b"OBS:")
        )

        child_exit_event = threading.Event()
        exit_code, stop_commands, _ = self._run_with_real_protocol(
            monkeypatch,
            tmp_path,
            [cmd_type, "mod.work", "-n", "2"],
            [frames],
            close_after_frames=False,
            child_exit_event=child_exit_event,
            child_status=(3 << 8),
            release_exit_on_stop=True,
        )

        printed = [
            json.loads(line)
            for line in capsys.readouterr().out.strip().splitlines()
            if line
        ]
        assert [obs["seq"] for obs in printed] == [1, 2]
        assert len(stop_commands) == 1
        assert stop_commands[0]["type"] == cmd_type
        assert stop_commands[0]["action"] == "stop"
        assert stop_commands[0]["watch_id"] == "probe_run_1"
        assert exit_code == 3
