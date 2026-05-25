"""
Thread-safety tests for peeka.core.client

Tests concurrent access patterns from Textual worker threads to ensure
no race conditions occur when multiple workers call send_command() simultaneously.

Inspired by Textual's own tests/test_concurrency.py patterns.
"""

import json
import os
import socket
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

import pytest

from peeka.core.client import AgentClient, StreamingAgentClient


class ThreadSafeMockServer:
    """
    Mock agent server that tracks concurrent requests to verify thread-safety.

    Uses threading.Lock to ensure its own operations are thread-safe for
    verification purposes.
    """

    def __init__(self, sock_path: str, persistent=False):
        self.sock_path = sock_path
        self.persistent = persistent  # Whether to keep connections alive
        self.server_sock: socket.socket = None
        self.running = False
        self.requests_received: List[Dict] = []
        self.lock = threading.Lock()
        self._server_thread = None

    def start(self):
        """Start the mock server in a background thread."""
        self.server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_sock.bind(self.sock_path)
        self.server_sock.listen(50)  # Increased for stress tests
        self.running = True

        self._server_thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._server_thread.start()
        time.sleep(0.1)  # Give server time to start

    def stop(self):
        """Stop the mock server."""
        self.running = False
        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass

    def _accept_loop(self):
        """Accept connections and handle them in separate threads."""
        while self.running:
            try:
                self.server_sock.settimeout(0.5)
                conn, _ = self.server_sock.accept()
                threading.Thread(target=self._handle_client, args=(conn,), daemon=True).start()
            except socket.timeout:
                continue
            except Exception:
                if self.running:
                    break

    def _handle_client(self, conn: socket.socket):
        """Handle a single client connection."""
        try:
            if self.persistent:
                # Keep connection open and handle multiple requests
                while self.running:
                    if not self._handle_one_request(conn):
                        break
            else:
                # Handle one request and close
                self._handle_one_request(conn)
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _handle_one_request(self, conn: socket.socket) -> bool:
        """
        Handle a single request on the connection.

        Returns:
            True if more requests should be processed, False if connection should close.
        """
        try:
            # Read length-prefixed request
            length_bytes = self._recv_exact(conn, 4)
            if not length_bytes:
                return False

            length = int.from_bytes(length_bytes, "big")
            data = self._recv_exact(conn, length)
            if not data:
                return False

            request = json.loads(data.decode("utf-8"))

            # Track request (thread-safe)
            with self.lock:
                self.requests_received.append(request)

            # Send response
            response = {"status": "success", "request_id": request.get("id", 0)}
            payload = json.dumps(response).encode("utf-8")
            conn.sendall(len(payload).to_bytes(4, "big"))
            conn.sendall(payload)

            return self.persistent

        except Exception:
            return False

    @staticmethod
    def _recv_exact(sock: socket.socket, size: int) -> bytes:
        """Receive exactly size bytes."""
        chunks = []
        remaining = size
        sock.settimeout(5.0)
        while remaining > 0:
            try:
                chunk = sock.recv(remaining)
            except socket.timeout:
                return b""
            if not chunk:
                return b""
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


class TestAgentClientThreadSafety:
    """Test AgentClient thread-safety with concurrent calls."""

    @pytest.fixture
    def mock_server(self, tmp_path):
        """Fixture providing a thread-safe mock server."""
        sock_path = str(tmp_path / "test.sock")
        server = ThreadSafeMockServer(sock_path, persistent=False)
        server.start()
        yield server
        server.stop()
        if os.path.exists(sock_path):
            os.unlink(sock_path)

    def test_concurrent_send_command_no_exceptions(self, mock_server):
        """Test that concurrent send_command calls don't raise exceptions."""
        client = AgentClient(mock_server.sock_path, timeout=5.0)

        errors = []

        def send_request(request_id: int):
            try:
                result = client.send_command({"id": request_id, "type": "test"})
                return result
            except Exception as e:
                errors.append(e)
                return {"status": "error", "error": str(e)}

        # Simulate 10 concurrent Textual workers
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(send_request, i) for i in range(10)]
            results = [f.result() for f in as_completed(futures)]

        # Verify no exceptions occurred
        assert len(errors) == 0, f"Exceptions raised: {errors}"

        # Verify all requests succeeded
        assert all(r["status"] == "success" for r in results)

        # Verify server received all 10 requests
        assert len(mock_server.requests_received) == 10

    def test_concurrent_requests_unique_responses(self, mock_server):
        """Test that concurrent requests get unique, non-mixed responses."""
        client = AgentClient(mock_server.sock_path, timeout=5.0)

        def send_request(request_id: int):
            result = client.send_command({"id": request_id, "type": "test"})
            return (request_id, result)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(send_request, i) for i in range(10)]
            results = [f.result() for f in as_completed(futures)]

        # Verify each request got the correct response (no mixing)
        for sent_id, response in results:
            assert response["status"] == "success"
            assert response["request_id"] == sent_id, \
                f"Response mismatch: sent {sent_id}, got {response['request_id']}"

    def test_stress_concurrent_access_50_workers(self, mock_server):
        """Stress test with 50 concurrent workers to expose race conditions."""
        client = AgentClient(mock_server.sock_path, timeout=10.0)

        errors = []

        def send_request(request_id: int):
            try:
                result = client.send_command({"id": request_id})
                if result["status"] != "success":
                    errors.append(f"Request {request_id} failed: {result}")
                return result
            except Exception as e:
                errors.append(f"Request {request_id} raised: {e}")
                return {"status": "error"}

        # Reduce concurrency to avoid overwhelming the server's accept queue
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(send_request, i) for i in range(50)]
            results = [f.result() for f in as_completed(futures)]

        assert len(errors) == 0, f"Errors in stress test: {errors}"
        assert len(mock_server.requests_received) == 50


