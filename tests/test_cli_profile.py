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
    calls = []

    class MockClient:
        def send_command(self, command):
            calls.append(command)
            assert command["type"] == "profile"
            assert command["action"] == "start"
            assert command["backend"] == "sampling"
            assert command["interval_ms"] == 25
            assert command["duration_ms"] == 1500
            assert command["max_samples"] == 42
            return {"status": "success", "profile_id": "profile_123"}

    args = argparse.Namespace(
        profile_subcommand="start",
        backend="sampling",
        interval=0.025,
        duration=1.5,
        max_samples=42,
    )

    exit_code = handle_profile(args, MockClient())
    captured = capsys.readouterr()

    assert exit_code == 0
    assert calls == [{"type": "profile", "action": "start", "backend": "sampling", "interval_ms": 25, "duration_ms": 1500, "max_samples": 42}]
    obj = json.loads(captured.out.strip())
    assert obj["type"] == "result"
    assert obj["command"] == "profile.start"
    assert obj["data"]["profile_id"] == "profile_123"


def test_handle_profile_snapshot_and_export_dispatch(capsys, tmp_path) -> None:
    commands = []

    class MockClient:
        def execute(self, namespace, payload):
            commands.append((namespace, payload))
            if payload["action"] == "snapshot":
                return {"status": "success", "profile_id": payload["profile_id"], "snapshot": {"ok": True}}
            return {"status": "success", "content": "exported-profile", "format": payload["format"]}

    snapshot_args = argparse.Namespace(
        profile_subcommand="snapshot",
        profile_id="profile_1",
        format="speedscope",
    )
    assert handle_profile(snapshot_args, MockClient()) == 0
    snapshot_out = json.loads(capsys.readouterr().out.strip())
    assert snapshot_out["command"] == "profile.snapshot"
    assert snapshot_out["data"]["snapshot"]["ok"] is True

    export_path = tmp_path / "profile.json"
    export_args = argparse.Namespace(
        profile_subcommand="export",
        profile_id="profile_2",
        format="json",
        output=str(export_path),
    )
    assert handle_profile(export_args, MockClient()) == 0
    export_out = json.loads(capsys.readouterr().out.strip())
    assert export_out["command"] == "profile.export"
    assert export_out["data"]["output"] == str(export_path)
    assert export_path.read_text(encoding="utf-8") == "exported-profile"
    assert commands[0][0] == "profile"
    assert commands[0][1]["action"] == "snapshot"
    assert commands[1][1]["action"] == "export"
