"""Tests for peeka-cli profile command parsing and dispatch."""

import argparse
import json

from peeka.cli.handlers.profile import handle_profile
from peeka.cli.parser import build_parser
from peeka.cli.parsers.profile import add_profile_parser


def test_profile_parser_registers_subcommands() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    add_profile_parser(subparsers)

    profile_parser = subparsers.choices["profile"]
    help_text = profile_parser.format_help().lower()

    for subcommand in ("start", "stop", "snapshot", "list", "cleanup", "export"):
        assert subcommand in help_text


def test_profile_start_parser_defaults() -> None:
    parser = build_parser()
    args = parser.parse_args(["profile", "start"])

    assert args.command == "profile"
    assert args.profile_subcommand == "start"
    assert args.backend == "sampling"
    assert args.interval == 0.01
    assert args.duration is None
    assert args.max_samples is None


def test_handle_profile_start_dispatches_command_and_converts_units(capsys) -> None:
    args = build_parser().parse_args(
        ["profile", "start", "--interval", "0.025", "--duration", "1.5", "--max-samples", "42"]
    )
    calls = []

    class MockClient:
        def connect(self):
            return {"status": "success"}

        def send_command(self, command):
            calls.append(command)
            assert command["type"] == "profile"
            assert command["action"] == "start"
            assert command["backend"] == "sampling"
            assert command["interval_ms"] == 25
            assert command["duration_ms"] == 1500
            assert command["max_samples"] == 42
            return {"status": "success", "profile_id": "profile_123"}

        def disconnect(self):
            pass

    args.target = None
    exit_code = _run_profile_with_client(args, MockClient())
    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == [{"type": "profile", "action": "start", "backend": "sampling", "interval_ms": 25, "duration_ms": 1500, "max_samples": 42}]
    obj = json.loads(captured.out.strip())
    assert obj["type"] == "result"
    assert obj["command"] == "profile.start"
    assert obj["data"]["profile_id"] == "profile_123"


def test_handle_profile_matches_main_single_arg_dispatch(monkeypatch, capsys) -> None:
    from peeka.cli import connection as cli_connection
    from peeka.cli import sessions as cli_sessions

    calls = []

    class MockStreamingAgentClient:
        def __init__(self, socket_path):
            self.socket_path = socket_path

        def connect(self):
            return {"status": "success"}

        def send_command(self, command):
            calls.append(command)
            return {"status": "success", "sessions": []}

        def disconnect(self):
            pass

    monkeypatch.setattr(cli_connection, "StreamingAgentClient", MockStreamingAgentClient)
    monkeypatch.setattr(
        cli_sessions, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234)
    )
    args = build_parser().parse_args(["profile", "list"])

    exit_code = args.handler(args)
    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == [{"type": "profile", "action": "list"}]
    assert json.loads(captured.out.strip())["command"] == "profile.list"


def test_handle_profile_snapshot_and_export_dispatch(capsys, tmp_path) -> None:
    commands = []

    class MockClient:
        def connect(self):
            return {"status": "success"}

        def send_command(self, command):
            commands.append(command)
            if command["action"] == "snapshot":
                return {"status": "success", "profile_id": command["profile_id"], "snapshot": {"ok": True}}
            return {"status": "success", "content": "exported-profile", "format": command["format"]}

        def disconnect(self):
            pass

    snapshot_args = build_parser().parse_args(
        ["profile", "snapshot", "--profile-id", "profile_1", "--format", "speedscope"]
    )
    snapshot_args.target = None
    assert _run_profile_with_client(snapshot_args, MockClient()) == 0
    snapshot_out = json.loads(capsys.readouterr().out.strip())
    assert snapshot_out["command"] == "profile.snapshot"
    assert snapshot_out["data"]["snapshot"]["ok"] is True

    export_path = tmp_path / "profile.json"
    export_args = build_parser().parse_args(
        [
            "profile",
            "export",
            "--profile-id",
            "profile_2",
            "--format",
            "json",
            "--output",
            str(export_path),
        ]
    )
    export_args.target = None
    assert _run_profile_with_client(export_args, MockClient()) == 0
    export_out = json.loads(capsys.readouterr().out.strip())
    assert export_out["command"] == "profile.export"
    assert export_out["data"]["output"] == str(export_path)
    assert export_path.read_text(encoding="utf-8") == "exported-profile"
    assert commands[0]["type"] == "profile"
    assert commands[0]["action"] == "snapshot"
    assert commands[1]["action"] == "export"


def _run_profile_with_client(args, client) -> int:
    from peeka.cli import connection as cli_connection
    from peeka.cli import sessions as cli_sessions

    original_client = cli_connection.StreamingAgentClient
    original_check = cli_sessions._check_agent_attached
    cli_connection.StreamingAgentClient = lambda socket_path: client
    cli_sessions._check_agent_attached = lambda: ("/tmp/peeka_test.sock", 1234)
    try:
        return handle_profile(args)
    finally:
        cli_connection.StreamingAgentClient = original_client
        cli_sessions._check_agent_attached = original_check
