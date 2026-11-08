"""TUI tests that run inside the container via pytest.

These tests use textual's run_test() API to verify PeekaApp behavior.
They are executed by test_tui.py which orchestrates pytest inside the container.
"""

import pytest

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen

pytestmark = [pytest.mark.tui, pytest.mark.asyncio]

# Default (non-experimental) top-level tabs, in display order.
EXPECTED_TABS = [
    "dashboard",
    "watch",
    "trace",
    "stack",
    "monitor",
    "memory",
    "logger",
    "inspect",
    "threads",
    "top",
]


def _pane_labels(app, pane_id):
    """Return the input-label texts rendered inside one tab pane."""
    from textual.widgets import TabPane

    pane = app.screen.query_one(f"#{pane_id}", TabPane)
    return [label.render().plain for label in pane.query("Static.input-label")]


class TestTUIInContainer:
    """TUI integration tests running inside the container."""

    async def test_tui_app_starts(self):
        """Verify PeekaApp instantiates and runs."""
        app = PeekaApp()
        async with app.run_test():
            assert app.is_running

    async def test_tui_help_screen(self):
        """Verify help screen can be opened with '?' key."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            await pilot.press("?")
            assert app.is_running

    async def test_main_screen_has_default_tabs(self):
        """Verify MainScreen has exactly the default top-level tab panes."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()
            from textual.widgets import TabbedContent, TabPane

            tabbed = app.screen.query_one("#main-content", TabbedContent)
            panes = tabbed.query_one("ContentSwitcher").query_children(TabPane)
            assert len(panes) == len(EXPECTED_TABS)

    async def test_tab_ids_correct(self):
        """Verify top-level tab pane IDs match expected names and order."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()
            from textual.widgets import TabbedContent, TabPane

            tabbed = app.screen.query_one("#main-content", TabbedContent)
            panes = tabbed.query_one("ContentSwitcher").query_children(TabPane)
            assert [pane.id for pane in panes] == EXPECTED_TABS

    async def test_tab_switching(self):
        """Verify tab switching updates TabbedContent.active."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()
            from textual.widgets import TabbedContent

            tabbed = app.screen.query_one("#main-content", TabbedContent)

            for tab_name in EXPECTED_TABS[1:] + EXPECTED_TABS[:1]:
                app.screen.action_switch_tab(tab_name)
                await pilot.pause()
                assert tabbed.active == tab_name, (
                    f"Tab '{tab_name}': expected active='{tab_name}', got '{tabbed.active}'"
                )

    async def test_trace_view_labels(self):
        """Verify trace view has Pattern, Min Duration, and Condition labels."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()
            app.screen.action_switch_tab("trace")
            await pilot.pause()

            assert _pane_labels(app, "trace") == [
                "Pattern:",
                "Min Duration (ms):",
                "Condition:",
            ]

    async def test_trace_view_buttons(self):
        """Verify trace view has Trace, Stop, and Clear buttons."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()
            app.screen.action_switch_tab("trace")
            await pilot.pause()
            from textual.widgets import Button

            trace_btn = app.screen.query_one("#trace-btn", Button)
            stop_btn = app.screen.query_one("#stop-trace-btn", Button)
            clear_btn = app.screen.query_one("#clear-trace-btn", Button)
            assert trace_btn is not None
            assert stop_btn is not None
            assert clear_btn is not None

    async def test_trace_view_tree_widget(self):
        """Verify trace view has a Tree widget for call tree display."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()
            app.screen.action_switch_tab("trace")
            await pilot.pause()
            from textual.widgets import Tree

            tree = app.screen.query_one("#call-tree", Tree)
            assert tree is not None

    async def test_watch_view_inputs(self):
        """Verify watch view has pattern and condition inputs."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()
            app.screen.action_switch_tab("watch")
            await pilot.pause()

            assert _pane_labels(app, "watch") == ["Pattern:", "Condition:"]

    async def test_views_label_counts(self):
        """Verify each view with inputs has the correct number of labels."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()

            from textual.widgets import TabbedContent

            tabbed = app.screen.query_one("#main-content", TabbedContent)
            # digit key -> (tab id, input-label count in that tab)
            tab_label_counts = {
                "2": ("watch", 2),  # Pattern, Condition
                "3": ("trace", 3),  # Pattern, Min Duration, Condition
                "4": ("stack", 1),  # Pattern
                "5": ("monitor", 2),  # Pattern, Interval
                "7": ("logger", 2),  # Filter, Logger
                "8": ("inspect", 1),  # Object Path
            }

            for key, (tab_id, expected_count) in tab_label_counts.items():
                await pilot.press(key)
                await pilot.pause()
                assert tabbed.active == tab_id, f"key {key!r} did not open {tab_id}"
                assert len(_pane_labels(app, tab_id)) == expected_count
