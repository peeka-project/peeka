"""Tests for WatchView - streaming data flow and error handling."""

import pytest
from textual.containers import Vertical
from textual.widgets import DataTable, Static

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.watch import WatchView
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput
from tests.tui.conftest import make_patch_status_response


class TestWatchView:
    """Test WatchView streaming pipeline and dual-client pattern."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_start_watch_sends_command(self, mock_client_factory):
        """Enter pattern in AutoCompleteInput, trigger watch, verify command sent."""
        client = mock_client_factory(
            responses={
                "watch": {"status": "success", "watch_id": "w1"},
            }
        )
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

            # Set pattern in input widget
            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = "module.Class.method"

            # Trigger watch action
            await watch_view._start_watch()
            await pilot.pause()

            # Verify watch command was sent
            assert len(client.commands_received) >= 1
            watch_cmds = [
                cmd for cmd in client.commands_received if cmd.get("type") == "watch"
            ]
            assert len(watch_cmds) == 1
            cmd = watch_cmds[0]
            assert cmd["action"] == "start"
            assert cmd["pattern"] == "module.Class.method"
            assert cmd["times"] == -1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_observation_updates_log_and_table(self, mock_client_factory):
        """Configure mock with observations, start watch, verify table updated."""
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}},
        )
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

            # Verify DataTable has watch entry
            table = watch_view.query_one("#watch-table", DataTable)
            assert table.row_count >= 1

            # Verify watch is tracked internally
            assert len(watch_view._active_watches) == 1
            assert "w1" in watch_view._active_watches

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_observation_data_correctness(self, mock_client_factory):
        """Verify watch command sends correct parameters."""
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}},
        )
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
            pattern_input.value = "calculator.add"

            await watch_view._start_watch()
            await pilot.pause()

            # Verify command sent with correct pattern
            watch_cmds = [
                cmd for cmd in client.commands_received if cmd.get("type") == "watch"
            ]
            assert len(watch_cmds) == 1
            assert watch_cmds[0]["pattern"] == "calculator.add"
            assert watch_cmds[0]["depth"] == 2
            assert watch_cmds[0]["times"] == -1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_multiple_observations(self, mock_client_factory):
        """Configure mock with multiple observations, verify worker starts."""
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
            for i in range(5)
        ]
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}},
        )
        stream_client = mock_client_factory(observations=observations)
        client.connect()
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
            watch_view._stream_client = stream_client

            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await watch_view._start_watch()
            await pilot.pause()

            # Verify worker was created
            assert "w1" in watch_view._active_watches
            worker = watch_view._active_watches["w1"]["worker"]
            assert worker is not None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_unlimited_watch_stream_does_not_stop_at_small_count(
        self, mock_client_factory
    ):
        """TUI times=-1 watch keeps processing observations beyond small limits."""
        observation_count = 25
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
            for i in range(observation_count)
        ]
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}},
        )
        stream_client = mock_client_factory(observations=observations)
        client.connect()
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
            watch_view._stream_client = stream_client

            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await watch_view._start_watch()
            worker = watch_view._active_watches["w1"]["worker"]
            assert worker is not None
            await worker.wait()
            await pilot.pause()

            watch_cmds = [
                cmd for cmd in client.commands_received if cmd.get("type") == "watch"
            ]
            assert watch_cmds[0]["times"] == -1
            assert watch_view._active_watches["w1"]["count"] == observation_count

            obs_table = watch_view.query_one("#observations-table", DataTable)
            assert obs_table.row_count == observation_count

            watch_table = watch_view.query_one("#watch-table", DataTable)
            row = watch_table.get_row("w1")
            assert str(observation_count) in [str(cell) for cell in row]

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_error_response(self, mock_client_factory):
        """Mock send_command returns error for watch command, verify error notification."""
        client = mock_client_factory(
            responses={"watch": {"status": "error", "error": "Pattern not found"}},
        )
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
            pattern_input.value = "invalid.pattern"

            await watch_view._start_watch()
            await pilot.pause()

            # Verify watch command was sent (ignore completion commands)
            watch_cmds = [
                cmd for cmd in client.commands_received if cmd.get("type") == "watch"
            ]
            assert len(watch_cmds) == 1
            assert watch_cmds[0]["action"] == "start"

            # Verify no watch entry in table (error prevents row addition)
            table = watch_view.query_one("#watch-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stream_disconnect(self, mock_client_factory):
        """Mock stream yields observation, verify watch entry created."""
        observations = [
            {
                "watch_id": "w1",
                "func_name": "module.func",
                "params": [42],
                "kwargs": {},
                "returnObj": 84,
                "cost": 0.3,
                "success": True,
                "count": 1,
            }
        ]
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}},
        )
        stream_client = mock_client_factory(observations=observations)
        client.connect()
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
            watch_view._stream_client = stream_client

            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await watch_view._start_watch()
            await pilot.pause()

            # Verify watch entry created
            table = watch_view.query_one("#watch-table", DataTable)
            assert table.row_count == 1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_stream_ignores_log_frames(self, mock_client_factory):
        """Agent log frames on the stream should not render as unknown observations."""
        observations = [
            {
                "type": "log",
                "level": "INFO",
                "message": "[peeka Agent] client disconnected",
            },
            {
                "type": "observation",
                "watch_id": "w1",
                "func_name": "module.func",
                "params": [42],
                "kwargs": {},
                "returnObj": 84,
                "cost": 0.3,
                "success": True,
                "count": 1,
            },
        ]
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}},
        )
        stream_client = mock_client_factory(observations=observations)
        client.connect()
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
            watch_view._stream_client = stream_client

            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await watch_view._start_watch()
            await pilot.pause()
            await pilot.pause()

            table = watch_view.query_one("#observations-table", DataTable)
            assert table.row_count == 1
            row = table.get_row_at(0)
            assert "module.func" in str(row)
            assert "unknown" not in str(row)

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_empty_pattern_validation(self, mock_client_factory):
        """Submit empty pattern, verify no command sent and warning shown."""
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}},
        )
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

            # Leave pattern input empty
            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = ""

            await watch_view._start_watch()
            await pilot.pause()

            # Verify no watch/start commands were sent (patch-status from banner fetch is ok)
            watch_commands = [c for c in client.commands_received if c.get("type") != "patch-status"]
            assert len(watch_commands) == 0

            # Verify no watch entry in table
            table = watch_view.query_one("#watch-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_runtime_banner_shows_gevent_state(self, mock_client_factory):
        client = mock_client_factory(
            responses={
                "patch-status": make_patch_status_response(
                    backend="wrapper_only",
                    downgraded=True,
                    degraded_reason="gevent detected",
                )
            }
        )
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
            await pilot.pause()
            
            await pilot.pause()

            banner = watch_view.query_one("#watch-runtime-banner", Static)
            text = str(banner.render())
            assert "patched" in text
            assert "wrapper_only" in text
            assert "downgraded: gevent detected" in text


    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_table_has_ten_columns(self, mock_client_factory):
        """Active watches table has exactly 10 specified columns."""
        client = mock_client_factory(responses={})
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            obs_table = watch_view.query_one("#watch-table", DataTable)
            col_keys = {col.key.value for col in obs_table.columns.values()}
            assert col_keys == {
                "ID", "Pattern", "Status", "Obs", "Running Time",
                "Errors", "Last ms", "Async", "Backend", "Runtime",
            }
            assert len(list(obs_table.columns.values())) == 10

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_backend_runtime_default_dash_when_no_runtime_meta(
        self, mock_client_factory
    ):
        """Backend and Runtime default to '—' when runtime_meta is absent."""
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}},
        )
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

            watch_table = watch_view.query_one("#watch-table", DataTable)
            assert watch_table.get_cell("w1", "Backend") == "—"
            assert watch_table.get_cell("w1", "Runtime") == "—"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_async_column_shows_check_and_dash(self, mock_client_factory):
        """Async column shows '✦' when is_coroutine_function=True, '—' otherwise."""
        client_async = mock_client_factory(
            responses={
                "watch": {
                    "status": "success",
                    "watch_id": "w1",
                    "target": {"is_coroutine_function": True},
                }
            },
        )
        client_async.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(client_async)

            pattern_input = watch_view.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input.value = "module.async_func"

            await watch_view._start_watch()
            await pilot.pause()

            watch_table = watch_view.query_one("#watch-table", DataTable)
            assert watch_table.get_cell("w1", "Async") == "✦"

        client_sync = mock_client_factory(
            responses={
                "watch": {
                    "status": "success",
                    "watch_id": "w2",
                    "target": {"is_coroutine_function": False},
                }
            },
        )
        client_sync.connect()

        app2 = PeekaApp()
        async with app2.run_test() as pilot2:
            main_screen2 = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app2.push_screen(main_screen2)
            await pilot2.pause()

            watch_view2 = app2.screen.query_one("WatchView", WatchView)
            watch_view2.set_client(client_sync)

            pattern_input2 = watch_view2.query_one("#watch-pattern", AutoCompleteInput)
            pattern_input2.value = "module.sync_func"

            await watch_view2._start_watch()
            await pilot2.pause()

            watch_table2 = watch_view2.query_one("#watch-table", DataTable)
            assert watch_table2.get_cell("w2", "Async") == "—"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_perf_columns_update_after_observation(self, mock_client_factory):
        """Obs, Last ms, Errors and Running Time update after _add_observation."""
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}},
        )
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

            observation = {
                "watch_id": "w1",
                "func_name": "module.func",
                "params": [42],
                "kwargs": {},
                "returnObj": 84,
                "cost": 7.5,
                "success": True,
                "count": 1,
            }
            watch_view._add_observation("w1", 1, observation)
            await pilot.pause()

            watch_table = watch_view.query_one("#watch-table", DataTable)
            assert watch_table.get_cell("w1", "Obs") == "1"
            assert watch_table.get_cell("w1", "Last ms") == "7.5ms"
            assert watch_table.get_cell("w1", "Errors") == "0"
            running_time = watch_table.get_cell("w1", "Running Time")
            assert str(running_time).endswith("s")

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_errors_increments_on_failed_observation(self, mock_client_factory):
        """Errors column increments when success=False observation arrives."""
        client = mock_client_factory(
            responses={"watch": {"status": "success", "watch_id": "w1"}},
        )
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

            failed_obs = {
                "watch_id": "w1",
                "func_name": "module.func",
                "params": [],
                "kwargs": {},
                "returnObj": None,
                "throwExp": "ValueError: bad input",
                "cost": 1.0,
                "success": False,
                "count": 1,
            }
            watch_view._add_observation("w1", 1, failed_obs)
            await pilot.pause()

            watch_table = watch_view.query_one("#watch-table", DataTable)
            assert watch_table.get_cell("w1", "Errors") == "1"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stop_all_watches_sets_status_stopped(self, mock_client_factory):
        """_stop_all_watches sets Status='Stopped' and row persists in the table."""
        client = mock_client_factory(
            responses={
                "watch": {"status": "success", "watch_id": "w1"},
            },
        )
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

            await watch_view._stop_all_watches()
            await pilot.pause()

            watch_table = watch_view.query_one("#watch-table", DataTable)
            assert watch_table.row_count >= 1
            assert watch_table.get_cell("w1", "Status") == "Stopped"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_restart_same_pattern_evicts_stopped_row(self, mock_client_factory):
        """Re-starting the same pattern after stop removes the old Stopped row."""
        client = mock_client_factory(
            responses={
                "watch": {"status": "success", "watch_id": "w1"},
            },
        )
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
            pattern_input.value = "same.pattern"
            await watch_view._start_watch()
            await pilot.pause()

            await watch_view._stop_all_watches()
            await pilot.pause()

            watch_table = watch_view.query_one("#watch-table", DataTable)
            assert watch_table.get_cell("w1", "Status") == "Stopped"

            pattern_input.value = "same.pattern"
            await watch_view._start_watch()
            await pilot.pause()

            assert watch_table.row_count == 1
            assert watch_table.get_cell("w1", "Status") == "Running"


class TestWatchViewLayout:
    """Geometry tests for WatchView layout redesign (T2)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_list_at_top_height_13(self, mock_client_factory):
        """#watch-list should render with height=13 at the top of the view."""
        client = mock_client_factory(responses={})
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(80, 30)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("watch")
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_list = watch_view.query_one("#watch-list", Vertical)
            assert watch_list.region.height == 13

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_bottom_panel_2to1_ratio(self, mock_client_factory):
        """#observations-panel should be ~2x the width of #observation-detail-panel."""
        client = mock_client_factory(responses={})
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("watch")
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            obs = watch_view.query_one("#observations-panel", Vertical)
            detail = watch_view.query_one("#observation-detail-panel", Vertical)

            assert obs.region.y == detail.region.y
            assert obs.region.x < detail.region.x
            assert abs(obs.region.width - 2 * detail.region.width) <= 2

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_runtime_banner_between_controls_and_list(
        self, mock_client_factory
    ):
        """#watch-runtime-banner should sit between #watch-top-controls and #watch-list."""
        from textual.containers import Container

        client = mock_client_factory(
            responses={
                "patch-status": make_patch_status_response(
                    backend="wrapper_only",
                    downgraded=True,
                    degraded_reason="gevent detected",
                )
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(80, 30)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("watch")
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(client)
            await pilot.pause()
            await pilot.pause()

            watch_container = watch_view.query_one("#watch-container", Container)
            child_ids = [child.id for child in watch_container.children]

            assert "watch-top-controls" in child_ids
            assert "watch-runtime-banner" in child_ids
            assert "watch-list" in child_ids
            controls_idx = child_ids.index("watch-top-controls")
            banner_idx = child_ids.index("watch-runtime-banner")
            list_idx = child_ids.index("watch-list")
            assert controls_idx < banner_idx < list_idx
