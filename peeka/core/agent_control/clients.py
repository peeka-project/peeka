"""AgentClientControlMixin implementation."""

import traceback
from typing import Any, Dict


class AgentClientControlMixin:
    def _handle_client_create(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.create command - create and register a client session."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict

            target_id = command.get("target_id", "")
            source = command.get("source", "")
            user_id = command.get("user_id")

            if not target_id:
                return self._client_error(
                    "UNSUPPORTED_CAPABILITY",
                    "target_id is required and cannot be empty",
                )

            valid_sources = {"cli", "tui", "mcp", "api", "internal"}
            if source not in valid_sources:
                return self._client_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"source must be one of {valid_sources}, got {source!r}",
                )

            registry = self._get_client_registry()
            client = registry.create(target_id=target_id, source=source, user_id=user_id)

            return self._client_success(client_to_dict(client))
        except Exception as e:
            result = self._client_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_client_list(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.list command - list client sessions optionally filtered by target_id."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict

            target_id = command.get("target_id")

            registry = self._get_client_registry()
            clients = registry.list(target_id=target_id)

            return self._client_success({"clients": [client_to_dict(c) for c in clients]})
        except Exception as e:
            result = self._client_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_client_status(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.status command - get client session details by ID."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict

            client_session_id = command.get("client_session_id", "")
            if not client_session_id:
                return self._client_error("CLIENT_NOT_FOUND", "client_session_id is required")

            registry = self._get_client_registry()
            client = registry.get(client_session_id)

            if client is None:
                return self._client_error(
                    "CLIENT_NOT_FOUND",
                    f"Client session {client_session_id!r} not found",
                )

            return self._client_success(client_to_dict(client))
        except Exception as e:
            result = self._client_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_client_close(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.close command - close a client session by ID."""
        try:
            client_session_id = command.get("client_session_id", "")
            if not client_session_id:
                return self._client_error("CLIENT_NOT_FOUND", "client_session_id is required")

            registry = self._get_client_registry()
            removed = registry.close(client_session_id)

            if not removed:
                return self._client_error(
                    "CLIENT_NOT_FOUND",
                    f"Client session {client_session_id!r} not found",
                )

            return self._client_success({"closed": True, "client_session_id": client_session_id})
        except Exception as e:
            result = self._client_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result
