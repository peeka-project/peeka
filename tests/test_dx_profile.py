import argparse
import json
from pathlib import Path
from typing import Any
from typing import Dict

import pytest

from peeka.core.agent import PeekaAgent
from peeka.core.profile.models import ProfileConfig


@pytest.fixture(autouse=True)
def reset_registries():
    from peeka.core import agent
    from peeka.commands.top import _PROFILE_REGISTRY

    agent._client_registry = None
    agent._dx_case_registry = None
    yield
    agent._client_registry = None
    agent._dx_case_registry = None
    for session in _PROFILE_REGISTRY.list_sessions():
        try:
            _PROFILE_REGISTRY.stop(session.profile_id)
        except KeyError:
            pass
    _PROFILE_REGISTRY.cleanup(max_sessions=0)


@pytest.fixture
def peeka_agent() -> PeekaAgent:
    return PeekaAgent(session_id="test-dx-profile", attached_pid=99999)


@pytest.fixture
def profile_id() -> str:
    from peeka.commands.top import _PROFILE_REGISTRY

    config = ProfileConfig(backend="sampling", interval_ms=10)
    return _PROFILE_REGISTRY.start(config)


class TestHandlerAddProfile:
    def test_add_profile_creates_profile_section(
        self, peeka_agent: PeekaAgent, profile_id: str
    ) -> None:
        created = peeka_agent._handle_dx_create(
            {"target_id": "target_1", "title": "Profile case"}
        )
        dx_case_id = created["data"]["dx_case_id"]

        result = peeka_agent._handle_dx_add_profile(
            {"dx_case_id": dx_case_id, "profile_id": profile_id}
        )

        assert result["status"] == "success"
        assert result["data"]["dx_case_id"] == dx_case_id
        assert result["data"]["section_id"].startswith("section_")

        registry = peeka_agent._get_dx_case_registry()
        dx_case = registry.get(dx_case_id)
        assert dx_case is not None
        assert len(dx_case.sections) == 1
        section = dx_case.sections[0]
        assert section.section_type == "profile"
        assert section.title == f"Profile {profile_id}"
        assert section.payload["profile_id"] == profile_id
        assert section.payload["backend"] == "sampling"
        assert "status" in section.payload
        assert "sample_count" in section.payload
        assert "summary" in section.payload

    def test_add_profile_missing_required_fields(
        self, peeka_agent: PeekaAgent
    ) -> None:
        result = peeka_agent._handle_dx_add_profile(
            {"dx_case_id": "", "profile_id": "prof_abc"}
        )
        assert result["status"] == "error"
        assert result["error_code"] == "DX_CASE_INVALID"

        result2 = peeka_agent._handle_dx_add_profile(
            {"dx_case_id": "dx_abc", "profile_id": ""}
        )
        assert result2["status"] == "error"
        assert result2["error_code"] == "DX_CASE_INVALID"

    def test_add_profile_dx_case_not_found(
        self, peeka_agent: PeekaAgent, profile_id: str
    ) -> None:
        result = peeka_agent._handle_dx_add_profile(
            {"dx_case_id": "dx_nonexistent", "profile_id": profile_id}
        )
        assert result["status"] == "error"
        assert result["error_code"] == "DX_CASE_NOT_FOUND"

    def test_add_profile_profile_not_found(self, peeka_agent: PeekaAgent) -> None:
        created = peeka_agent._handle_dx_create(
            {"target_id": "target_1", "title": "Missing profile"}
        )
        dx_case_id = created["data"]["dx_case_id"]

        result = peeka_agent._handle_dx_add_profile(
            {"dx_case_id": dx_case_id, "profile_id": "prof_nonexistent"}
        )
        assert result["status"] == "error"
        assert result["error_code"] == "PROFILE_NOT_FOUND"

    def test_add_profile_stores_summary_when_present(
        self, peeka_agent: PeekaAgent
    ) -> None:
        from peeka.commands.top import _PROFILE_REGISTRY
        from peeka.core.profile.models import ProfileSummary

        config = ProfileConfig(backend="sampling", interval_ms=10)
        pid = _PROFILE_REGISTRY.start(config)
        session = _PROFILE_REGISTRY.get_session(pid)
        assert session is not None

        session.summary = ProfileSummary(
            sample_count=5,
            duration_ms=50.0,
            start_time=session.started_at,
            top_functions=[{"name": "foo", "own_pct": 100.0}],
        )
        _PROFILE_REGISTRY._sessions[pid] = session

        created = peeka_agent._handle_dx_create(
            {"target_id": "target_1", "title": "Summary profile"}
        )
        dx_case_id = created["data"]["dx_case_id"]

        result = peeka_agent._handle_dx_add_profile(
            {"dx_case_id": dx_case_id, "profile_id": pid}
        )

        assert result["status"] == "success"
        registry = peeka_agent._get_dx_case_registry()
        dx_case = registry.get(dx_case_id)
        assert dx_case is not None
        stored_summary = dx_case.sections[0].payload["summary"]
        assert stored_summary["sample_count"] == 5
        assert stored_summary["top_functions"][0]["name"] == "foo"


