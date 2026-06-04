import pytest

from peeka.core.agent import PeekaAgent


@pytest.fixture(autouse=True)
def reset_consumer_registries():
    from peeka.core import agent

    agent._client_registry = None
    agent._consumer_registry = None
    yield
    agent._client_registry = None
    agent._consumer_registry = None


@pytest.fixture
def peeka_agent() -> PeekaAgent:
    return PeekaAgent(session_id="test-consumer-session", attached_pid=99999)


class TestAgentConsumerHandlers:
    def test_create_returns_consumer_id(self, peeka_agent: PeekaAgent) -> None:
        result = peeka_agent._handle_consumer_create(
            {
                "target_id": "target_12345678",
                "source": "cli",
                "scope_type": "probe",
                "scope_id": "prb_deadbeef",
            }
        )

        assert result["status"] == "success"
        data = result["data"]
        assert data["consumer_id"].startswith("consumer_")
        assert data["target_id"] == "target_12345678"
        assert data["scope_type"] == "probe"
        assert data["scope_id"] == "prb_deadbeef"
        assert data["schema_version"] == "1"

    def test_create_with_unknown_client_returns_CLIENT_NOT_FOUND(
        self, peeka_agent: PeekaAgent
    ) -> None:
        result = peeka_agent._handle_consumer_create(
            {
                "target_id": "target_12345678",
                "source": "cli",
                "scope_type": "probe",
                "scope_id": "prb_deadbeef",
                "client_session_id": "client_missing",
            }
        )

        assert result["status"] == "error"
        assert result["error_code"] == "CLIENT_NOT_FOUND"

    def test_list_filters_by_scope_type(self, peeka_agent: PeekaAgent) -> None:
        peeka_agent._handle_consumer_create(
            {
                "target_id": "target_1",
                "source": "cli",
                "scope_type": "probe",
                "scope_id": "prb_1",
            }
        )
        peeka_agent._handle_consumer_create(
            {
                "target_id": "target_1",
                "source": "cli",
                "scope_type": "job",
                "scope_id": "job_1",
            }
        )

        result = peeka_agent._handle_consumer_list({"scope_type": "probe"})
        assert result["status"] == "success"
        assert len(result["data"]["consumers"]) == 1
        assert result["data"]["consumers"][0]["scope_type"] == "probe"

    def test_status_returns_CONSUMER_NOT_FOUND_when_missing(
        self, peeka_agent: PeekaAgent
    ) -> None:
        result = peeka_agent._handle_consumer_status({"consumer_id": "consumer_missing"})
        assert result["status"] == "error"
        assert result["error_code"] == "CONSUMER_NOT_FOUND"

    def test_status_hides_owned_consumer_without_matching_client(
        self, peeka_agent: PeekaAgent
    ) -> None:
        client_result = peeka_agent._handle_client_create(
            {"target_id": "target_1", "source": "cli"}
        )
        client_session_id = client_result["data"]["client_session_id"]
        create_result = peeka_agent._handle_consumer_create(
            {
                "target_id": "target_1",
                "source": "cli",
                "scope_type": "probe",
                "scope_id": "prb_1",
                "client_session_id": client_session_id,
            }
        )
        consumer_id = create_result["data"]["consumer_id"]

        result = peeka_agent._handle_consumer_status(
            {"consumer_id": consumer_id, "client_session_id": "client_other"}
        )
        assert result["status"] == "error"
        assert result["error_code"] == "CONSUMER_NOT_FOUND"

    def test_drain_returns_records(self, peeka_agent: PeekaAgent) -> None:
        create_result = peeka_agent._handle_consumer_create(
            {
                "target_id": "target_1",
                "source": "cli",
                "scope_type": "probe",
                "scope_id": "prb_1",
            }
        )
        consumer_id = create_result["data"]["consumer_id"]

        from peeka.core.agent import _get_consumer_registry

        registry = _get_consumer_registry()
        assert registry.append_record(
            consumer_id,
            source_type="probe",
            source_id="prb_1",
            record_type="observation",
            payload={"value": 1},
        ) is True

        result = peeka_agent._handle_consumer_drain(
            {"consumer_id": consumer_id, "limit": 10}
        )
        assert result["status"] == "success"
        assert len(result["data"]["records"]) == 1
        assert result["data"]["records"][0]["payload"]["value"] == 1

    def test_drain_closed_consumer_returns_CONSUMER_CLOSED(
        self, peeka_agent: PeekaAgent
    ) -> None:
        create_result = peeka_agent._handle_consumer_create(
            {
                "target_id": "target_1",
                "source": "cli",
                "scope_type": "probe",
                "scope_id": "prb_1",
            }
        )
        consumer_id = create_result["data"]["consumer_id"]
        peeka_agent._handle_consumer_close({"consumer_id": consumer_id})

        result = peeka_agent._handle_consumer_drain(
            {"consumer_id": consumer_id, "limit": 10, "timeout_ms": 0}
        )
        assert result["status"] == "error"
        assert result["error_code"] == "CONSUMER_CLOSED"

    def test_drain_timeout_returns_CONSUMER_DRAIN_TIMEOUT(
        self, peeka_agent: PeekaAgent
    ) -> None:
        create_result = peeka_agent._handle_consumer_create(
            {
                "target_id": "target_1",
                "source": "cli",
                "scope_type": "probe",
                "scope_id": "prb_1",
            }
        )
        consumer_id = create_result["data"]["consumer_id"]

        result = peeka_agent._handle_consumer_drain(
            {"consumer_id": consumer_id, "limit": 10, "timeout_ms": 5}
        )
        assert result["status"] == "error"
        assert result["error_code"] == "CONSUMER_DRAIN_TIMEOUT"

    def test_close_and_cleanup(self, peeka_agent: PeekaAgent) -> None:
        create_result = peeka_agent._handle_consumer_create(
            {
                "target_id": "target_1",
                "source": "cli",
                "scope_type": "job",
                "scope_id": "job_1",
            }
        )
        consumer_id = create_result["data"]["consumer_id"]

        close_result = peeka_agent._handle_consumer_close(
            {"consumer_id": consumer_id}
        )
        assert close_result["status"] == "success"
        assert close_result["data"]["closed"] is True

        cleanup_result = peeka_agent._handle_consumer_cleanup({"closed_only": True})
        assert cleanup_result["status"] == "success"
        assert cleanup_result["data"]["removed_ids"] == [consumer_id]

    def test_create_and_cleanup_updates_client_result_consumers(
        self, peeka_agent: PeekaAgent
    ) -> None:
        client_result = peeka_agent._handle_client_create(
            {"target_id": "target_1", "source": "cli"}
        )
        client_session_id = client_result["data"]["client_session_id"]

        consumer_result = peeka_agent._handle_consumer_create(
            {
                "target_id": "target_1",
                "source": "cli",
                "scope_type": "probe",
                "scope_id": "prb_1",
                "client_session_id": client_session_id,
            }
        )
        consumer_id = consumer_result["data"]["consumer_id"]

        status_result = peeka_agent._handle_client_status(
            {"client_session_id": client_session_id}
        )
        assert status_result["status"] == "success"
        assert status_result["data"]["result_consumers"] == [consumer_id]

        peeka_agent._handle_consumer_close(
            {"consumer_id": consumer_id, "client_session_id": client_session_id}
        )
        cleanup_result = peeka_agent._handle_consumer_cleanup(
            {"closed_only": True, "client_session_id": client_session_id}
        )
        assert cleanup_result["status"] == "success"

        status_after = peeka_agent._handle_client_status(
            {"client_session_id": client_session_id}
        )
        assert status_after["status"] == "success"
        assert status_after["data"]["result_consumers"] == []
