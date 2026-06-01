"""Tests for agent client.{create,list,status,close} handlers."""

import pytest

from peeka.core.agent import PeekaAgent


@pytest.fixture(autouse=True)
def reset_client_registry():
    from peeka.core import agent

    agent._client_registry = None
    yield
    agent._client_registry = None


@pytest.fixture
def peeka_agent() -> PeekaAgent:
    return PeekaAgent(session_id="test-session-12345678", attached_pid=99999)


class TestAgentClientHandlers:
    def test_create_returns_client_session_id(self, peeka_agent: PeekaAgent) -> None:
        result = peeka_agent._handle_client_create(
            {"target_id": "target_12345678", "source": "cli"}
        )

        assert result["status"] == "success"
        data = result["data"]
        assert data["client_session_id"].startswith("client_")
        assert data["target_id"] == "target_12345678"
        assert data["source"] == "cli"
        assert data["input_status"] == "idle"
        assert data["result_consumers"] == []
        assert data["schema_version"] == "1"

    def test_create_invalid_source_returns_error(self, peeka_agent: PeekaAgent) -> None:
        result = peeka_agent._handle_client_create(
            {"target_id": "target_12345678", "source": "invalid_source"}
        )

        assert result["status"] == "error"
        assert result["error_code"] == "UNSUPPORTED_CAPABILITY"
        assert "invalid_source" in result["message"]

    def test_list_filters_by_target_id(self, peeka_agent: PeekaAgent) -> None:
        peeka_agent._handle_client_create({"target_id": "target_A", "source": "cli"})
        peeka_agent._handle_client_create({"target_id": "target_B", "source": "tui"})
        peeka_agent._handle_client_create({"target_id": "target_A", "source": "mcp"})

        result_all = peeka_agent._handle_client_list({})
        assert result_all["status"] == "success"
        assert len(result_all["data"]["clients"]) == 3

        result_filtered = peeka_agent._handle_client_list({"target_id": "target_A"})
        assert result_filtered["status"] == "success"
        assert len(result_filtered["data"]["clients"]) == 2
        for client in result_filtered["data"]["clients"]:
            assert client["target_id"] == "target_A"

    def test_status_returns_full_dict_when_found(self, peeka_agent: PeekaAgent) -> None:
        create_result = peeka_agent._handle_client_create(
            {"target_id": "target_99999", "source": "api", "user_id": "user123"}
        )
        client_session_id = create_result["data"]["client_session_id"]

        status_result = peeka_agent._handle_client_status(
            {"client_session_id": client_session_id}
        )

        assert status_result["status"] == "success"
        data = status_result["data"]
        assert data["client_session_id"] == client_session_id
        assert data["target_id"] == "target_99999"
        assert data["source"] == "api"
        assert data["user_id"] == "user123"
        assert "created_at" in data
        assert "last_access_at" in data

    def test_status_not_found_returns_CLIENT_NOT_FOUND(self, peeka_agent: PeekaAgent) -> None:
        result = peeka_agent._handle_client_status({"client_session_id": "client_nonexistent"})

        assert result["status"] == "error"
        assert result["error_code"] == "CLIENT_NOT_FOUND"
        assert "client_nonexistent" in result["message"]

    def test_close_idempotent_returns_CLIENT_NOT_FOUND_second_call(
        self, peeka_agent: PeekaAgent
    ) -> None:
        create_result = peeka_agent._handle_client_create(
            {"target_id": "target_close_test", "source": "internal"}
        )
        client_session_id = create_result["data"]["client_session_id"]

        close_result_1 = peeka_agent._handle_client_close(
            {"client_session_id": client_session_id}
        )
        assert close_result_1["status"] == "success"
        assert close_result_1["data"]["closed"] is True
        assert close_result_1["data"]["client_session_id"] == client_session_id

        close_result_2 = peeka_agent._handle_client_close(
            {"client_session_id": client_session_id}
        )
        assert close_result_2["status"] == "error"
        assert close_result_2["error_code"] == "CLIENT_NOT_FOUND"
