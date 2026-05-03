"""
Main Screen - Primary interface after attaching to a process.
"""

from typing import Any, Dict, Optional, Set, Type

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Header, Footer, TabbedContent, TabPane

from peeka.tui.views.dashboard import DashboardView
from peeka.tui.views.inspect import InspectView
from peeka.tui.views.logger import LoggerView
from peeka.tui.views.memory import MemoryView
from peeka.tui.views.monitor import MonitorView
from peeka.tui.views.stack import StackView
from peeka.tui.views.trace import TraceView
from peeka.tui.views.watch import WatchView
from peeka.tui.views.thread import ThreadView
from peeka.tui.views.top import TopView


class MainScreen(Screen):
    """Main screen with tabbed interface for different diagnostic views."""

    BINDINGS = [
        Binding("1", "switch_tab('dashboard')", "Dashboard"),
        Binding("2", "switch_tab('watch')", "Watch"),
        Binding("3", "switch_tab('trace')", "Trace"),
        Binding("4", "switch_tab('stack')", "Stack"),
        Binding("5", "switch_tab('monitor')", "Monitor"),
        Binding("6", "switch_tab('memory')", "Memory"),
        Binding("7", "switch_tab('logger')", "Logger"),
        Binding("8", "switch_tab('inspect')", "Inspect"),
        Binding("9", "switch_tab('threads')", "Threads"),
        Binding("escape", "go_back", "Back", priority=True),
        Binding("0", "switch_tab('top')", "Top"),
        Binding("q", "go_back", "Back"),
    ]

    _VIEW_BY_TAB: Dict[str, Type[Any]] = {
        "dashboard": DashboardView,
        "watch": WatchView,
        "trace": TraceView,
        "stack": StackView,
        "monitor": MonitorView,
        "memory": MemoryView,
        "logger": LoggerView,
        "inspect": InspectView,
        "threads": ThreadView,
        "top": TopView,
    }

    def __init__(self, pid: int, session_id: str, socket_path: str) -> None:
        super().__init__()
        self.pid = pid
        self.session_id = session_id
        self.socket_path = socket_path
        self._client = None
        self._activated_tabs: Set[str] = set()
        self._active_tab_id: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            with TabbedContent(
                initial="dashboard",
                id="main-content",
            ):
                with TabPane("[bold underline]1[/]·Dashboard", id="dashboard"):
                    yield DashboardView(self.pid)
                with TabPane("[bold underline]2[/]·Watch", id="watch"):
                    yield WatchView(self.pid)
                with TabPane("[bold underline]3[/]·Trace", id="trace"):
                    yield TraceView(self.pid)
                with TabPane("[bold underline]4[/]·Stack", id="stack"):
                    yield StackView(self.pid)
                with TabPane("[bold underline]5[/]·Monitor", id="monitor"):
                    yield MonitorView(self.pid)
                with TabPane("[bold underline]6[/]·Memory", id="memory"):
                    yield MemoryView(self.pid)
                with TabPane("[bold underline]7[/]·Logger", id="logger"):
                    yield LoggerView(self.pid)
                with TabPane("[bold underline]8[/]·Inspect", id="inspect"):
                    yield InspectView(self.pid)
                with TabPane("[bold underline]9[/]·Threads", id="threads"):
                    yield ThreadView(self.pid)
                with TabPane("[bold underline]0[/]·Top", id="top"):
                    yield TopView(self.pid)
        yield Footer()

    async def on_mount(self) -> None:
        await self._connect()

        if self._client:
            self.app.sub_title = f"Attached to PID {self.pid}"
            tabbed = self.query_one("#main-content", TabbedContent)
            self._select_tab(tabbed.active or "dashboard")

    def on_unmount(self) -> None:
        self._cleanup_all_views()

    def _record_client_activity(self, level: str, message: str) -> None:
        """Record a client-side activity entry when the app supports it."""
        recorder = getattr(self.app, "record_client_activity", None)
        if callable(recorder):
            recorder(level, message, source="main")

    async def _connect(self) -> None:
        """Connect to the target process agent with retry logic.

        Uses exponential backoff to handle the case where the agent socket
        is still initializing when MainScreen is pushed immediately after attach.
        """
        import asyncio

        from peeka.core.client import StreamingAgentClient

        max_retries = 5
        base_delay = 0.5  # seconds

        for attempt in range(max_retries):
            try:
                self._client = StreamingAgentClient(self.socket_path)
                result = self._client.connect()

                if result.get("status") == "success":
                    break

                error_msg = result.get("error", "Unknown connection error")
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                else:
                    self.notify(f"Failed to connect: {error_msg}", severity="error")
                    self._client = None
                    return
            except Exception as e:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    await asyncio.sleep(delay)
                    continue
                else:
                    self.notify(f"Failed to connect: {e}", severity="error")
                    self._client = None
                    return

        # Each streaming view now creates its own dedicated connection
        # in set_client(), so no shared stream client is needed.
        if self._client:
            self._record_client_activity(
                "INFO",
                f"connected to agent session {self.session_id} for pid {self.pid}",
            )

    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a specific view."""
        tabbed = self.query_one("#main-content", TabbedContent)
        tabbed.active = tab_id

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Initialize a tab's view the first time the main tab is shown."""
        if event.tabbed_content.id != "main-content":
            return
        if event.pane.id:
            self._select_tab(event.pane.id)

    def _select_tab(self, tab_id: str) -> None:
        """Activate a tab and notify views when they become visible or hidden."""
        if self._active_tab_id and self._active_tab_id != tab_id:
            self._set_tab_active(self._active_tab_id, False)

        self._activate_tab(tab_id)
        self._set_tab_active(tab_id, True)
        self._active_tab_id = tab_id

    def _activate_tab(self, tab_id: str) -> None:
        """Attach the shared client to a view only when its tab is used."""
        if not self._client or tab_id in self._activated_tabs:
            return

        view_cls = self._VIEW_BY_TAB.get(tab_id)
        if not view_cls:
            return

        view = self.query_one(view_cls)
        view.set_client(self._client)
        self._activated_tabs.add(tab_id)

    def _set_tab_active(self, tab_id: str, active: bool) -> None:
        """Notify a view about tab visibility when it supports that hook."""
        if tab_id not in self._activated_tabs:
            return

        view_cls = self._VIEW_BY_TAB.get(tab_id)
        if not view_cls:
            return

        view = self.query_one(view_cls)
        set_active = getattr(view, "set_active", None)
        if set_active:
            set_active(active)

    def action_go_back(self) -> None:
        self._cleanup_all_views()
        self.app.sub_title = "Python Runtime Diagnostics"
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
        if self._client:
            self._record_client_activity(
                "INFO",
                f"disconnected from agent session {self.session_id}",
            )
            self._client.disconnect()