class TestStreamingAgentClientThreadSafety:
    """Test StreamingAgentClient thread-safety with concurrent calls."""

    @pytest.fixture
    def mock_server(self, tmp_path):
        """Fixture providing a persistent mock server for streaming client."""
        sock_path = str(tmp_path / "test.sock")
        server = ThreadSafeMockServer(sock_path, persistent=True)
        server.start()
        yield server
        server.stop()
        if os.path.exists(sock_path):
            os.unlink(sock_path)

    def test_concurrent_send_command_with_lock(self, mock_server):
        """Test that StreamingAgentClient._send_lock prevents race conditions."""
        client = StreamingAgentClient(mock_server.sock_path)
        client.connect()

        errors = []

        def send_request(request_id: int):
            try:
                result = client.send_command({"id": request_id, "type": "test"})
                return result
            except Exception as e:
                errors.append(e)
                return {"status": "error", "error": str(e)}

        try:
            # Simulate concurrent Textual workers
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(send_request, i) for i in range(10)]
                results = [f.result() for f in as_completed(futures)]

            assert len(errors) == 0, f"Exceptions raised: {errors}"
            assert all(r["status"] == "success" for r in results), \
                f"Failed requests: {[r for r in results if r['status'] != 'success']}"
            assert len(mock_server.requests_received) == 10

        finally:
            client.disconnect()

    def test_lock_acquisition_order(self, mock_server):
        """Test that _send_lock prevents interleaved socket operations."""
        client = StreamingAgentClient(mock_server.sock_path)
        client.connect()

        # Track which thread acquired the lock when
        lock_acquisitions = []
        lock_releases = []
        tracking_lock = threading.Lock()

        original_send = client.send_command

        def tracked_send(cmd):
            with tracking_lock:
                lock_acquisitions.append((threading.current_thread().ident, time.time()))
            result = original_send(cmd)
            with tracking_lock:
                lock_releases.append((threading.current_thread().ident, time.time()))
            return result

        try:
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(tracked_send, {"id": i}) for i in range(5)]
                [f.result() for f in as_completed(futures)]

            # Verify no interleaving: each acquire must be followed by its release
            # before the next acquire (within the same connection)
            assert len(lock_acquisitions) == 5
            assert len(lock_releases) == 5

        finally:
            client.disconnect()


