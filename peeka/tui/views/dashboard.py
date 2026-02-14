"""
Dashboard View - Overview of attached process.
"""

import time
from typing import TYPE_CHECKING, Any, Dict, Optional

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
        # Trigger initial data load and periodic refresh.
        # set_client is called after on_mount, so we must start here.
        self._refresh_dashboard_sync()
        self._start_refresh_worker()

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
        pass

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
            for _ in range(30):
                if worker.is_cancelled:
                    return
                time.sleep(0.1)

            if worker.is_cancelled:
                break

            self.app.call_from_thread(self._refresh_dashboard_sync)
            self.app.call_from_thread(self._update_uptime)

    def _refresh_dashboard_sync(self) -> None:
        """Launch worker thread to fetch dashboard data."""
        if not self._client:
            return

        def worker_fn():
            data: Dict[str, Any] = {}
            ver_resp = lambda: self._client.send_command(
                {"type": "vmtool", "action": "get", "target": "sys.version", "depth": 1}
            )
            ver_result = ver_resp()
            if ver_result.get("status") == "success":
                data["python_version"] = ver_result.get("value", "unknown")
            mem_resp = lambda: self._client.send_command(
                {"type": "memory", "action": "overview"}
            )
            mem_result = mem_resp()
            if mem_result.get("status") == "success":
                data["rss_bytes"] = mem_result.get("rss_bytes", 0)
                data["tracemalloc"] = mem_result.get("tracemalloc", {})
                data["gc"] = mem_result.get("gc", {})
            self.app.call_from_thread(self._update_dashboard_ui, data)
            return data

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _update_dashboard_ui(self, data: Dict[str, Any]) -> None:
        """Update UI with fetched data (runs on main thread)."""
        # Update Python version
        if "python_version" in data:
            version = data["python_version"]
            if isinstance(version, str):
                version_short = version.split()[0]
                self.query_one("#python-version", Static).update(
                    f"Python: {version_short}"
                )

        # Update memory
        if "rss_bytes" in data:
            rss_bytes = data["rss_bytes"]
            rss_mb = rss_bytes / (1024 * 1024)
            self.query_one("#mem-rss", Static).update(f"RSS: {rss_mb:.1f} MB")

            tracemalloc_data = data.get("tracemalloc", {})
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

            gc_data = data.get("gc", {})
            gc_counts = gc_data.get("counts", [0, 0, 0])

            self.query_one("#gc-gen0", Static).update(f"Gen0: {gc_counts[0]}")
            self.query_one("#gc-gen1", Static).update(f"Gen1: {gc_counts[1]}")
            self.query_one("#gc-gen2", Static).update(f"Gen2: {gc_counts[2]}")

    def _update_uptime(self) -> None:
        """Update uptime display."""
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
