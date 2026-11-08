"""
Main Screen - Primary interface after attaching to a process.
"""

from functools import partial
from typing import Any, Dict, List, NamedTuple, Optional, Set, Tuple, Type

from textual.app import ComposeResult
from textual.binding import Binding
from textual.command import DiscoveryHit, Hit, Hits, Provider
from textual.containers import Container
from textual.screen import Screen
from textual.widget import Widget
from textual.widgets import Header, Footer, Input, TabbedContent, TabPane, Tabs

from peeka.tui.activity import make_activity_reporter, make_client_info
from peeka.tui.views.dashboard import DashboardView
from peeka.tui.views.inspect import InspectView
from peeka.tui.views.logger import LoggerView
from peeka.tui.views.memory import MemoryView
from peeka.tui.views.monitor import MonitorView
from peeka.tui.views.profile import ProfileView
from peeka.tui.views.stack import StackView
from peeka.tui.views.thread import ThreadView
from peeka.tui.views.timeline import TimelineView
from peeka.tui.views.top import TopView
from peeka.tui.views.trace import TraceView
from peeka.tui.views.watch import WatchView
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput


class TabSpec(NamedTuple):
    """Static description of one main-screen tab."""

    tab_id: str
    key: str
    title: str
    experimental: bool = False


# Order defines tab order. Digit keys are reserved for the most used views;
# everything is also reachable from the command palette (Ctrl+P), so new or
# rarely used views do not need a global key.
TAB_SPECS: List[TabSpec] = [
    TabSpec("dashboard", "1", "Dashboard"),
    TabSpec("watch", "2", "Watch"),
    TabSpec("trace", "3", "Trace"),
    TabSpec("stack", "4", "Stack"),
    TabSpec("monitor", "5", "Monitor"),
    TabSpec("memory", "6", "Memory"),
    TabSpec("logger", "7", "Logger"),
    TabSpec("inspect", "8", "Inspect"),
    TabSpec("threads", "9", "Threads"),
    TabSpec("top", "0", "Performance"),
    TabSpec("timeline", "", "Timeline (Experimental)", experimental=True),
]

# Tabs that group several views behind a nested sub-tab bar. The first entry
# is the default sub-tab. Live Top and Profile sessions share the same
# sampling data (top records into a transient ProfileSession), so they live
# together under one top-level tab.
SUB_TABS: Dict[str, List[Tuple[str, str]]] = {
    "top": [("top-live", "Live Top"), ("top-profile", "Profiles")],
}


class JumpTarget(NamedTuple):
    """A view the command palette can jump to."""

    tab_id: str
    title: str
    key: str


