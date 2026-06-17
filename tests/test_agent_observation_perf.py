"""Performance baseline data collection for the observation queue.

These tests collect baseline measurements (throughput, latency, memory) for
the observation queue without asserting hard thresholds.  The only hard
assertion is ``test_backpressure_drop_accuracy`` which verifies the exact
``dropped_count`` value for deterministic overflow scenarios.

Run with:
    uv run pytest tests/test_agent_observation_perf.py -v -s
"""
import json
import os
import socket
import time
import tracemalloc
from typing import Any, Dict, List, cast

import pytest

from peeka.core.agent import PeekaAgent


_is_ci = os.environ.get("CI") == "true"

PERF_THRESHOLDS: Dict[str, Any] = {
    # CI runners (shared, variable CPU) run ~200k obs/s; local baseline ~688k.
    # Use a relaxed threshold in CI to prevent noise failures.
    "enqueue_throughput_obs_per_sec": 120_000 if _is_ci else 344_000,
    "flush_latency_64_ms": 1.78,                # 2x of ~0.89ms baseline
    "memory_peak_50k_kb": 348.0,                # 1.5x of ~232KB baseline
    "fast_client_ms_under_slow": 0.80,          # 2x of ~0.40ms baseline
}

_baseline: Dict[str, Any] = {}


def _make_agent() -> PeekaAgent:
    agent = PeekaAgent("perf-baseline-test")
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
    sock: socket.socket, expected_count: int, timeout: float = 5.0
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


def _make_obs_frame(event_id: str) -> bytes:
    payload = json.dumps(
        {"type": "observation", "event_id": event_id, "probe_id": "prb_perf"}
    ).encode("utf-8")
    return b"OBS:" + len(payload).to_bytes(4, "big") + payload


@pytest.fixture(scope="session", autouse=True)
def write_baseline_json() -> Any:  # type: ignore[misc]
    yield
    try:
        os.makedirs(".sisyphus/evidence", exist_ok=True)
        with open(".sisyphus/evidence/perf-baseline.json", "w") as f:
            json.dump(_baseline, f, indent=2)
    except OSError:
        pass


