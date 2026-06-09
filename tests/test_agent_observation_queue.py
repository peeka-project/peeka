import json
import socket
import threading
import time
from typing import Any, Dict, List, Optional, cast
from unittest.mock import Mock

import pytest

from peeka.core import agent as agent_module
from peeka.core.agent import PeekaAgent


OBSERVATION_QUEUE_CAPACITY = 1024
STOP_DRAIN_BOUND_SECONDS = 0.4


def _make_agent() -> PeekaAgent:
    agent = PeekaAgent("observation-queue-test")
    agent._emit_log = lambda level, message, details=None: None  # type: ignore[method-assign]
    return agent


def _recv_exact(sock: socket.socket, size: int, timeout: float = 0.5) -> bytes:
    sock.settimeout(timeout)
    chunks: List[bytes] = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            return b""
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_obs(sock: socket.socket, timeout: float = 0.5) -> Dict[str, Any]:
    assert _recv_exact(sock, 4, timeout=timeout) == b"OBS:"
    payload_length = int.from_bytes(_recv_exact(sock, 4, timeout=timeout), "big")
    payload = _recv_exact(sock, payload_length, timeout=timeout)
    assert payload
    return json.loads(payload.decode("utf-8"))


def _recv_obs_until(
    sock: socket.socket, expected_count: int, timeout: float = 2.0
) -> List[Dict[str, Any]]:
    deadline = time.monotonic() + timeout
    observations: List[Dict[str, Any]] = []
    while len(observations) < expected_count and time.monotonic() < deadline:
        remaining = max(0.01, deadline - time.monotonic())
        try:
            observations.append(_recv_obs(sock, timeout=remaining))
        except socket.timeout:
            break
    return observations


def _connection_registered(agent: PeekaAgent, conn: socket.socket) -> bool:
    return conn in agent._snapshot_client_connections(kind="stream")


def _observation_queues(agent: PeekaAgent) -> Dict[Any, Any]:
    assert hasattr(agent, "_observation_queues"), (
        "PeekaAgent must maintain per-connection observation queues at "
        "agent._observation_queues"
    )
    queues = getattr(agent, "_observation_queues")
    assert isinstance(queues, dict)
    return queues


def _observation_queue_stats(agent: PeekaAgent) -> Dict[Any, Any]:
    assert hasattr(agent, "_observation_queue_stats"), (
        "PeekaAgent must expose per-connection observation queue stats at "
        "agent._observation_queue_stats"
    )
    stats = getattr(agent, "_observation_queue_stats")
    assert isinstance(stats, dict)
    return stats


def _dropped_count(stats: Any) -> int:
    if isinstance(stats, dict):
        value = stats.get("dropped_count")
    else:
        value = getattr(stats, "dropped_count", None)
    assert isinstance(value, int), "queue stats must expose integer dropped_count"
    return value


def _drain_dropped_count(stats: Any) -> int:
    if isinstance(stats, dict):
        value = stats.get("drain_dropped_count")
    else:
        value = getattr(stats, "drain_dropped_count", None)
    assert isinstance(value, int), "queue stats must expose integer drain_dropped_count"
    return value


def _slow_evicted_count(stats: Any) -> int:
    if isinstance(stats, dict):
        value = stats.get("slow_evicted_count", stats.get("evicted_count", 0))
    else:
        value = getattr(stats, "slow_evicted_count", getattr(stats, "evicted_count", 0))
    assert isinstance(value, int), "queue stats slow eviction counter must be an int"
    return value


def _split_obs_frames(frames: bytes) -> List[bytes]:
    offset = 0
    parsed: List[bytes] = []
    while offset < len(frames):
        assert frames[offset : offset + 4] == b"OBS:"
        payload_length = int.from_bytes(frames[offset + 4 : offset + 8], "big")
        frame_end = offset + 8 + payload_length
        parsed.append(frames[offset:frame_end])
        offset = frame_end
    return parsed


def _make_raw_obs_frame(payload_size: int) -> bytes:
    return b"OBS:" + payload_size.to_bytes(4, "big") + (b"x" * payload_size)


def _make_obs_frame(event_id: str) -> bytes:
    payload = json.dumps(
        {"type": "observation", "event_id": event_id, "probe_id": "prb_queue"}
    ).encode("utf-8")
    return b"OBS:" + len(payload).to_bytes(4, "big") + payload


class _SendallSpyConnection:
    def __init__(self, sock: socket.socket):
        self.sock = sock
        self.sendall = Mock()

    def close(self) -> None:
        self.sock.close()


