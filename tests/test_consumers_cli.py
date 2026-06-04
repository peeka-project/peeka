import argparse
import json
import sys
from typing import Any
from typing import Dict

import peeka.cli.main  # noqa: F401


class TestConsumerCLICreate:
    def test_consumer_create_emits_json_envelope(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "consumer"
                assert command["action"] == "create"
                assert command["target_id"] == "target_1"
                assert command["scope_type"] == "probe"
                assert command["scope_id"] == "prb_1"
                return {
                    "status": "success",
                    "data": {
                        "consumer_id": "consumer_abcd1234",
                        "target_id": "target_1",
                        "scope_type": "probe",
                        "scope_id": "prb_1",
                        "status": "active",
                        "buffer_size": 0,
                        "dropped_count": 0,
                    },
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        args = argparse.Namespace(
            command="consumer",
            consumer_action="create",
            target="target_1",
            source="cli",
            scope_type="probe",
            scope_id="prb_1",
            client=None,
            max_buffer_size=1000,
            backpressure_policy="drop_oldest",
            format="json",
        )

        exit_code = cli_main_module.cmd_consumer(args)
        captured = capsys.readouterr()
        assert exit_code == 0
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "success"
        assert obj["command"] == "consumer.create"
        assert obj["data"]["consumer_id"] == "consumer_abcd1234"


class TestConsumerCLIList:
    def test_consumer_list_emits_event_jsonl(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "consumer"
                assert command["action"] == "list"
                return {
                    "status": "success",
                    "data": {
                        "consumers": [
                            {
                                "consumer_id": "consumer_a",
                                "scope_type": "probe",
                                "scope_id": "prb_1",
                                "status": "active",
                                "buffer_size": 2,
                                "dropped_count": 0,
                            }
                        ]
                    },
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        args = argparse.Namespace(
            command="consumer",
            consumer_action="list",
            target=None,
            client=None,
            scope_type=None,
            scope_id=None,
            status=None,
            format="json",
        )

        exit_code = cli_main_module.cmd_consumer(args)
        captured = capsys.readouterr()
        assert exit_code == 0
        lines = captured.out.strip().split("\n")
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["type"] == "event"
        assert obj["event"] == "consumer.discovered"
        assert obj["data"]["consumer_id"] == "consumer_a"


class TestConsumerCLIStatus:
    def test_consumer_status_not_found_returns_exit_2(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                return {
                    "status": "error",
                    "error_code": "CONSUMER_NOT_FOUND",
                    "message": "Consumer not found",
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        args = argparse.Namespace(
            command="consumer",
            consumer_action="status",
            consumer="consumer_missing",
            format="json",
        )

        exit_code = cli_main_module.cmd_consumer(args)
        captured = capsys.readouterr()
        assert exit_code == 2
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "error"
        assert obj["error_code"] == "CONSUMER_NOT_FOUND"

    def test_consumer_status_passes_client_session_id(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        captured_command = {}

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                captured_command.update(command)
                return {"status": "error", "error_code": "CONSUMER_NOT_FOUND", "message": "missing"}

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        args = argparse.Namespace(
            command="consumer",
            consumer_action="status",
            consumer="consumer_missing",
            client="client_1",
            format="json",
        )
        _ = cli_main_module.cmd_consumer(args)
        _ = capsys.readouterr()
        assert captured_command["client_session_id"] == "client_1"


class TestConsumerCLIDrain:
    def test_consumer_drain_emits_envelope_then_jsonl_records(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["action"] == "drain"
                return {
                    "status": "success",
                    "data": {
                        "consumer_id": "consumer_a",
                        "next_sequence": 1,
                        "has_more": False,
                        "timed_out": False,
                        "records": [
                            {
                                "sequence": 0,
                                "source_type": "probe",
                                "source_id": "prb_1",
                                "record_type": "observation",
                                "payload": {"value": 1},
                            },
                            {
                                "sequence": 1,
                                "source_type": "probe",
                                "source_id": "prb_1",
                                "record_type": "observation",
                                "payload": {"value": 2},
                            },
                        ],
                    },
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        args = argparse.Namespace(
            command="consumer",
            consumer_action="drain",
            consumer="consumer_a",
            limit=100,
            after_sequence=None,
            format="json",
        )

        exit_code = cli_main_module.cmd_consumer(args)
        captured = capsys.readouterr()
        assert exit_code == 0
        lines = captured.out.strip().split("\n")
        assert len(lines) == 3
        envelope = json.loads(lines[0])
        first_record = json.loads(lines[1])
        second_record = json.loads(lines[2])
        assert envelope["command"] == "consumer.drain"
        assert first_record["sequence"] == 0
        assert second_record["sequence"] == 1

    def test_consumer_drain_timeout_maps_to_exit_2(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["timeout_ms"] == 5
                return {
                    "status": "error",
                    "error_code": "CONSUMER_DRAIN_TIMEOUT",
                    "message": "No records available",
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        args = argparse.Namespace(
            command="consumer",
            consumer_action="drain",
            consumer="consumer_a",
            limit=100,
            after_sequence=None,
            timeout_ms=5,
            format="json",
        )

        exit_code = cli_main_module.cmd_consumer(args)
        captured = capsys.readouterr()
        assert exit_code == 2
        obj = json.loads(captured.out.strip())
        assert obj["error_code"] == "CONSUMER_DRAIN_TIMEOUT"


class TestConsumerCLICloseCleanup:
    def test_consumer_close_and_cleanup(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClientClose:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                return {"status": "success", "data": {"closed": True, "consumer_id": "consumer_a"}}

            def disconnect(self):
                pass

        class MockStreamingAgentClientCleanup:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                return {"status": "success", "data": {"removed_ids": ["consumer_a"]}}

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClientClose)
        close_args = argparse.Namespace(
            command="consumer",
            consumer_action="close",
            consumer="consumer_a",
            format="json",
        )
        exit_code = cli_main_module.cmd_consumer(close_args)
        captured = capsys.readouterr()
        assert exit_code == 0
        assert json.loads(captured.out.strip())["command"] == "consumer.close"

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClientCleanup)
        cleanup_args = argparse.Namespace(
            command="consumer",
            consumer_action="cleanup",
            all=False,
            format="json",
        )
        exit_code = cli_main_module.cmd_consumer(cleanup_args)
        captured = capsys.readouterr()
        assert exit_code == 0
        assert json.loads(captured.out.strip())["data"]["removed_ids"] == ["consumer_a"]


class TestConsumerCLIHelp:
    def test_consumer_subcommand_registered_in_main_help(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "peeka.cli.main", "consumer", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "create" in result.stdout
        assert "list" in result.stdout
        assert "status" in result.stdout
        assert "drain" in result.stdout
        assert "close" in result.stdout
        assert "cleanup" in result.stdout


class TestConsumerMainDispatch:
    def test_main_dispatch_routes_consumer_command(self, monkeypatch):
        cli_main_module = sys.modules["peeka.cli.main"]

        def fake_cmd_consumer(args):
            assert args.command == "consumer"
            assert args.consumer_action == "list"
            return 7

        monkeypatch.setattr(cli_main_module, "cmd_consumer", fake_cmd_consumer)
        monkeypatch.setattr(
            sys,
            "argv",
            ["peeka-cli", "consumer", "list"],
        )

        assert cli_main_module.main() == 7
