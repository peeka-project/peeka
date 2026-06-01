import argparse
import json
import sys
from typing import Any
from typing import Dict

import peeka.cli.main  # noqa: F401


class TestProbeCLIList:
    def test_probe_list_parses_filters(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "probe"
                assert command["action"] == "list"
                assert command.get("target_id") == "target_test"
                assert command.get("probe_type") == "watch"
                assert command.get("status") == "active"
                return {
                    "status": "success",
                    "data": {
                        "probes": [
                            {
                                "id": "prb_abc123",
                                "type": "watch",
                                "status": "active",
                                "job_id": "job_xyz789",
                                "created_at": 1234567890.0,
                                "event_count": 42,
                            }
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
            command="probe",
            probe_action="list",
            target="target_test",
            probe_type="watch",
            status="active",
            format="table",
        )

        exit_code = cli_main_module.cmd_probe(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        output = captured.err + captured.out
        assert "PROBE_ID" in output
        assert "prb_abc123" in output


class TestProbeCLIStatus:
    def test_probe_status_requires_probe_id(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "probe"
                assert command["action"] == "status"
                assert command["probe_id"] == "prb_test123"
                return {
                    "status": "success",
                    "data": {
                        "probe": {
                            "id": "prb_test123",
                            "type": "trace",
                            "status": "stopped",
                            "event_count": 10,
                        }
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
            command="probe",
            probe_action="status",
            probe="prb_test123",
            format="table",
        )

        exit_code = cli_main_module.cmd_probe(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        output = captured.err + captured.out
        assert "prb_test123" in output or "trace" in output


class TestProbeCLIInspect:
    def test_probe_inspect_events_limit_default_100(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "probe"
                assert command["action"] == "inspect"
                assert command["probe_id"] == "prb_inspect"
                assert command["events_limit"] == 100
                return {
                    "status": "success",
                    "data": {
                        "probe": {"id": "prb_inspect", "type": "watch"},
                        "events": [],
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
            command="probe",
            probe_action="inspect",
            probe="prb_inspect",
            events=100,
            format="table",
        )

        exit_code = cli_main_module.cmd_probe(args)
        assert exit_code == 0

    def test_probe_inspect_events_limit_custom(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "probe"
                assert command["action"] == "inspect"
                assert command["events_limit"] == 50
                return {
                    "status": "success",
                    "data": {
                        "probe": {"id": "prb_custom", "type": "trace"},
                        "events": [
                            {
                                "event_id": "evt_abc_0",
                                "timestamp": 1234567890.5,
                                "payload": {"foo": "bar"},
                            }
                        ],
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
            command="probe",
            probe_action="inspect",
            probe="prb_custom",
            events=50,
            format="json",
        )

        exit_code = cli_main_module.cmd_probe(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        lines = captured.out.strip().split("\n")
        assert len(lines) == 2
        first_line = json.loads(lines[0])
        assert first_line["type"] == "success"
        assert first_line["command"] == "probe.inspect"
        event_line = json.loads(lines[1])
        assert event_line["event_id"] == "evt_abc_0"


class TestProbeCLIStop:
    def test_probe_stop_invokes_correct_cmd_type(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "probe"
                assert command["action"] == "stop"
                assert command["probe_id"] == "prb_stop_test"
                return {
                    "status": "success",
                    "data": {
                        "probe_id": "prb_stop_test",
                        "status": "stopped",
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
            command="probe",
            probe_action="stop",
            probe="prb_stop_test",
            format="table",
        )

        exit_code = cli_main_module.cmd_probe(args)
        assert exit_code == 0


class TestProbeCLICleanup:
    def test_probe_cleanup_parses_duration(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "probe"
                assert command["action"] == "cleanup"
                assert command["older_than_seconds"] == 600
                assert command["completed_only"] is True
                return {
                    "status": "success",
                    "data": {"removed": ["prb_old1", "prb_old2"]},
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
            command="probe",
            probe_action="cleanup",
            target=None,
            completed=True,
            older_than=600,
            format="table",
        )

        exit_code = cli_main_module.cmd_probe(args)
        captured = capsys.readouterr()

        assert exit_code == 0
        output = captured.err + captured.out
        assert "Removed 2 probe(s)" in output


class TestProbeFormatFlag:
    def test_format_flag_choices(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                return {
                    "status": "success",
                    "data": {"probes": []},
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(
            cli_main_module, "StreamingAgentClient", MockStreamingAgentClient
        )
        monkeypatch.setattr(
            cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234)
        )

        args_table = argparse.Namespace(
            command="probe",
            probe_action="list",
            target=None,
            probe_type=None,
            status=None,
            format="table",
        )

        exit_code = cli_main_module.cmd_probe(args_table)
        assert exit_code == 0

        args_json = argparse.Namespace(
            command="probe",
            probe_action="list",
            target=None,
            probe_type=None,
            status=None,
            format="json",
        )

        exit_code = cli_main_module.cmd_probe(args_json)
        assert exit_code == 0


class TestProbeErrorHandling:
    def test_error_envelope_exit_code_1(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                return {
                    "status": "error",
                    "error_code": "COMMAND_EXECUTION_ERROR",
                    "message": "Something went wrong",
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
            command="probe",
            probe_action="list",
            target=None,
            probe_type=None,
            status=None,
            format="json",
        )

        exit_code = cli_main_module.cmd_probe(args)
        captured = capsys.readouterr()

        assert exit_code == 1
        output_lines = [line for line in captured.out.split("\n") if line.strip()]
        assert len(output_lines) > 0
        error_obj = json.loads(output_lines[0])
        assert error_obj["type"] == "error"
        assert error_obj["command"] == "probe.list"
        assert error_obj["error_code"] == "COMMAND_EXECUTION_ERROR"


class TestProbeHelpOutput:
    def test_probe_help_lists_5_subcommands(self, monkeypatch, capsys):
        import subprocess

        result = subprocess.run(
            ["uv", "run", "peeka-cli", "probe", "--help"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        help_text = result.stdout + result.stderr
        assert "list" in help_text
        assert "status" in help_text
        assert "inspect" in help_text
        assert "stop" in help_text
        assert "cleanup" in help_text
