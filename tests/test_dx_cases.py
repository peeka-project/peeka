import json

from peeka.core.dx_cases import DXCaseRegistry
from peeka.core.dx_cases import build_export_document
from peeka.core.dx_cases import build_text_summary
from peeka.core.dx_cases import export_document_json


class TestDXCaseRegistry:
    def test_registry_crud(self) -> None:
        registry = DXCaseRegistry()

        dx_case = registry.create(
            target_id="target_1",
            title="Slow request diagnosis",
            client_session_id="client_1",
        )

        assert dx_case.dx_case_id.startswith("dx_")
        assert registry.get(dx_case.dx_case_id) is dx_case
        assert [item.dx_case_id for item in registry.list(target_id="target_1")] == [dx_case.dx_case_id]

        assert registry.close(dx_case.dx_case_id) is True
        closed = registry.get(dx_case.dx_case_id)
        assert closed is not None
        assert closed.status == "closed"

    def test_add_section_redacts_secret_like_keys(self) -> None:
        registry = DXCaseRegistry()
        dx_case = registry.create(target_id="target_1", title="Secrets")

        section = registry.add_section(
            dx_case.dx_case_id,
            section_type="note",
            title="Payload",
            payload={"API_KEY": "top-secret", "safe": "ok"},
        )

        assert section is not None
        assert section.payload["API_KEY"] == "<redacted>"
        assert section.redactions[0]["reason"] == "secret_key"
        stored = registry.get(dx_case.dx_case_id)
        assert stored is not None
        assert len(stored.redactions_applied) == 1

    def test_add_section_truncates_large_payloads(self) -> None:
        registry = DXCaseRegistry()
        dx_case = registry.create(target_id="target_1", title="Large payload")

        payload = {"message": "x" * 70000}
        section = registry.add_section(
            dx_case.dx_case_id,
            section_type="summary",
            title="Summary",
            payload=payload,
        )

        assert section is not None
        assert section.payload.get("_truncated") is True

    def test_add_section_records_object_refs(self) -> None:
        registry = DXCaseRegistry()
        dx_case = registry.create(target_id="target_1", title="Probe case")

        section = registry.add_section(
            dx_case.dx_case_id,
            section_type="probe",
            title="Probe snapshot",
            payload={"probe_id": "prb_1"},
            object_ref_type="probes",
            object_ref_id="prb_1",
        )

        assert section is not None
        stored = registry.get(dx_case.dx_case_id)
        assert stored is not None
        assert stored.object_refs["probes"] == ["prb_1"]

    def test_update_summary_and_text_summary(self) -> None:
        registry = DXCaseRegistry()
        dx_case = registry.create(target_id="target_1", title="Summary case")
        registry.add_section(
            dx_case.dx_case_id,
            section_type="error",
            title="Failure",
            payload={"message": "boom"},
        )

        summary = registry.update_summary(dx_case.dx_case_id)
        assert summary is not None
        assert summary["error_count"] == 1

        stored = registry.get(dx_case.dx_case_id)
        assert stored is not None
        text = build_text_summary(stored)
        assert "DXCase:" in text
        assert "Errors: 1" in text
        assert "Top Errors:" in text
        assert "boom" in text

    def test_export_document_is_deterministic(self) -> None:
        registry = DXCaseRegistry()
        dx_case = registry.create(target_id="target_1", title="Export case")
        registry.add_section(
            dx_case.dx_case_id,
            section_type="note",
            title="B",
            payload={"b": 2},
        )
        registry.add_section(
            dx_case.dx_case_id,
            section_type="note",
            title="A",
            payload={"a": 1},
        )
        stored = registry.get(dx_case.dx_case_id)
        assert stored is not None

        doc1 = build_export_document(stored, target_snapshot={"target_id": "target_1"})
        doc2 = build_export_document(stored, target_snapshot={"target_id": "target_1"})
        json1 = export_document_json(doc1)
        json2 = export_document_json(doc2)

        parsed1 = json.loads(json1)
        parsed2 = json.loads(json2)
        assert parsed1["dx_case"]["dx_case_id"] == parsed2["dx_case"]["dx_case_id"]
        assert parsed1["exported_at"] == parsed2["exported_at"]
        assert [section["title"] for section in parsed1["sections"]] == ["B", "A"]
        assert [section["title"] for section in parsed2["sections"]] == ["B", "A"]
