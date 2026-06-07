import json
import socket
import threading
from typing import Any, Dict, List, Optional, cast

import pytest

from peeka.core.agent import PeekaAgent


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    """Receive exactly *size* bytes or b'' on timeout/close."""
    chunks: List[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            return b""
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_response(sock: socket.socket) -> Dict[str, Any]:
    """Read the next JSON response, skipping streamed OBS/LOG frames."""
    while True:
        header = _recv_exact(sock, 4)
        assert header, "connection closed before response"
        if header in (b"OBS:", b"LOG:"):
            payload_length = int.from_bytes(_recv_exact(sock, 4), "big")
            assert _recv_exact(sock, payload_length)
            continue

        payload_length = int.from_bytes(header, "big")
        payload = _recv_exact(sock, payload_length)
        assert payload, "response payload missing"
        return json.loads(payload.decode("utf-8"))


class _SlowConnection:
    """Fake peer that blocks observation writes until released."""

    def __init__(self, entered_event: threading.Event, release_event: threading.Event):
        self.entered_event = entered_event
        self.release_event = release_event

    def sendall(self, frame: bytes) -> None:
        if frame.startswith(b"OBS:"):
            self.entered_event.set()
            assert self.release_event.wait(timeout=2.0)


class TestAgentTransport:
    @pytest.mark.parametrize(
        "stream_source",
        [
            "watch-stream",
            "trace-stream",
            "stack-stream",
            "monitor-stream",
            "dashboard-stream",
        ],
    )
    def test_stream_identity_receives_observations_after_hello(
        self, stream_source: str
    ) -> None:
        """TUI stream-only clients should receive OBS after client hello."""
        agent = PeekaAgent("transport-test")
        agent._emit_log = lambda level, message, details=None: None  # type: ignore[method-assign]

        server_sock, client_sock = socket.socketpair()
        worker = threading.Thread(
            target=agent._handle_client,
            args=(server_sock, 1),
            daemon=True,
        )
        worker.start()

        try:
            client_sock.settimeout(0.5)
            command = json.dumps(
                {
                    "type": "client",
                    "action": "hello",
                    "_client": {
                        "id": "tui-test01",
                        "kind": "tui",
                        "source": stream_source,
                        "pid": 12345,
                    },
                }
            ).encode("utf-8")
            client_sock.sendall(len(command).to_bytes(4, "big"))
            client_sock.sendall(command)
            response = _recv_response(client_sock)
            assert response["status"] == "success"

            agent._send_observation({"event_id": "evt_1", "probe_id": "prb_stream"})

            assert _recv_exact(client_sock, 4) == b"OBS:"
        finally:
            client_sock.close()
            worker.join(timeout=1.0)

    def test_observations_only_broadcast_to_stream_connections(self) -> None:
        """Control connections should not receive unrelated OBS frames."""
        agent = PeekaAgent("transport-test")

        control_server, control_client = socket.socketpair()
        stream_server, stream_client = socket.socketpair()

        try:
            agent._register_client_connection(control_server)
            agent._register_client_connection(stream_server)
            agent._set_client_connection_kind(stream_server, "stream")

            control_client.settimeout(0.2)
            stream_client.settimeout(0.5)

            agent._send_observation({"event_id": "evt_1", "probe_id": "prb_stream"})

            with pytest.raises(socket.timeout):
                control_client.recv(1)

            assert _recv_exact(stream_client, 4) == b"OBS:"
        finally:
            agent._unregister_client_connection(control_server)
            agent._unregister_client_connection(stream_server)
            control_server.close()
            control_client.close()
            stream_server.close()
            stream_client.close()

    def test_response_not_blocked_by_stalled_stream_broadcast(self) -> None:
        """Control-plane responses should not wait on unrelated stalled peers."""
        agent = PeekaAgent("transport-test")
        agent._emit_log = lambda level, message, details=None: None  # type: ignore[method-assign]

        command_started = threading.Event()
        allow_response = threading.Event()
        slow_send_entered = threading.Event()
        release_slow_send = threading.Event()

        def execute_command(command: Dict[str, Any]) -> Dict[str, Any]:
            command_started.set()
            assert allow_response.wait(timeout=2.0)
            return {"status": "success", "probe": command.get("probe")}

        agent._execute_command = execute_command  # type: ignore[method-assign]

        slow_conn = _SlowConnection(slow_send_entered, release_slow_send)
        slow_conn_key = cast(Any, slow_conn)
        agent._register_client_connection(slow_conn_key)
        agent._set_client_connection_kind(slow_conn_key, "stream")

        server_sock, client_sock = socket.socketpair()
        worker = threading.Thread(
            target=agent._handle_client,
            args=(server_sock, 1),
            daemon=True,
        )
        worker.start()

        broadcaster: Optional[threading.Thread] = None
        try:
            client_sock.settimeout(0.5)
            command = json.dumps(
                {"type": "probe", "action": "stop", "probe": "prb_test"}
            ).encode("utf-8")
            client_sock.sendall(len(command).to_bytes(4, "big"))
            client_sock.sendall(command)

            assert command_started.wait(timeout=1.0)

            broadcaster = threading.Thread(
                target=agent._send_observation,
                args=({"event_id": "evt_1", "probe_id": "prb_stream"},),
                daemon=True,
            )
            broadcaster.start()
            assert slow_send_entered.wait(timeout=1.0)

            allow_response.set()
            response = _recv_response(client_sock)
            assert response["status"] == "success"
            assert response["probe"] == "prb_test"
        finally:
            release_slow_send.set()
            if broadcaster is not None:
                broadcaster.join(timeout=1.0)
            client_sock.close()
            worker.join(timeout=1.0)
