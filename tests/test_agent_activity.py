"""Tests for agent-side activity logging."""

import json
import socket
import threading
from typing import List, Optional, Tuple

from peeka.core.agent import PeekaAgent


class TestAgentActivityLogging:
    """Verify agent activity logs surface useful client and command context."""

    def test_interesting_command_logs_client_lifecycle_and_result(self) -> None:
        """State-changing commands should log connect, request, result, and disconnect."""
        agent = PeekaAgent("test_session")
        logs: List[Tuple[str, str, Optional[str]]] = []

        agent._emit_log = lambda level, message, details=None: logs.append(  # type: ignore[method-assign]
            (level, message, details)
        )
        agent._execute_command = lambda command: {  # type: ignore[method-assign]
            "status": "success",
            "watch_id": "watch_001",
        }

        server_sock, client_sock = socket.socketpair()
        worker = threading.Thread(
            target=agent._handle_client,
            args=(server_sock, 7),
            daemon=True,
        )
        worker.start()

        try:
            command = {"type": "watch", "action": "start", "pattern": "pkg.func"}
            payload = json.dumps(command).encode("utf-8")
            client_sock.sendall(len(payload).to_bytes(4, "big"))
            client_sock.sendall(payload)

            response_len = int.from_bytes(client_sock.recv(4), "big")
            response = json.loads(client_sock.recv(response_len).decode("utf-8"))
            assert response["status"] == "success"
        finally:
            client_sock.close()
            worker.join(timeout=1.0)

        messages = [message for _, message, _ in logs]

        assert any("client#7 connected" in message for message in messages)
        assert any(
            "client#7 -> watch/start pattern=pkg.func" in message
            for message in messages
        )
        assert any(
            "client#7 watch/start pattern=pkg.func success watch_id=watch_001"
            in message
            for message in messages
        )
        assert any("client#7 disconnected" in message for message in messages)

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
            payload = json.dumps(command).encode("utf-8")
            client_sock.sendall(len(payload).to_bytes(4, "big"))
            client_sock.sendall(payload)

            response_len = int.from_bytes(client_sock.recv(4), "big")
            response = json.loads(client_sock.recv(response_len).decode("utf-8"))
            assert response["status"] == "success"
        finally:
            client_sock.close()
            worker.join(timeout=1.0)

        messages = [message for _, message, _ in logs]
        assert any("client#3 connected" in message for message in messages)
        assert any("client#3 disconnected" in message for message in messages)
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
            payload = json.dumps(command).encode("utf-8")
            client_sock.sendall(len(payload).to_bytes(4, "big"))
            client_sock.sendall(payload)

            response_len = int.from_bytes(client_sock.recv(4), "big")
            response = json.loads(client_sock.recv(response_len).decode("utf-8"))
            assert response["status"] == "error"
        finally:
            client_sock.close()
            worker.join(timeout=1.0)

        messages = [message for _, message, _ in logs]
        assert any(
            "client#11 vmtool/get target=sys.argv failed: remote exec failed"
            in message
            for message in messages
        )
