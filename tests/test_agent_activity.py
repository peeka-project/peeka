"""Tests for agent-side activity logging."""

import json
import socket
import threading
from typing import List, Optional, Tuple

from peeka.core.agent import PeekaAgent


def _send_command(
    client_sock: socket.socket,
    command: dict,
    instance_id: str = "tui-test01",
    source: str = "main",
) -> dict:
    command = dict(command)
    command["_client"] = {
        "id": instance_id,
        "kind": "tui",
        "source": source,
        "pid": 12345,
    }
    payload = json.dumps(command).encode("utf-8")
    client_sock.sendall(len(payload).to_bytes(4, "big"))
    client_sock.sendall(payload)

    response_len = int.from_bytes(client_sock.recv(4), "big")
    return json.loads(client_sock.recv(response_len).decode("utf-8"))


class TestAgentActivityLogging:
    """Verify agent activity logs surface useful client and command context."""

    def test_interesting_command_logs_client_lifecycle_and_result(self) -> None:
        """State-changing commands should log connect, request, result, and disconnect."""
        agent = PeekaAgent("test_session")
        logs: List[Tuple[str, str, Optional[str]]] = []
        handled_commands = []

        agent._emit_log = lambda level, message, details=None: logs.append(  # type: ignore[method-assign]
            (level, message, details)
        )

        def execute_command(command: dict) -> dict:
            handled_commands.append(command)
            return {"status": "success", "watch_id": "watch_001"}

        agent._execute_command = execute_command  # type: ignore[method-assign]

        server_sock, client_sock = socket.socketpair()
        worker = threading.Thread(
            target=agent._handle_client,
            args=(server_sock, 7),
            daemon=True,
        )
        worker.start()

        try:
            command = {"type": "watch", "action": "start", "pattern": "pkg.func"}
            response = _send_command(client_sock, command, source="watch-stream")
            assert response["status"] == "success"
        finally:
            client_sock.close()
            worker.join(timeout=1.0)

        messages = [message for _, message, _ in logs]

        client_label = "client tui-test01/watch-stream conn#7"
        assert any("conn#7 connected" in message for message in messages)
        assert any(
            f"{client_label} identified kind=tui pid=12345" in message
            for message in messages
        )
        assert any(
            f"{client_label} -> watch/start pattern=pkg.func" in message
            for message in messages
        )
        assert any(
            f"{client_label} watch/start pattern=pkg.func success watch_id=watch_001"
            in message
            for message in messages
        )
        assert any(f"{client_label} disconnected" in message for message in messages)
        assert handled_commands == [
            {"type": "watch", "action": "start", "pattern": "pkg.func"}
        ]

    def test_quiet_command_success_is_not_logged(self) -> None:
        """Dashboard poll-style read commands should stay out of the activity log."""
        agent = PeekaAgent("test_session")
        logs: List[Tuple[str, str, Optional[str]]] = []

        agent._emit_log = lambda level, message, details=None: logs.append(  # type: ignore[method-assign]
            (level, message, details)
        )
        agent._execute_command = lambda command: {"status": "success", "value": "3.12"}  # type: ignore[method-assign]

        server_sock, client_sock = socket.socketpair()
        worker = threading.Thread(
            target=agent._handle_client,
            args=(server_sock, 3),
            daemon=True,
        )
        worker.start()

        try:
            command = {"type": "vmtool", "action": "get", "target": "sys.version"}
            response = _send_command(client_sock, command, source="dashboard-data")
            assert response["status"] == "success"
        finally:
            client_sock.close()
            worker.join(timeout=1.0)

        messages = [message for _, message, _ in logs]
        client_label = "client tui-test01/dashboard-data conn#3"
        assert any("conn#3 connected" in message for message in messages)
        assert any(f"{client_label} disconnected" in message for message in messages)
        assert not any("vmtool/get" in message for message in messages)

    def test_quiet_command_error_is_still_logged(self) -> None:
        """Read commands should still produce an error activity entry when they fail."""
        agent = PeekaAgent("test_session")
        logs: List[Tuple[str, str, Optional[str]]] = []

        agent._emit_log = lambda level, message, details=None: logs.append(  # type: ignore[method-assign]
            (level, message, details)
        )
        agent._execute_command = lambda command: {  # type: ignore[method-assign]
            "status": "error",
            "error": "remote exec failed",
        }

        server_sock, client_sock = socket.socketpair()
        worker = threading.Thread(
            target=agent._handle_client,
            args=(server_sock, 11),
            daemon=True,
        )
        worker.start()

        try:
            command = {"type": "vmtool", "action": "get", "target": "sys.argv"}
            response = _send_command(client_sock, command, source="memory-data")
            assert response["status"] == "error"
        finally:
            client_sock.close()
            worker.join(timeout=1.0)

        messages = [message for _, message, _ in logs]
        assert any(
            "client tui-test01/memory-data conn#11 vmtool/get target=sys.argv "
            "failed: remote exec failed"
            in message
            for message in messages
        )
