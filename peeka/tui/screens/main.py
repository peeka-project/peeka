"""
Main Screen - Primary interface after attaching to a process.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Header, Footer, Static, TabbedContent, TabPane

from peeka.tui.views.dashboard import DashboardView
from peeka.tui.views.inspect import InspectView
from peeka.tui.views.logger import LoggerView
from peeka.tui.views.memory import MemoryView
from peeka.tui.views.monitor import MonitorView
from peeka.tui.views.stack import StackView
from peeka.tui.views.trace import TraceView
from peeka.tui.views.watch import WatchView
from peeka.tui.views.thread import ThreadView


class MainScreen(Screen):
    """Main screen with tabbed interface for different diagnostic views."""

    BINDINGS = [
        Binding("d", "switch_tab('dashboard')", "Dashboard", priority=True),
        Binding("w", "switch_tab('watch')", "Watch", priority=True),
        Binding("t", "switch_tab('trace')", "Trace", priority=True),
        Binding("s", "switch_tab('stack')", "Stack", priority=True),
        Binding("m", "switch_tab('monitor')", "Monitor", priority=True),
        Binding("e", "switch_tab('memory')", "Memory", priority=True),
        Binding("l", "switch_tab('logger')", "Logger", priority=True),
        Binding("i", "switch_tab('inspect')", "Inspect", priority=True),
        Binding("escape", "go_back", "Back", priority=True),
        Binding("h", "switch_tab('threads')", "Threads", priority=True),
        Binding("q", "go_back", "Back"),
    ]

    def __init__(self, pid: int, session_id: str, socket_path: str) -> None:
        super().__init__()
        self.pid = pid
        self.session_id = session_id
        self.socket_path = socket_path
        self._client = None
        self._stream_client = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            yield Static(f"Attached to PID: {self.pid}", id="pid-status")
            with TabbedContent(
                initial="dashboard",
                id="main-content",
            ):
                with TabPane("Dashboard", id="dashboard"):
                    yield DashboardView(self.pid)
                with TabPane("Watch", id="watch"):
                    yield WatchView(self.pid)
                with TabPane("Trace", id="trace"):
                    yield TraceView(self.pid)
                with TabPane("Stack", id="stack"):
                    yield StackView(self.pid)
                with TabPane("Monitor", id="monitor"):
                    yield MonitorView(self.pid)
                with TabPane("Memory", id="memory"):
                    yield MemoryView(self.pid)
                with TabPane("Logger", id="logger"):
                    yield LoggerView(self.pid)
                with TabPane("Inspect", id="inspect"):
                    yield InspectView(self.pid)
                with TabPane("Threads", id="threads"):
                    yield ThreadView(self.pid)
        yield Footer()

    async def on_mount(self) -> None:
        await self._connect()

        if self._client:
            dashboard_view = self.query_one(DashboardView)
            dashboard_view.set_client(self._client)

            watch_view = self.query_one(WatchView)
            watch_view.set_client(self._client)
            if self._stream_client:
                watch_view.set_stream_client(self._stream_client)

            trace_view = self.query_one(TraceView)
            trace_view.set_client(self._client)
            if self._stream_client:
                trace_view.set_stream_client(self._stream_client)

            logger_view = self.query_one(LoggerView)
            logger_view.set_client(self._client)

            stack_view = self.query_one(StackView)
            stack_view.set_client(self._client)
            if self._stream_client:
                stack_view.set_stream_client(self._stream_client)

            monitor_view = self.query_one(MonitorView)
            monitor_view.set_client(self._client)
            if self._stream_client:
                monitor_view.set_stream_client(self._stream_client)

            memory_view = self.query_one(MemoryView)
            memory_view.set_client(self._client)

            inspect_view = self.query_one(InspectView)
            inspect_view.set_client(self._client)

            thread_view = self.query_one(ThreadView)
            thread_view.set_client(self._client)

    def on_unmount(self) -> None:
        self._cleanup_all_views()

    async def _connect(self) -> None:
        """Connect to the target process agent with separate command and streaming sockets."""
        try:
            from peeka.core.client import StreamingAgentClient

            self._client = StreamingAgentClient(self.socket_path)
            result = self._client.connect()

            if result.get("status") != "success":
                error_msg = result.get("error", "Unknown connection error")
                self.notify(f"Failed to connect: {error_msg}", severity="error")
                return

            self._stream_client = StreamingAgentClient(self.socket_path)
            stream_result = self._stream_client.connect()

            if stream_result.get("status") != "success":
                error_msg = stream_result.get("error", "Unknown connection error")
                self.notify(
                    f"Stream connection failed: {error_msg}", severity="warning"
                )
                self._stream_client = None
        except Exception as e:
            self.notify(f"Failed to connect: {e}", severity="error")

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a specific view."""
        tabbed = self.query_one("#main-content", TabbedContent)
        tabbed.active = tab_id

    def action_go_back(self) -> None:
        self._cleanup_all_views()
        self.app.pop_screen()

    def _cleanup_all_views(self) -> None:
        for view_cls in (WatchView, TraceView, StackView, MonitorView):
            try:
                self.query_one(view_cls).cleanup_for_exit()
            except Exception:
                pass

        if self._client:
            try:
                self._client.send_command({"type": "detach"})
            except Exception:
                pass

        self._disconnect_clients()

    def _disconnect_clients(self) -> None:
        if self._stream_client:
            self._stream_client.disconnect()
        if self._client:
            self._client.disconnect()
