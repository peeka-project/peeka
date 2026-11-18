"""Top view for function-level sampling profiler."""

import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Dict, Optional

from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Static
from textual.worker import Worker, get_current_worker

from peeka.tui.activity import make_activity_reporter, make_client_info

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class TopView(Container):
    """Top view displays function-level CPU profiling statistics."""

    BINDINGS = [
        Binding("r", "reset_stats", "Reset"),
    ]

    def __init__(self, pid: int) -> None:
        """Initialize TopView.

        Args:
            pid: Target process ID
        """
        super().__init__(id="top-container")
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._own_client: Optional["StreamingAgentClient"] = None
        self._client_lock = threading.Lock()
        self._socket_path: Optional[str] = None
        self._top_id: Optional[str] = None
        self._is_profiling = False
        self._refresh_worker: Optional[Worker] = None
        self._command_worker: Optional[Worker] = None
        self._log = logging.getLogger(__name__)

    def compose(self):
        """Compose the Top view layout."""
        with Vertical():
            yield Horizontal(
                Static("Stopped", id="top-header"),
                Static("", classes="spacer"),
                Button("Start", id="top-start-btn", variant="success", flat=True),
                Button("Stop", id="top-stop-btn", variant="error", flat=True),
                Button("Reset", id="top-reset-btn", variant="warning", flat=True),
                id="top-controls",
                classes="compact-control",
            )
            yield DataTable(id="top-table")

    def set_client(self, client: "StreamingAgentClient") -> None:
        """Set the agent client (does NOT auto-start profiling).

        Args:
            client: Streaming agent client instance
        """
        self._client = client
        self._socket_path = client.socket_path
        # Defer client creation to first use (lazy connection)
        self._update_button_states()

    def _connect_own_client(self) -> None:
        """Create a dedicated client for TopView to avoid socket contention."""
        if not self._socket_path:
            return
        try:
            from peeka.core.client import StreamingAgentClient

            try:
                app = self.app
            except Exception:
                app = None

            client = StreamingAgentClient(
                self._socket_path,
                activity_reporter=make_activity_reporter(app, "top-data"),
                client_info=make_client_info(app, "top-data"),
            )
            result = client.connect()
            if result.get("status") == "success":
                self._own_client = client
            else:
                self._log.warning(
                    "Top dedicated client failed: %s", result.get("error")
                )
                try:
                    client.disconnect()
                except Exception:
                    pass
                self._own_client = None
        except Exception as e:
            self._log.warning("Top dedicated client error: %s", e)
            self._own_client = None

    def _ensure_own_client(self) -> Optional["StreamingAgentClient"]:
        """Lazily create dedicated client on first use."""
        with self._client_lock:
            if self._own_client is None:
                self._connect_own_client()
            return self._own_client or self._client

    def _disconnect_own_client(self) -> None:
        """Disconnect and clear the dedicated client if present."""
        with self._client_lock:
            if self._own_client is not None:
                try:
                    self._own_client.disconnect()
                except Exception:
                    pass
                self._own_client = None

    async def on_mount(self) -> None:
        """Initialize when view is mounted."""
        # Setup DataTable columns
        table = self.query_one("#top-table", DataTable)
        table.add_columns("%Own", "%Total", "OwnTime", "TotalTime", "Function")
        table.show_cursor = False
        self._update_button_states()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "top-start-btn":
            self._start_profiling()
        elif event.button.id == "top-stop-btn":
            self._stop_profiling()
        elif event.button.id == "top-reset-btn":
            self.action_reset_stats()

    def _update_button_states(self) -> None:
        """Update button disabled states based on profiling status."""
        try:
            start_btn = self.query_one("#top-start-btn", Button)
            stop_btn = self.query_one("#top-stop-btn", Button)
            reset_btn = self.query_one("#top-reset-btn", Button)

            has_client = (self._own_client or self._client) is not None

            start_btn.disabled = self._is_profiling or not has_client
            stop_btn.disabled = not self._is_profiling
            reset_btn.disabled = not self._is_profiling
        except Exception:
            pass  # Widgets may not be mounted yet

    def _set_header_text(self, text: str) -> None:
        """Update the top view header text on the UI thread."""
        header = self.query_one("#top-header", Static)
        header.update(text)

    def _start_profiling(self) -> None:
        """Start the profiler and refresh worker without blocking the UI thread."""
        if not self._client and not self._own_client and not self._socket_path:
            return
        if self._command_worker:
            self._command_worker.cancel()
        self._command_worker = self.run_worker(
            self._start_profiling_worker,
            thread=True,
            exclusive=True,
            group="top-commands",
        )

    def _start_profiling_worker(self) -> None:
        """Send top start command on a worker thread."""
        worker = get_current_worker()
        client = self._ensure_own_client()
        if not client or worker.is_cancelled:
            return
        try:
            response = client.send_command(
                {"type": "top", "action": "start", "stream": False}
            )
            if worker.is_cancelled:
                return
            if response.get("status") == "success":
                top_id = response.get("top_id")

                def _apply_started() -> None:
                    self._top_id = top_id
                    self._is_profiling = True
                    self._start_refresh_worker()
                    self._update_button_states()
                    self._set_header_text(
                        "Profiling... | Samples: 0 | Interval: 10.0ms"
                    )

                self.app.call_from_thread(_apply_started)
            else:
                error = response.get("error", "Unknown error")
                self.app.call_from_thread(
                    self._set_header_text, f"Error starting profiler: {error}"
                )
        except Exception as e:
            if not worker.is_cancelled:
                try:
                    self.app.call_from_thread(
                        self._set_header_text, f"Error starting profiler: {e}"
                    )
                except Exception:
                    pass

    def _stop_profiling(self) -> None:
        """Stop the profiler and refresh worker without blocking the UI thread."""
        # Cancel refresh worker first
        if self._refresh_worker:
            self._refresh_worker.cancel()
            self._refresh_worker = None

        if not (self._own_client or self._client):
            return
        if self._command_worker:
            self._command_worker.cancel()
        self._command_worker = self.run_worker(
            self._stop_profiling_worker,
            thread=True,
            exclusive=True,
            group="top-commands",
        )

    def _stop_profiling_worker(self) -> None:
        """Send top stop command on a worker thread."""
        worker = get_current_worker()
        client = self._own_client or self._client
        if not client or worker.is_cancelled:
            return
        try:
            response = client.send_command({"type": "top", "action": "stop"})
            if worker.is_cancelled:
                return
            if response.get("status") == "success":

                def _apply_stopped() -> None:
                    self._is_profiling = False
                    self._top_id = None
                    self._update_button_states()
                    self._set_header_text("Top View - Stopped")
                    self.app.notify("Profiler stopped", severity="information")

                self.app.call_from_thread(_apply_stopped)
            else:
                error = response.get("error", "Unknown error")
                self.app.call_from_thread(
                    self.app.notify, f"Stop failed: {error}", severity="error"
                )
        except Exception as e:
            if not worker.is_cancelled:
                try:
                    self.app.call_from_thread(
                        self.app.notify, f"Stop error: {e}", severity="error"
                    )
                except Exception:
                    pass

    def _start_refresh_worker(self) -> None:
        """Start background refresh worker."""
        self._refresh_worker = self.run_worker(
            self._periodic_refresh,
            thread=True,
            exclusive=True,
            group="top-refresh",
        )

    def _periodic_refresh(self) -> None:
        """Periodically fetch and update top snapshot."""
        worker = get_current_worker()

        while not worker.is_cancelled:
            # Sleep in 0.1s increments (total 1s) for responsive cancellation
            for _ in range(10):
                if worker.is_cancelled:
                    return
                time.sleep(0.1)

            if worker.is_cancelled:
                break

            client = self._own_client or self._client
            if client and self._is_profiling:
                try:
                    response = client.send_command(
                        {"type": "top", "action": "snapshot"}
                    )
                    if response.get("status") == "success":
                        snapshot = response.get("snapshot", {})
                        self.app.call_from_thread(self._update_table, snapshot)
                except Exception:
                    pass  # Silent failure, keep retrying

    def _update_table(self, snapshot: Dict[str, Any]) -> None:
        """Update DataTable with new snapshot data.

        Args:
            snapshot: Top snapshot data from agent
        """
        # Update header
        header = self.query_one("#top-header", Static)
        total_samples = snapshot.get("total_samples", 0)
        interval = snapshot.get("sample_interval", 0.01)
        interval_ms = interval * 1000
        profile_id = snapshot.get("profile_id", "")

        if profile_id:
            header.update(
                f"Profiling... \\[{profile_id}] | Samples: {total_samples} | Interval: {interval_ms:.1f}ms"
            )
        else:
            header.update(
                f"Profiling... | Samples: {total_samples} | Interval: {interval_ms:.1f}ms"
            )

        # Update table
        table = self.query_one("#top-table", DataTable)
        table.clear()

        functions = snapshot.get("functions", [])
        for func in functions:
            table.add_row(
                f"{func['own_pct']:.1f}%",
                f"{func['total_pct']:.1f}%",
                f"{func['own_time']:.2f}s",
                f"{func['total_time']:.2f}s",
                f"{func['name']} ({func['filename']}:{func['line']})",
            )

    def action_reset_stats(self) -> None:
        """Reset profiling statistics (triggered by 'r' key or Reset button)."""
        client = self._own_client or self._client
        if not client or not self._is_profiling:
            self.app.notify("Profiler not running", severity="warning")
            return
        if self._command_worker:
            self._command_worker.cancel()
        self._command_worker = self.run_worker(
            self._reset_stats_worker,
            thread=True,
            exclusive=True,
            group="top-commands",
        )

    def _reset_stats_worker(self) -> None:
        """Send top reset command on a worker thread."""
        worker = get_current_worker()
        client = self._own_client or self._client
        if not client or not self._is_profiling or worker.is_cancelled:
            return
        try:
            response = client.send_command({"type": "top", "action": "reset"})
            if worker.is_cancelled:
                return
            if response.get("status") == "success":

                def _apply_reset() -> None:
                    self.app.notify("Statistics reset", severity="information")
                    table = self.query_one("#top-table", DataTable)
                    table.clear()
                    self._set_header_text("Profiling... | Samples: 0 | Stats reset")

                self.app.call_from_thread(_apply_reset)
            else:
                error = response.get("error", "Unknown error")
                self.app.call_from_thread(
                    self.app.notify, f"Reset failed: {error}", severity="error"
                )
        except Exception as e:
            if not worker.is_cancelled:
                try:
                    self.app.call_from_thread(
                        self.app.notify, f"Reset error: {e}", severity="error"
                    )
                except Exception:
                    pass

    def on_unmount(self) -> None:
        """Cleanup when view is unmounted."""
        if self._command_worker:
            self._command_worker.cancel()
            self._command_worker = None
        # Cancel refresh worker
        if self._refresh_worker:
            self._refresh_worker.cancel()
            self._refresh_worker = None

        # Stop profiling
        client = self._own_client or self._client
        if client and self._is_profiling:
            try:
                client.send_command({"type": "top", "action": "stop"})
            except Exception:
                pass  # Best effort
            finally:
                self._is_profiling = False
                self._top_id = None

        # Disconnect dedicated client
        self._disconnect_own_client()

    def cleanup_for_exit(self) -> None:
        """Cleanup profiling state and dedicated connection on exit."""
        self.on_unmount()