@pytest.mark.unit
class TestObservationQueuePerfBaseline:
    @pytest.mark.perf
    @pytest.mark.slow
    def test_enqueue_throughput_baseline(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()

        try:
            agent._register_client_connection(server_sock, kind="stream")

            t0 = time.perf_counter()
            for i in range(10_000):
                agent._send_observation(
                    {"event_id": f"evt_{i}", "probe_id": "prb_perf"}
                )
            elapsed = time.perf_counter() - t0

            throughput = 10_000 / elapsed
            threshold = cast(int, PERF_THRESHOLDS["enqueue_throughput_obs_per_sec"])
            threshold_label = "CI threshold" if _is_ci else "local threshold"
            print(
                f"\nThroughput: {throughput:.0f} obs/s (elapsed={elapsed * 1000:.1f}ms)"
                f"; active threshold={threshold} ({threshold_label})"
            )

            assert elapsed > 0
            _baseline["enqueue_throughput_obs_per_sec"] = throughput
            assert throughput >= threshold, (
                f"Throughput {throughput:.0f} obs/s < threshold "
                f"{threshold} obs/s"
            )
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()

    @pytest.mark.perf
    @pytest.mark.slow
    def test_flush_latency_baseline(self) -> None:
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()

        try:
            agent._register_client_connection(server_sock, kind="stream")

            t0 = time.perf_counter()
            for i in range(64):
                agent._send_observation(
                    {"event_id": f"evt_{i}", "probe_id": "prb_perf"}
                )
            received = _recv_obs_until(client_sock, 64, timeout=5.0)
            elapsed = time.perf_counter() - t0

            print(
                f"\nFlush latency (64 items): {elapsed * 1000:.1f}ms"
                f" (received={len(received)})"
            )

            assert elapsed > 0
            _baseline["flush_latency_64_ms"] = elapsed * 1000
            assert elapsed * 1000 <= PERF_THRESHOLDS["flush_latency_64_ms"], (
                f"Flush latency {elapsed * 1000:.2f}ms > threshold "
                f"{PERF_THRESHOLDS['flush_latency_64_ms']}ms"
            )
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()

    @pytest.mark.perf
    @pytest.mark.slow
    def test_memory_growth_baseline(self) -> None:
        """Measure peak memory during 50_000 enqueues with overflow dropping.

        The queue holds at most 1024 items; the remaining 48_976 are dropped
        (oldest evicted by deque.append).  Peak memory reflects the bounded
        steady-state footprint, not an unbounded accumulation.
        """
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()

        try:
            agent._get_or_create_connection_queue(server_sock)

            tracemalloc.start()
            for i in range(50_000):
                agent._enqueue_observation(
                    server_sock,
                    {"event_id": f"evt_{i}", "probe_id": "prb_perf"},
                )
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()

            peak_kb = peak / 1024
            print(f"\nMemory peak for 50k obs: {peak_kb:.1f} KB")

            assert peak > 0
            _baseline["memory_peak_50k_kb"] = peak_kb
            assert peak_kb <= PERF_THRESHOLDS["memory_peak_50k_kb"], (
                f"Memory peak {peak_kb:.1f}KB > threshold "
                f"{PERF_THRESHOLDS['memory_peak_50k_kb']}KB"
            )
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()

    def test_backpressure_drop_accuracy(self) -> None:
        """Verify dropped_count is exactly 100 after enqueuing 1024+100 items.

        The flush thread is intentionally not started so the queue stays full
        and every extra enqueue triggers the drop-oldest path.  This is the
        one test that asserts a hard value rather than just collecting data.
        """
        agent = _make_agent()
        server_sock, client_sock = socket.socketpair()

        try:
            agent._get_or_create_connection_queue(server_sock)

            frame = _make_obs_frame("fill")

            for _ in range(1024):
                agent._enqueue_observation(server_sock, frame)

            for _ in range(100):
                agent._enqueue_observation(server_sock, frame)

            stats = agent._observation_queue_stats[server_sock]
            dropped_count = stats["dropped_count"]

            assert dropped_count == 100
            print(f"\nBackpressure: dropped_count={dropped_count}")
        finally:
            agent._unregister_client_connection(server_sock)
            server_sock.close()
            client_sock.close()

    @pytest.mark.perf
    @pytest.mark.slow
    def test_slow_client_does_not_block_fast_client_latency(self) -> None:
        agent = _make_agent()
        fast_server, fast_client = socket.socketpair()
        slow_server, slow_client = socket.socketpair()

        try:
            agent._register_client_connection(fast_server, kind="stream")
            agent._register_client_connection(slow_server, kind="stream")

            t0 = time.perf_counter()
            for i in range(10):
                agent._send_observation(
                    {"event_id": f"evt_{i}", "probe_id": "prb_perf"}
                )
            received = _recv_obs_until(fast_client, 10, timeout=5.0)
            elapsed = time.perf_counter() - t0

            print(
                f"\nFast client latency under slow client: {elapsed * 1000:.1f}ms"
                f" (received={len(received)})"
            )

            assert elapsed > 0
            _baseline["fast_client_ms_under_slow"] = elapsed * 1000
            assert elapsed * 1000 <= PERF_THRESHOLDS["fast_client_ms_under_slow"], (
                f"Fast client latency {elapsed * 1000:.2f}ms > threshold "
                f"{PERF_THRESHOLDS['fast_client_ms_under_slow']}ms"
            )
        finally:
            agent._unregister_client_connection(fast_server)
            agent._unregister_client_connection(slow_server)
            fast_server.close()
            fast_client.close()
            slow_server.close()
            slow_client.close()
