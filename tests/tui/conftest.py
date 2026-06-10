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
        "vms_bytes": 209715200,  # 200 MB
        "tracemalloc": {"enabled": False, "current_bytes": 0, "peak_bytes": 0},
        "gc": {"counts": [700, 10, 1], "thresholds": [700, 10, 10]},
    },
    "thread": {
        "status": "success",
        "total": 2,
        "threads": [
            {
                "tid": 1234,
                "name": "MainThread",
                "state": "RUNNABLE",
                "daemon": False,
                "stack_depth": 5,
                "top_frame": {
                    "filename": "test.py",
                    "lineno": 10,
                    "funcname": "main",
                },
            },
            {
                "tid": 5678,
                "name": "Worker-1",
                "state": "WAITING",
                "daemon": True,
                "stack_depth": 3,
                "top_frame": {
                    "filename": "threading.py",
                    "lineno": 300,
                    "funcname": "wait",
                },
            },
        ],
    },
    "top": {
        "status": "success",
        "type": "top_snapshot",
        "top_id": "top_001",
        "total_samples": 1000,
        "sample_interval": 0.01,
        "functions": [
            {"name": "process_request", "filename": "app/server.py", "line": 45, "own_pct": 25.3, "total_pct": 68.2, "own_time": 2.53, "total_time": 6.82, "own_count": 253, "total_count": 682},
            {"name": "parse_json", "filename": "app/parser.py", "line": 12, "own_pct": 18.7, "total_pct": 22.1, "own_time": 1.87, "total_time": 2.21, "own_count": 187, "total_count": 221},
            {"name": "query_db", "filename": "app/db.py", "line": 88, "own_pct": 15.2, "total_pct": 45.6, "own_time": 1.52, "total_time": 4.56, "own_count": 152, "total_count": 456},
            {"name": "serialize_response", "filename": "app/serializer.py", "line": 33, "own_pct": 8.4, "total_pct": 12.1, "own_time": 0.84, "total_time": 1.21, "own_count": 84, "total_count": 121},
            {"name": "validate_input", "filename": "app/validator.py", "line": 7, "own_pct": 5.1, "total_pct": 5.3, "own_time": 0.51, "total_time": 0.53, "own_count": 51, "total_count": 53},
        ]
    },
}


def make_patch_status_response(
    gevent_status: str = "active",
    backend: Optional[str] = None,
    downgraded: bool = False,
    degraded_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Return a patch-status response with the real command envelope shape."""
    if gevent_status == "not_imported":
        gevent: Any = "not_imported"
    else:
        gevent = {
            "status": gevent_status,
            "patched_modules": ["socket", "threading"],
        }

    payload: Dict[str, Any] = {
        "schema_version": "1",
        "pid": 12345,
        "timestamp": 1714972801.0,
        "monkey_patch": {
            "gevent": gevent,
            "eventlet": "not_imported",
        },
        "stdlib_origin": {},
        "asyncio_loop": {},
        "thread_model": {},
        "rpl_integrity": {"ok": True},
    }
    if backend is not None:
        payload["backend"] = backend
    if downgraded:
        payload["downgraded"] = True
    if degraded_reason is not None:
        payload["degraded_reason"] = degraded_reason

    return {"status": "success", "data": payload}


class MockStreamingAgentClient:
    """Mock implementation of StreamingAgentClient for TUI testing."""

    def __init__(
        self,
        responses: Optional[Dict[str, Dict[str, Any]]] = None,
        observations: Optional[List[Dict[str, Any]]] = None,
        should_fail_connect: bool = False,
        should_fail_send: bool = False,
        socket_path: str = "/tmp/peeka_mock.sock",
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
        self.socket_path = socket_path

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
