"""
Dashboard View - Arthas-style overview of attached process.

Layout inspired by Alibaba Arthas dashboard and py-spy top:
  - Thread table (top, dominant) — TID, Name, State, Daemon, Depth, Top Frame
  - Memory + GC table (middle-left / middle-right)
  - Runtime info (bottom)
"""

import logging
import os
import platform
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Static
from textual.worker import Worker, get_current_worker

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


# State badge styling (shared with thread view)
_STATE_BADGES = {
    "RUNNABLE": "[bold green]RUNNABLE[/]",
    "WAITING": "[bold yellow]WAITING[/]",
    "TIMED_WAITING": "[bold cyan]TIMED_WAIT[/]",
    "UNKNOWN": "[dim]UNKNOWN[/]",
}

_STATE_ORDER = {
    "RUNNABLE": 0,
    "TIMED_WAITING": 1,
    "WAITING": 2,
    "UNKNOWN": 3,
}


class DashboardView(Container):
    """Arthas-style dashboard with thread table, memory/GC stats, and runtime info."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._own_client: Optional["StreamingAgentClient"] = None
        self._socket_path: Optional[str] = None
        self._refresh_worker: Optional[Worker] = None
        self._start_time = time.time()
        self._log = logging.getLogger(__name__)

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client
        self._socket_path = client.socket_path
        # Create a dedicated connection for dashboard worker to avoid
        # socket contention with other views sharing the same client.
        self._connect_own_client()
        self._refresh_dashboard_sync()
        self._start_refresh_worker()

    def _connect_own_client(self) -> None:
        """Create a dedicated StreamingAgentClient for dashboard data fetching."""
        if not self._socket_path:
            return
        from peeka.core.client import StreamingAgentClient
        self._own_client = StreamingAgentClient(self._socket_path)
        result = self._own_client.connect()
        if result.get("status") != "success":
            self._log.warning("Dashboard dedicated client failed: %s", result.get("error"))
            self._own_client = None
    def compose(self) -> ComposeResult:
        # -- Controls bar (status + refresh button) --
        thread_summary = Static(
            "Threads: - total | - runnable | - waiting | - timed | - daemon",
            id="dash-thread-summary",
        )

        # -- Thread table (Arthas: dominant top section) --
        thread_section = Vertical(
            DataTable(id="dash-thread-table"),
            id="dash-thread-section",
            classes="panel",
        )
        thread_section.border_title = "Threads"

        # -- Memory table (Arthas-style: used / total / max / usage) --
        memory_section = Vertical(
            DataTable(id="dash-mem-table"),
            id="dash-memory-section",
            classes="panel",
        )
        memory_section.border_title = "Memory"

        # -- GC Statistics (Arthas-style: generation counts) --
        gc_section = Vertical(
            DataTable(id="dash-gc-table"),
            id="dash-gc-section",
            classes="panel",
        )
        gc_section.border_title = "GC"

        # -- Runtime info (Arthas-style: key-value pairs) --
        runtime_section = Vertical(
            Static("", id="dash-runtime-info"),
            id="dash-runtime-section",
            classes="panel",
        )
        runtime_section.border_title = "Runtime"

        yield Horizontal(
            thread_summary,
            Static("", classes="spacer"),
            Button("Refresh", id="dash-refresh-btn", variant="default", flat=True),
            id="dash-controls",
        )
        yield Container(
            thread_section,
            Horizontal(
                memory_section,
                gc_section,
                id="dash-mid-row",
            ),
            runtime_section,
            id="dashboard-container",
        )

    async def on_mount(self) -> None:
        container = self.query_one("#dashboard-container", Container)
        container.border_title = "Dashboard"

        # Thread table columns (Arthas-inspired)
        thread_table = self.query_one("#dash-thread-table", DataTable)
        thread_table.add_columns("TID", "Name", "State", "Daemon", "Depth", "Top Frame")
        thread_table.cursor_type = "row"

        # Memory table columns (Arthas: type / used / total / max / usage)
        mem_table = self.query_one("#dash-mem-table", DataTable)
        mem_table.add_columns("Type", "Used", "Total", "Max", "Usage")
        mem_table.show_cursor = False

        # GC table columns
        gc_table = self.query_one("#dash-gc-table", DataTable)
        gc_table.add_columns("Generation", "Collections", "Threshold", "Objects")
        gc_table.show_cursor = False

    def on_unmount(self) -> None:
        if self._refresh_worker:
            self._refresh_worker.cancel()
        if self._own_client:
            self._own_client.disconnect()
            self._own_client = None

    def action_refresh(self) -> None:
        """Refresh dashboard data."""
        if self._client:
            self._refresh_dashboard_sync()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "dash-refresh-btn":
            self.action_refresh()

    # -- Periodic refresh -------------------------------------------------------

    def _start_refresh_worker(self) -> None:
        if not self._client or self._refresh_worker:
            return

        self._refresh_worker = self.run_worker(
            lambda: self._periodic_refresh(), thread=True, exclusive=False
        )

    def _periodic_refresh(self) -> None:
        worker = get_current_worker()

        while not worker.is_cancelled:
            for _ in range(30):
                if worker.is_cancelled:
                    return
                time.sleep(0.1)

            if worker.is_cancelled:
                break

            self.app.call_from_thread(self._refresh_dashboard_sync)

    # -- Data fetch -------------------------------------------------------------

    def _refresh_dashboard_sync(self) -> None:
        """Launch worker thread to fetch dashboard data."""
        client = self._own_client or self._client
        if not client:
            return

        def worker_fn() -> Dict[str, Any]:
            data: Dict[str, Any] = {}
            # Use the dedicated client to avoid socket contention
            c = self._own_client or self._client
            if not c:
                return data

            # Python version
            ver_result = c.send_command(
                {"type": "vmtool", "action": "get", "target": "sys.version", "depth": 1}
            )
            if ver_result.get("status") == "success":
                data["python_version"] = ver_result.get("value", "unknown")
            elif ver_result.get("status") == "error":
                self._log.debug("vmtool(version) failed: %s", ver_result.get("error"))

            # sys.argv
            argv_result = c.send_command(
                {"type": "vmtool", "action": "get", "target": "sys.argv", "depth": 2}
            )
            if argv_result.get("status") == "success":
                data["sys_argv"] = argv_result.get("value", [])

            # Memory overview
            mem_result = c.send_command(
                {"type": "memory", "action": "overview"}
            )
            if mem_result.get("status") == "success":
                data["rss_bytes"] = mem_result.get("rss_bytes", 0)
                data["vms_bytes"] = mem_result.get("vms_bytes", 0)
                data["tracemalloc"] = mem_result.get("tracemalloc", {})
                data["gc"] = mem_result.get("gc", {})

            # Thread list
            thread_result = c.send_command(
                {"type": "thread", "action": "list"}
            )
            if thread_result.get("status") == "success":
                data["threads"] = thread_result.get("threads", [])
            elif thread_result.get("status") == "error":
                self._log.debug("thread(list) failed: %s", thread_result.get("error"))

            self.app.call_from_thread(self._update_dashboard_ui, data)
            return data

        self.run_worker(worker_fn, thread=True, exclusive=False)

    # -- UI updates -------------------------------------------------------------

    def _update_dashboard_ui(self, data: Dict[str, Any]) -> None:
        """Update all dashboard sections (runs on main thread)."""
        self._update_thread_section(data.get("threads", []))
        self._update_memory_table(data)
        self._update_gc_table(data)
        self._update_runtime_info(data)

    def _update_thread_section(self, threads: List[Dict[str, Any]]) -> None:
        """Update thread summary bar and thread table (Arthas-style)."""
        # Summary stats (py-spy top style)
        total = len(threads)
        runnable = sum(1 for t in threads if t.get("state") == "RUNNABLE")
        waiting = sum(1 for t in threads if t.get("state") == "WAITING")
        timed = sum(1 for t in threads if t.get("state") == "TIMED_WAITING")
        daemon_count = sum(1 for t in threads if t.get("daemon"))

        summary = (
            f"  Threads: [bold]{total}[/] total  |  "
            f"[bold green]{runnable}[/] runnable  |  "
            f"[bold yellow]{waiting}[/] waiting  |  "
            f"[bold cyan]{timed}[/] timed  |  "
            f"{daemon_count} daemon"
        )
        self.query_one("#dash-thread-summary", Static).update(summary)

        # Thread table — sort by state (RUNNABLE first, like Arthas sorts by CPU%)
        table = self.query_one("#dash-thread-table", DataTable)
        table.clear()

        sorted_threads = sorted(
            threads,
            key=lambda t: _STATE_ORDER.get(t.get("state", "UNKNOWN"), 99),
        )

        for t in sorted_threads[:20]:
            tid = t.get("tid", 0)
            name = t.get("name", "?")
            state = t.get("state", "UNKNOWN")
            daemon = t.get("daemon", False)
            stack_depth = t.get("stack_depth", 0)

            # Format top frame (py-spy style: function @ file:line)
            top_frame = t.get("top_frame")
            if top_frame:
                funcname = top_frame.get("funcname", "?")
                filename = top_frame.get("filename", "?")
                if "/" in filename:
                    filename = filename.rsplit("/", 1)[-1]
                lineno = top_frame.get("lineno", 0)
                top_str = f"{funcname} @ {filename}:{lineno}"
            else:
                top_str = "[dim]-[/]"

            state_badge = _STATE_BADGES.get(state, state)
            daemon_str = "[green]✓[/]" if daemon else ""

            table.add_row(
                str(tid),
                name,
                state_badge,
                daemon_str,
                str(stack_depth),
                top_str,
                key=str(tid),
            )

    def _update_memory_table(self, data: Dict[str, Any]) -> None:
        """Update memory table in Arthas style (type / used / total / max / usage)."""
        table = self.query_one("#dash-mem-table", DataTable)
        table.clear()

        rss_bytes = data.get("rss_bytes", 0)
        vms_bytes = data.get("vms_bytes", 0)
        tracemalloc_data = data.get("tracemalloc", {})

        # RSS row
        rss_mb = rss_bytes / (1024 * 1024) if rss_bytes else 0
        vms_mb = vms_bytes / (1024 * 1024) if vms_bytes else 0
        rss_usage = f"{rss_mb / vms_mb * 100:.1f}%" if vms_mb > 0 else "-"
        table.add_row(
            "rss",
            f"{rss_mb:.1f}M",
            f"{vms_mb:.1f}M" if vms_mb > 0 else "-",
            "-",
            rss_usage,
        )

        # VMS row
        table.add_row(
            "vms",
            f"{vms_mb:.1f}M",
            "-",
            "-",
            "-",
        )

        # Tracemalloc rows
        if tracemalloc_data.get("enabled"):
            current_bytes = tracemalloc_data.get("current_bytes", 0)
            peak_bytes = tracemalloc_data.get("peak_bytes", 0)
            current_mb = current_bytes / (1024 * 1024)
            peak_mb = peak_bytes / (1024 * 1024)
            trace_usage = f"{current_mb / peak_mb * 100:.1f}%" if peak_mb > 0 else "-"

            table.add_row(
                "traced",
                f"{current_mb:.1f}M",
                "-",
                f"{peak_mb:.1f}M",
                trace_usage,
            )
        else:
            table.add_row(
                "[dim]traced[/]",
                "[dim]N/A[/]",
                "[dim]-[/]",
                "[dim]-[/]",
                "[dim]disabled[/]",
            )

    def _update_gc_table(self, data: Dict[str, Any]) -> None:
        """Update GC statistics table (Arthas-style)."""
        table = self.query_one("#dash-gc-table", DataTable)
        table.clear()

        gc_data = data.get("gc", {})
        gc_counts = gc_data.get("counts", [0, 0, 0])
        gc_thresholds = gc_data.get("thresholds", [700, 10, 10])

        gen_names = ["gen0", "gen1", "gen2"]
        for i, gen_name in enumerate(gen_names):
            count = gc_counts[i] if i < len(gc_counts) else 0
            threshold = gc_thresholds[i] if i < len(gc_thresholds) else "-"

            # Color code based on how close to threshold
            if isinstance(threshold, int) and threshold > 0:
                ratio = count / threshold
                if ratio >= 0.8:
                    count_str = f"[bold red]{count}[/]"
                elif ratio >= 0.5:
                    count_str = f"[yellow]{count}[/]"
                else:
                    count_str = str(count)
            else:
                count_str = str(count)

            table.add_row(
                gen_name,
                count_str,
                str(threshold),
                "-",
            )

    def _update_runtime_info(self, data: Dict[str, Any]) -> None:
        """Update runtime info section (Arthas-style key-value pairs)."""
        # Python version
        python_version = data.get("python_version", "")
        if isinstance(python_version, str):
            short_ver = python_version.split()[0] if python_version else "unknown"
        else:
            short_ver = "unknown"

        # sys.argv
        argv_list = data.get("sys_argv", [])
        if isinstance(argv_list, list) and argv_list:
            argv_str = " ".join(str(a) for a in argv_list[:4])
            if len(argv_list) > 4:
                argv_str += " ..."
        else:
            argv_str = "N/A"

        # Uptime
        elapsed = time.time() - self._start_time
        hours = int(elapsed // 3600)
        minutes = int((elapsed % 3600) // 60)
        seconds = int(elapsed % 60)
        if hours > 0:
            uptime_str = f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            uptime_str = f"{minutes}m {seconds}s"
        else:
            uptime_str = f"{seconds}s"

        # Build Arthas-style runtime info block
        lines = [
            f"  os.name              {platform.system()}",
            f"  os.version           {platform.release()}",
            f"  python.version       {short_ver}",
            f"  pid                  {self.pid}",
            f"  sys.argv             {argv_str}",
            f"  processors           {os.cpu_count() or '-'}",
            f"  uptime               {uptime_str}",
        ]

        self.query_one("#dash-runtime-info", Static).update("\n".join(lines))
