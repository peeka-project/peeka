"""Tests for MemoryView - data-flow and error handling."""

import pytest
from textual.widgets import Static, DataTable, Button

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.memory import MemoryView


class ActionRoutingClient:
    """Mock client that routes memory commands by action field."""

    def __init__(self, action_responses):
        self.action_responses = action_responses
        self.connected = False
        self.commands_received = []
        self.socket_path = "/tmp/peeka_mock.sock"

    def connect(self):
        self.connected = True
        return {"status": "success"}

    def disconnect(self):
        self.connected = False

    def send_command(self, command):
        if not self.connected:
            return {"status": "error", "error": "Not connected"}
        self.commands_received.append(command)
        if command.get("type") == "memory":
            action = command.get("action")
            if action in self.action_responses:
                return self.action_responses[action]
            return {"status": "error", "error": f"Unknown action: {action}"}
        return {"status": "error", "error": f"Unknown type: {command.get('type')}"}


class TestMemoryView:
    """Test MemoryView widget population from mock client responses."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_refresh_overview_displays_rss(self):
        """Refresh overview populates RSS widget with formatted memory data."""
        memory_client = ActionRoutingClient(
            action_responses={
                "overview": {
                    "status": "success",
                    "rss_bytes": 104857600,
                    "tracemalloc": {"enabled": False},
                    "gc": {"counts": [500, 20, 2]},
                },
                "gc": {
                    "status": "success",
                    "objects_by_type": [],
                    "total_objects": 0,
                },
            }
        )
        memory_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            memory_view = app.screen.query_one("MemoryView", MemoryView)
            memory_view.set_client(memory_client)

            await memory_view._refresh_overview()
            await pilot.pause()

            rss_widget = memory_view.query_one("#mem-rss", Static)
            assert "100.00 MB" in rss_widget.render().plain

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_toggle_tracking_start(self):
        """Starting memory tracking sends start command and updates UI."""

        class StatefulTrackingClient:
            def __init__(self):
                self.connected = False
                self.commands_received = []
                self.tracking_started = False
                self.socket_path = "/tmp/peeka_mock.sock"

            def connect(self):
                self.connected = True
                return {"status": "success"}

            def disconnect(self):
                self.connected = False

            def send_command(self, command):
                if not self.connected:
                    return {"status": "error", "error": "Not connected"}
                self.commands_received.append(command)

                action = command.get("action")
                if action == "overview":
                    return {
                        "status": "success",
                        "rss_bytes": 52428800,
                        "tracemalloc": {
                            "enabled": self.tracking_started,
                            "current_bytes": 10485760 if self.tracking_started else 0,
                            "peak_bytes": 20971520 if self.tracking_started else 0,
                        },
                        "gc": {"counts": [700, 10, 1]},
                    }
                elif action == "start":
                    self.tracking_started = True
                    return {"status": "success", "message": "Tracking started"}
                elif action == "gc":
                    return {
                        "status": "success",
                        "objects_by_type": [],
                        "total_objects": 0,
                    }
                return {"status": "error", "error": f"Unknown action: {action}"}

        tracking_client = StatefulTrackingClient()
        tracking_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            memory_view = app.screen.query_one("MemoryView", MemoryView)
            memory_view.set_client(tracking_client)

            assert memory_view._tracking_enabled is False

            await memory_view._toggle_tracking()
            await pilot.pause()
            await pilot.pause()

            commands = [cmd.get("action") for cmd in tracking_client.commands_received]
            assert "start" in commands

            # After tracking starts: Track button hidden, Stop button visible
            track_btn = memory_view.query_one("#mem-track-btn", Button)
            stop_btn = memory_view.query_one("#mem-stop-btn", Button)
            assert track_btn.styles.display == "none"
            assert stop_btn.styles.display == "block"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_toggle_tracking_stop(self):
        """Stopping memory tracking sends stop command and updates UI."""
        tracking_client = ActionRoutingClient(
            action_responses={
                "overview": {
                    "status": "success",
                    "rss_bytes": 52428800,
                    "tracemalloc": {
                        "enabled": False,
                        "current_bytes": 10485760,
                        "peak_bytes": 20971520,
                    },
                    "gc": {"counts": [700, 10, 1]},
                },
                "stop": {"status": "success", "message": "Tracking stopped"},
                "gc": {
                    "status": "success",
                    "objects_by_type": [],
                    "total_objects": 0,
                },
            }
        )
        tracking_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            memory_view = app.screen.query_one("MemoryView", MemoryView)
            memory_view.set_client(tracking_client)

            memory_view._tracking_enabled = True

            await memory_view._toggle_tracking()
            await pilot.pause()
            await pilot.pause()

            commands = [cmd.get("action") for cmd in tracking_client.commands_received]
            assert "stop" in commands

            # After tracking stops: Track button visible, Stop button hidden
            track_btn = memory_view.query_one("#mem-track-btn", Button)
            stop_btn = memory_view.query_one("#mem-stop-btn", Button)
            assert track_btn.styles.display == "block"
            assert stop_btn.styles.display == "none"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_gc_objects_refresh(self):
        """GC objects refresh sends gc command and populates table."""
        gc_client = ActionRoutingClient(
            action_responses={
                "overview": {
                    "status": "success",
                    "rss_bytes": 52428800,
                    "tracemalloc": {"enabled": False},
                    "gc": {"counts": [300, 5, 0]},
                },
                "gc": {
                    "status": "success",
                    "total_objects": 12345,
                    "objects_by_type": [
                        {"type": "dict", "count": 5000},
                        {"type": "list", "count": 3000},
                        {"type": "str", "count": 2000},
                    ],
                },
            }
        )
        gc_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            memory_view = app.screen.query_one("MemoryView", MemoryView)
            memory_view.set_client(gc_client)

            await memory_view._refresh_gc_objects()
            await pilot.pause()
            await pilot.pause()

            commands = [cmd.get("action") for cmd in gc_client.commands_received]
            assert "gc" in commands

            table = memory_view.query_one("#mem-objects-table", DataTable)
            assert table.row_count > 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_gc_objects_table_populated(self):
        """GC objects table is populated with type data from gc command."""
        top_client = ActionRoutingClient(
            action_responses={
                "overview": {
                    "status": "success",
                    "rss_bytes": 52428800,
                    "tracemalloc": {"enabled": False},
                    "gc": {"counts": [700, 10, 1]},
                },
                "gc": {
                    "status": "success",
                    "objects_by_type": [
                        {"type": "dict", "count": 5000},
                        {"type": "list", "count": 3000},
                        {"type": "tuple", "count": 2500},
                    ],
                    "total_objects": 10500,
                },
            }
        )
        top_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            memory_view = app.screen.query_one("MemoryView", MemoryView)
            memory_view.set_client(top_client)

            await memory_view._refresh_gc_objects()
            await pilot.pause()
            await pilot.pause()

            table = memory_view.query_one("#mem-objects-table", DataTable)
            assert table.row_count > 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_error_response_handling(self, mock_client_factory):
        """MemoryView handles error responses gracefully without crashing."""
        error_client = mock_client_factory(
            responses={
                "memory": {"status": "error", "error": "Memory command failed"},
            }
        )
        error_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            memory_view = app.screen.query_one("MemoryView", MemoryView)
            memory_view.set_client(error_client)

            await memory_view._refresh_overview()
            await pilot.pause()

            rss_widget = memory_view.query_one("#mem-rss", Static)
            content = rss_widget.render().plain
            assert "calculating" in content or "RSS" in content

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_no_client_connected(self):
        """MemoryView with no client shows initial placeholder text."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            memory_view = app.screen.query_one("MemoryView", MemoryView)

            rss_widget = memory_view.query_one("#mem-rss", Static)
            total_widget = memory_view.query_one("#mem-total", Static)

            assert "calculating" in rss_widget.render().plain
            # When not tracking, mem-total shows "Not tracking" instead of "calculating"
            assert "Not tracking" in total_widget.render().plain

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_action_refresh_triggers_refresh(self):
        """Calling action_refresh() triggers overview and gc_objects refresh."""
        refresh_client = ActionRoutingClient(
            action_responses={
                "overview": {
                    "status": "success",
                    "rss_bytes": 52428800,
                    "tracemalloc": {"enabled": False},
                    "gc": {"counts": [700, 10, 1]},
                },
                "gc": {
                    "status": "success",
                    "objects_by_type": [],
                    "total_objects": 0,
                },
            }
        )
        refresh_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            memory_view = app.screen.query_one("MemoryView", MemoryView)
            memory_view.set_client(refresh_client)

            initial_count = len(refresh_client.commands_received)

            await memory_view.action_refresh()
            await pilot.pause()
            await pilot.pause()

            assert len(refresh_client.commands_received) > initial_count
            commands = [cmd.get("action") for cmd in refresh_client.commands_received]
            assert "overview" in commands
            assert "gc" in commands
