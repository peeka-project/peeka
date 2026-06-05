"""Schema contract tests for session-optimize domain objects.

Verifies that every domain object serializes with required common fields
and documented public identifiers.
"""

import time

from peeka.core.client_sessions import CLIENT_SCHEMA_VERSION, ClientRegistry, to_dict as client_to_dict
from peeka.core.dx_cases import (
    DX_CASE_SCHEMA_VERSION,
    DX_SECTION_SCHEMA_VERSION,
    DXCaseRegistry,
    build_export_document,
    to_dict as dx_to_dict,
)
from peeka.core.jobs import JOB_SCHEMA_VERSION, JobRegistry, to_dict as job_to_dict
from peeka.core.probes import (
    OBSERVATION_EVENT_SCHEMA_VERSION,
    PROBE_SCHEMA_VERSION,
    ObservationEvent,
    ProbeRegistry,
)
from peeka.core.result_consumers import (
    RESULT_CONSUMER_SCHEMA_VERSION,
    RESULT_CONSUMER_RECORD_SCHEMA_VERSION,
    ResultConsumerRegistry,
    to_dict as consumer_to_dict,
)
from peeka.core.targets import TARGET_SCHEMA_VERSION, TargetAgent


class TestTargetAgentContract:
    def test_target_agent_to_dict_has_required_fields(self) -> None:
        target = TargetAgent(
            target_id="target_abc123",
            legacy_session_id="abc123",
            pid=1234,
            socket_path="/tmp/peeka_abc123.sock",
            state="alive",
            agent_mode="injected",
            injection_mode="pep768",
            python_version="3.14.2",
            peeka_version="0.1.15",
        )
        result = target.to_dict()
        assert result["schema_version"] == TARGET_SCHEMA_VERSION
        assert result["target_id"] == "target_abc123"
        assert "state" in result
        assert "created_at" in result
        assert "next_valid_actions" in result


class TestClientSessionContract:
    def test_client_session_to_dict_has_required_fields(self) -> None:
        registry = ClientRegistry()
        client = registry.create(target_id="target_1", source="cli")
        result = client_to_dict(client)
        assert result["schema_version"] == CLIENT_SCHEMA_VERSION
        assert result["client_session_id"].startswith("client_")
        assert result["target_id"] == "target_1"
        assert "input_status" in result
        assert "created_at" in result
        assert "next_valid_actions" in result


class TestCommandJobContract:
    def test_command_job_to_dict_has_required_fields(self) -> None:
        registry = JobRegistry()
        job = registry.create(
            target_id="target_1",
            client_session_id="client_1",
            command_type="watch",
            action="start",
        )
        result = job_to_dict(job)
        assert result["schema_version"] == JOB_SCHEMA_VERSION
        assert result["id"].startswith("job_")
        assert result["target_id"] == "target_1"
        assert result["status"] == "created"
        assert "created_at" in result
        assert "updated_at" in result
        assert "next_valid_actions" in result


class TestProbeRunContract:
    def test_probe_run_to_dict_has_required_fields_and_probe_id_alias(self) -> None:
        registry = ProbeRegistry()
        probe = registry.create(
            target_id="target_1",
            client_session_id="client_1",
            job_id="job_1",
            type="watch",
            pattern="module.fn",
            config={"depth": 3},
        )
        result = probe.to_dict()
        assert result["schema_version"] == PROBE_SCHEMA_VERSION
        assert result["id"].startswith("prb_")
        assert result["probe_id"] == result["id"]
        assert result["target_id"] == "target_1"
        assert result["status"] == "created"
        assert "next_valid_actions" in result
        assert "created_at" in result

    def test_probe_run_probe_id_property(self) -> None:
        registry = ProbeRegistry()
        probe = registry.create(
            target_id="target_1",
            client_session_id="client_1",
            job_id="job_1",
            type="watch",
            pattern=None,
            config=None,
        )
        assert probe.probe_id == probe.id


class TestObservationEventContract:
    def test_observation_event_has_required_fields(self) -> None:
        event = ObservationEvent(
            event_id="evt_abc123_0",
            probe_id="prb_abc123",
            target_id="target_1",
            sequence=0,
            timestamp=time.time(),
            payload={"key": "value"},
        )
        assert event.event_id == "evt_abc123_0"
        assert event.probe_id == "prb_abc123"
        assert event.target_id == "target_1"
        assert event.sequence == 0
        assert "timestamp" in event.__dict__
        assert event.schema_version == OBSERVATION_EVENT_SCHEMA_VERSION


