"""
Monitor View - Performance statistics interface.
"""

from typing import Optional, Dict, TYPE_CHECKING
import logging
import threading

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button
from textual.worker import Worker, get_current_worker

from peeka.tui.activity import make_activity_reporter
from peeka.tui.completion import CompletionSource
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient

class MonitorView(Container):
    """Monitor view for performance statistics."""

    BINDINGS = [
        Binding("enter", "start_monitor", "Monitor"),
        Binding("delete", "stop_monitors", "Stop All"),
    ]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._stream_client: Optional["StreamingAgentClient"] = None
        self._stream_client_lock: threading.Lock = threading.Lock()
        self._socket_path: Optional[str] = None
        self._completion_source: Optional[CompletionSource] = None
        self._workers: Dict[str, Worker] = {}
        self._log = logging.getLogger(__name__)

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client
        self._socket_path = client.socket_path
        self._completion_source = CompletionSource(client)
        # Defer stream client creation to first use (lazy connection)

    def _connect_own_stream_client(self) -> None:
        """Create a dedicated StreamingAgentClient for streaming observations."""
        if not self._socket_path:
            return
        try:
            from peeka.core.client import StreamingAgentClient
            self._stream_client = StreamingAgentClient(
                self._socket_path,
                activity_reporter=make_activity_reporter(self.app, "monitor-stream"),
            )
            result = self._stream_client.connect()
            if result.get("status") != "success":
                self._log.warning(
                    "Monitor stream client failed: %s", result.get("error")
                )
                self._stream_client = None
        except Exception as e:
            self._log.warning("Monitor stream client error: %s", e)
            self._stream_client = None

    def _ensure_stream_client(self) -> Optional["StreamingAgentClient"]:
        """Lazily create stream client on first use (thread-safe)."""
        if self._stream_client is None:
            with self._stream_client_lock:
                if self._stream_client is None:
                    self._connect_own_stream_client()
        return self._stream_client

    def _get_pattern_completions(self, prefix: str):
        """Get completions for pattern input."""
        if self._completion_source:
            return self._completion_source.get_completions(prefix)
        return []

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Static("Pattern:", classes="input-label"),
                AutoCompleteInput(
                    placeholder="module.Class.method",
                    completions_callback=self._get_pattern_completions,
                    id="monitor-pattern",
                ),
                Static("Interval:", classes="input-label"),
                Input(
                    placeholder="interval (seconds)",
                    value="5",
                    id="monitor-interval",
                ),
                Button("Monitor", id="monitor-btn", variant="primary", flat=True),
                Button("Stop", id="stop-monitor-btn", variant="error", flat=True),
                id="monitor-controls",
                classes="compact-control",
            ),
            Vertical(
                DataTable(id="stats-table"),
                id="stats-panel",
                classes="panel",
            ),
            id="monitor-container",
        )

    def on_mount(self) -> None:
        container = self.query_one("#monitor-container", Container)
        container.border_title = "Monitor"

        table = self.query_one("#stats-table", DataTable)
        table.add_columns(
            ("Pattern", "Pattern"),
            ("Calls", "Calls"),
            ("Success", "Success"),
            ("Fail", "Fail"),
            ("Avg(ms)", "Avg(ms)"),
            ("Min(ms)", "Min(ms)"),
            ("Max(ms)", "Max(ms)"),
            ("P95(ms)", "P95(ms)"),
        )

        stats_panel = self.query_one("#stats-panel", Vertical)
        stats_panel.border_title = "Performance Statistics"

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "monitor-btn":
            await self._start_monitor()
        elif event.button.id == "stop-monitor-btn":
            await self._stop_all_monitors()

    def action_start_monitor(self) -> None:
        """Start monitoring (triggered by Enter key)."""
        self.app.call_later(self._start_monitor)

    def action_stop_monitors(self) -> None:
        """Stop all monitors (triggered by Delete key)."""
        self.app.call_later(self._stop_all_monitors)

    async def _start_monitor(self) -> None:
        if not self._client:
            self.app.notify("Not connected to agent", severity="error")
            return

        pattern_widget = self.query_one("#monitor-pattern")
        if isinstance(pattern_widget, AutoCompleteInput):
            pattern = pattern_widget.value.strip()
        else:
            pattern = pattern_widget.value.strip()  # type: ignore

        interval_input = self.query_one("#monitor-interval", Input)
        if not pattern:
            self.app.notify("Please enter a function pattern", severity="warning")
            return

        try:
            interval = int(interval_input.value.strip() or "5")
            if interval < 1:
                raise ValueError("Interval must be at least 1 second")
        except ValueError as e:
            self.app.notify(f"Invalid interval: {e}", severity="warning")
            return

        command = {
            "type": "monitor",
            "action": "start",
            "pattern": pattern,
            "cycle": interval,
            "cycles": -1,
        }

        worker = self.run_worker(
            lambda: self._client.send_command(command),
            thread=True,
        )
        await worker.wait()
        try:
            response = worker.result
        except Exception as e:
            self.app.notify(f"Connection error: {e}", severity="error")
            return

        if response.get("status") != "success":
            self.app.notify(
                f"Monitor failed: {response.get('error', 'Unknown error')}",
                severity="error",
            )
            return

        watch_id = response.get("watch_id", "")

        table = self.query_one("#stats-table", DataTable)
        table.add_row(pattern, "0", "0", "0", "0.0", "0.0", "0.0", "0.0", key=watch_id)

        worker = self.run_worker(
            lambda: self._stream_stats(watch_id, pattern), thread=True, exclusive=False
        )
        self._workers[watch_id] = worker

        self.app.notify(
            f"Monitoring started: {pattern} (every {interval}s)", severity="information"
        )

    def _stream_stats(self, watch_id: str, pattern: str):
        stream = self._ensure_stream_client() or self._client
        if not stream:
            return

        worker = get_current_worker()

        for observation in stream.stream_observations():
            if worker.is_cancelled:
                break

            obs_watch_id = observation.get("watch_id", "")
            if obs_watch_id != watch_id:
                continue

            total = observation.get("total", 0)
            success = observation.get("success", 0)
            fail = observation.get("fail", 0)
            rt_avg = observation.get("rt_avg", 0.0)
            rt_min = observation.get("rt_min", 0.0)
            rt_max = observation.get("rt_max", 0.0)
            rt_p95 = observation.get("rt_p95", 0.0)

            self.app.call_from_thread(
                self._update_stats_ui,
                watch_id,
                pattern,
                total,
                success,
                fail,
                rt_avg,
                rt_min,
                rt_max,
                rt_p95,
            )

    def _update_stats_ui(
        self,
        watch_id: str,
        pattern: str,
        total: int,
        success: int,
        fail: int,
        rt_avg: float,
        rt_min: float,
        rt_max: float,
        rt_p95: float,
    ) -> None:
        table = self.query_one("#stats-table", DataTable)

        try:
            table.update_cell(watch_id, "Calls", str(total))
            table.update_cell(watch_id, "Success", str(success))
            table.update_cell(watch_id, "Fail", str(fail))
            table.update_cell(watch_id, "Avg(ms)", f"{rt_avg:.2f}")
            table.update_cell(watch_id, "Min(ms)", f"{rt_min:.2f}")
            table.update_cell(watch_id, "Max(ms)", f"{rt_max:.2f}")
            table.update_cell(watch_id, "P95(ms)", f"{rt_p95:.2f}")
        except Exception:
            pass

    async def _stop_all_monitors(self) -> None:
        if not self._workers:
            self.app.notify("No active monitors", severity="information")
            return

        for watch_id, worker in list(self._workers.items()):
            if worker:
                worker.cancel()

            try:
                if self._client:
                    stop_worker = self.run_worker(
                        lambda wid=watch_id: self._client.send_command(
                            {"type": "monitor", "action": "stop", "watch_id": wid}
                        ),
                        thread=True,
                    )
                    await stop_worker.wait()
            except Exception:
                pass

        self._workers.clear()

        table = self.query_one("#stats-table", DataTable)
        table.clear()

        self.app.notify("All monitors stopped", severity="information")

    def on_unmount(self) -> None:
        """Cancel all workers and disconnect stream client when view is unmounted."""
        for worker in self._workers.values():
            if worker:
                worker.cancel()
        if self._stream_client:
            self._stream_client.disconnect()
            self._stream_client = None

    def cleanup_for_exit(self) -> None:
        """Stop all monitors before TUI exit."""
        if not self._client:
            return

        for watch_id, worker in list(self._workers.items()):
            if worker:
                worker.cancel()

            try:
                self._client.send_command(
                    {
                        "type": "monitor",
                        "action": "stop",
                        "watch_id": watch_id,
                    }
                )
            except Exception:
                pass

        self._workers.clear()
        if self._stream_client:
            self._stream_client.disconnect()
            self._stream_client = None
