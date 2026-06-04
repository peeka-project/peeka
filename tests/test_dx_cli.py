import argparse
import json
import sys
from typing import Any
from typing import Dict

import peeka.cli.main  # noqa: F401


class TestDXCLICreate:
    def test_dx_create_emits_json_envelope(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "dx"
                assert command["action"] == "create"
                return {
                    "status": "success",
                    "data": {
                        "dx_case_id": "dx_abcd1234",
                        "target_id": "target_1",
                        "title": "Slow request",
                        "status": "open",
                    },
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        args = argparse.Namespace(
            command="dx",
            dx_action="create",
            target="target_1",
            title="Slow request",
            client=None,
            format="json",
        )
        exit_code = cli_main_module.cmd_dx(args)
        captured = capsys.readouterr()
        assert exit_code == 0
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "success"
        assert obj["command"] == "dx.create"


class TestDXCLIList:
    def test_dx_list_emits_event_jsonl(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                return {
                    "status": "success",
                    "data": {"cases": [{"dx_case_id": "dx_a", "target_id": "target_1", "status": "open", "title": "A"}]},
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        args = argparse.Namespace(
            command="dx",
            dx_action="list",
            target=None,
            client=None,
            status=None,
            format="json",
        )
        exit_code = cli_main_module.cmd_dx(args)
        captured = capsys.readouterr()
        assert exit_code == 0
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "event"
        assert obj["event"] == "dx.discovered"

    def test_dx_list_passes_client_session_id(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]
        captured_command = {}

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                captured_command.update(command)
                return {"status": "success", "data": {"cases": []}}

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        args = argparse.Namespace(
            command="dx",
            dx_action="list",
            target=None,
            client="client_1",
            status=None,
            format="json",
        )
        _ = cli_main_module.cmd_dx(args)
        _ = capsys.readouterr()
        assert captured_command["client_session_id"] == "client_1"


class TestDXCLIAddSummaryExportClose:
    def test_dx_add_validates_payload_json(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        args = argparse.Namespace(
            command="dx",
            dx_action="add",
            dx_case="dx_1",
            section_type="note",
            title="Bad",
            payload_json="{bad",
            object_ref_type=None,
            object_ref_id=None,
            format="json",
        )
        exit_code = cli_main_module.cmd_dx(args)
        captured = capsys.readouterr()
        assert exit_code == 2
        assert json.loads(captured.out.strip())["error_code"] == "DX_CASE_INVALID"

    def test_dx_summary_and_export(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                if command["action"] == "summary":
                    return {
                        "status": "success",
                        "data": {
                            "dx_case_id": "dx_a",
                            "summary": {"section_count": 1},
                            "text_summary": "DXCase: dx_a",
                        },
                    }
                return {
                    "status": "success",
                    "data": {
                        "dx_case": {"dx_case_id": "dx_a"},
                        "output_path": "/tmp/dx_a.json",
                        "text_summary": "DXCase: dx_a",
                    },
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        summary_args = argparse.Namespace(command="dx", dx_action="summary", dx_case="dx_a", format="json")
        exit_code = cli_main_module.cmd_dx(summary_args)
        captured = capsys.readouterr()
        assert exit_code == 0
        assert json.loads(captured.out.strip())["command"] == "dx.summary"

        export_args = argparse.Namespace(command="dx", dx_action="export", dx_case="dx_a", output_path=None, format="json")
        exit_code = cli_main_module.cmd_dx(export_args)
        captured = capsys.readouterr()
        assert exit_code == 0
        assert json.loads(captured.out.strip())["command"] == "dx.export"

    def test_dx_close_not_found_exit_2(self, monkeypatch, capsys):
        cli_main_module = sys.modules["peeka.cli.main"]

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                return {"status": "error", "error_code": "DX_CASE_NOT_FOUND", "message": "missing"}

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_main_module, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(cli_main_module, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))

        args = argparse.Namespace(command="dx", dx_action="close", dx_case="dx_missing", format="json")
        exit_code = cli_main_module.cmd_dx(args)
        captured = capsys.readouterr()
        assert exit_code == 2
        assert json.loads(captured.out.strip())["error_code"] == "DX_CASE_NOT_FOUND"


class TestDXCLIHelp:
    def test_dx_subcommand_registered_in_main_help(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, "-m", "peeka.cli.main", "dx", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert "create" in result.stdout
        assert "list" in result.stdout
        assert "status" in result.stdout
        assert "add" in result.stdout
        assert "summary" in result.stdout
        assert "export" in result.stdout
        assert "close" in result.stdout