class TestResultConsumerContract:
    def test_result_consumer_to_dict_has_required_fields(self) -> None:
        registry = ResultConsumerRegistry()
        consumer = registry.create(
            target_id="target_1",
            source="cli",
            scope_type="job",
            scope_id="job_1",
        )
        result = consumer_to_dict(consumer)
        assert result["schema_version"] == RESULT_CONSUMER_SCHEMA_VERSION
        assert result["consumer_id"].startswith("consumer_")
        assert result["target_id"] == "target_1"
        assert result["status"] == "active"
        assert "next_valid_actions" in result
        assert "created_at" in result

    def test_consumer_record_has_schema_version(self) -> None:
        registry = ResultConsumerRegistry()
        consumer = registry.create(
            target_id="target_1",
            source="cli",
            scope_type="job",
            scope_id="job_1",
        )
        registry.append_record(
            consumer.consumer_id,
            source_type="job",
            source_id="job_1",
            record_type="result",
            payload={"data": "test"},
        )
        drain_result = registry.drain(consumer.consumer_id)
        assert drain_result is not None
        records = drain_result["records"]
        assert len(records) == 1
        assert records[0]["schema_version"] == RESULT_CONSUMER_RECORD_SCHEMA_VERSION


class TestDXCaseContract:
    def test_dx_case_to_dict_has_required_fields(self) -> None:
        registry = DXCaseRegistry()
        dx_case = registry.create(target_id="target_1", title="Test Case")
        result = dx_to_dict(dx_case)
        assert result["schema_version"] == DX_CASE_SCHEMA_VERSION
        assert result["dx_case_id"].startswith("dx_")
        assert result["target_id"] == "target_1"
        assert result["status"] == "open"
        assert "next_valid_actions" in result
        assert "created_at" in result

    def test_dx_section_has_schema_version(self) -> None:
        registry = DXCaseRegistry()
        dx_case = registry.create(target_id="target_1", title="Test Case")
        section = registry.add_section(
            dx_case.dx_case_id,
            section_type="note",
            title="Note",
            payload={"message": "hello"},
        )
        assert section is not None
        assert section.schema_version == DX_SECTION_SCHEMA_VERSION

    def test_export_document_has_schema_version(self) -> None:
        registry = DXCaseRegistry()
        dx_case = registry.create(target_id="target_1", title="Test Case")
        document = build_export_document(dx_case)
        assert document["schema_version"] == DX_CASE_SCHEMA_VERSION
        assert "dx_case" in document
        assert "sections" in document


class TestCrossObjectReferences:
    def test_object_graph_references_are_strings(self) -> None:
        job_registry = JobRegistry()
        probe_registry = ProbeRegistry()
        consumer_registry = ResultConsumerRegistry()
        dx_registry = DXCaseRegistry()
        client_registry = ClientRegistry()

        client = client_registry.create(target_id="target_1", source="cli")
        job = job_registry.create(
            target_id="target_1",
            client_session_id=client.client_session_id,
            command_type="watch",
            action="start",
        )
        probe = probe_registry.create(
            target_id="target_1",
            client_session_id=client.client_session_id,
            job_id=job.id,
            type="watch",
            pattern=None,
            config=None,
        )
        consumer = consumer_registry.create(
            target_id="target_1",
            source="cli",
            scope_type="probe",
            scope_id=probe.id,
            client_session_id=client.client_session_id,
        )
        dx_case = dx_registry.create(
            target_id="target_1",
            title="Integration Test",
            client_session_id=client.client_session_id,
        )

        assert isinstance(job.id, str)
        assert isinstance(probe.id, str)
        assert isinstance(consumer.consumer_id, str)
        assert isinstance(dx_case.dx_case_id, str)
        assert isinstance(client.client_session_id, str)

        assert job.target_id == "target_1"
        assert job.client_session_id == client.client_session_id
        assert probe.target_id == "target_1"
        assert probe.client_session_id == client.client_session_id
        assert probe.job_id == job.id
        assert consumer.target_id == "target_1"
        assert consumer.scope_id == probe.id
        assert dx_case.target_id == "target_1"
        assert dx_case.client_session_id == client.client_session_id
