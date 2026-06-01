import argparse
import json
import sys
from typing import Any
from typing import Dict

import peeka.cli.main  # noqa: F401


class TestClientCLICreate:
    def test_client_create_emits_json_envelope(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "client"
                assert command["action"] == "create"
                assert command["target_id"] == "target_12345678"
                assert command["source"] == "cli"
                assert command.get("user_id") == "alice"
                return {
                    "ok": True,
                    "data": {
                        "client_session_id": "client_abcd1234",
                        "target_id": "target_12345678",
                        "source": "cli",
                        "user_id": "alice",
                        "input_status": "idle",
                        "foreground_job_id": None,
                        "created_at": 1234567890.0,
                        "last_access_at": 1234567890.0,
                        "schema_version": "1",
                    },
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(
            cli_main_module, "StreamingAgentClient", MockStreamingAgentClient
        )
        monkeypatch.setattr(
            cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234)
        )

        args = argparse.Namespace(
            command="client",
            client_action="create",
            target="target_12345678",
            source="cli",
            user="alice",
            format="json",
        )

        exit_code = cli_main_module.cmd_client(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "success"
        assert obj["command"] == "client.create"
        assert obj["data"]["client_session_id"] == "client_abcd1234"
        assert obj["data"]["target_id"] == "target_12345678"
        assert obj["data"]["source"] == "cli"


class TestClientCLIList:
    def test_client_list_filter_by_target(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "client"
                assert command["action"] == "list"
                assert command["target_id"] == "target_12345678"
                return {
                    "ok": True,
                    "data": {
                        "clients": [
                            {
                                "client_session_id": "client_aaaa1111",
                                "target_id": "target_12345678",
                                "source": "cli",
                                "user_id": "alice",
                                "input_status": "idle",
                                "foreground_job_id": None,
                                "created_at": 1234567890.0,
                                "last_access_at": 1234567890.0,
                                "schema_version": "1",
                            },
                            {
                                "client_session_id": "client_bbbb2222",
                                "target_id": "target_12345678",
                                "source": "tui",
                                "user_id": None,
                                "input_status": "streaming",
                                "foreground_job_id": "job_xyz",
                                "created_at": 1234567800.0,
                                "last_access_at": 1234567895.0,
                                "schema_version": "1",
                            },
                        ]
                    },
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(
            cli_main_module, "StreamingAgentClient", MockStreamingAgentClient
        )
        monkeypatch.setattr(
            cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234)
        )

        args = argparse.Namespace(
            command="client",
            client_action="list",
            target="target_12345678",
            format="json",
        )

        exit_code = cli_main_module.cmd_client(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        lines = captured.out.strip().split("\n")
        assert len(lines) == 2

        for line in lines:
            obj = json.loads(line)
            assert obj["type"] == "event"
            assert obj["event"] == "client.discovered"
            assert "client_session_id" in obj["data"]
            assert obj["data"]["target_id"] == "target_12345678"


class TestClientCLIStatus:
    def test_client_status_found(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "client"
                assert command["action"] == "status"
                assert command["client_session_id"] == "client_abcd1234"
                return {
                    "ok": True,
                    "data": {
                        "client_session_id": "client_abcd1234",
                        "target_id": "target_12345678",
                        "source": "cli",
                        "user_id": "alice",
                        "input_status": "idle",
                        "foreground_job_id": None,
                        "created_at": 1234567890.0,
                        "last_access_at": 1234567890.0,
                        "schema_version": "1",
                    },
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(
            cli_main_module, "StreamingAgentClient", MockStreamingAgentClient
        )
        monkeypatch.setattr(
            cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234)
        )

        args = argparse.Namespace(
            command="client",
            client_action="status",
            client="client_abcd1234",
            format="json",
        )

        exit_code = cli_main_module.cmd_client(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "success"
        assert obj["command"] == "client.status"
        assert obj["data"]["client_session_id"] == "client_abcd1234"

    def test_client_status_not_found_returns_CLIENT_NOT_FOUND_and_exits_2(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "client"
                assert command["action"] == "status"
                return {
                    "ok": False,
                    "error_code": "CLIENT_NOT_FOUND",
                    "message": "Client session 'client_notfound' not found",
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(
            cli_main_module, "StreamingAgentClient", MockStreamingAgentClient
        )
        monkeypatch.setattr(
            cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234)
        )

        args = argparse.Namespace(
            command="client",
            client_action="status",
            client="client_notfound",
            format="json",
        )

        exit_code = cli_main_module.cmd_client(args)
        captured = capsys.readouterr()

        assert exit_code == 2
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "error"
        assert obj["command"] == "client.status"
        assert obj["error_code"] == "CLIENT_NOT_FOUND"


class TestClientCLIClose:
    def test_client_close_idempotent_exit_codes(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClientSuccess:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "client"
                assert command["action"] == "close"
                return {
                    "ok": True,
                    "data": {"closed": True},
                }

            def disconnect(self):
                pass

        class MockStreamingAgentClientNotFound:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "client"
                assert command["action"] == "close"
                return {
                    "ok": False,
                    "error_code": "CLIENT_NOT_FOUND",
                    "message": "Client session not found",
                }

            def disconnect(self):
                pass

        # Test success case
        monkeypatch.setattr(
            cli_main_module, "StreamingAgentClient", MockStreamingAgentClientSuccess
        )
        monkeypatch.setattr(
            cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234)
        )

        args = argparse.Namespace(
            command="client",
            client_action="close",
            client="client_abcd1234",
            format="json",
        )

        exit_code = cli_main_module.cmd_client(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "success"
        assert obj["command"] == "client.close"

        # Test not found case (should exit 2)
        monkeypatch.setattr(
            cli_main_module, "StreamingAgentClient", MockStreamingAgentClientNotFound
        )

        exit_code = cli_main_module.cmd_client(args)
        captured = capsys.readouterr()

        assert exit_code == 2
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "error"
        assert obj["error_code"] == "CLIENT_NOT_FOUND"
