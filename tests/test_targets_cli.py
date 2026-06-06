import argparse
import json
import subprocess
import sys
from typing import Any
from typing import Dict

from peeka.cli.handlers import targets as cli_targets


class TestTargetCLIList:
    def test_target_list_json_jsonl(self, monkeypatch, capsys):
        targets_data = [
            {
                "target_id": "target_12345678",
                "legacy_session_id": "12345678-1234-1234-1234-123456789012",
                "pid": 1234,
                "socket_path": "/tmp/peeka_12345678-1234-1234-1234-123456789012.sock",
                "state": "alive",
                "agent_mode": "injected",
                "injection_mode": "pep768",
                "python_version": "3.14.0",
                "peeka_version": "0.1.15",
                "capabilities": {},
                "runtime": {},
                "created_at": 1234567890.0,
                "last_seen_at": 1234567890.0,
                "recent_errors": [],
                "next_valid_actions": ["detach"],
            },
            {
                "target_id": "target_87654321",
                "legacy_session_id": "87654321-4321-4321-4321-210987654321",
                "pid": 5678,
                "socket_path": "/tmp/peeka_87654321-4321-4321-4321-210987654321.sock",
                "state": "stale",
                "agent_mode": "injected",
                "injection_mode": "gdb_dlopen",
                "python_version": "3.12.0",
                "peeka_version": "0.1.15",
                "capabilities": {},
                "runtime": {},
                "created_at": 1234567800.0,
                "last_seen_at": 1234567800.0,
                "recent_errors": [],
                "next_valid_actions": ["cleanup", "detach"],
            },
        ]

        def mock_to_dict(self):
            result = {"schema_version": "1"}
            for key in [
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
            ]:
                result[key] = getattr(self, key)
            return result

        class MockTarget:
            def __init__(self, data: Dict[str, Any]):
                for key, value in data.items():
                    setattr(self, key, value)

            to_dict = mock_to_dict

        mock_targets = [MockTarget(data) for data in targets_data]

        monkeypatch.setattr(cli_targets, "discover_targets", lambda: mock_targets)

        args = argparse.Namespace(command="target", target_action="list", format="json")

        exit_code = cli_targets.cmd_target(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        lines = captured.out.strip().split("\n")
        assert len(lines) == 2

        for line in lines:
            obj = json.loads(line)
            assert obj["type"] == "event"
            assert obj["event"] == "target.discovered"
            assert "data" in obj
            assert obj["data"]["schema_version"] == "1"
            assert "target_id" in obj["data"]
            assert "state" in obj["data"]


class TestTargetCLICurrent:
    def test_current_zero_alive_exits_1(self, monkeypatch, capsys):
        monkeypatch.setattr(cli_targets, "discover_targets", lambda: [])

        args = argparse.Namespace(
            command="target", target_action="current", format="json"
        )

        exit_code = cli_targets.cmd_target(args)
        captured = capsys.readouterr()

        assert exit_code == 1
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "error"
        assert obj["command"] == "target.current"
        assert obj["error_code"] == "TARGET_NOT_FOUND"

    def test_current_one_alive_exits_0(self, monkeypatch, capsys):
        target_data = {
            "target_id": "target_12345678",
            "legacy_session_id": "12345678-1234-1234-1234-123456789012",
            "pid": 1234,
            "socket_path": "/tmp/peeka_12345678-1234-1234-1234-123456789012.sock",
            "state": "alive",
            "agent_mode": "injected",
            "injection_mode": "pep768",
            "python_version": "3.14.0",
            "peeka_version": "0.1.15",
            "capabilities": {},
            "runtime": {},
            "created_at": 1234567890.0,
            "last_seen_at": 1234567890.0,
            "recent_errors": [],
            "next_valid_actions": ["detach"],
        }

        def mock_to_dict(self):
            result = {"schema_version": "1"}
            for key in [
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
            ]:
                result[key] = getattr(self, key)
            return result

        class MockTarget:
            def __init__(self, data: Dict[str, Any]):
                for key, value in data.items():
                    setattr(self, key, value)

            to_dict = mock_to_dict

        mock_target = MockTarget(target_data)

        monkeypatch.setattr(cli_targets, "discover_targets", lambda: [mock_target])

        args = argparse.Namespace(
            command="target", target_action="current", format="json"
        )

        exit_code = cli_targets.cmd_target(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "success"
        assert obj["command"] == "target.current"
        assert obj["data"]["target_id"] == "target_12345678"

    def test_current_ambiguous_exits_2(self, monkeypatch, capsys):
        targets_data = [
            {
                "target_id": "target_12345678",
                "legacy_session_id": "12345678-1234-1234-1234-123456789012",
                "pid": 1234,
                "socket_path": "/tmp/peeka_12345678-1234-1234-1234-123456789012.sock",
                "state": "alive",
                "agent_mode": "injected",
                "injection_mode": "pep768",
                "python_version": "3.14.0",
                "peeka_version": "0.1.15",
                "capabilities": {},
                "runtime": {},
                "created_at": 1234567890.0,
                "last_seen_at": 1234567890.0,
                "recent_errors": [],
                "next_valid_actions": ["detach"],
            },
            {
                "target_id": "target_87654321",
                "legacy_session_id": "87654321-4321-4321-4321-210987654321",
                "pid": 5678,
                "socket_path": "/tmp/peeka_87654321-4321-4321-4321-210987654321.sock",
                "state": "alive",
                "agent_mode": "injected",
                "injection_mode": "gdb_dlopen",
                "python_version": "3.12.0",
                "peeka_version": "0.1.15",
                "capabilities": {},
                "runtime": {},
                "created_at": 1234567800.0,
                "last_seen_at": 1234567800.0,
                "recent_errors": [],
                "next_valid_actions": ["detach"],
            },
        ]

        def mock_to_dict(self):
            result = {"schema_version": "1"}
            for key in [
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
            ]:
                result[key] = getattr(self, key)
            return result

        class MockTarget:
            def __init__(self, data: Dict[str, Any]):
                for key, value in data.items():
                    setattr(self, key, value)

            to_dict = mock_to_dict

        mock_targets = [MockTarget(data) for data in targets_data]

        monkeypatch.setattr(cli_targets, "discover_targets", lambda: mock_targets)

        args = argparse.Namespace(
            command="target", target_action="current", format="json"
        )

        exit_code = cli_targets.cmd_target(args)
        captured = capsys.readouterr()

        assert exit_code == 2
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "error"
        assert obj["command"] == "target.current"
        assert obj["error_code"] == "TARGET_AMBIGUOUS"
        assert "targets" in obj


class TestTargetCLIDetach:
    def test_detach_alive_without_force_exits_2(self, monkeypatch, capsys):
        def mock_detach_target(target_id: str, force: bool = False) -> Dict[str, Any]:
            if not force:
                return {
                    "ok": False,
                    "error_code": "UNSUPPORTED_CAPABILITY",
                    "message": "force required for alive detach",
                }
            return {"ok": True, "target_id": target_id}

        monkeypatch.setattr(cli_targets, "detach_target", mock_detach_target)

        args = argparse.Namespace(
            command="target",
            target_action="detach",
            target="target_12345678",
            force=False,
            format="json",
        )

        exit_code = cli_targets.cmd_target(args)
        captured = capsys.readouterr()

        assert exit_code == 2
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "error"
        assert obj["command"] == "target.detach"
        assert obj["error_code"] == "UNSUPPORTED_CAPABILITY"


class TestTargetCLICleanup:
    def test_cleanup_dry_run_no_unlink(self, monkeypatch, capsys):
        def mock_cleanup_stale_targets(
            dry_run: bool = False, target_id: str = None
        ) -> Dict[str, Any]:
            if dry_run:
                return {"removed": ["target_12345678"], "skipped": [], "errors": []}
            return {"removed": [], "skipped": [], "errors": []}

        monkeypatch.setattr(
            cli_targets, "cleanup_stale_targets", mock_cleanup_stale_targets
        )

        args = argparse.Namespace(
            command="target",
            target_action="cleanup",
            target=None,
            stale_only=True,
            dry_run=True,
            format="json",
        )

        exit_code = cli_targets.cmd_target(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "success"
        assert obj["command"] == "target.cleanup"
        assert obj["data"]["removed"] == ["target_12345678"]

    def test_cleanup_target_flag(self, monkeypatch, capsys):
        def mock_cleanup_stale_targets(
            dry_run: bool = False, target_id: str = None
        ) -> Dict[str, Any]:
            if target_id == "target_12345678":
                return {"removed": ["target_12345678"], "skipped": [], "errors": []}
            return {"removed": [], "skipped": [], "errors": []}

        monkeypatch.setattr(
            cli_targets, "cleanup_stale_targets", mock_cleanup_stale_targets
        )

        args = argparse.Namespace(
            command="target",
            target_action="cleanup",
            target="target_12345678",
            stale_only=True,
            dry_run=False,
            format="json",
        )

        exit_code = cli_targets.cmd_target(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "success"
        assert obj["command"] == "target.cleanup"
        assert obj["data"]["removed"] == ["target_12345678"]


class TestTargetCLIHelp:
    def test_target_help_lists_6_subcommands(self):
        result = subprocess.run(
            [sys.executable, "-m", "peeka.cli.main", "target", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        help_text = result.stdout

        subcommands = ["list", "current", "status", "inspect", "cleanup", "detach"]
        for subcommand in subcommands:
            assert subcommand in help_text
