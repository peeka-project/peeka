"""
Unit tests for peeka.core.client boundary conditions
"""

import json
import os
import socket
import threading
import time

from peeka.core.client import AgentClient, StreamingAgentClient


class TestAgentClientSocketNotFound:
    """Test AgentClient when socket doesn't exist."""

    def test_socket_not_found(self):
        """Test error when socket file doesn't exist."""
        client = AgentClient("/nonexistent/path/socket.sock")
        result = client.send_command({"cmd": "test"})

        assert result["status"] == "error"
        assert "not found" in result["error"]
        assert "hint" in result

    def test_socket_path_empty(self):
        """Test with empty socket path."""
        client = AgentClient("")
        result = client.send_command({"cmd": "test"})

        assert result["status"] == "error"


class TestAgentClientTimeout:
    """Test AgentClient timeout handling."""

    def test_connection_timeout(self, tmp_path):
        """Test timeout when server doesn't respond."""
        # Create a socket file but don't accept connections
        sock_path = str(tmp_path / "test.sock")

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)

        try:
            # Client with very short timeout
            client = AgentClient(sock_path, timeout=0.1)

            # Start a thread to accept but not respond
            def slow_server():
                conn, _ = server.accept()
                time.sleep(1)  # Don't respond
                conn.close()

            t = threading.Thread(target=slow_server)
            t.daemon = True
            t.start()

            result = client.send_command({"cmd": "test"})

            # Should get timeout error
            assert result["status"] == "error"
        finally:
            server.close()
            if os.path.exists(sock_path):
                os.unlink(sock_path)


class TestAgentClientRecvExact:
    """Test _recv_exact helper method."""

    def test_recv_exact_success(self, tmp_path):
        """Test successful exact receive."""
        sock_path = str(tmp_path / "test.sock")

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)

        try:

            def send_response():
                conn, _ = server.accept()
                # Read the request (length-prefixed protocol)
                length_bytes = conn.recv(4)
                if length_bytes:
                    length = int.from_bytes(length_bytes, "big")
                    conn.recv(length)  # Read the payload
                # Send response
                response = json.dumps({"status": "ok"}).encode()
                conn.sendall(len(response).to_bytes(4, "big"))
                conn.sendall(response)
                conn.close()

            t = threading.Thread(target=send_response)
            t.daemon = True
            t.start()

            client = AgentClient(sock_path, timeout=5.0)
            result = client.send_command({"cmd": "test"})

            assert result["status"] == "ok"
        finally:
            server.close()
            if os.path.exists(sock_path):
                os.unlink(sock_path)

    def test_send_command_attaches_default_client_info(self, tmp_path):
        """One-shot clients should also identify their process."""
        sock_path = str(tmp_path / "test.sock")
        received = []

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)

        try:

            def send_response():
                conn, _ = server.accept()
                length_bytes = conn.recv(4)
                if length_bytes:
                    length = int.from_bytes(length_bytes, "big")
                    received.append(json.loads(conn.recv(length).decode("utf-8")))
                response = json.dumps({"status": "ok"}).encode()
                conn.sendall(len(response).to_bytes(4, "big"))
                conn.sendall(response)
                conn.close()

            worker = threading.Thread(target=send_response, daemon=True)
            worker.start()

            client = AgentClient(sock_path, timeout=5.0)
            result = client.send_command({"cmd": "test"})

            assert result["status"] == "ok"
            assert received[0]["cmd"] == "test"
            assert received[0]["_client"]["kind"] == "cli"
            assert received[0]["_client"]["source"] == "request"
            assert received[0]["_client"]["id"].startswith("cli-")
        finally:
            server.close()
            if os.path.exists(sock_path):
                os.unlink(sock_path)


class TestStreamingAgentClientConnect:
    """Test StreamingAgentClient connection handling."""

    def test_connect_socket_not_found(self):
        """Test connect when socket doesn't exist."""
        client = StreamingAgentClient("/nonexistent/socket.sock")
        result = client.connect()

        assert result["status"] == "error"
        assert "not found" in result["error"]

    def test_connect_success(self, tmp_path):
        """Test successful connection."""
        sock_path = str(tmp_path / "test.sock")

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)

        try:
            client = StreamingAgentClient(sock_path)
            result = client.connect()

            assert result["status"] == "success"
            assert client._sock is not None
        finally:
            client.disconnect()
            server.close()
            if os.path.exists(sock_path):
                os.unlink(sock_path)


