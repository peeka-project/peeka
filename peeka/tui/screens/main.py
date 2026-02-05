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
from peeka.tui.views.watch import WatchView


class MainScreen(Screen):
    """Main screen with tabbed interface for different diagnostic views."""

    BINDINGS = [
        Binding("d", "switch_tab('dashboard')", "Dashboard"),
        Binding("w", "switch_tab('watch')", "Watch"),
        Binding("s", "switch_tab('stack')", "Stack"),
        Binding("m", "switch_tab('monitor')", "Monitor"),
        Binding("e", "switch_tab('memory')", "Memory"),
        Binding("l", "switch_tab('logger')", "Logger"),
        Binding("i", "switch_tab('inspect')", "Inspect"),
        Binding("escape", "go_back", "Back", priority=True),
        Binding("q", "go_back", "Back"),
    ]

    def __init__(self, pid: int, session_id: str, socket_path: str) -> None:
        super().__init__()
        self.pid = pid
        self.session_id = session_id
        self.socket_path = socket_path
        self._client = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            yield Static(f"Attached to PID: {self.pid}", id="pid-status")
            with TabbedContent(id="main-tabs"):
                with TabPane("Dashboard", id="dashboard"):
                    yield DashboardView(self.pid)
                with TabPane("Watch", id="watch"):
                    yield WatchView(self.pid)
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
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize connection to target process."""
        await self._connect()

        if self._client:
            watch_view = self.query_one(WatchView)
            watch_view.set_client(self._client)

    async def _connect(self) -> None:
        """Connect to the target process agent."""
        try:
            from peeka.core.client import StreamingAgentClient

            self._client = StreamingAgentClient(self.socket_path)
            result = self._client.connect()

            if result.get("status") != "success":
                error_msg = result.get("error", "Unknown connection error")
                self.notify(f"Failed to connect: {error_msg}", severity="error")
        except Exception as e:
            self.notify(f"Failed to connect: {e}", severity="error")

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a specific tab."""
        tabs = self.query_one("#main-tabs", TabbedContent)
        tabs.active = tab_id

    def action_go_back(self) -> None:
        """Go back to process selector."""
        self.app.pop_screen()
