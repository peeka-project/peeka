"""Agent log broadcast must not let one non-reading client freeze the agent."""

import socket
import threading
import time
from typing import List

import pytest

from peeka.core.agent import PeekaAgent


def _make_agent() -> PeekaAgent:
    agent = PeekaAgent("log-broadcast-test")
    agent._LOG_SEND_TIMEOUT = 0.2  # type: ignore[misc]
    return agent


def _stuck_pair() -> "tuple[socket.socket, socket.socket]":
    """Return (server, client) where the client never reads and buffers are tiny."""
    server, client = socket.socketpair()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4096)
    client.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    return server, client


def _drain_log_frames(sock: socket.socket, timeout: float = 0.5) -> int:
    """Read LOG frames until the socket goes quiet; return how many arrived."""
    sock.settimeout(timeout)
    count = 0
    buffer = b""
    try:
        while True:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buffer += chunk
            while len(buffer) >= 8 and buffer.startswith(b"LOG:"):
                size = int.from_bytes(buffer[4:8], "big")
                if len(buffer) < 8 + size:
                    break
                buffer = buffer[8 + size:]
                count += 1
    except socket.timeout:
        pass
    return count


@pytest.mark.unit
class TestLogBroadcastWithStuckClient:
    def test_stuck_client_is_evicted_and_others_keep_receiving(self) -> None:
        agent = _make_agent()
        stuck_server, stuck_client = _stuck_pair()
        live_server, live_client = socket.socketpair()
        received: List[int] = []
        reader = threading.Thread(
            target=lambda: received.append(_drain_log_frames(live_client, timeout=1.0)),
            daemon=True,
        )
        try:
            agent._register_client_connection(stuck_server, kind="stream")
            agent._register_client_connection(live_server, kind="stream")
            reader.start()

            broadcaster = threading.Thread(
                target=lambda: [agent._send_log("INFO", "x" * 200) for _ in range(500)],
                daemon=True,
            )
            started = time.monotonic()
            broadcaster.start()
            broadcaster.join(timeout=5.0)

            assert not broadcaster.is_alive(), "log broadcast blocked on a non-reading client"
            assert time.monotonic() - started < 5.0
            connections = agent._snapshot_client_connections()
            assert stuck_server not in connections
            assert live_server in connections

            reader.join(timeout=3.0)
            assert received and received[0] == 500
        finally:
            agent._unregister_client_connection(stuck_server)
            agent._unregister_client_connection(live_server)
            for sock in (stuck_server, stuck_client, live_server, live_client):
                sock.close()

    def test_evicted_client_sees_the_connection_close(self) -> None:
        agent = _make_agent()
        stuck_server, stuck_client = _stuck_pair()
        try:
            agent._register_client_connection(stuck_server, kind="stream")
            for _ in range(500):
                agent._send_log("INFO", "x" * 200)
                if stuck_server not in agent._snapshot_client_connections():
                    break
            assert stuck_server not in agent._snapshot_client_connections()

            stuck_client.settimeout(1.0)
            while True:
                chunk = stuck_client.recv(65536)
                if not chunk:
                    break
        finally:
            stuck_server.close()
            stuck_client.close()

    def test_busy_writer_skips_frame_without_evicting(self) -> None:
        agent = _make_agent()
        server, client = socket.socketpair()
        try:
            agent._register_client_connection(server, kind="stream")
            write_lock = agent._client_write_locks[server]
            write_lock.acquire()
            try:
                assert agent._send_frame_bounded(server, b"LOG:\x00\x00\x00\x00", 0.05) is None
                agent._send_log("INFO", "while another writer holds the socket")
            finally:
                write_lock.release()

            assert server in agent._snapshot_client_connections()
            agent._send_log("INFO", "after release")
            assert _drain_log_frames(client) == 1
        finally:
            agent._unregister_client_connection(server)
            server.close()
            client.close()

    def test_bounded_send_writes_whole_frame(self) -> None:
        agent = _make_agent()
        server, client = socket.socketpair()
        try:
            agent._register_client_connection(server, kind="stream")
            frame = b"LOG:" + (3).to_bytes(4, "big") + b"abc"
            assert agent._send_frame_bounded(server, frame, 0.5) is True
            client.settimeout(0.5)
            assert client.recv(64) == frame
        finally:
            agent._unregister_client_connection(server)
            server.close()
            client.close()

    def test_control_connections_do_not_receive_log_frames(self) -> None:
        """A control client only reads while awaiting its own reply."""
        agent = _make_agent()
        control_server, control_client = _stuck_pair()
        stream_server, stream_client = socket.socketpair()
        try:
            agent._register_client_connection(control_server)
            agent._register_client_connection(stream_server, kind="stream")
            for _ in range(20):
                agent._send_log("INFO", "x" * 200)

            assert control_server in agent._snapshot_client_connections()
            control_client.setblocking(False)
            with pytest.raises(BlockingIOError):
                control_client.recv(1)
            assert _drain_log_frames(stream_client) == 20
        finally:
            for conn in (control_server, stream_server):
                agent._unregister_client_connection(conn)
            for sock in (control_server, control_client, stream_server, stream_client):
                sock.close()