class _BlockingForwardingConnection:
    def __init__(
        self,
        sock: socket.socket,
        entered_event: threading.Event,
        release_event: threading.Event,
    ):
        self.sock = sock
        self.entered_event = entered_event
        self.release_event = release_event

    def sendall(self, frame: bytes) -> None:
        if frame.startswith(b"OBS:"):
            self.entered_event.set()
            assert self.release_event.wait(timeout=2.0)
        self.sock.sendall(frame)

    def close(self) -> None:
        self.sock.close()


class _FailingBindSocket:
    def __init__(self) -> None:
        self.closed = False

    def bind(self, path: str) -> None:
        raise OSError("bind failed")

    def close(self) -> None:
        self.closed = True


class _BlockingObservationConnection:
    def __init__(self, entered_event: threading.Event, release_event: threading.Event):
        self.entered_event = entered_event
        self.release_event = release_event

    def sendall(self, frame: bytes) -> None:
        if frame.startswith(b"OBS:"):
            self.entered_event.set()
            assert self.release_event.wait(timeout=2.0)

    def close(self) -> None:
        self.release_event.set()


@pytest.mark.unit
class TestObservationQueueDataStructures:
    def test_per_connection_queue_exists_after_stream_register(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()

        try:
            agent._register_client_connection(server_sock, kind="stream")

            queues = _observation_queues(agent)
            assert server_sock in queues
            assert queues[server_sock].maxsize == OBSERVATION_QUEUE_CAPACITY
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()

    def test_unregister_stream_connection_removes_queue_state(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()

        try:
            agent._register_client_connection(server_sock, kind="stream")
            queues = _observation_queues(agent)
            stats = _observation_queue_stats(agent)
            flushers = getattr(agent, "_observation_queue_flushers")

            assert server_sock in queues
            assert server_sock in stats
            assert server_sock in flushers

            connection_count = agent._unregister_client_connection(server_sock)

            assert connection_count == 0
            assert server_sock not in queues
            assert server_sock not in stats
            assert server_sock not in flushers
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()


@pytest.mark.unit
class TestObservationEnqueuePath:
    def test_enqueue_does_not_call_sendall_synchronously(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()
        spy_conn = cast(socket.socket, cast(object, _SendallSpyConnection(server_sock)))

        try:
            agent._register_client_connection(spy_conn, kind="stream")

            agent._send_observation({"event_id": "evt_sync", "probe_id": "prb_queue"})

            cast(Any, spy_conn).sendall.assert_not_called()
        finally:
            agent._unregister_client_connection(spy_conn)
            cast(Any, spy_conn).close()
            client_sock.close()


@pytest.mark.unit
class TestObservationQueueStats:
    def test_dropped_counter_increments_on_overflow(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()

        try:
            agent._register_client_connection(server_sock, kind="stream")
            queues = _observation_queues(agent)
            stats = _observation_queue_stats(agent)
            queue = queues[server_sock]

            for index in range(OBSERVATION_QUEUE_CAPACITY):
                queue.put_nowait(b"OBS:" + index.to_bytes(4, "big"))

            before = _dropped_count(stats[server_sock])
            agent._send_observation({"event_id": "evt_overflow", "probe_id": "prb_queue"})

            assert _dropped_count(stats[server_sock]) == before + 1
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()


@pytest.mark.unit
class TestObservationQueueFlusher:
    def test_flusher_delivers_frames_as_OBS_format(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()

        try:
            agent._register_client_connection(server_sock, kind="stream")
            assert hasattr(agent, "_observation_queue_flushers"), (
                "PeekaAgent must start one observation queue flusher per stream connection"
            )
            assert server_sock in getattr(agent, "_observation_queue_flushers")

            agent._send_observation({"event_id": "evt_flush", "probe_id": "prb_queue"})

            observation = _recv_obs(client_sock)
            assert observation["type"] == "observation"
            assert observation["event_id"] == "evt_flush"
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()

    def test_flush_keeps_items_beyond_batch_count_limit(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()
        sent_frames: List[bytes] = []

        def capture_send(conn: socket.socket, frames: bytes, timeout: float = 0.1) -> bool:
            sent_frames.append(frames)
            return True

        agent._send_observation_frames_with_timeout = capture_send  # type: ignore[method-assign]

        try:
            queue = agent._get_or_create_connection_queue(server_sock)
            for index in range(65):
                queue.append(_make_obs_frame(f"evt_batch_{index}"))

            assert agent._flush_connection(server_sock) is True

            assert len(sent_frames) == 1
            assert len(_split_obs_frames(sent_frames[0])) == 64
            assert len(queue) == 1
            assert queue[0] == _make_obs_frame("evt_batch_64")
            assert _observation_queue_stats(agent)[server_sock]["delivered"] == 64
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()

    def test_flush_keeps_item_that_exceeds_batch_bytes_limit(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()
        sent_frames: List[bytes] = []

        def capture_send(conn: socket.socket, frames: bytes, timeout: float = 0.1) -> bool:
            sent_frames.append(frames)
            return True

        agent._send_observation_frames_with_timeout = capture_send  # type: ignore[method-assign]

        try:
            first = _make_raw_obs_frame(100_000)
            second = _make_raw_obs_frame(100_000)
            third = _make_raw_obs_frame(100_000)
            queue = agent._get_or_create_connection_queue(server_sock)
            queue.extend([first, second, third])

            assert agent._flush_connection(server_sock) is True

            assert len(sent_frames) == 1
            assert len(_split_obs_frames(sent_frames[0])) == 2
            assert list(queue) == [third]
            assert _observation_queue_stats(agent)[server_sock]["delivered"] == 2
            assert _dropped_count(_observation_queue_stats(agent)[server_sock]) == 0
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()

    def test_flush_drops_single_oversize_observation_and_continues(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()
        sent_frames: List[bytes] = []

        def capture_send(conn: socket.socket, frames: bytes, timeout: float = 0.1) -> bool:
            sent_frames.append(frames)
            return True

        agent._send_observation_frames_with_timeout = capture_send  # type: ignore[method-assign]

        try:
            queue = agent._get_or_create_connection_queue(server_sock)
            queue.append(_make_raw_obs_frame((256 * 1024) + 1))
            queue.append(_make_obs_frame("evt_after_oversize"))

            assert agent._flush_connection(server_sock) is True

            stats = _observation_queue_stats(agent)[server_sock]
            assert len(_split_obs_frames(sent_frames[0])) == 1
            assert len(queue) == 0
            assert _dropped_count(stats) == 1
            assert stats["oversize_dropped_count"] == 1
            assert stats["delivered"] == 1
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()

    def test_flush_drops_unencodable_observation_and_continues(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()
        sent_frames: List[bytes] = []

        def capture_send(conn: socket.socket, frames: bytes, timeout: float = 0.1) -> bool:
            sent_frames.append(frames)
            return True

        agent._send_observation_frames_with_timeout = capture_send  # type: ignore[method-assign]

        try:
            queue = agent._get_or_create_connection_queue(server_sock)
            queue.append(object())
            queue.append(_make_obs_frame("evt_after_bad_encode"))

            assert agent._flush_connection(server_sock) is True

            stats = _observation_queue_stats(agent)[server_sock]
            assert len(_split_obs_frames(sent_frames[0])) == 1
            assert len(queue) == 0
            assert _dropped_count(stats) == 1
            assert stats["encode_dropped_count"] == 1
            assert stats["delivered"] == 1
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()


@pytest.mark.unit
class TestObservationQueueSlowClient:
    def test_fast_client_unaffected_by_slow_client(self) -> None:
        agent = _make_agent()
        slow_server, slow_client = socket.socketpair()
        fast_server, fast_client = socket.socketpair()
        slow_entered = threading.Event()
        release_slow = threading.Event()
        slow_conn = cast(
            socket.socket,
            cast(
                object,
                _BlockingForwardingConnection(slow_server, slow_entered, release_slow),
            ),
        )
        broadcaster: Optional[threading.Thread] = None

        try:
            agent._register_client_connection(slow_conn, kind="stream")
            agent._register_client_connection(fast_server, kind="stream")

            broadcaster = threading.Thread(
                target=lambda: [
                    agent._send_observation(
                        {"event_id": f"evt_fast_{index}", "probe_id": "prb_queue"}
                    )
                    for index in range(50)
                ],
                daemon=True,
            )
            broadcaster.start()
            assert slow_entered.wait(timeout=1.0)

            observations = _recv_obs_until(fast_client, expected_count=10, timeout=2.0)
            assert len(observations) >= 10
        finally:
            release_slow.set()
            if broadcaster is not None:
                broadcaster.join(timeout=1.0)
            agent._unregister_client_connection(slow_conn)
            agent._unregister_client_connection(fast_server)
            cast(Any, slow_conn).close()
            slow_client.close()
            fast_server.close()
            fast_client.close()

    def test_slow_client_receives_frames_or_gets_evicted(self) -> None:
        agent = _make_agent()
        slow_server, slow_client = socket.socketpair()
        slow_entered = threading.Event()
        release_slow = threading.Event()
        slow_conn = cast(
            socket.socket,
            cast(
                object,
                _BlockingForwardingConnection(slow_server, slow_entered, release_slow),
            ),
        )
        broadcaster: Optional[threading.Thread] = None

        try:
            agent._register_client_connection(slow_conn, kind="stream")
            broadcaster = threading.Thread(
                target=agent._send_observation,
                args=({"event_id": "evt_slow_timeout", "probe_id": "prb_queue"},),
                daemon=True,
            )
            broadcaster.start()
            assert slow_entered.wait(timeout=1.0)
            time.sleep(0.6)

            stats = getattr(agent, "_observation_queue_stats", {}).get(slow_conn, {})
            assert (not _connection_registered(agent, slow_conn)) or _slow_evicted_count(stats) > 0
        finally:
            release_slow.set()
            if broadcaster is not None:
                broadcaster.join(timeout=1.0)
            agent._unregister_client_connection(slow_conn)
            cast(Any, slow_conn).close()
            slow_client.close()


@pytest.mark.unit
class TestObservationOrdering:
    def test_sequence_numbers_monotonic_per_connection(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()

        def producer(producer_index: int) -> None:
            for event_index in range(10):
                agent._send_observation(
                    {
                        "event_id": f"evt_order_{producer_index}_{event_index}",
                        "probe_id": "prb_queue",
                    }
                )

        try:
            agent._register_client_connection(server_sock, kind="stream")
            threads = [threading.Thread(target=producer, args=(index,)) for index in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=1.0)

            observations = _recv_obs_until(client_sock, expected_count=20, timeout=2.0)
            seq_values = [observation["seq"] for observation in observations]

            assert len(seq_values) == 20
            assert seq_values == sorted(seq_values)
            assert len(set(seq_values)) == len(seq_values)
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()


@pytest.mark.unit
class TestObservationQueueOverflow:
    def test_overflow_drops_oldest_not_newest(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()

        try:
            agent._register_client_connection(server_sock, kind="stream")
            queues = _observation_queues(agent)
            queue = queues[server_sock]

            for index in range(OBSERVATION_QUEUE_CAPACITY):
                queue.append({"type": "observation", "event_id": f"old_{index}"})

            agent._send_observation({"event_id": "newest", "probe_id": "prb_queue"})

            delivered_event_ids = []
            while queue:
                item = queue.popleft()
                assert isinstance(item, dict)
                delivered_event_ids.append(item["event_id"])

            assert "newest" in delivered_event_ids
            assert "old_0" not in delivered_event_ids
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()


@pytest.mark.unit
class TestObservationQueueLifecycle:

    def test_start_failure_does_not_leave_flush_thread_running(self, monkeypatch) -> None:
        agent = _make_agent()
        failing_socket = _FailingBindSocket()

        def create_failing_socket(family: str, kind: str) -> _FailingBindSocket:
            return failing_socket

        monkeypatch.setattr(agent_module._rpl, "create_socket", create_failing_socket)

        assert agent.start() is False
        assert agent._flush_thread_running is False
        assert agent._flush_thread_id is None
        assert failing_socket.closed is True

    def test_stop_drains_within_bound(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()

        try:
            agent._register_client_connection(server_sock, kind="stream")
            for index in range(10):
                agent._send_observation(
                    {"event_id": f"evt_stop_{index}", "probe_id": "prb_queue"}
                )

            started_at = time.monotonic()
            agent.stop()
            elapsed = time.monotonic() - started_at

            assert elapsed <= STOP_DRAIN_BOUND_SECONDS
            queues = _observation_queues(agent)
            assert all(queue.empty() for queue in queues.values())
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()

    def test_stop_drops_remaining_after_drain_timeout(self) -> None:
        agent = _make_agent()
        entered_send = threading.Event()
        release_send = threading.Event()
        stalled_conn = cast(
            socket.socket,
            cast(object, _BlockingObservationConnection(entered_send, release_send)),
        )

        try:
            agent._register_client_connection(stalled_conn, kind="stream")
            queues = _observation_queues(agent)
            stats = _observation_queue_stats(agent)
            queue = queues[stalled_conn]

            for index in range(10):
                queue.put_nowait(_make_obs_frame(f"evt_stop_drop_{index}"))

            started_at = time.monotonic()
            agent.stop()
            elapsed = time.monotonic() - started_at

            assert elapsed <= STOP_DRAIN_BOUND_SECONDS
            assert _drain_dropped_count(stats[stalled_conn]) == 10
            assert queue.empty()
        finally:
            release_send.set()
            agent._unregister_client_connection(stalled_conn)
            cast(Any, stalled_conn).close()

    def test_stop_orders_uninject_after_drain(self) -> None:
        agent = _make_agent()
        lifecycle_events: List[str] = []

        def signal_drain() -> None:
            lifecycle_events.append("drain_signal")

        def uninject_all() -> int:
            lifecycle_events.append("uninject_all")
            return 0

        setattr(agent, "_signal_observation_queue_drain", signal_drain)
        agent.injector.uninject_all = uninject_all  # type: ignore[method-assign]

        agent.stop()

        assert lifecycle_events == ["drain_signal", "uninject_all"]
