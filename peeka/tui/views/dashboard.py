"""
Dashboard View - Arthas-style overview of attached process.

Layout inspired by Alibaba Arthas dashboard and py-spy top:
  - Thread table (top, dominant) — TID, Name, State, Daemon, Depth, Top Frame
  - Memory + GC table (middle-left / middle-right)
  - Runtime info (bottom-left)
  - Activity Log (bottom-right) - displays agent and current-client activity
"""

import logging
import os
import platform
import re
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, RichLog, Static
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

_SESSION_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d+(?:\.\d+)?) (?P<level>[A-Z]+) (?P<message>.*)$"
)


class DashboardView(Container):
    """Arthas-style dashboard with thread table, memory/GC stats, and runtime info."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("c", "clear_agent_log", "Clear Activity Log"),
    ]

    MAX_LOG_LINES = 1000

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._own_client: Optional["StreamingAgentClient"] = None
        self._stream_client: Optional["StreamingAgentClient"] = None
        self._stream_client_lock: threading.Lock = threading.Lock()
        self._socket_path: Optional[str] = None
        self._refresh_worker: Optional[Worker] = None
        self._log_worker: Optional[Worker] = None
        self._start_time = time.time()
        self._log = logging.getLogger(__name__)
        self._active = True
        self._session_id: Optional[str] = None
        self._agent_history_loaded = False
        self._last_client_activity_seq = 0
        self._activity_listener_registered = False

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client
        self._socket_path = client.socket_path
        self._session_id = self._extract_session_id(client.socket_path)
        self._load_client_activity_history()
        self._register_client_activity_listener()
        self._load_persisted_agent_log_history()
        # Create a dedicated connection for dashboard worker to avoid
        # socket contention with other views sharing the same client.
        self._connect_own_client()
        self._connect_agent_log_stream()
        self._refresh_dashboard_sync()
        self._start_refresh_worker()

    def set_active(self, active: bool) -> None:
        """Pause background work while the dashboard tab is hidden.

        Args:
            active: Whether this view is currently visible.
        """
        if self._active == active:
            return

        self._active = active
        if active:
            if self._client:
                self._load_persisted_agent_log_history()
                self._load_client_activity_history()
                if not self._own_client:
                    self._connect_own_client()
                if not self._stream_client:
                    self._connect_agent_log_stream()
                self._refresh_dashboard_sync()
                self._start_refresh_worker()
        else:
            self._stop_refresh_worker()
            self._stop_log_worker()
            self._disconnect_dedicated_clients()

    def _connect_own_client(self) -> None:
        """Create a dedicated StreamingAgentClient for dashboard data fetching."""
        if not self._socket_path:
            return
        from peeka.core.client import StreamingAgentClient

        self._own_client = StreamingAgentClient(self._socket_path)
        result = self._own_client.connect()
        if result.get("status") != "success":
            error = result.get("error")
            self._log.warning("Dashboard dedicated client failed: %s", error)
            self._record_client_activity(
                "WARNING", f"dedicated data client failed: {error}"
            )
            self._own_client = None
            return

        self._record_client_activity("INFO", "dedicated data client connected")

    def _connect_agent_log_stream(self) -> None:
        """Create a dedicated StreamingAgentClient for agent log streaming."""
        if not self._socket_path:
            return
        try:
            from peeka.core.client import StreamingAgentClient

            self._stream_client = StreamingAgentClient(self._socket_path)
            result = self._stream_client.connect()
            if result.get("status") != "success":
                error = result.get("error")
                self._log.warning("Agent log stream client failed: %s", error)
                self._record_client_activity(
                    "WARNING", f"activity stream failed: {error}"
                )
                self._stream_client = None
                return
            self._record_client_activity("INFO", "activity stream connected")
            self._start_log_worker()
        except Exception as e:
            self._log.warning("Agent log stream client error: %s", e)
            self._record_client_activity("WARNING", f"activity stream error: {e}")
            self._stream_client = None

    def action_clear_agent_log(self) -> None:
        """Clear the activity log display."""
        rich_log = self.query_one("#dash-agent-log", RichLog)
        rich_log.clear()

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
            classes="panel panel--primary",
        )
        thread_section.border_title = "Threads"

        # -- Memory table (Arthas-style: used / total / max / usage) --
        memory_section = Vertical(
            DataTable(id="dash-mem-table"),
            id="dash-memory-section",
            classes="panel panel--detail",
        )
        memory_section.border_title = "Memory"

        # -- GC Statistics (Arthas-style: generation counts) --
        gc_section = Vertical(
            DataTable(id="dash-gc-table"),
            id="dash-gc-section",
            classes="panel panel--detail",
        )
        gc_section.border_title = "GC"

        # -- Runtime info (Arthas-style: key-value pairs) --
        runtime_section = Vertical(
            Static("", id="dash-runtime-info"),
            id="dash-runtime-section",
            classes="panel panel--detail",
        )
        runtime_section.can_focus = True
        runtime_section.border_title = "Runtime"

        # -- Activity Log (agent-side logs + current client activity) --
        agent_log_section = Vertical(
            RichLog(
                id="dash-agent-log",
                highlight=True,
                max_lines=self.MAX_LOG_LINES,
                auto_scroll=True,
            ),
            id="dash-agent-log-section",
            classes="panel panel--stream",
        )
        agent_log_section.border_title = "Activity Log (c to clear)"

        yield Horizontal(
            thread_summary,
            Static("", classes="spacer"),
            Button("Refresh", id="dash-refresh-btn", variant="default", flat=True),
            id="dash-controls",
            classes="compact-control",
        )
        yield Container(
            thread_section,
            Horizontal(
                Vertical(
                    memory_section,
                    gc_section,
                    runtime_section,
                    id="dash-summary-column",
                ),
                agent_log_section,
                id="dash-detail-row",
            ),
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
        self._stop_refresh_worker()
        self._stop_log_worker()
        self._disconnect_dedicated_clients()
        self._unregister_client_activity_listener()

    def action_refresh(self) -> None:
        """Refresh dashboard data."""
        if self._client:
            self._record_client_activity("INFO", "manual refresh")
            self._refresh_dashboard_sync()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "dash-refresh-btn":
            self.action_refresh()

    # -- Periodic refresh -------------------------------------------------------

    def _start_refresh_worker(self) -> None:
        if not self._active or not self._client or self._refresh_worker:
            return

        self._refresh_worker = self.run_worker(
            lambda: self._periodic_refresh(), thread=True, exclusive=False
        )

    def _stop_refresh_worker(self) -> None:
        """Cancel the periodic dashboard refresh worker."""
        if self._refresh_worker:
            self._refresh_worker.cancel()
            self._refresh_worker = None

    def _start_log_worker(self) -> None:
        """Start agent log streaming when the dashboard is active."""
        if not self._active or not self._stream_client or self._log_worker:
            return

        self._log_worker = self.run_worker(
            lambda: self._stream_agent_log_messages(),
            thread=True,
            exclusive=False,
        )

    def _stop_log_worker(self) -> None:
        """Cancel the agent log streaming worker."""
        if self._log_worker:
            self._log_worker.cancel()
            self._log_worker = None

    def _disconnect_dedicated_clients(self) -> None:
        """Disconnect dashboard-owned clients."""
        if self._own_client:
            self._own_client.disconnect()
            self._own_client = None
        if self._stream_client:
            self._stream_client.disconnect()
            self._stream_client = None

    def _periodic_refresh(self) -> None:
        worker = get_current_worker()

        while not worker.is_cancelled:
            for _ in range(30):
                if worker.is_cancelled:
                    return
                time.sleep(0.1)

            if worker.is_cancelled:
                break

            if self._active:
                self.app.call_from_thread(self._refresh_dashboard_sync)

    # -- Data fetch -------------------------------------------------------------

    def _refresh_dashboard_sync(self) -> None:
        """Launch worker thread to fetch dashboard data."""
        client = self._own_client or self._client
        if not self._active or not client:
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

            if self._active:
                self.app.call_from_thread(self._update_dashboard_ui, data)
            return data

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _extract_session_id(self, socket_path: str) -> Optional[str]:
        """Extract the peeka session id from a socket path."""
        stem = Path(socket_path).stem
        if not stem.startswith("peeka_"):
            return None
        return stem.replace("peeka_", "", 1)

    def _get_session_log_path(self) -> Optional[Path]:
        """Return the persisted session log path when the session is known."""
        if not self._session_id:
            return None
        return Path(tempfile.gettempdir()) / f"peeka_{self._session_id}.log"

    def _register_client_activity_listener(self) -> None:
        """Subscribe to app-level client activity updates."""
        if self._activity_listener_registered:
            return

        register = getattr(self.app, "register_activity_listener", None)
        if not callable(register):
            return

        register(self._handle_client_activity)
        self._activity_listener_registered = True

    def _unregister_client_activity_listener(self) -> None:
        """Unsubscribe from app-level client activity updates."""
        if not self._activity_listener_registered:
            return

        unregister = getattr(self.app, "unregister_activity_listener", None)
        if callable(unregister):
            unregister(self._handle_client_activity)
        self._activity_listener_registered = False

    def _load_client_activity_history(self) -> None:
        """Replay buffered client activity emitted before the dashboard mounted."""
        getter = getattr(self.app, "get_client_activity_entries", None)
        if not callable(getter):
            return

        for entry in getter(after_seq=self._last_client_activity_seq):
            self._ingest_client_activity_entry(entry)

    def _handle_client_activity(self, entry: Dict[str, Any]) -> None:
        """Append future client activity entries to the dashboard log."""
        if threading.current_thread() is threading.main_thread():
            self._ingest_client_activity_entry(entry)
            return

        self.app.call_from_thread(self._ingest_client_activity_entry, dict(entry))

    def _record_client_activity(
        self, level: str, message: str, source: str = "dashboard"
    ) -> None:
        """Emit a client-side activity entry when the app supports it."""
        recorder = getattr(self.app, "record_client_activity", None)
        if callable(recorder):
            recorder(level, message, source=source)

    def _ingest_client_activity_entry(self, entry: Dict[str, Any]) -> None:
        """Render one buffered client activity entry into the activity log."""
        seq = int(entry.get("seq", 0))
        if seq <= self._last_client_activity_seq:
            return

        self._last_client_activity_seq = seq
        message = str(entry.get("message", ""))
        source = str(entry.get("source", "client"))
        if source and source not in ("client", "main"):
            message = f"{source}: {message}"

        self._write_activity_entry(
            "client",
            str(entry.get("level", "INFO")),
            message,
            entry.get("timestamp", ""),
        )

    def _load_persisted_agent_log_history(self) -> None:
        """Replay the persisted session log so late-opened dashboards aren't blank."""
        if self._agent_history_loaded:
            return

        log_path = self._get_session_log_path()
        if not log_path or not log_path.exists():
            return

        last_level = "INFO"
        last_timestamp = ""

        try:
            for raw_line in log_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                if not raw_line.strip():
                    continue

                match = _SESSION_LOG_PATTERN.match(raw_line)
                if match:
                    last_timestamp = match.group("timestamp")
                    last_level = match.group("level")
                    message = match.group("message")
                else:
                    message = raw_line

                self._write_activity_entry(
                    "agent", last_level, message, last_timestamp
                )
        except OSError as e:
            self._log.debug("Failed to replay agent session log: %s", e)
            return

        self._agent_history_loaded = True

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

    # -- Activity Log Streaming ----------------------------------------------

    def _stream_agent_log_messages(self) -> None:
        """Stream log messages from the agent in background thread."""
        stream = self._stream_client or self._client
        if not stream:
            return

        worker = get_current_worker()

        for observation in stream.stream_observations():
            if worker.is_cancelled:
                break

            # Check if this is a log message
            if observation.get("type") != "log":
                continue

            level = observation.get("level", "INFO").upper()
            message = observation.get("message", "")
            timestamp = observation.get("timestamp", "")

            self.app.call_from_thread(
                self._write_activity_entry, "agent", level, message, timestamp
            )

    def _format_timestamp(self, timestamp: Any) -> str:
        """Format numeric timestamps into a stable human-readable time."""
        if timestamp in ("", None):
            return ""

        try:
            return time.strftime("%H:%M:%S", time.localtime(float(timestamp)))
        except (TypeError, ValueError):
            return str(timestamp)

    def _write_activity_entry(
        self, source: str, level: str, message: str, timestamp: Any
    ) -> None:
        """Add an activity entry to the RichLog widget (runs on main thread).

        Args:
            source: Entry origin label such as ``agent`` or ``client``.
            level: Log level (INFO, WARNING, ERROR, etc.)
            message: Log message text
            timestamp: Optional timestamp or timestamp string
        """
        rich_log = self.query_one("#dash-agent-log", RichLog)

        # Choose color based on log level
        style_map = {
            "DEBUG": "dim blue",
            "INFO": "blue",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold red",
        }
        style = style_map.get(level, "white")
        source_style_map = {
            "agent": "magenta",
            "client": "green",
        }
        source_style = source_style_map.get(source, "cyan")

        # Format the entry
        rendered_timestamp = self._format_timestamp(timestamp)
        if rendered_timestamp:
            text = Text(f"[{rendered_timestamp}] ", style="dim")
        else:
            text = Text()

        source_text = Text(f"{source.upper():7} ", style=source_style)
        level_text = Text(f"{level:8} ", style=style)
        message_text = Text(message, style=style)

        text.append(source_text)
        text.append(level_text)
        text.append(message_text)

        rich_log.write(text)
        # Auto-scroll is handled automatically by RichLog when auto_scroll=True
