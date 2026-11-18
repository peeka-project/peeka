# pyright: reportPrivateUsage=false, reportDeprecated=false

"""Regression tests for CLI target ambiguity, permission preservation, stream filtering, and run command."""

import argparse
import errno
import json
import os
import sys
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

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