class ViewJumpProvider(Provider):
    """Command palette entries that jump to a main-screen tab."""

    def _commands(self) -> List[JumpTarget]:
        screen = self.screen
        if not isinstance(screen, MainScreen):
            return []
        return screen.jump_targets()

    def _jump(self, tab_id: str) -> None:
        screen = self.screen
        if isinstance(screen, MainScreen):
            screen.action_switch_tab(tab_id)

    @staticmethod
    def _help(spec: JumpTarget) -> str:
        return f"Shortcut: {spec.key.upper()}" if spec.key else "No shortcut"

    async def discover(self) -> Hits:
        for spec in self._commands():
            yield DiscoveryHit(
                f"Go to {spec.title}",
                partial(self._jump, spec.tab_id),
                help=self._help(spec),
            )

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for spec in self._commands():
            text = f"Go to {spec.title}"
            score = matcher.match(text)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(text),
                    partial(self._jump, spec.tab_id),
                    text=text,
                    help=self._help(spec),
                )


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
        Binding("0", "switch_tab('top')", "Performance"),
        Binding("q", "go_back", "Back"),
    ]

    COMMANDS = {ViewJumpProvider}

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
        "top-live": TopView,
        "top-profile": ProfileView,
        "timeline": TimelineView,
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
                for spec in self.visible_tab_specs():
                    label = (
                        f"[bold underline]{spec.key.upper()}[/]·{spec.title}"
                        if spec.key
                        else spec.title
                    )
                    with TabPane(label, id=spec.tab_id):
                        sub_tabs = SUB_TABS.get(spec.tab_id)
                        if not sub_tabs:
                            yield self._VIEW_BY_TAB[spec.tab_id](self.pid)
                            continue
                        with TabbedContent(
                            initial=sub_tabs[0][0],
                            id=f"{spec.tab_id}-content",
                            classes="sub-tabs",
                        ):
                            for sub_id, sub_title in sub_tabs:
                                with TabPane(sub_title, id=sub_id):
                                    yield self._VIEW_BY_TAB[sub_id](self.pid)
        yield Footer()

    def visible_tab_specs(self) -> List[TabSpec]:
        """Return the tabs shown on this screen, honouring the experimental flag."""
        experimental = bool(getattr(self.app, "experimental", False))
        return [spec for spec in TAB_SPECS if experimental or not spec.experimental]

    def jump_targets(self) -> List[JumpTarget]:
        """Return every view reachable from the command palette, in tab order."""
        targets: List[JumpTarget] = []
        for spec in self.visible_tab_specs():
            sub_tabs = SUB_TABS.get(spec.tab_id)
            if not sub_tabs:
                targets.append(JumpTarget(spec.tab_id, spec.title, spec.key))
                continue
            for index, (sub_id, sub_title) in enumerate(sub_tabs):
                targets.append(
                    JumpTarget(
                        sub_id,
                        f"{spec.title} › {sub_title}",
                        spec.key if index == 0 else "",
                    )
                )
        return targets

    @staticmethod
    def _parent_tab(tab_id: str) -> Optional[str]:
        """Return the top-level tab that hosts sub-tab ``tab_id``, if any."""
        for parent, sub_tabs in SUB_TABS.items():
            if any(sub_id == tab_id for sub_id, _ in sub_tabs):
                return parent
        return None

    def _leaf_tab(self, tab_id: str) -> str:
        """Resolve a top-level tab to the view tab currently shown inside it."""
        sub_tabs = SUB_TABS.get(tab_id)
        if not sub_tabs:
            return tab_id
        nested = self.query_one(f"#{tab_id}-content", TabbedContent)
        return nested.active or sub_tabs[0][0]

    async def on_mount(self) -> None:
        # Tabs are switched with digit/letter keys; keep the tab strip out of
        # the focus chain so the first Tab after switching lands in the view's
        # first input instead of on the strip.
        tabbed = self.query_one("#main-content", TabbedContent)
        for child in tabbed.children:
            if isinstance(child, Tabs):
                child.can_focus = False

        # Each view takes focus itself when shown and when Esc leaves an
        # input, so its own bindings (Enter, Delete, r, c, ...) keep working
        # and show in the footer. Keys a view does not bind (digits, q, Esc)
        # still bubble up to this screen.
        for view in self._views():
            view.can_focus = True
        self.call_after_refresh(self._focus_active_view)

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
                self._client = StreamingAgentClient(
                    self.socket_path,
                    activity_reporter=make_activity_reporter(self.app, "main"),
                    client_info=make_client_info(self.app, "main"),
                )
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
        # Clear focus from the old pane first. Otherwise Textual may reactivate
        # that pane when the hidden focused widget receives focus bookkeeping.
        visible = {spec.tab_id for spec in self.visible_tab_specs()}
        parent = self._parent_tab(tab_id)
        if (parent or tab_id) not in visible:
            return
        self.set_focus(None)
        tabbed = self.query_one("#main-content", TabbedContent)
        if parent:
            # Select the sub-tab first so activating the parent resolves to it.
            self.query_one(f"#{parent}-content", TabbedContent).active = tab_id
            tabbed.active = parent
        else:
            tabbed.active = tab_id
        self.call_after_refresh(self._focus_active_view)

    def on_tabbed_content_tab_activated(
        self, event: TabbedContent.TabActivated
    ) -> None:
        """Initialize a tab's view the first time it is shown."""
        pane_id = event.pane.id
        if not pane_id:
            return
        if event.tabbed_content.id == "main-content":
            self._select_tab(self._leaf_tab(pane_id))
            self.call_after_refresh(self._focus_active_view)
            return
        parent = self._parent_tab(pane_id)
        if parent is None:
            return
        # A nested sub-tab only counts as shown while its parent tab is active.
        main = self.query_one("#main-content", TabbedContent)
        if main.active == parent:
            self._select_tab(pane_id)
            self.call_after_refresh(self._focus_active_view)

    def _views(self) -> List[Widget]:
        """Return the view of every composed tab (experimental ones may be absent)."""
        views: List[Widget] = []
        for view_cls in self._VIEW_BY_TAB.values():
            views.extend(self.query(view_cls))
        return views

    def _active_view(self) -> Optional[Widget]:
        """Return the view actually shown, resolving nested sub-tabs."""
        tabbed = self.query_one("#main-content", TabbedContent)
        view_cls = self._VIEW_BY_TAB.get(self._leaf_tab(tabbed.active or ""))
        if view_cls is None:
            return None
        found = self.query(view_cls)
        return found.first() if found else None

    def _focus_active_view(self) -> None:
        """Focus the active view when focus is empty or left in a hidden view.

        Focus already inside the active view, or on a visible control outside
        every view (such as a sub-tab strip), is left alone.
        """
        view = self._active_view()
        if view is None:
            return
        focused = self.focused
        if focused is not None:
            if focused is view or view in focused.ancestors:
                return
            views = self._views()
            if not any(other is focused or other in focused.ancestors for other in views):
                return
        view.focus(scroll_visible=False)

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
        """Esc/q: step out of text entry before leaving the screen.

        Going back detaches from the target and stops every watch/trace, so a
        stray Esc while typing must not trigger it. Order of precedence:
        close an open completion dropdown, then move focus from a focused
        input back to its view, and only when nothing is focused for typing,
        go back.
        """
        if self._leave_text_entry():
            return

        self._cleanup_all_views()
        self.app.sub_title = "Python Runtime Diagnostics"
        self.app.pop_screen()

    def _leave_text_entry(self) -> bool:
        """Dismiss a completion dropdown or blur a focused input.

        Returns:
            True if Esc was consumed by leaving text entry.
        """
        focused = self.focused
        if focused is None:
            return False

        autocomplete = None
        for node in (focused, *focused.ancestors):
            if isinstance(node, AutoCompleteInput):
                autocomplete = node
                break

        if autocomplete is not None and autocomplete.dismiss_dropdown():
            return True
        if autocomplete is not None or isinstance(focused, Input):
            view = self._active_view()
            if view is not None and view in focused.ancestors:
                view.focus(scroll_visible=False)
            else:
                self.set_focus(None)
            return True
        return False

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