class TestStreamingAgentClientDisconnect:
    """Test StreamingAgentClient disconnect handling."""

    def test_disconnect_clears_state(self, tmp_path):
        """Test that disconnect clears socket and buffer."""
        sock_path = str(tmp_path / "test.sock")

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)

        try:
            client = StreamingAgentClient(sock_path)
            client.connect()
            client._buffer = b"some data"

            client.disconnect()

            assert client._sock is None
            assert client._buffer == b""
        finally:
            server.close()
            if os.path.exists(sock_path):
                os.unlink(sock_path)

    def test_disconnect_when_not_connected(self):
        """Test disconnect when not connected doesn't error."""
        client = StreamingAgentClient("/fake/path")
        client.disconnect()  # Should not raise

        assert client._sock is None


class TestStreamingAgentClientSendCommand:
    """Test StreamingAgentClient send_command method."""

    def test_send_command_not_connected(self):
        """Test send_command when not connected."""
        client = StreamingAgentClient("/fake/path")
        result = client.send_command({"cmd": "test"})

        assert result["status"] == "error"
        assert "Not connected" in result["error"]

    def test_send_command_attaches_client_info(self, tmp_path):
        """Persistent TUI clients identify on connect and on each command."""
        sock_path = str(tmp_path / "test.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)
        received = []
        client = None

        try:

            def respond_success():
                conn, _ = server.accept()
                for _ in range(2):
                    length_bytes = conn.recv(4)
                    if length_bytes:
                        length = int.from_bytes(length_bytes, "big")
                        received.append(json.loads(conn.recv(length).decode("utf-8")))
                    response = json.dumps({"status": "success"}).encode()
                    conn.sendall(len(response).to_bytes(4, "big"))
                    conn.sendall(response)
                conn.close()

            worker = threading.Thread(target=respond_success, daemon=True)
            worker.start()

            client = StreamingAgentClient(
                sock_path,
                client_info={
                    "id": "tui-abc123",
                    "kind": "tui",
                    "source": "watch-stream",
                    "pid": 42,
                },
            )
            assert client.connect()["status"] == "success"

            result = client.send_command(
                {"type": "watch", "action": "start", "pattern": "pkg.func"}
            )

            assert result["status"] == "success"
            assert received[0]["type"] == "client"
            assert received[0]["action"] == "hello"
            assert received[0]["_client"] == {
                "id": "tui-abc123",
                "kind": "tui",
                "source": "watch-stream",
                "pid": 42,
            }
            assert received[1]["_client"] == {
                "id": "tui-abc123",
                "kind": "tui",
                "source": "watch-stream",
                "pid": 42,
            }
            assert received[1]["type"] == "watch"
        finally:
            if client is not None:
                client.disconnect()
            server.close()
            if os.path.exists(sock_path):
                os.unlink(sock_path)


class TestStreamingAgentClientExtractObservation:
    """Test _extract_observation method."""

    def test_extract_complete_observation(self):
        """Test extracting complete observation from buffer."""
        client = StreamingAgentClient("/fake/path")

        obs_data = json.dumps({"func": "test", "result": 42}).encode()
        # OBS: prefix + 4 bytes length + data
        client._buffer = b"OBS:" + len(obs_data).to_bytes(4, "big") + obs_data

        result = client._extract_observation()

        assert result is not None
        assert result["func"] == "test"
        assert result["result"] == 42
        assert client._buffer == b""  # Buffer should be empty

    def test_extract_incomplete_observation(self):
        """Test extracting incomplete observation returns None."""
        client = StreamingAgentClient("/fake/path")

        # Only prefix and length, no data
        client._buffer = b"OBS:" + (100).to_bytes(4, "big")

        result = client._extract_observation()

        assert result is None
        assert len(client._buffer) > 0  # Buffer unchanged

    def test_extract_no_prefix(self):
        """Test extracting when no OBS: prefix."""
        client = StreamingAgentClient("/fake/path")
        client._buffer = b"garbage data"

        result = client._extract_observation()

        assert result is None

    def test_extract_with_garbage_before_prefix(self):
        """Test extracting when there's garbage before OBS: prefix."""
        client = StreamingAgentClient("/fake/path")

        obs_data = json.dumps({"test": True}).encode()
        # Garbage + OBS: prefix + length + data
        client._buffer = (
            b"garbage" + b"OBS:" + len(obs_data).to_bytes(4, "big") + obs_data
        )

        result = client._extract_observation()

        assert result is not None
        assert result["test"] is True

    def test_extract_invalid_json(self):
        """Test extracting when JSON is invalid."""
        client = StreamingAgentClient("/fake/path")

        invalid_data = b"not valid json"
        client._buffer = b"OBS:" + len(invalid_data).to_bytes(4, "big") + invalid_data

        result = client._extract_observation()

        assert result is None  # Should return None on JSON error

    def test_extract_multiple_observations(self):
        """Test extracting multiple observations sequentially."""
        client = StreamingAgentClient("/fake/path")

        obs1 = json.dumps({"n": 1}).encode()
        obs2 = json.dumps({"n": 2}).encode()

        client._buffer = (
            b"OBS:"
            + len(obs1).to_bytes(4, "big")
            + obs1
            + b"OBS:"
            + len(obs2).to_bytes(4, "big")
            + obs2
        )

        result1 = client._extract_observation()
        assert result1["n"] == 1

        result2 = client._extract_observation()
        assert result2["n"] == 2

        result3 = client._extract_observation()
        assert result3 is None


class TestStreamingAgentClientContextManager:
    """Test context manager protocol."""

    def test_context_manager(self, tmp_path):
        """Test using client as context manager."""
        sock_path = str(tmp_path / "test.sock")

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)

        try:
            with StreamingAgentClient(sock_path) as client:
                assert client._sock is not None

            # After exiting context, should be disconnected
            assert client._sock is None
        finally:
            server.close()
            if os.path.exists(sock_path):
                os.unlink(sock_path)


