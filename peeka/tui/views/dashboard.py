"""
Dashboard View - Overview of attached process.
"""

import time
from typing import TYPE_CHECKING, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Static
from textual.worker import Worker, get_current_worker

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class DashboardView(Container):
    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._refresh_worker: Optional[Worker] = None
        self._start_time = time.time()

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client

    def compose(self) -> ComposeResult:
        process_info = Vertical(
            Static(f"PID: {self.pid}", id="pid-info"),
            Static("Python: detecting...", id="python-version"),
            Static("Uptime: calculating...", id="uptime"),
            id="process-info",
            classes="panel",
        )
        process_info.border_title = "Process Info"

        memory_section = Vertical(
            Static("RSS: detecting...", id="mem-rss"),
            Static("Traced: N/A", id="mem-traced"),
            Static("Peak: N/A", id="mem-peak"),
            id="memory-section",
            classes="panel",
        )
        memory_section.border_title = "Memory Usage"

        watch_section = Vertical(
            Static("0", id="watch-count"),
            id="watch-section",
            classes="panel",
        )
        watch_section.border_title = "Active Watches"

        gc_section = Vertical(
            Static("Gen0: 0", id="gc-gen0"),
            Static("Gen1: 0", id="gc-gen1"),
            Static("Gen2: 0", id="gc-gen2"),
            id="gc-section",
            classes="panel",
        )
        gc_section.border_title = "GC Statistics"

        yield Container(
            Horizontal(
                process_info,
                memory_section,
                id="metrics-row",
            ),
            Horizontal(
                watch_section,
                gc_section,
                id="activity-row",
            ),
            id="dashboard-container",
        )

    async def on_mount(self) -> None:
        if self._client:
            await self._refresh_dashboard()
            self._start_refresh_worker()

    def on_unmount(self) -> None:
        if self._refresh_worker:
            self._refresh_worker.cancel()

    def action_refresh(self) -> None:
        """Refresh dashboard data."""
        if self._client:
            self._refresh_dashboard_sync()

    def _start_refresh_worker(self) -> None:
        if not self._client or self._refresh_worker:
            return

        self._refresh_worker = self.run_worker(
            lambda: self._periodic_refresh(), thread=True, exclusive=False
        )

    def _periodic_refresh(self):
        worker = get_current_worker()

        while not worker.is_cancelled:
            time.sleep(3)

            if worker.is_cancelled:
                break

            self.app.call_from_thread(self._refresh_dashboard_sync)

    def _refresh_dashboard_sync(self) -> None:
        self.run_worker(self._refresh_dashboard(), exclusive=False)

    async def _refresh_dashboard(self) -> None:
        if not self._client:
            return

        await self._update_python_version()
        await self._update_memory_stats()
        await self._update_uptime()

    async def _update_python_version(self) -> None:
        if not self._client:
            return

        response = self._client.send_command(
            {"type": "vmtool", "action": "get", "target": "sys.version", "depth": 1}
        )

        if response.get("status") == "success":
            version = response.get("value", "unknown")
            if isinstance(version, str):
                version_short = version.split()[0]
                self.query_one("#python-version", Static).update(
                    f"Python: {version_short}"
                )

    async def _update_memory_stats(self) -> None:
        if not self._client:
            return

        response = self._client.send_command({"type": "memory", "action": "overview"})

        if response.get("status") == "success":
            rss_bytes = response.get("rss_bytes", 0)
            rss_mb = rss_bytes / (1024 * 1024)

            self.query_one("#mem-rss", Static).update(f"RSS: {rss_mb:.1f} MB")

            tracemalloc_data = response.get("tracemalloc", {})
            if tracemalloc_data.get("enabled"):
                current_bytes = tracemalloc_data.get("current_bytes", 0)
                peak_bytes = tracemalloc_data.get("peak_bytes", 0)
                current_mb = current_bytes / (1024 * 1024)
                peak_mb = peak_bytes / (1024 * 1024)

                self.query_one("#mem-traced", Static).update(
                    f"Traced: {current_mb:.1f} MB"
                )
                self.query_one("#mem-peak", Static).update(f"Peak: {peak_mb:.1f} MB")
            else:
                self.query_one("#mem-traced", Static).update("Traced: Not enabled")
                self.query_one("#mem-peak", Static).update("Peak: N/A")

            gc_data = response.get("gc", {})
            gc_counts = gc_data.get("counts", [0, 0, 0])

            self.query_one("#gc-gen0", Static).update(f"Gen0: {gc_counts[0]}")
            self.query_one("#gc-gen1", Static).update(f"Gen1: {gc_counts[1]}")
            self.query_one("#gc-gen2", Static).update(f"Gen2: {gc_counts[2]}")

    async def _update_uptime(self) -> None:
        elapsed = time.time() - self._start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)

        if hours > 0:
            uptime_str = f"Uptime: {hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            uptime_str = f"Uptime: {minutes}m {seconds}s"
        else:
            uptime_str = f"Uptime: {seconds}s"

        self.query_one("#uptime", Static).update(uptime_str)
