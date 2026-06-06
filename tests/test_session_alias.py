import argparse
import json
from typing import Any
from typing import Dict

from peeka.cli.handlers import targets as cli_targets


class TestSessionAlias:
    def test_session_list_emits_deprecation_and_matches_target_list(
        self, monkeypatch, capsys
    ):
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

        monkeypatch.setattr(
            cli_targets,
            "discover_targets",
            lambda: [MockTarget(t) for t in targets_data],
        )

        args = argparse.Namespace(
            command="session",
            session_action="list",
            format="json",
        )

        result = cli_targets.cmd_session_list(args)

        captured = capsys.readouterr()

        assert result == 0
        assert "[deprecated]" in captured.err
        assert "'peeka-cli session <X>' is deprecated" in captured.err
        assert "use 'peeka-cli target <X>'" in captured.err

        lines = [
            line.strip() for line in captured.out.strip().split("\n") if line.strip()
        ]
        assert len(lines) == 1

        parsed = json.loads(lines[0])
        assert parsed["type"] == "event"
        assert parsed["event"] == "target.discovered"
        assert "data" in parsed
        assert parsed["data"]["schema_version"] == "1"
        assert parsed["data"]["target_id"] == "target_12345678"
        assert parsed["data"]["state"] == "alive"

    def test_session_status_delegates_to_target_status(self, monkeypatch, capsys):
        target_data = {
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

        monkeypatch.setattr(
            cli_targets,
            "get_target",
            lambda target_id: MockTarget(target_data),
        )

        args = argparse.Namespace(
            command="session",
            session_action="status",
            target="target_87654321",
            format="json",
        )

        result = cli_targets.cmd_session_status(args)

        captured = capsys.readouterr()

        assert result == 0
        assert "[deprecated]" in captured.err
        assert "'peeka-cli session <X>' is deprecated" in captured.err

        parsed = json.loads(captured.out.strip())
        assert parsed["type"] == "success"
        assert parsed["command"] == "target.status"
        assert "data" in parsed
        assert parsed["data"]["schema_version"] == "1"
        assert parsed["data"]["target_id"] == "target_87654321"
        assert parsed["data"]["state"] == "alive"

    def test_session_detach_delegates_to_target_detach(self, monkeypatch, capsys):
        detach_result = {
            "ok": True,
            "target_id": "target_11111111",
            "message": "Successfully detached",
            "errors": [],
        }

        monkeypatch.setattr(
            cli_targets,
            "detach_target",
            lambda target_id, force: detach_result,
        )

        args = argparse.Namespace(
            command="session",
            session_action="detach",
            target="target_11111111",
            force=False,
            format="json",
        )

        result = cli_targets.cmd_session_detach(args)

        captured = capsys.readouterr()

        assert result == 0
        assert "[deprecated]" in captured.err
        assert "'peeka-cli session <X>' is deprecated" in captured.err

        parsed = json.loads(captured.out.strip())
        assert parsed["type"] == "success"
        assert parsed["command"] == "target.detach"
        assert "data" in parsed
        assert parsed["data"]["ok"] is True
        assert parsed["data"]["target_id"] == "target_11111111"