class TestTextualWorkerPattern:
    """Test patterns specific to Textual worker thread usage."""

    @pytest.fixture
    def mock_server(self, tmp_path):
        """Fixture providing a persistent mock server."""
        sock_path = str(tmp_path / "test.sock")
        server = ThreadSafeMockServer(sock_path, persistent=True)
        server.start()
        yield server
        server.stop()
        if os.path.exists(sock_path):
            os.unlink(sock_path)

    def test_simulated_textual_worker_pattern(self, mock_server):
        """
        Simulate the Textual pattern where multiple views call run_worker()
        with lambdas that invoke send_command().

        This is the actual bug pattern from peeka TUI views.
        """
        client = StreamingAgentClient(mock_server.sock_path)
        client.connect()

        def simulate_watch_view_start():
            """Simulates WatchView.start_watch() calling run_worker()."""
            return client.send_command({"type": "watch", "pattern": "test.func"})

        def simulate_stack_view_start():
            """Simulates StackView.start_stack() calling run_worker()."""
            return client.send_command({"type": "stack", "pattern": "test.func"})

        def simulate_monitor_view_start():
            """Simulates MonitorView.start_monitor() calling run_worker()."""
            return client.send_command({"type": "monitor", "pattern": "test.func"})

        try:
            # Simulate user rapidly switching between views and starting commands
            with ThreadPoolExecutor(max_workers=3) as executor:
                futures = [
                    executor.submit(simulate_watch_view_start),
                    executor.submit(simulate_stack_view_start),
                    executor.submit(simulate_monitor_view_start),
                ]
                results = [f.result() for f in as_completed(futures)]

            # Verify all commands succeeded
            assert all(r["status"] == "success" for r in results), \
                f"Failed requests: {[r for r in results if r['status'] != 'success']}"
            assert len(mock_server.requests_received) == 3

            # Verify correct command types were received
            types_received = {req["type"] for req in mock_server.requests_received}
            assert types_received == {"watch", "stack", "monitor"}

        finally:
            client.disconnect()

    def test_rapid_sequential_commands(self, mock_server):
        """Test rapid sequential commands from same thread (no concurrency)."""
        client = StreamingAgentClient(mock_server.sock_path)
        client.connect()

        try:
            results = []
            for i in range(20):
                result = client.send_command({"id": i, "type": "test"})
                results.append(result)

            # All should succeed
            assert all(r["status"] == "success" for r in results)
            assert len(mock_server.requests_received) == 20

        finally:
            client.disconnect()

class TestSendLockRegressionGuard:
    """Regression tests to ensure _send_lock is never removed."""

    def test_send_lock_attribute_exists(self):
        """Verify StreamingAgentClient has a _send_lock threading.Lock."""
        client = StreamingAgentClient("/fake/path")
        assert hasattr(client, "_send_lock"), "_send_lock attribute missing — thread-safety regression!"
        assert isinstance(client._send_lock, type(threading.Lock())), (
            f"_send_lock should be threading.Lock, got {type(client._send_lock)}"
        )

    def test_send_command_acquires_lock(self, tmp_path):
        """Verify send_command actually acquires _send_lock during execution."""
        sock_path = str(tmp_path / "test.sock")
        server = ThreadSafeMockServer(sock_path, persistent=True)
        server.start()

        client = StreamingAgentClient(sock_path)
        client.connect()

        lock_was_held = []

        original_recv_exact = client._recv_exact

        def patched_recv_exact(size):
            # Check if the lock is held (locked() returns True when acquired)
            lock_was_held.append(client._send_lock.locked())
            return original_recv_exact(size)

        try:
            client._recv_exact = patched_recv_exact
            client.send_command({"type": "test", "id": 1})

            # Lock should have been held during _recv_exact calls
            assert len(lock_was_held) > 0, "_recv_exact was never called"
            assert all(lock_was_held), (
                "_send_lock was NOT held during _recv_exact \u2014 thread-safety regression!"
            )
        finally:
            client.disconnect()
            server.stop()