class TestExportBundleContainsProfileSection:
    def test_export_bundle_contains_profile_section(
        self, peeka_agent: PeekaAgent, profile_id: str, tmp_path: Path
    ) -> None:
        created = peeka_agent._handle_dx_create(
            {"target_id": "target_1", "title": "Export with profile"}
        )
        dx_case_id = created["data"]["dx_case_id"]

        peeka_agent._handle_dx_add_profile(
            {"dx_case_id": dx_case_id, "profile_id": profile_id}
        )

        output_path = tmp_path / "dx_profile.json"
        exported = peeka_agent._handle_dx_export(
            {"dx_case_id": dx_case_id, "output_path": str(output_path)}
        )

        assert exported["status"] == "success"
        assert output_path.exists()
        document = json.loads(output_path.read_text(encoding="utf-8"))
        profile_sections = [
            s for s in document["sections"] if s["section_type"] == "profile"
        ]
        assert len(profile_sections) == 1
        assert profile_sections[0]["payload"]["profile_id"] == profile_id


class TestCLIAddProfile:
    def test_cli_add_profile_emits_json_success(self, monkeypatch, capsys) -> None:
        from peeka.cli import connection as cli_connection
        from peeka.cli import sessions as cli_sessions
        from peeka.cli.handlers import dx as cli_dx

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                assert command["type"] == "dx"
                assert command["action"] == "add_profile"
                assert command["dx_case_id"] == "dx_abc123"
                assert command["profile_id"] == "prof_xyz"
                return {
                    "status": "success",
                    "data": {
                        "dx_case_id": "dx_abc123",
                        "section_id": "section_001",
                    },
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_connection, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(
            cli_sessions, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234)
        )

        args = argparse.Namespace(
            command="dx",
            dx_action="add-profile",
            dx_case="dx_abc123",
            profile_id="prof_xyz",
            format="json",
        )
        exit_code = cli_dx.cmd_dx(args)
        captured = capsys.readouterr()
        assert exit_code == 0
        obj = json.loads(captured.out.strip())
        assert obj["type"] == "success"
        assert obj["command"] == "dx.add_profile"

    def test_cli_add_profile_profile_not_found_exit_2(self, monkeypatch, capsys) -> None:
        from peeka.cli import connection as cli_connection
        from peeka.cli import sessions as cli_sessions
        from peeka.cli.handlers import dx as cli_dx

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path

            def connect(self) -> Dict[str, Any]:
                return {"status": "success"}

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                return {
                    "status": "error",
                    "error_code": "PROFILE_NOT_FOUND",
                    "message": "not found",
                    "error": "PROFILE_NOT_FOUND: not found",
                }

            def disconnect(self):
                pass

        monkeypatch.setattr(cli_connection, "StreamingAgentClient", MockStreamingAgentClient)
        monkeypatch.setattr(
            cli_sessions, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234)
        )

        args = argparse.Namespace(
            command="dx",
            dx_action="add-profile",
            dx_case="dx_abc123",
            profile_id="prof_missing",
            format="json",
        )
        exit_code = cli_dx.cmd_dx(args)
        captured = capsys.readouterr()
        assert exit_code == 2
        obj = json.loads(captured.out.strip())
        assert obj["error_code"] == "PROFILE_NOT_FOUND"
