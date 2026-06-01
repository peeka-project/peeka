"""Tests for agent client.{create,list,status,close} handlers."""

import time
from typing import Any, Dict

import pytest


@pytest.fixture(autouse=True)
def reset_client_registry():
    """Reset the global client registry before each test to avoid state pollution."""
    from peeka.core import agent
    agent._client_registry = None
    yield
    agent._client_registry = None


class MockAgent:
    """Minimal agent mock for testing client handlers."""

    def __init__(
        self,
        session_id: str = "test-session-12345678",
        attached_pid: int = 99999,
    ):
        self.session_id = session_id
        self.attached_pid = attached_pid
        self.running = True

    def _handle_client_create(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.create command - create and register a client session."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict
            
            from peeka.core.agent import _get_client_registry
            
            target_id = params.get("target_id", "")
            source = params.get("source", "")
            user_id = params.get("user_id")
            
            if not target_id:
                return {
                    "ok": False,
                    "error_code": "UNSUPPORTED_CAPABILITY",
                    "message": "target_id is required and cannot be empty",
                }
            
            valid_sources = {"cli", "tui", "mcp", "api", "internal"}
            if source not in valid_sources:
                return {
                    "ok": False,
                    "error_code": "UNSUPPORTED_CAPABILITY",
                    "message": f"source must be one of {valid_sources}, got {source!r}",
                }
            
            registry = _get_client_registry()
            client = registry.create(target_id=target_id, source=source, user_id=user_id)
            
            return {"ok": True, "data": client_to_dict(client)}
        except Exception as e:
            import traceback
            return {
                "ok": False,
                "error_code": "TRANSPORT_ERROR",
                "message": str(e),
                "traceback": traceback.format_exc(),
            }

    def _handle_client_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.list command - list client sessions optionally filtered by target_id."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict
            
            from peeka.core.agent import _get_client_registry
            
            target_id = params.get("target_id")
            
            registry = _get_client_registry()
            clients = registry.list(target_id=target_id)
            
            return {"ok": True, "data": {"clients": [client_to_dict(c) for c in clients]}}
        except Exception as e:
            import traceback
            return {
                "ok": False,
                "error_code": "TRANSPORT_ERROR",
                "message": str(e),
                "traceback": traceback.format_exc(),
            }

    def _handle_client_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.status command - get client session details by ID."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict
            
            from peeka.core.agent import _get_client_registry
            
            client_session_id = params.get("client_session_id", "")
            if not client_session_id:
                return {
                    "ok": False,
                    "error_code": "CLIENT_NOT_FOUND",
                    "message": "client_session_id is required",
                }
            
            registry = _get_client_registry()
            client = registry.get(client_session_id)
            
            if client is None:
                return {
                    "ok": False,
                    "error_code": "CLIENT_NOT_FOUND",
                    "message": f"Client session {client_session_id!r} not found",
                }
            
            return {"ok": True, "data": client_to_dict(client)}
        except Exception as e:
            import traceback
            return {
                "ok": False,
                "error_code": "TRANSPORT_ERROR",
                "message": str(e),
                "traceback": traceback.format_exc(),
            }

    def _handle_client_close(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.close command - close a client session by ID."""
        try:
            from peeka.core.agent import _get_client_registry
            
            client_session_id = params.get("client_session_id", "")
            if not client_session_id:
                return {
                    "ok": False,
                    "error_code": "CLIENT_NOT_FOUND",
                    "message": "client_session_id is required",
                }
            
            registry = _get_client_registry()
            removed = registry.close(client_session_id)
            
            if not removed:
                return {
                    "ok": False,
                    "error_code": "CLIENT_NOT_FOUND",
                    "message": f"Client session {client_session_id!r} not found",
                }
            
            return {"ok": True, "data": {"closed": True}}
        except Exception as e:
            import traceback
            return {
                "ok": False,
                "error_code": "TRANSPORT_ERROR",
                "message": str(e),
                "traceback": traceback.format_exc(),
            }


class TestAgentClientHandlers:
    def test_create_returns_client_session_id(self):
        """Verify client.create returns a valid client session with ID."""
        agent = MockAgent()
        result = agent._handle_client_create({
            "target_id": "target_12345678",
            "source": "cli",
        })

        assert result["ok"] is True
        assert "data" in result
        data = result["data"]
        assert "client_session_id" in data
        assert data["client_session_id"].startswith("client_")
        assert data["target_id"] == "target_12345678"
        assert data["source"] == "cli"
        assert data["input_status"] == "idle"
        assert data["schema_version"] == "1"

    def test_create_invalid_source_returns_error(self):
        """Verify client.create rejects invalid source values."""
        agent = MockAgent()
        result = agent._handle_client_create({
            "target_id": "target_12345678",
            "source": "invalid_source",
        })

        assert result["ok"] is False
        assert result["error_code"] == "UNSUPPORTED_CAPABILITY"
        assert "invalid_source" in result["message"]

    def test_list_filters_by_target_id(self):
        """Verify client.list filters by target_id when provided."""
        agent = MockAgent()
        
        agent._handle_client_create({"target_id": "target_A", "source": "cli"})
        agent._handle_client_create({"target_id": "target_B", "source": "tui"})
        agent._handle_client_create({"target_id": "target_A", "source": "mcp"})

        result_all = agent._handle_client_list({})
        assert result_all["ok"] is True
        assert len(result_all["data"]["clients"]) == 3

        result_filtered = agent._handle_client_list({"target_id": "target_A"})
        assert result_filtered["ok"] is True
        assert len(result_filtered["data"]["clients"]) == 2
        for client in result_filtered["data"]["clients"]:
            assert client["target_id"] == "target_A"

    def test_status_returns_full_dict_when_found(self):
        """Verify client.status returns complete client session dict."""
        agent = MockAgent()
        create_result = agent._handle_client_create({
            "target_id": "target_99999",
            "source": "api",
            "user_id": "user123",
        })
        client_session_id = create_result["data"]["client_session_id"]

        status_result = agent._handle_client_status({"client_session_id": client_session_id})

        assert status_result["ok"] is True
        data = status_result["data"]
        assert data["client_session_id"] == client_session_id
        assert data["target_id"] == "target_99999"
        assert data["source"] == "api"
        assert data["user_id"] == "user123"
        assert "created_at" in data
        assert "last_access_at" in data

    def test_status_not_found_returns_CLIENT_NOT_FOUND(self):
        """Verify client.status returns CLIENT_NOT_FOUND for missing session."""
        agent = MockAgent()
        result = agent._handle_client_status({"client_session_id": "client_nonexistent"})

        assert result["ok"] is False
        assert result["error_code"] == "CLIENT_NOT_FOUND"
        assert "client_nonexistent" in result["message"]

    def test_close_idempotent_returns_CLIENT_NOT_FOUND_second_call(self):
        """Verify client.close is idempotent: success first, CLIENT_NOT_FOUND second."""
        agent = MockAgent()
        create_result = agent._handle_client_create({
            "target_id": "target_close_test",
            "source": "internal",
        })
        client_session_id = create_result["data"]["client_session_id"]

        close_result_1 = agent._handle_client_close({"client_session_id": client_session_id})
        assert close_result_1["ok"] is True
        assert close_result_1["data"]["closed"] is True

        close_result_2 = agent._handle_client_close({"client_session_id": client_session_id})
        assert close_result_2["ok"] is False
        assert close_result_2["error_code"] == "CLIENT_NOT_FOUND"


class TestAgentClientHandlersIntegration:
    """Integration tests with real PeekaAgent if available."""

    def test_real_agent_client_create(self):
        """Test client.create with real agent instance."""
        try:
            from peeka.core.agent import PeekaAgent
        except ImportError:
            pytest.skip("PeekaAgent not available")

        session_id = f"test-client-create-{int(time.time())}"
        agent = PeekaAgent(session_id=session_id, attached_pid=12345)

        command = {
            "type": "client",
            "action": "create",
            "params": {"target_id": "target_real", "source": "cli"},
        }
        result = agent._execute_command(command)

        assert result["ok"] is True
        assert "data" in result
        assert result["data"]["target_id"] == "target_real"

    def test_real_agent_client_list(self):
        """Test client.list with real agent instance."""
        try:
            from peeka.core.agent import PeekaAgent
        except ImportError:
            pytest.skip("PeekaAgent not available")

        session_id = f"test-client-list-{int(time.time())}"
        agent = PeekaAgent(session_id=session_id, attached_pid=67890)

        agent._execute_command({
            "type": "client",
            "action": "create",
            "params": {"target_id": "target_list", "source": "tui"},
        })

        list_command = {"type": "client", "action": "list", "params": {}}
        result = agent._execute_command(list_command)

        assert result["ok"] is True
        assert "clients" in result["data"]
        assert len(result["data"]["clients"]) >= 1

    def test_real_agent_client_status(self):
        """Test client.status with real agent instance."""
        try:
            from peeka.core.agent import PeekaAgent
        except ImportError:
            pytest.skip("PeekaAgent not available")

        session_id = f"test-client-status-{int(time.time())}"
        agent = PeekaAgent(session_id=session_id, attached_pid=11111)

        create_result = agent._execute_command({
            "type": "client",
            "action": "create",
            "params": {"target_id": "target_status", "source": "mcp"},
        })
        client_session_id = create_result["data"]["client_session_id"]

        status_command = {
            "type": "client",
            "action": "status",
            "params": {"client_session_id": client_session_id},
        }
        result = agent._execute_command(status_command)

        assert result["ok"] is True
        assert result["data"]["client_session_id"] == client_session_id

    def test_real_agent_client_close(self):
        """Test client.close with real agent instance."""
        try:
            from peeka.core.agent import PeekaAgent
        except ImportError:
            pytest.skip("PeekaAgent not available")

        session_id = f"test-client-close-{int(time.time())}"
        agent = PeekaAgent(session_id=session_id, attached_pid=22222)

        create_result = agent._execute_command({
            "type": "client",
            "action": "create",
            "params": {"target_id": "target_close", "source": "api"},
        })
        client_session_id = create_result["data"]["client_session_id"]

        close_command = {
            "type": "client",
            "action": "close",
            "params": {"client_session_id": client_session_id},
        }
        result = agent._execute_command(close_command)

        assert result["ok"] is True
        assert result["data"]["closed"] is True