class TestStreamingAgentClientActivityReporting:
    """Test client-side activity reporting hooks."""

    def test_connect_failure_reports_activity(self):
        """Missing sockets should emit a client activity error."""
        events = []
        client = StreamingAgentClient(
            "/nonexistent/socket.sock",
            activity_reporter=lambda level, message: events.append((level, message)),
        )

        result = client.connect()

        assert result["status"] == "error"
        assert any("connect failed" in message for _, message in events)

    def test_send_command_error_response_reports_activity(self, tmp_path):
        """Agent error responses should be mirrored into client activity logs."""
        sock_path = str(tmp_path / "test.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)
        events = []
        client = None

        try:

            def respond_with_error():
                conn, _ = server.accept()
                length_bytes = conn.recv(4)
                if length_bytes:
                    length = int.from_bytes(length_bytes, "big")
                    conn.recv(length)
                response = json.dumps({"status": "error", "error": "boom"}).encode()
                conn.sendall(len(response).to_bytes(4, "big"))
                conn.sendall(response)
                conn.close()

            worker = threading.Thread(target=respond_with_error, daemon=True)
            worker.start()

            client = StreamingAgentClient(
                sock_path,
                activity_reporter=lambda level, message: events.append((level, message)),
            )
            assert client.connect()["status"] == "success"

            result = client.send_command(
                {"type": "watch", "action": "start", "pattern": "pkg.func"}
            )

            assert result["status"] == "error"
            assert any(
                "watch/start pattern=pkg.func failed: boom" in message
                for _, message in events
            )
        finally:
            if client is not None:
                client.disconnect()
            server.close()
            if os.path.exists(sock_path):
                os.unlink(sock_path)

    def test_stream_close_reports_activity(self, tmp_path):
        """Unexpected stream closure should emit a client activity warning."""
        sock_path = str(tmp_path / "test.sock")
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(sock_path)
        server.listen(1)
        events = []
        client = None

        try:

            def close_immediately():
                conn, _ = server.accept()
                conn.close()

            worker = threading.Thread(target=close_immediately, daemon=True)
            worker.start()

            client = StreamingAgentClient(
                sock_path,
                activity_reporter=lambda level, message: events.append((level, message)),
            )
            assert client.connect()["status"] == "success"

            list(client.stream_observations())

            assert any(
                "observation stream closed by peer" in message
                for _, message in events
            )
        finally:
            if client is not None:
                client.disconnect()
            server.close()
            if os.path.exists(sock_path):
                os.unlink(sock_path)
