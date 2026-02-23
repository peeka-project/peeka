"""
Monitor View - Performance statistics interface.
"""

from typing import Optional, Dict, TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button
from textual.worker import Worker, get_current_worker

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
        self._workers: Dict[str, Worker] = {}

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client

    def set_stream_client(self, client: "StreamingAgentClient") -> None:
        self._stream_client = client

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Static("Pattern:", classes="input-label"),
                Input(
                    placeholder="module.Class.method",
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
            "Pattern",
            "Calls",
            "Success",
            "Fail",
            "Avg(ms)",
            "Min(ms)",
            "Max(ms)",
            "P95(ms)",
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

        pattern_input = self.query_one("#monitor-pattern", Input)
        interval_input = self.query_one("#monitor-interval", Input)

        pattern = pattern_input.value.strip()
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
            "interval": 3,  # seconds
        }

        worker = self.run_worker(
            lambda: self._client.send_command(command),
            thread=True,
        )
        await worker.wait()
        response = worker.result

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
        stream = self._stream_client or self._client
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
        """Cancel all workers when view is unmounted."""
        for worker in self._workers.values():
            if worker:
                worker.cancel()

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
