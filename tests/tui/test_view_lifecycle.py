"""Tests for TUI view background worker lifecycle."""

from typing import Any, List, Tuple

from peeka.tui.views.dashboard import DashboardView
from peeka.tui.views.thread import ThreadView


class FakeWorker:
    """Minimal worker object with cancellable state."""

    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakeClient:
    """Minimal client object with disconnect tracking."""

    socket_path = "/tmp/peeka-test.sock"

    def __init__(self) -> None:
        self.disconnected = False

    def disconnect(self) -> None:
        self.disconnected = True


class TestDashboardLifecycle:
    """Verify DashboardView pauses background work when hidden."""

    def test_set_inactive_cancels_workers_and_disconnects_clients(self) -> None:
        view = DashboardView(pid=12345)
        refresh_worker = FakeWorker()
        log_worker = FakeWorker()
        own_client = FakeClient()
        stream_client = FakeClient()

        view._refresh_worker = refresh_worker
        view._log_worker = log_worker
        view._own_client = own_client
        view._stream_client = stream_client

        view.set_active(False)

        assert refresh_worker.cancelled is True
        assert log_worker.cancelled is True
        assert own_client.disconnected is True
        assert stream_client.disconnected is True
        assert view._refresh_worker is None
        assert view._log_worker is None
        assert view._own_client is None
        assert view._stream_client is None

    def test_set_active_restarts_dashboard_work(self) -> None:
        view = DashboardView(pid=12345)
        calls: List[str] = []

        view._active = False
        view._client = FakeClient()  # type: ignore[assignment]
        view._connect_own_client = lambda: calls.append("own_client")  # type: ignore[method-assign]
        view._connect_agent_log_stream = lambda: calls.append("log_stream")  # type: ignore[method-assign]
        view._refresh_dashboard_sync = lambda: calls.append("refresh")  # type: ignore[method-assign]
        view._start_refresh_worker = lambda: calls.append("worker")  # type: ignore[method-assign]

        view.set_active(True)

        assert calls == ["own_client", "log_stream", "refresh", "worker"]


class TestThreadLifecycle:
    """Verify ThreadView pauses periodic refresh when hidden."""

    def test_set_inactive_cancels_refresh_worker(self) -> None:
        view = ThreadView(pid=12345)
        refresh_worker = FakeWorker()
        view._refresh_worker = refresh_worker

        view.set_active(False)

        assert refresh_worker.cancelled is True
        assert view._refresh_worker is None

    def test_set_active_restarts_thread_refresh_when_ready(self) -> None:
        view = ThreadView(pid=12345)
        calls: List[Tuple[str, Any]] = []

        view._active = False
        view._mounted = True
        view._client = FakeClient()  # type: ignore[assignment]
        view._refresh_threads = lambda: calls.append(("refresh", None))  # type: ignore[method-assign]
        view._start_refresh_worker = lambda: calls.append(("worker", None))  # type: ignore[method-assign]

        view.set_active(True)

        assert calls == [("refresh", None), ("worker", None)]
