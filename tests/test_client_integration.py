import time

import pytest

from peeka.core.agent import PeekaAgent


@pytest.fixture(autouse=True)
def reset_client_registry():
    from peeka.core import agent

    agent._client_registry = None
    yield
    agent._client_registry = None


class TestClientIntegration:
    def test_dispatch_create_returns_success_envelope(self) -> None:
        agent = PeekaAgent(session_id="test-client-create", attached_pid=12345)

        result = agent._execute_command(
            {
                "type": "client",
                "action": "create",
                "target_id": "t1",
                "source": "cli",
            }
        )

        assert result["status"] == "success"
        data = result["data"]
        assert data["client_session_id"].startswith("client_")
        assert data["schema_version"] == "1"
        assert data["target_id"] == "t1"

    def test_round_trip_create_list_status_close(self) -> None:
        agent = PeekaAgent(session_id="test-client-roundtrip", attached_pid=12345)

        create_result = agent._execute_command(
            {
                "type": "client",
                "action": "create",
                "target_id": "t1",
                "source": "cli",
            }
        )
        assert create_result["status"] == "success"
        client_session_id = create_result["data"]["client_session_id"]

        list_result = agent._execute_command(
            {"type": "client", "action": "list", "target_id": "t1"}
        )
        assert list_result["status"] == "success"
        assert [client["client_session_id"] for client in list_result["data"]["clients"]] == [
            client_session_id
        ]

        status_result = agent._execute_command(
            {
                "type": "client",
                "action": "status",
                "client_session_id": client_session_id,
            }
        )
        assert status_result["status"] == "success"
        assert status_result["data"]["client_session_id"] == client_session_id

        close_result = agent._execute_command(
            {
                "type": "client",
                "action": "close",
                "client_session_id": client_session_id,
            }
        )
        assert close_result["status"] == "success"
        assert close_result["data"]["closed"] is True

    def test_cleanup_idle_runs_before_other_client_calls(self) -> None:
        agent = PeekaAgent(session_id="test-client-cleanup", attached_pid=12345)

        create_result = agent._execute_command(
            {
                "type": "client",
                "action": "create",
                "target_id": "t1",
                "source": "cli",
            }
        )
        client_session_id = create_result["data"]["client_session_id"]

        from peeka.core.agent import _get_client_registry

        registry = _get_client_registry()
        session = registry.get(client_session_id)
        assert session is not None
        session.last_access_at = time.time() - (16 * 60)

        list_result = agent._execute_command(
            {"type": "client", "action": "list", "target_id": "t1"}
        )
        assert list_result["status"] == "success"
        assert list_result["data"]["clients"] == []
