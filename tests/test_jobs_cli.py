import argparse
import json
import sys
from typing import Any
from typing import Dict

import peeka.cli.main  # noqa: F401


class TestJobCLIList:
    def test_job_list_table_renders_columns(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "job"
                assert command["action"] == "list"
                return {
                    "status": "success",
                    "data": {
                        "jobs": [
                            {
                                "id": "job_abc123",
                                "target_id": "target_12345678",
                                "client_session_id": "client_aaaa1111",
                                "command_type": "watch",
                                "action": "start",
                                "category": "mutation",
                                "status": "running",
                                "updated_at": 1234567890.0,
                            },
                            {
                                "id": "job_def456",
                                "target_id": "target_87654321",
                                "client_session_id": "client_bbbb2222",
                                "command_type": "memory",
                                "action": "overview",
                                "category": "snapshot",
                                "status": "completed",
                                "updated_at": 1234567900.0,
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
            command="job",
            job_action="list",
            target=None,
            client=None,
            status=None,
            format="table",
        )

        exit_code = cli_main_module.cmd_job(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        output = captured.err + captured.out
        assert "JOB_ID" in output
        assert "TARGET" in output
        assert "CLIENT" in output
        assert "TYPE/ACTION" in output
        assert "STATUS" in output
        assert "CATEGORY" in output
        assert "UPDATED" in output
        assert "job_abc123" in output
        assert "job_def456" in output

    def test_job_list_json_format(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "job"
                assert command["action"] == "list"
                return {
                    "status": "success",
                    "data": {
                        "jobs": [
                            {
                                "id": "job_abc123",
                                "target_id": "target_12345678",
                                "client_session_id": "client_aaaa1111",
                                "command_type": "watch",
                                "action": "start",
                                "category": "mutation",
                                "status": "running",
                                "updated_at": 1234567890.0,
                            },
                            {
                                "id": "job_def456",
                                "target_id": "target_87654321",
                                "client_session_id": "client_bbbb2222",
                                "command_type": "memory",
                                "action": "overview",
                                "category": "snapshot",
                                "status": "completed",
                                "updated_at": 1234567900.0,
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
            command="job",
            job_action="list",
            target=None,
            client=None,
            status=None,
            format="json",
        )

        exit_code = cli_main_module.cmd_job(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        lines = captured.out.strip().split("\n")
        assert len(lines) == 2

        job_ids = []
        for line in lines:
            obj = json.loads(line)
            job_ids.append(obj["id"])

        assert "job_abc123" in job_ids
        assert "job_def456" in job_ids

    def test_job_list_filters_passed_through(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        captured_command = {}

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                captured_command.update(command)
                return {
                    "status": "success",
                    "data": {"jobs": []},
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
            command="job",
            job_action="list",
            target="target_12345678",
            client="client_aaaa1111",
            status="running",
            format="table",
        )

        exit_code = cli_main_module.cmd_job(args)
        _ = capsys.readouterr()

        assert exit_code == 0
        assert captured_command["type"] == "job"
        assert captured_command["action"] == "list"
        assert captured_command["target_id"] == "target_12345678"
        assert captured_command["client_session_id"] == "client_aaaa1111"
        assert captured_command["status"] == "running"


class TestJobCLIStatus:
    def test_job_status_requires_job_flag(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        job_parser = subparsers.add_parser("job")
        job_subparsers = job_parser.add_subparsers(dest="job_action")
        job_status_parser = job_subparsers.add_parser("status")
        job_status_parser.add_argument("--job", required=True)

        try:
            parser.parse_args(["job", "status"])
            assert False, "Expected SystemExit"
        except SystemExit as e:
            assert e.code != 0


class TestJobCLIInterrupt:
    def test_job_interrupt_success(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "job"
                assert command["action"] == "interrupt"
                assert command["job_id"] == "job_abc123"
                return {
                    "status": "success",
                    "data": {
                        "job_id": "job_abc123",
                        "status": "interrupted",
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
            command="job",
            job_action="interrupt",
            job="job_abc123",
            format="table",
        )

        exit_code = cli_main_module.cmd_job(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        assert "job_abc123" in captured.err
        assert "interrupted" in captured.err

    def test_job_interrupt_unsupported_capability(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "job"
                assert command["action"] == "interrupt"
                return {
                    "status": "error",
                    "error_code": "UNSUPPORTED_CAPABILITY",
                    "message": "Job interrupt is not implemented",
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
            command="job",
            job_action="interrupt",
            job="job_abc123",
            format="table",
        )

        exit_code = cli_main_module.cmd_job(args)
        captured = capsys.readouterr()

        assert exit_code == 2
        assert "UNSUPPORTED_CAPABILITY" in captured.err


class TestJobCLICleanup:
    def test_job_cleanup_default_older_than_is_10_minutes(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        captured_command = {}

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                captured_command.update(command)
                return {
                    "status": "success",
                    "data": {"removed": []},
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
            command="job",
            job_action="cleanup",
            target="target_12345678",
            completed=False,
            older_than=600,
            format="table",
        )

        exit_code = cli_main_module.cmd_job(args)
        _ = capsys.readouterr()

        assert exit_code == 0
        assert captured_command["older_than_seconds"] == 600

    def test_job_cleanup_custom_older_than_parses_units(self, monkeypatch):
        cli_main_module = sys.modules["peeka.cli.main"]

        assert cli_main_module._parse_duration("1h") == 3600
        assert cli_main_module._parse_duration("30s") == 30
        assert cli_main_module._parse_duration("5m") == 300
        assert cli_main_module._parse_duration("120") == 120

    def test_job_cleanup_invalid_older_than_rejected(self):
        cli_main_module = sys.modules["peeka.cli.main"]

        try:
            cli_main_module._parse_duration("5xyz")
            assert False, "Expected ArgumentTypeError"
        except argparse.ArgumentTypeError:
            pass


class TestJobCLIPull:
    def test_job_pull_stub_returns_unsupported(self, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        args = argparse.Namespace(
            command="job",
            job_action="pull",
            job="job_abc123",
            consumer="consumer_xyz",
            format="json",
        )

        exit_code = cli_main_module.cmd_job_pull(args)
        captured = capsys.readouterr()

        assert exit_code == 2
        payload = json.loads(captured.out.strip())
        assert payload["status"] == "error"
        assert payload["error_code"] == "UNSUPPORTED_CAPABILITY"
        assert "result-consumer.md" in payload["message"]

    def test_job_pull_accepts_format_flag(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        job_parser = subparsers.add_parser("job")
        job_subparsers = job_parser.add_subparsers(dest="job_action")
        
        job_pull_parser = job_subparsers.add_parser("pull")
        job_pull_parser.add_argument("--job", type=str, required=True)
        job_pull_parser.add_argument("--consumer", type=str, required=True)
        job_pull_parser.add_argument("--format", choices=["json", "table"], default="table")

        parsed = parser.parse_args([
            "job", "pull", "--job", "j1", "--consumer", "c1", "--format", "json"
        ])

        assert parsed.job == "j1"
        assert parsed.consumer == "c1"
        assert parsed.format == "json"


class TestJobCLIHelp:
    def test_job_subcommand_in_help(self):
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        job_parser = subparsers.add_parser("job")
        job_subparsers = job_parser.add_subparsers(dest="job_action")
        job_subparsers.add_parser("list")
        job_subparsers.add_parser("status")
        job_subparsers.add_parser("inspect")
        job_subparsers.add_parser("interrupt")
        job_subparsers.add_parser("cleanup")
        job_subparsers.add_parser("pull")

        help_text = parser.format_help()

        assert "job" in help_text
