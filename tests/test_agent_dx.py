import json
from pathlib import Path

import pytest

from peeka.core.agent import PeekaAgent


@pytest.fixture(autouse=True)
def reset_dx_registries():
    from peeka.core import agent

    agent._client_registry = None
    agent._consumer_registry = None
    agent._dx_case_registry = None
    yield
    agent._client_registry = None
    agent._consumer_registry = None
    agent._dx_case_registry = None


@pytest.fixture
def peeka_agent() -> PeekaAgent:
    return PeekaAgent(session_id="test-dx-session", attached_pid=99999)


class TestAgentDXHandlers:
    def test_create_and_status(self, peeka_agent: PeekaAgent) -> None:
        created = peeka_agent._handle_dx_create(
            {"target_id": "target_1", "title": "Slow request", "client_session_id": None}
        )
        assert created["status"] == "success"
        dx_case_id = created["data"]["dx_case_id"]

        status = peeka_agent._handle_dx_status({"dx_case_id": dx_case_id})
        assert status["status"] == "success"
        assert status["data"]["title"] == "Slow request"

    def test_add_and_summary(self, peeka_agent: PeekaAgent) -> None:
        created = peeka_agent._handle_dx_create(
            {"target_id": "target_1", "title": "Case 1"}
        )
        dx_case_id = created["data"]["dx_case_id"]

        added = peeka_agent._handle_dx_add(
            {
                "dx_case_id": dx_case_id,
                "section_type": "note",
                "title": "Note",
                "payload": {"message": "hello"},
            }
        )
        assert added["status"] == "success"

        summary = peeka_agent._handle_dx_summary({"dx_case_id": dx_case_id})
        assert summary["status"] == "success"
        assert summary["data"]["summary"]["section_count"] == 1
        assert "DXCase:" in summary["data"]["text_summary"]

    def test_export_writes_json_file(self, peeka_agent: PeekaAgent, tmp_path: Path) -> None:
        created = peeka_agent._handle_dx_create(
            {"target_id": "target_1", "title": "Case export"}
        )
        dx_case_id = created["data"]["dx_case_id"]
        output_path = tmp_path / "dx-case.json"

        exported = peeka_agent._handle_dx_export(
            {"dx_case_id": dx_case_id, "output_path": str(output_path)}
        )
        assert exported["status"] == "success"
        assert output_path.exists()
        document = json.loads(output_path.read_text(encoding="utf-8"))
        assert document["dx_case"]["dx_case_id"] == dx_case_id

    def test_export_adds_error_sections_for_missing_refs(
        self, peeka_agent: PeekaAgent, tmp_path: Path
    ) -> None:
        created = peeka_agent._handle_dx_create(
            {"target_id": "target_1", "title": "Case export"}
        )
        dx_case_id = created["data"]["dx_case_id"]
        peeka_agent._handle_dx_add(
            {
                "dx_case_id": dx_case_id,
                "section_type": "note",
                "title": "Missing job",
                "payload": {"job_id": "job_missing"},
                "object_ref_type": "jobs",
                "object_ref_id": "job_missing",
            }
        )
        output_path = tmp_path / "dx-case-missing.json"

        exported = peeka_agent._handle_dx_export(
            {"dx_case_id": dx_case_id, "output_path": str(output_path)}
        )
        assert exported["status"] == "success"
        document = json.loads(output_path.read_text(encoding="utf-8"))
        error_sections = [
            section for section in document["sections"] if section["section_type"] == "error"
        ]
        assert len(error_sections) >= 1
        assert "JOB_NOT_FOUND" in {
            section["payload"]["error_code"] for section in error_sections
        }

    def test_close_not_found(self, peeka_agent: PeekaAgent) -> None:
        result = peeka_agent._handle_dx_close({"dx_case_id": "dx_missing"})
        assert result["status"] == "error"
        assert result["error_code"] == "DX_CASE_NOT_FOUND"
