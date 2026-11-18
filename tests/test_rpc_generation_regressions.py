"""Regression tests for StreamingAgentClient/AgentClient RPC & stream generations."""

import json
import socket
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List, Tuple, cast

import pytest

import peeka.core.client as client_mod
from peeka.core.client import AgentClient, StreamingAgentClient


def _frame_json(payload: Dict[str, Any]) -> bytes:
    encoded = json.dumps(payload).encode("utf-8")
    return len(encoded).to_bytes(4, "big") + encoded


def _frame_raw(payload: bytes) -> bytes:
    return len(payload).to_bytes(4, "big") + payload


class TestRpcFailureNoReuseOrRetry:
    """Timeout, truncation, and parse failures invalidate the socket and never retry."""

    def test_timeout_invalidates_socket_prevents_mismatch_and_no_retry(self) -> None:
        client = StreamingAgentClient("", rpc_timeout=0.03)
        client_sock, peer = socket.socketpair()
        client._sock = client_sock
        received_requests: List[Dict[str, Any]] = []

        try:
            first = client.send_command({"type": "watch", "action": "start", "id": "A"})

            assert first["status"] == "error"
            assert first["error_code"] == "TRANSPORT_ERROR"
            assert first["outcome_uncertain"] is True
            assert first["retried"] is False
            assert "No response received" in first["error"]
            assert "uncertain" in first["error"].lower()
            assert "not retried" in first["error"].lower()
            assert first["message"] == first["error"]
            assert client._sock is None

            raw = peer.recv(4096)
            req_len = int.from_bytes(raw[:4], "big")
            received_requests.append(json.loads(raw[4 : 4 + req_len].decode("utf-8")))
            assert len(raw) == 4 + req_len
            assert len(received_requests) == 1
            assert received_requests[0]["id"] == "A"

            second = client.send_command({"type": "probe", "action": "list", "id": "B"})
            assert second["status"] == "error"
            assert second["error"] == "Not connected"
            assert "outcome_uncertain" not in second
        finally:
            client.disconnect()
            peer.close()

    def test_truncated_response_invalidates_socket_and_reports_uncertain(self) -> None:
        client = StreamingAgentClient("", rpc_timeout=0.2)
        client_sock, peer = socket.socketpair()
        client._sock = client_sock

        try:
            partial = json.dumps({"status": "success", "id": "A"}).encode("utf-8")
            peer.sendall(len(partial).to_bytes(4, "big") + partial[:6])
            peer.shutdown(socket.SHUT_WR)

            first = client.send_command({"type": "reset", "id": "A"})
            assert first["status"] == "error"
            assert first["error_code"] == "TRANSPORT_ERROR"
            assert first["outcome_uncertain"] is True
            assert first["retried"] is False
            assert "Incomplete response" in first["error"]
            assert client._sock is None
            assert client._buffer == b""

            second = client.send_command({"type": "probe", "action": "list", "id": "B"})
            assert second == {"status": "error", "error": "Not connected"}
        finally:
            client.disconnect()
            peer.close()

    @pytest.mark.parametrize(
        ("wire_bytes", "expected_fragment"),
        [
            (b"OBS:" + b"\x00\x00", "Truncated frame"),
            (b"OBS:" + (20).to_bytes(4, "big") + b"short", "Truncated payload"),
        ],
    )
    def test_truncated_control_frame_invalidates_socket(
        self, wire_bytes: bytes, expected_fragment: str
    ) -> None:
        client = StreamingAgentClient("", rpc_timeout=0.2)
        client_sock, peer = socket.socketpair()
        client._sock = client_sock

        try:
            peer.sendall(wire_bytes)
            peer.shutdown(socket.SHUT_WR)

            first = client.send_command({"type": "logger", "action": "set"})
            assert first["status"] == "error"
            assert first["outcome_uncertain"] is True
            assert first["retried"] is False
            assert expected_fragment in first["error"]
            assert client._sock is None

            second = client.send_command({"type": "logger", "action": "list"})
            assert second == {"status": "error", "error": "Not connected"}
        finally:
            client.disconnect()
            peer.close()

    @pytest.mark.parametrize(
        "bad_payload",
        [
            b"{not-json",
            b"\xff\xfe\xfd",
            json.dumps(["not", "a", "dict"]).encode("utf-8"),
        ],
    )
    def test_parse_failure_invalidates_socket_and_reports_uncertain(
        self, bad_payload: bytes
    ) -> None:
        client = StreamingAgentClient("", rpc_timeout=0.2)
        client_sock, peer = socket.socketpair()
        client._sock = client_sock

        try:
            peer.sendall(_frame_raw(bad_payload) + _frame_json({"status": "success", "id": "B"}))

            first = client.send_command({"type": "watch", "action": "start", "id": "A"})
            assert first["status"] == "error"
            assert first["error_code"] == "TRANSPORT_ERROR"
            assert first["outcome_uncertain"] is True
            assert first["retried"] is False
            assert "Invalid response payload" in first["error"]
            assert client._sock is None

            second = client.send_command({"type": "watch", "action": "list", "id": "B"})
            assert second == {"status": "error", "error": "Not connected"}
        finally:
            client.disconnect()
            peer.close()

    def test_pre_send_serialization_error_keeps_socket_healthy(self) -> None:
        client = StreamingAgentClient("", rpc_timeout=0.2)
        client_sock, peer = socket.socketpair()
        client._sock = client_sock

        try:
            bad = client.send_command({"type": "test", "bad": object()})
            assert bad["status"] == "error"
            assert "outcome_uncertain" not in bad
            assert client._sock is client_sock

            peer.sendall(_frame_json({"status": "success", "ok": True}))
            good = client.send_command({"type": "test", "ok": True})
            assert good == {"status": "success", "ok": True}
        finally:
            client.disconnect()
            peer.close()

    def test_reconnect_after_rpc_failure_succeeds_without_mismatch(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            sock_path = str(Path(tmpdir) / "rpc.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(sock_path)
            listener.listen(2)
            client = StreamingAgentClient(sock_path, timeout=0.2, rpc_timeout=0.05)

            try:
                assert client.connect()["status"] == "success"
                conn1, _ = listener.accept()
                try:
                    failed = client.send_command({"type": "watch", "action": "start", "id": "A"})
                    assert failed["status"] == "error"
                    assert failed["outcome_uncertain"] is True
                    assert failed["retried"] is False
                    assert client._sock is None
                finally:
                    conn1.close()

                assert client.connect()["status"] == "success"
                conn2, _ = listener.accept()
                try:
                    conn2.sendall(_frame_json({"status": "success", "reply": "B"}))
                    ok = client.send_command({"type": "probe", "action": "list", "id": "B"})
                    assert ok == {"status": "success", "reply": "B"}
                    raw = conn2.recv(4096)
                    req_len = int.from_bytes(raw[:4], "big")
                    req_payload = json.loads(raw[4 : 4 + req_len].decode("utf-8"))
                    assert req_payload["id"] == "B"
                finally:
                    conn2.close()
            finally:
                client.disconnect()
                listener.close()

    def test_agent_client_post_send_timeout_reports_uncertain_no_retry(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            sock_path = str(Path(tmpdir) / "oneshot.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(sock_path)
            listener.listen(2)
            accepted: List[bytes] = []
            done = threading.Event()

            def server_loop() -> None:
                conn, _ = listener.accept()
                try:
                    accepted.append(conn.recv(4096))
                    done.wait(1.0)
                finally:
                    conn.close()

            worker = threading.Thread(target=server_loop, daemon=True)
            worker.start()
            try:
                client = AgentClient(sock_path, timeout=0.5, rpc_timeout=0.04)
                result = client.send_command({"type": "detach"})
                assert result["status"] == "error"
                assert result["error_code"] == "TRANSPORT_ERROR"
                assert result["outcome_uncertain"] is True
                assert result["retried"] is False
                assert "uncertain" in result["error"].lower()
                assert "not retried" in result["error"].lower()
                assert len(accepted) == 1
            finally:
                done.set()
                worker.join(timeout=1.0)
                listener.close()


class TestTrailingFramesAndReaderGeneration:
    """stream_observations drains buffered tail frames first and binds to its generation."""

    def test_trailing_obs_and_log_frames_after_rpc_are_drained_before_eof(self) -> None:
        client = StreamingAgentClient("", rpc_timeout=0.5)
        client_sock, peer = socket.socketpair()
        client._sock = client_sock

        try:
            peer.sendall(
                _frame_json({"status": "success"})
                + b"OBS:"
                + _frame_json({"seq": 1})
                + b"LOG:"
                + _frame_json({"type": "log", "seq": 2})
            )
            rpc_result = client.send_command({"type": "watch", "action": "start"})
            assert rpc_result == {"status": "success"}
            peer.shutdown(socket.SHUT_WR)

            items = list(client.stream_observations())
            assert items == [{"seq": 1}, {"type": "log", "seq": 2}]
            assert client._buffer == b""
        finally:
            client.disconnect()
            peer.close()

    def test_buffered_tail_frame_yields_immediately_without_blocking_recv(self) -> None:
        class BlockingSocket:
            def recv(self, size: int) -> bytes:
                raise AssertionError("recv() called before draining buffered tail frame")

            def shutdown(self, how: int) -> None:
                pass

            def close(self) -> None:
                pass

        client = StreamingAgentClient("/tmp/unused.sock")
        client._sock = cast(Any, BlockingSocket())
        client._buffer = b"OBS:" + _frame_json({"seq": 99})

        reader = client.stream_observations()
        assert next(reader) == {"seq": 99}
        assert client._buffer == b""

    def test_old_generator_does_not_read_from_reconnected_socket(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            sock_path = str(Path(tmpdir) / "gen.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(sock_path)
            listener.listen(2)
            client = StreamingAgentClient(sock_path, timeout=0.3)

            try:
                assert client.connect()["status"] == "success"
                conn1, _ = listener.accept()
                try:
                    conn1.sendall(b"OBS:" + _frame_json({"gen": 1}))
                    old_reader = client.stream_observations()
                    assert next(old_reader) == {"gen": 1}
                    client.disconnect()
                finally:
                    conn1.close()

                assert client.connect()["status"] == "success"
                conn2, _ = listener.accept()
                try:
                    conn2.sendall(b"OBS:" + _frame_json({"gen": 2}))
                    with pytest.raises(StopIteration):
                        next(old_reader)

                    new_reader = client.stream_observations()
                    assert next(new_reader) == {"gen": 2}
                finally:
                    conn2.close()
            finally:
                client.disconnect()
                listener.close()

    def test_old_generator_stops_mid_batch_after_disconnect_and_reconnect(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            sock_path = str(Path(tmpdir) / "batch.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(sock_path)
            listener.listen(2)
            client = StreamingAgentClient(sock_path, timeout=0.3)

            try:
                assert client.connect()["status"] == "success"
                conn1, _ = listener.accept()
                try:
                    conn1.sendall(
                        b"OBS:" + _frame_json({"gen": 1, "idx": 1})
                        + b"OBS:" + _frame_json({"gen": 1, "idx": 2})
                    )
                    old_reader = client.stream_observations()
                    assert next(old_reader) == {"gen": 1, "idx": 1}
                    client.disconnect()
                finally:
                    conn1.close()

                assert client.connect()["status"] == "success"
                conn2, _ = listener.accept()
                try:
                    conn2.sendall(b"OBS:" + _frame_json({"gen": 2, "idx": 1}))
                    with pytest.raises(StopIteration):
                        next(old_reader)

                    new_reader = client.stream_observations()
                    assert next(new_reader) == {"gen": 2, "idx": 1}
                finally:
                    conn2.close()
            finally:
                client.disconnect()
                listener.close()

    def test_direct_reconnect_without_disconnect_stops_previous_generator(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            sock_path = str(Path(tmpdir) / "direct.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(sock_path)
            listener.listen(2)
            client = StreamingAgentClient(sock_path, timeout=0.3)

            try:
                assert client.connect()["status"] == "success"
                conn1, _ = listener.accept()
                conn1.sendall(b"OBS:" + _frame_json({"gen": 1}))
                old_reader = client.stream_observations()
                assert next(old_reader) == {"gen": 1}

                assert client.connect()["status"] == "success"
                conn2, _ = listener.accept()
                try:
                    conn2.sendall(b"OBS:" + _frame_json({"gen": 2}))
                    with pytest.raises(StopIteration):
                        next(old_reader)

                    new_reader = client.stream_observations()
                    assert next(new_reader) == {"gen": 2}
                finally:
                    conn2.close()
                    conn1.close()
            finally:
                client.disconnect()
                listener.close()


class TestReporterLockReleaseAndConcurrency:
    """Error activity reporters run outside locks; signal reentry and concurrency remain."""

    def test_send_command_releases_send_lock_before_error_reporter(self) -> None:
        client = StreamingAgentClient("", rpc_timeout=0.02)
        client_sock, peer = socket.socketpair()
        client._sock = client_sock
        observed: List[Tuple[str, bool, Dict[str, Any]]] = []

        reentered = False

        def report(level: str, message: str) -> None:
            nonlocal reentered
            if level == "ERROR":
                lock_free = client._send_lock.acquire(blocking=False)
                if lock_free:
                    client._send_lock.release()
                reentrant = None
                if not reentered:
                    reentered = True
                    reentrant = client.send_command({"type": "probe", "action": "list"})
                observed.append((message, lock_free, reentrant))

        client._activity_reporter = report

        try:
            result = client.send_command({"type": "watch", "action": "start"})
            assert result["status"] == "error"
            assert len(observed) == 2
            msg, lock_free, reentrant = observed[1]
            assert "uncertain" in msg.lower()
            assert lock_free is True
            assert reentrant == {"status": "error", "error": "Not connected"}
            assert observed[0] == ("probe/list failed: not connected", True, None)
        finally:
            client.disconnect()
            peer.close()

    def test_send_command_releases_lock_before_agent_error_reporter(self) -> None:
        client = StreamingAgentClient("", rpc_timeout=0.2)
        client_sock, peer = socket.socketpair()
        client._sock = client_sock
        lock_states: List[bool] = []

        def report(level: str, message: str) -> None:
            if level == "ERROR":
                lock_free = client._send_lock.acquire(blocking=False)
                if lock_free:
                    client._send_lock.release()
                lock_states.append(lock_free)

        client._activity_reporter = report

        try:
            peer.sendall(_frame_json({"status": "error", "error": "boom"}))
            result = client.send_command({"type": "watch", "action": "start"})
            assert result == {"status": "error", "error": "boom"}
            assert lock_states == [True]
        finally:
            client.disconnect()
            peer.close()

    def test_stream_reporter_runs_outside_stream_read_lock(self) -> None:
        client = StreamingAgentClient("/tmp/unused-peeka-stream.sock")
        client_sock, peer = socket.socketpair()
        client._sock = client_sock
        can_acquire_from_other_thread: List[bool] = []

        def report(level: str, message: str) -> None:
            acquired = threading.Event()

            def probe() -> None:
                if client._stream_read_lock.acquire(blocking=False):
                    try:
                        acquired.set()
                    finally:
                        client._stream_read_lock.release()

            t = threading.Thread(target=probe)
            t.start()
            t.join(timeout=1.0)
            can_acquire_from_other_thread.append(acquired.is_set())

        client._activity_reporter = report

        try:
            peer.close()
            assert list(client.stream_observations()) == []
            assert can_acquire_from_other_thread == [True]
        finally:
            client.disconnect()

    def test_signal_reentry_and_concurrent_stream_readers_preserved(self) -> None:
        client = StreamingAgentClient("/tmp/unused-peeka-concurrent.sock", timeout=0.2)
        client_sock, peer = socket.socketpair()
        client._sock = client_sock
        collected: List[int] = []
        collect_lock = threading.Lock()

        try:
            for seq in range(6):
                peer.sendall(b"OBS:" + _frame_json({"seq": seq}))
            peer.shutdown(socket.SHUT_WR)

            def consume() -> None:
                for item in client.stream_observations():
                    with collect_lock:
                        collected.append(item["seq"])

            t1 = threading.Thread(target=consume)
            t2 = threading.Thread(target=consume)
            t1.start()
            t2.start()
            t1.join(timeout=2.0)
            t2.join(timeout=2.0)

            assert sorted(collected) == list(range(6))
        finally:
            client.disconnect()
            peer.close()

    def test_stale_invalidate_does_not_clear_reconnected_buffer(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            sock_path = str(Path(tmpdir) / "reconn.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(sock_path)
            listener.listen(2)
            client = StreamingAgentClient(sock_path, timeout=0.3)

            class ReconnectingOnCloseSocket:
                def shutdown(self, how: int) -> None:
                    pass

                def close(self) -> None:
                    assert client.connect()["status"] == "success"
                    conn, _ = listener.accept()
                    try:
                        conn.sendall(b"OBS:" + _frame_json({"gen": 2, "seq": 2}))
                        conn.shutdown(socket.SHUT_WR)
                        # Populate generation 2's buffer before old invalidation finishes.
                        with client._state_lock:
                            client._buffer = b"OBS:" + _frame_json({"gen": 2, "seq": 1})
                    finally:
                        conn.close()

            client._sock = cast(Any, ReconnectingOnCloseSocket())
            try:
                client.disconnect()
                items = list(client.stream_observations())
                assert items == [{"gen": 2, "seq": 1}, {"gen": 2, "seq": 2}]
            finally:
                client.disconnect()
                listener.close()


class TestConnectDisconnectOwnership:
    """Connect attempts bind to their generation across disconnect, reconnect, and hello."""

    def test_disconnect_during_blocked_connect_prevents_stale_publish(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            sock_path = str(Path(tmpdir) / "race.sock")
            Path(sock_path).touch()
            client = StreamingAgentClient(sock_path, timeout=0.3)

            entered_connect = threading.Event()
            release_connect = threading.Event()
            closed_sockets: List[Any] = []

            class CandidateSocket:
                def __init__(self) -> None:
                    self.closed = False

                def settimeout(self, timeout: Any) -> None:
                    pass

                def connect(self, address: str) -> None:
                    entered_connect.set()
                    assert release_connect.wait(2.0)

                def shutdown(self, how: int) -> None:
                    pass

                def close(self) -> None:
                    self.closed = True
                    closed_sockets.append(self)

            candidate = CandidateSocket()
            monkeypatch.setattr(client_mod.socket, "socket", lambda *a, **kw: candidate)

            results: List[Dict[str, Any]] = []
            worker = threading.Thread(target=lambda: results.append(client.connect()))
            worker.start()
            assert entered_connect.wait(2.0)

            client.disconnect()
            release_connect.set()
            worker.join(timeout=2.0)

            assert len(results) == 1
            assert results[0]["status"] == "error"
            assert client._sock is None
            assert candidate.closed is True
            assert candidate in closed_sockets

    @pytest.mark.parametrize("late_raises", [False, True])
    def test_late_connect_does_not_overwrite_or_invalidate_newer_connection(
        self, monkeypatch: pytest.MonkeyPatch, late_raises: bool
    ) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            sock_path = str(Path(tmpdir) / "interleave.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(sock_path)
            listener.listen(4)
            client = StreamingAgentClient(sock_path, timeout=0.3, rpc_timeout=0.3)

            entered_first = threading.Event()
            release_first = threading.Event()
            real_socket_cls = socket.socket
            created_socks: List[Any] = []
            create_lock = threading.Lock()
            call_count = 0

            class DelayedFirstSocket:
                def __init__(self) -> None:
                    self.closed = False
                    self.timeout: Any = None

                def settimeout(self, timeout: Any) -> None:
                    self.timeout = timeout

                def gettimeout(self) -> Any:
                    return self.timeout

                def connect(self, address: str) -> None:
                    entered_first.set()
                    assert release_first.wait(2.0)
                    if late_raises:
                        raise OSError("late connect failed")

                def shutdown(self, how: int) -> None:
                    pass

                def close(self) -> None:
                    self.closed = True

            def socket_factory(*args: Any, **kwargs: Any) -> Any:
                nonlocal call_count
                with create_lock:
                    call_count += 1
                    idx = call_count
                if idx == 1:
                    s: Any = DelayedFirstSocket()
                else:
                    s = real_socket_cls(*args, **kwargs)
                created_socks.append(s)
                return s

            monkeypatch.setattr(client_mod.socket, "socket", socket_factory)

            first_results: List[Dict[str, Any]] = []
            t1 = threading.Thread(target=lambda: first_results.append(client.connect()))
            t1.start()
            assert entered_first.wait(2.0)

            try:
                second = client.connect()
                assert second == {"status": "success"}
                conn2, _ = listener.accept()
                try:
                    newer_sock = client._sock
                    assert newer_sock is created_socks[1]

                    release_first.set()
                    t1.join(timeout=2.0)

                    assert len(first_results) == 1
                    assert first_results[0]["status"] == "error"
                    assert created_socks[0].closed is True
                    assert client._sock is newer_sock

                    conn2.sendall(_frame_json({"status": "success", "conn": 2}))
                    assert client.send_command({"type": "probe", "action": "list"}) == {
                        "status": "success",
                        "conn": 2,
                    }
                finally:
                    conn2.close()
            finally:
                release_first.set()
                t1.join(timeout=1.0)
                client.disconnect()
                listener.close()

    def test_hello_failure_or_supersede_cleans_only_owning_generation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            sock_path = str(Path(tmpdir) / "hello.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(sock_path)
            listener.listen(4)
            client = StreamingAgentClient(
                sock_path,
                timeout=0.3,
                rpc_timeout=0.3,
                client_info={"source": "watch-stream"},
            )

            hello_entered = threading.Event()
            release_hello = threading.Event()
            original_identify = client._identify_connection
            attempt_lock = threading.Lock()
            identify_calls = 0

            def gated_identify(
                expected_sock: Any = None, expected_gen: Any = None
            ) -> Dict[str, Any]:
                nonlocal identify_calls
                with attempt_lock:
                    identify_calls += 1
                    call_idx = identify_calls
                if call_idx == 1:
                    hello_entered.set()
                    assert release_hello.wait(2.0)
                return original_identify(expected_sock, expected_gen)

            monkeypatch.setattr(client, "_identify_connection", gated_identify)

            first_results: List[Dict[str, Any]] = []
            t1 = threading.Thread(target=lambda: first_results.append(client.connect()))
            t1.start()

            conn1, _ = listener.accept()
            conn2 = None
            try:
                assert hello_entered.wait(2.0)
                first_sock = client._sock
                assert first_sock is not None

                # Newer connect supersedes attempt 1 while attempt 1 is in hello.
                second_results: List[Dict[str, Any]] = []
                t2 = threading.Thread(
                    target=lambda: second_results.append(client.connect())
                )
                t2.start()
                conn2, _ = listener.accept()
                # Read hello from conn2 and reply success.
                raw_len = conn2.recv(4)
                assert len(raw_len) == 4
                conn2.recv(int.from_bytes(raw_len, "big"))
                conn2.sendall(_frame_json({"status": "success"}))
                t2.join(timeout=2.0)

                assert second_results == [{"status": "success"}]
                second_sock = client._sock
                assert second_sock is not None
                assert second_sock is not first_sock

                # Release attempt 1's hello: even if conn1 hadn't failed, ownership was lost.
                release_hello.set()
                t1.join(timeout=2.0)

                assert len(first_results) == 1
                assert first_results[0]["status"] == "error"
                assert client._sock is second_sock

                conn2.sendall(_frame_json({"status": "success", "conn": 2}))
                assert client.send_command({"type": "probe", "action": "list"}) == {
                    "status": "success",
                    "conn": 2,
                }
            finally:
                release_hello.set()
                t1.join(timeout=1.0)
                conn1.close()
                if conn2 is not None:
                    conn2.close()
                client.disconnect()
                listener.close()

    def test_hello_disconnect_right_before_return_and_hello_rejection(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmpdir:
            sock_path = str(Path(tmpdir) / "hello2.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(sock_path)
            listener.listen(4)
            client = StreamingAgentClient(
                sock_path,
                timeout=0.3,
                rpc_timeout=0.3,
                client_info={"source": "watch-stream"},
            )

            original_identify = client._identify_connection

            def disconnect_after_hello(
                expected_sock: Any = None, expected_gen: Any = None
            ) -> Dict[str, Any]:
                res = original_identify(expected_sock, expected_gen)
                client.disconnect()
                return res

            monkeypatch.setattr(client, "_identify_connection", disconnect_after_hello)

            def serve_one(reply: Dict[str, Any]) -> None:
                conn, _ = listener.accept()
                try:
                    raw_len = conn.recv(4)
                    if len(raw_len) == 4:
                        conn.recv(int.from_bytes(raw_len, "big"))
                        conn.sendall(_frame_json(reply))
                finally:
                    conn.close()

            srv1 = threading.Thread(
                target=serve_one, args=({"status": "success"},), daemon=True
            )
            srv1.start()
            try:
                res1 = client.connect()
                srv1.join(timeout=2.0)
                assert res1["status"] == "error"
                assert client._sock is None

                monkeypatch.setattr(client, "_identify_connection", original_identify)
                srv2 = threading.Thread(
                    target=serve_one,
                    args=({"status": "error", "error": "rejected"},),
                    daemon=True,
                )
                srv2.start()
                res2 = client.connect()
                srv2.join(timeout=2.0)
                assert res2 == {"status": "error", "error": "rejected"}
                assert client._sock is None
            finally:
                client.disconnect()
                listener.close()