class TestAutoCompleteAndCommandConcurrency:
    """
    Reproduce the exact TUI bug pattern: autocomplete CompletionSource
    calls send_command(complete) while a view's run_worker calls
    send_command(watch/trace/stack) on the SAME client instance.

    This was the original bug — no lock on send_command caused
    interleaved socket writes → BrokenPipeError / garbled responses.
    """

    @pytest.fixture
    def mock_server(self, tmp_path):
        """Fixture providing a persistent mock server."""
        sock_path = str(tmp_path / "test.sock")
        server = ThreadSafeMockServer(sock_path, persistent=True)
        server.start()
        yield server
        server.stop()
        if os.path.exists(sock_path):
            os.unlink(sock_path)

    def test_autocomplete_during_trace_start(self, mock_server):
        """
        Simulate autocomplete worker firing while trace command starts.

        In real TUI:
        - Thread A: AutoCompleteInput._fetch_sync → CompletionSource.get_completions
                    → client.send_command({type: 'complete', ...})
        - Thread B: TraceView._start_trace → run_worker
                    → client.send_command({type: 'trace', ...})
        Both hit the SAME StreamingAgentClient instance.
        """
        client = StreamingAgentClient(mock_server.sock_path)
        client.connect()

        errors = []
        results_by_type = {"complete": [], "trace": []}
        result_lock = threading.Lock()

        def simulate_autocomplete(iteration: int):
            """Simulates CompletionSource.get_completions() debounce calls."""
            try:
                for i in range(5):
                    result = client.send_command({
                        "type": "complete",
                        "prefix": f"demo.Calc.ad",
                        "id": iteration * 100 + i,
                    })
                    with result_lock:
                        results_by_type["complete"].append(result)
                    time.sleep(0.01)  # Simulate debounce delay
            except Exception as e:
                errors.append(("complete", e))

        def simulate_trace_start():
            """Simulates TraceView._start_trace() run_worker call."""
            try:
                result = client.send_command({
                    "type": "trace",
                    "pattern": "demo.Calculator.add",
                    "depth": 3,
                    "id": 999,
                })
                with result_lock:
                    results_by_type["trace"].append(result)
            except Exception as e:
                errors.append(("trace", e))

        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                # Two autocomplete workers + one trace command, all at once
                futures = [
                    executor.submit(simulate_autocomplete, 0),
                    executor.submit(simulate_autocomplete, 1),
                    executor.submit(simulate_trace_start),
                ]
                for f in as_completed(futures):
                    f.result()  # Propagate any exception

            # No exceptions should have occurred
            assert len(errors) == 0, f"Concurrent errors: {errors}"

            # All responses should be successful
            all_results = results_by_type["complete"] + results_by_type["trace"]
            assert all(r["status"] == "success" for r in all_results), (
                f"Failed: {[r for r in all_results if r['status'] != 'success']}"
            )

            # 5 + 5 autocomplete + 1 trace = 11 total requests
            assert len(mock_server.requests_received) == 11

            # Verify both command types were received
            types_received = {req["type"] for req in mock_server.requests_received}
            assert "complete" in types_received
            assert "trace" in types_received

        finally:
            client.disconnect()

    def test_autocomplete_during_watch_continuous(self, mock_server):
        """
        Simulate continuous autocomplete calls during watch command setup.

        This tests the pattern where a user is typing a pattern (triggering
        autocomplete) and then clicks Watch — both operations use the same
        shared client in the TUI.
        """
        client = StreamingAgentClient(mock_server.sock_path)
        client.connect()

        errors = []

        def autocomplete_burst():
            """Simulate rapid keystroke → autocomplete cycle."""
            for i in range(10):
                try:
                    client.send_command({"type": "complete", "prefix": f"d{'e' * i}"})
                except Exception as e:
                    errors.append(("complete", e))
                time.sleep(0.005)

        def watch_command():
            """Simulate clicking Watch button."""
            try:
                client.send_command({"type": "watch", "pattern": "demo.func"})
            except Exception as e:
                errors.append(("watch", e))

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(autocomplete_burst),
                    executor.submit(watch_command),
                ]
                for f in as_completed(futures):
                    f.result()

            assert len(errors) == 0, f"Errors during concurrent access: {errors}"
            assert len(mock_server.requests_received) == 11  # 10 complete + 1 watch

        finally:
            client.disconnect()

    def test_stress_autocomplete_with_multiple_views(self, mock_server):
        """
        Stress test: autocomplete + watch + trace + stack all calling
        send_command on the same client simultaneously.

        Represents worst-case TUI scenario where user is typing (autocomplete)
        while multiple views have pending commands.
        """
        client = StreamingAgentClient(mock_server.sock_path)
        client.connect()

        errors = []
        total_expected = 0
        count_lock = threading.Lock()

        def burst_send(cmd_type: str, count: int):
            nonlocal total_expected
            with count_lock:
                total_expected += count
            for i in range(count):
                try:
                    result = client.send_command({
                        "type": cmd_type,
                        "id": i,
                        "pattern": "demo.func",
                    })
                    if result["status"] != "success":
                        errors.append(f"{cmd_type}[{i}]: {result}")
                except Exception as e:
                    errors.append(f"{cmd_type}[{i}]: {e}")

        try:
            with ThreadPoolExecutor(max_workers=4) as executor:
                futures = [
                    executor.submit(burst_send, "complete", 20),  # autocomplete
                    executor.submit(burst_send, "watch", 5),
                    executor.submit(burst_send, "trace", 5),
                    executor.submit(burst_send, "stack", 5),
                ]
                for f in as_completed(futures):
                    f.result()

            assert len(errors) == 0, f"Stress test errors: {errors}"
            assert len(mock_server.requests_received) == total_expected

        finally:
            client.disconnect()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
