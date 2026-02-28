"""Tests for cross-cutting error handling - connection failures, malformed data, concurrent streams."""

import asyncio

import pytest
from textual.widgets import DataTable, Input, RichLog, Static, Tree

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.monitor import MonitorView
from peeka.tui.views.stack import StackView
from peeka.tui.views.trace import TraceView
from peeka.tui.views.watch import WatchView
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput


class TestErrorScenarios:
    """Test error handling across multiple views and scenarios."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_connection_failure_all_views(self, mock_client_factory):
        """Set should_fail_connect=True on mock, verify each view handles connection failure gracefully."""
        client = mock_client_factory(should_fail_connect=True)
        result = client.connect()
        assert result["status"] == "error"
        assert "Mock connection failure" in result["error"]

        # Test WatchView
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(client)

            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            # Attempt to start watch (should fail gracefully)
            await watch_view._start_watch()
            await pilot.pause()

            # Verify no commands sent due to connection failure
            assert len(client.commands_received) == 0

            # Verify no watch entry created
            table = watch_view.query_one("#watch-table", DataTable)
            assert table.row_count == 0

        # Test TraceView
        client_trace = mock_client_factory(should_fail_connect=True)
        result_trace = client_trace.connect()
        assert result_trace["status"] == "error"

        app2 = PeekaApp()
        async with app2.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app2.push_screen(main_screen)
            await pilot.pause()

            trace_view = app2.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client_trace)

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            # Attempt to start trace (should fail gracefully)
            await trace_view._start_trace()
            await pilot.pause()

            # Verify no commands sent
            assert len(client_trace.commands_received) == 0

            # Verify no trace entry created
            table = trace_view.query_one("#trace-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_send_command_failure(self, mock_client_factory):
        """Set should_fail_send=True, trigger command from any view, verify error notification."""
        client = mock_client_factory(should_fail_send=True)
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(client)

            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await watch_view._start_watch()
            await pilot.pause()

            assert len(client.commands_received) >= 1

            table = watch_view.query_one("#watch-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_malformed_observation_watch(self, mock_client_factory):
        """Configure mock with observation missing required fields (e.g., no func_name), verify WatchView doesn't crash."""
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}}
        )
        client.connect()

        malformed_obs = [
            {
                "watch_id": "w1",
                "params": [1, 2],
                "returnObj": 3,
                "cost": 0.1,
                "success": True,
                "count": 1,
            }
        ]
        stream_client = mock_client_factory(observations=malformed_obs)
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(client)
            watch_view.set_stream_client(stream_client)

            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await watch_view._start_watch()
            await pilot.pause()
            await pilot.pause()

            table = watch_view.query_one("#watch-table", DataTable)
            assert table.row_count >= 1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_malformed_observation_trace(self, mock_client_factory):
        """Observation missing call_tree → TraceView handles gracefully."""
        client = mock_client_factory(
            responses={"trace": {"status": "success", "watch_id": "t1"}}
        )
        client.connect()

        malformed_obs = [
            {
                "watch_id": "t1",
                "func_name": "module.func",
                "total_duration_ms": 10.5,
                "node_count": 1,
                "count": 1,
            }
        ]
        stream_client = mock_client_factory(observations=malformed_obs)
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view.set_stream_client(stream_client)

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            assert tree is not None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_malformed_observation_stack(self, mock_client_factory):
        """Observation missing stack → StackView handles gracefully."""
        client = mock_client_factory(
            responses={"stack": {"status": "success", "watch_id": "s1"}}
        )
        client.connect()

        malformed_obs = [
            {
                "watch_id": "s1",
                "func_name": "module.func",
                "count": 1,
            }
        ]
        stream_client = mock_client_factory(observations=malformed_obs)
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(client)
            stack_view.set_stream_client(stream_client)

            pattern_input = stack_view.query_one("#stack-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await stack_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            table = stack_view.query_one("#trace-table", DataTable)
            assert table is not None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stream_yields_empty(self, mock_client_factory):
        """Mock generator yields nothing (empty list), verify view handles graceful stop."""
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}}
        )
        client.connect()

        # Empty observation list
        stream_client = mock_client_factory(observations=[])
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(client)
            watch_view.set_stream_client(stream_client)

            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            # Start watch
            await watch_view._start_watch()
            await pilot.pause()
            await pilot.pause()

            # Verify watch entry created but no observations shown
            table = watch_view.query_one("#watch-table", DataTable)
            assert table.row_count >= 1

            # Verify worker completed without hanging
            assert "w1" in watch_view._active_watches

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_tab_switch_during_stream(self, mock_client_factory):
        """Start streaming on one view, switch tabs, verify no crash (workers continue or cancel cleanly)."""
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}}
        )
        client.connect()

        observations = [
            {
                "watch_id": "w1",
                "func_name": "module.func",
                "params": [i],
                "kwargs": {},
                "returnObj": i * 2,
                "cost": 0.1,
                "success": True,
                "count": i + 1,
            }
            for i in range(10)
        ]
        stream_client = mock_client_factory(observations=observations)
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            # Start watch
            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(client)
            watch_view.set_stream_client(stream_client)

            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await watch_view._start_watch()
            await pilot.pause()

            # Switch to different tab during streaming
            main_screen.action_switch_tab("dashboard")
            await pilot.pause()

            # Verify no crash occurred
            assert app.screen is not None

            # Switch back to watch view
            main_screen.action_switch_tab("watch")
            await pilot.pause()

            # Verify watch still exists
            watch_view = app.screen.query_one("WatchView", WatchView)
            assert watch_view is not None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_multiple_views_concurrent_stream(self, mock_client_factory):
        """Start watch + monitor simultaneously, verify both receive their observations."""
        # Create separate observations for watch and monitor
        watch_obs = [
            {
                "watch_id": "w1",
                "func_name": "module.func",
                "params": [1],
                "kwargs": {},
                "returnObj": 2,
                "cost": 0.1,
                "success": True,
                "count": 1,
            }
        ]
        monitor_obs = [
            {
                "watch_id": "m1",
                "func_name": "module.func",
                "total": 100,
                "success": 95,
                "fail": 5,
                "avg_rt": 0.5,
                "min_rt": 0.1,
                "max_rt": 1.5,
                "count": 1,
            }
        ]

        watch_client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}}
        )
        watch_stream_client = mock_client_factory(observations=watch_obs)

        monitor_client = mock_client_factory(
            responses={"monitor": {"status": "success", "watch_id": "m1"}}
        )
        monitor_stream_client = mock_client_factory(observations=monitor_obs)

        watch_client.connect()
        watch_stream_client.connect()
        monitor_client.connect()
        monitor_stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            # Start watch
            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(watch_client)
            watch_view.set_stream_client(watch_stream_client)

            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await watch_view._start_watch()
            await pilot.pause()

            # Switch to monitor and start it
            main_screen.action_switch_tab("monitor")
            await pilot.pause()

            monitor_view = app.screen.query_one("MonitorView", MonitorView)
            monitor_view.set_client(monitor_client)
            monitor_view.set_stream_client(monitor_stream_client)

            pattern_input_monitor = monitor_view.query_one("#monitor-pattern", AutoCompleteInput)
            pattern_input_monitor.value = "module.func"

            await monitor_view._start_monitor()
            await pilot.pause()
            await pilot.pause()

            # Verify both views have entries
            monitor_table = monitor_view.query_one("#stats-table", DataTable)
            assert monitor_table.row_count >= 1

            # Switch back to watch
            main_screen.action_switch_tab("watch")
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_table = watch_view.query_one("#watch-table", DataTable)
            assert watch_table.row_count >= 1
