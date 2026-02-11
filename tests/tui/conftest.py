"""Shared fixtures and mocks for TUI testing."""

import pytest
from typing import Any, Dict, Generator, List, Optional


DEFAULT_RESPONSES = {
    "vmtool": {
        "status": "success",
        "value": "3.12.0 (main, Jan 1 2025, 00:00:00) [GCC 11.4.0]",
    },
    "memory": {
        "status": "success",
        "rss_bytes": 52428800,  # 50 MB
        "tracemalloc": {"enabled": False, "current_bytes": 0, "peak_bytes": 0},
        "gc": {"counts": [700, 10, 1]},
    },
}


class MockStreamingAgentClient:
    """Mock implementation of StreamingAgentClient for TUI testing."""

    def __init__(
        self,
        responses: Optional[Dict[str, Dict[str, Any]]] = None,
        observations: Optional[List[Dict[str, Any]]] = None,
        should_fail_connect: bool = False,
        should_fail_send: bool = False,
    ):
        """
        Initialize mock client.

        Args:
            responses: Command responses keyed by command type
            observations: List of observations to yield from stream
            should_fail_connect: If True, connect() returns error
            should_fail_send: If True, send_command() returns error
        """
        self.responses = responses or {}
        self.observations = observations or []
        self.connected = False
        self.commands_received: List[Dict[str, Any]] = []
        self._should_fail_connect = should_fail_connect
        self._should_fail_send = should_fail_send

    def connect(self) -> Dict[str, Any]:
        """Connect to agent socket (mock)."""
        if self._should_fail_connect:
            return {"status": "error", "error": "Mock connection failure"}
        self.connected = True
        return {"status": "success"}

    def disconnect(self) -> None:
        """Close connection (mock)."""
        self.connected = False

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send command and receive response (mock)."""
        if not self.connected:
            return {"status": "error", "error": "Not connected"}

        self.commands_received.append(command)

        if self._should_fail_send:
            return {"status": "error", "error": "Mock send failure"}

        command_type = command.get("type")
        if command_type in self.responses:
            return self.responses[command_type]

        return {"status": "error", "error": f"Unknown command type: {command_type}"}

    def stream_observations(self) -> Generator[Dict[str, Any], None, None]:
        """Yield observations as they arrive (mock - finite generator)."""
        if not self.connected:
            return
        yield from list(self.observations)

    def __enter__(self) -> "MockStreamingAgentClient":
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.disconnect()


@pytest.fixture
def mock_client() -> MockStreamingAgentClient:
    """Fixture providing mock client with default responses."""
    return MockStreamingAgentClient(responses=DEFAULT_RESPONSES)


@pytest.fixture
def mock_client_factory():
    """Factory fixture for creating customized mock clients."""

    def _create(
        responses: Optional[Dict[str, Dict[str, Any]]] = None,
        observations: Optional[List[Dict[str, Any]]] = None,
        should_fail_connect: bool = False,
        should_fail_send: bool = False,
    ) -> MockStreamingAgentClient:
        return MockStreamingAgentClient(
            responses=responses,
            observations=observations,
            should_fail_connect=should_fail_connect,
            should_fail_send=should_fail_send,
        )

    return _create
