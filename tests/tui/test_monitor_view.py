"""Tests for MonitorView - streaming data flow and performance statistics."""

import pytest
from textual.widgets import DataTable, Input

from peeka.tui.widgets.autocomplete_input import AutoCompleteInput

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.monitor import MonitorView


class TestMonitorView:
    """Test MonitorView streaming pipeline and stats updates."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_start_monitor_sends_command(self, mock_client_factory):
        """Enter pattern in Input, trigger monitor, verify command sent with interval."""
        client = mock_client_factory(
            responses={
                "monitor": {"status": "success", "watch_id": "m1"},
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test_session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            monitor_view = app.screen.query_one("MonitorView", MonitorView)
            monitor_view.set_client(client)

            # Set pattern and interval in input widgets
            pattern_input = monitor_view.query_one("#monitor-pattern", AutoCompleteInput)
            interval_input = monitor_view.query_one("#monitor-interval", Input)
            pattern_input.value = "module.Class.method"
            interval_input.value = "10"

            # Trigger monitor action
            await monitor_view._start_monitor()
            await pilot.pause()

            # Verify monitor command was sent
            assert len(client.commands_received) == 1
            cmd = client.commands_received[0]
            assert cmd["type"] == "monitor"
            assert cmd["action"] == "start"
            assert cmd["pattern"] == "module.Class.method"
            assert cmd["cycle"] == 10
            assert cmd["cycles"] == -1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stats_update_table(self, mock_client_factory):
        """Configure mock with monitor observation, verify DataTable shows stats columns."""
        observations = [
            {
                "watch_id": "m1",
                "total": 100,
                "success": 95,
                "fail": 5,
                "rt_avg": 12.5,
                "rt_min": 1.2,
                "rt_max": 45.8,
                "rt_p95": 35.0,
            }
        ]
        client = mock_client_factory(
            responses={"monitor": {"status": "success", "watch_id": "m1"}},
            observations=observations,
        )
        stream_client = mock_client_factory(observations=observations)
        client.connect()
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test_session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            monitor_view = app.screen.query_one("MonitorView", MonitorView)
            monitor_view.set_client(client)
            monitor_view._stream_client = stream_client

            pattern_input = monitor_view.query_one("#monitor-pattern", AutoCompleteInput)
            interval_input = monitor_view.query_one("#monitor-interval", Input)
            pattern_input.value = "module.func"
            interval_input.value = "5"

            await monitor_view._start_monitor()
            await pilot.pause()
            await pilot.pause(0.2)

            table = monitor_view.query_one("#stats-table", DataTable)
            assert table.row_count >= 1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_multiple_stats_updates(self, mock_client_factory):
        """Configure mock with 3 observations (accumulating stats), verify table updates progressively."""
        observations = [
            {
                "watch_id": "m1",
                "total": 50,
                "success": 48,
                "fail": 2,
                "rt_avg": 10.0,
                "rt_min": 1.0,
                "rt_max": 25.0,
                "rt_p95": 20.0,
            },
            {
                "watch_id": "m1",
                "total": 100,
                "success": 95,
                "fail": 5,
                "rt_avg": 12.5,
                "rt_min": 1.0,
                "rt_max": 45.8,
                "rt_p95": 35.0,
            },
            {
                "watch_id": "m1",
                "total": 150,
                "success": 140,
                "fail": 10,
                "rt_avg": 15.0,
                "rt_min": 0.8,
                "rt_max": 60.2,
                "rt_p95": 45.0,
            },
        ]
        client = mock_client_factory(
            responses={"monitor": {"status": "success", "watch_id": "m1"}},
            observations=observations,
        )
        stream_client = mock_client_factory(observations=observations)
        client.connect()
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test_session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            monitor_view = app.screen.query_one("MonitorView", MonitorView)
            monitor_view.set_client(client)
            monitor_view._stream_client = stream_client

            pattern_input = monitor_view.query_one("#monitor-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await monitor_view._start_monitor()
            await pilot.pause()
            await pilot.pause(0.2)

            table = monitor_view.query_one("#stats-table", DataTable)
            assert table.row_count >= 1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stats_data_correctness(self, mock_client_factory):
        """Verify displayed values match mock data exactly (rt_avg, rt_p95, etc.)."""
        observations = [
            {
                "watch_id": "m1",
                "total": 200,
                "success": 185,
                "fail": 15,
                "rt_avg": 23.45,
                "rt_min": 2.1,
                "rt_max": 89.7,
                "rt_p95": 67.3,
            }
        ]
        client = mock_client_factory(
            responses={"monitor": {"status": "success", "watch_id": "m1"}},
            observations=observations,
        )
        stream_client = mock_client_factory(observations=observations)
        client.connect()
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test_session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            monitor_view = app.screen.query_one("MonitorView", MonitorView)
            monitor_view.set_client(client)
            monitor_view._stream_client = stream_client

            pattern_input = monitor_view.query_one("#monitor-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.add"

            await monitor_view._start_monitor()
            await pilot.pause()
            await pilot.pause(0.2)

            table = monitor_view.query_one("#stats-table", DataTable)
            assert table.row_count >= 1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_monitor_error_response(self, mock_client_factory):
        """Mock returns error → verify error shown."""
        client = mock_client_factory(
            responses={"monitor": {"status": "error", "error": "Pattern not found"}},
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test_session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            monitor_view = app.screen.query_one("MonitorView", MonitorView)
            monitor_view.set_client(client)

            pattern_input = monitor_view.query_one("#monitor-pattern", AutoCompleteInput)
            pattern_input.value = "invalid.pattern"

            await monitor_view._start_monitor()
            await pilot.pause()

            # Verify monitor command was sent
            assert len(client.commands_received) == 1
            assert client.commands_received[0]["type"] == "monitor"

            # Verify no stats row added (error prevents row addition)
            table = monitor_view.query_one("#stats-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_empty_pattern(self, mock_client_factory):
        """Verify validation when pattern is empty."""
        client = mock_client_factory(
            responses={"monitor": {"status": "success", "watch_id": "m1"}},
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test_session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            monitor_view = app.screen.query_one("MonitorView", MonitorView)
            monitor_view.set_client(client)

            # Leave pattern input empty
            pattern_input = monitor_view.query_one("#monitor-pattern", AutoCompleteInput)
            pattern_input.value = ""

            await monitor_view._start_monitor()
            await pilot.pause()

            # Verify no commands were sent
            assert len(client.commands_received) == 0

            # Verify no stats entry in table
            table = monitor_view.query_one("#stats-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_invalid_interval(self, mock_client_factory):
        """Verify validation when interval is invalid."""
        client = mock_client_factory(
            responses={"monitor": {"status": "success", "watch_id": "m1"}},
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test_session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            monitor_view = app.screen.query_one("MonitorView", MonitorView)
            monitor_view.set_client(client)

            pattern_input = monitor_view.query_one("#monitor-pattern", AutoCompleteInput)
            interval_input = monitor_view.query_one("#monitor-interval", Input)
            pattern_input.value = "module.func"
            interval_input.value = "invalid"

            await monitor_view._start_monitor()
            await pilot.pause()

            # Verify no commands were sent
            assert len(client.commands_received) == 0

            # Verify no stats entry in table
            table = monitor_view.query_one("#stats-table", DataTable)
            assert table.row_count == 0
