"""
Main Screen - Primary interface after attaching to a process.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
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
        Binding("escape", "go_back", "Back"),
    ]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static(f"Attached to PID: {self.pid}", id="pid-status"),
            TabbedContent(
                TabPane("Dashboard", DashboardView(self.pid), id="dashboard"),
                TabPane("Watch", WatchView(self.pid), id="watch"),
                TabPane("Stack", StackView(self.pid), id="stack"),
                TabPane("Monitor", MonitorView(self.pid), id="monitor"),
                TabPane("Memory", MemoryView(self.pid), id="memory"),
                TabPane("Logger", LoggerView(self.pid), id="logger"),
                TabPane("Inspect", InspectView(self.pid), id="inspect"),
                id="main-tabs",
            ),
            id="main-container",
        )
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize connection to target process."""
        await self._connect()

    async def _connect(self) -> None:
        """Connect to the target process agent."""
        try:
            from peeka.core.client import StreamingAgentClient

            # Construct socket path based on PID
            socket_path = f"/tmp/peeka_{self.pid}.sock"

            self._client = StreamingAgentClient(socket_path)
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
