"""TUI tests that run inside the container via pytest.

These tests use textual's run_test() API to verify PeekaApp behavior.
They are executed by test_tui.py which orchestrates pytest inside the container.
"""

import pytest

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen

pytestmark = [pytest.mark.tui, pytest.mark.asyncio]


class TestTUIInContainer:
    """TUI integration tests running inside the container."""

    async def test_tui_app_starts(self):
        """Verify PeekaApp instantiates and runs."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            assert app.is_running

    async def test_tui_help_screen(self):
        """Verify help screen can be opened with '?' key."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            await pilot.press("?")
            assert app.is_running

    async def test_main_screen_has_eight_tabs(self):
        """Verify MainScreen has exactly 8 tab panes."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()
            from textual.widgets import ContentSwitcher

            switcher = app.screen.query_one("#main-content", ContentSwitcher)
            children = list(switcher.children)
            assert len(children) == 8

    async def test_tab_ids_correct(self):
        """Verify all 8 tab view IDs match expected names."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()
            from textual.widgets import ContentSwitcher

            switcher = app.screen.query_one("#main-content", ContentSwitcher)
            children = list(switcher.children)
            child_ids = [child.id for child in children]
            expected = [
                "dashboard-view",
                "watch-view",
                "trace-view",
                "stack-view",
                "monitor-view",
                "memory-view",
                "logger-view",
                "inspect-view",
            ]
            assert child_ids == expected

    async def test_tab_switching(self):
        """Verify tab switching updates ContentSwitcher.current."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()
            from textual.widgets import ContentSwitcher

            switcher = app.screen.query_one("#main-content", ContentSwitcher)

            # Test switching to each tab
            tab_keys = {
                "watch": "watch-view",
                "trace": "trace-view",
                "stack": "stack-view",
                "monitor": "monitor-view",
                "memory": "memory-view",
                "logger": "logger-view",
                "inspect": "inspect-view",
                "dashboard": "dashboard-view",
            }
            for tab_name, expected_id in tab_keys.items():
                app.screen.action_switch_tab(tab_name)
                await pilot.pause()
                assert switcher.current == expected_id, (
                    f"Tab '{tab_name}': expected '{expected_id}', got '{switcher.current}'"
                )

    async def test_trace_view_labels(self):
        """Verify trace view has Pattern, Depth, and Condition labels."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()
            app.screen.action_switch_tab("trace")
            await pilot.pause()
            from textual.widgets import Static

            labels = app.screen.query("Static.input-label")
            label_texts = [label.render().plain for label in labels]
            assert "Pattern:" in label_texts
            assert "Depth:" in label_texts
            assert "Condition:" in label_texts

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
            from textual.widgets import Static

            labels = app.screen.query("Static.input-label")
            label_texts = [label.render().plain for label in labels]
            assert "Pattern:" in label_texts
            assert "Condition:" in label_texts

    async def test_views_label_counts(self):
        """Verify each view with inputs has the correct number of labels."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
            )
            await pilot.pause()

            tab_label_counts = {
                "w": 2,  # Watch: Pattern, Condition
                "t": 3,  # Trace: Pattern, Depth, Condition
                "s": 1,  # Stack: Pattern
                "m": 2,  # Monitor: Pattern, Interval
                "l": 2,  # Logger: Filter, Logger
                "i": 1,  # Inspect: Object Path
            }

            for key, expected_count in tab_label_counts.items():
                await pilot.press(key)
                await pilot.pause()
                labels = app.screen.query("Static.input-label")
                assert len(labels) >= expected_count, (
                    f"Tab '{key}': expected >= {expected_count} labels, "
                    f"got {len(labels)}"
                )
