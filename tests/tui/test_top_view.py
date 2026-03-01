"""Tests for Top view (function-level profiling table)."""

import pytest
from textual.widgets import Button, DataTable, Static

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.top import TopView


class TestTopView:
    """Test TopView widget population from mock client responses."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_top_view_renders(self, mock_client):
        """Test that TopView renders with correct structure."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            # Switch to Top tab
            main_screen.action_switch_tab("top")
            await pilot.pause()

            # Assert TopView is present
            top_view = app.screen.query_one(TopView)
            assert top_view is not None
            assert top_view.id == "top-container"

            # Assert DataTable exists
            table = top_view.query_one("#top-table", DataTable)
            assert table is not None

            # Assert 5 columns
            assert len(table.columns) == 5

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_top_view_has_table(self, mock_client):
        """Test TopView has properly initialized DataTable."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            # Switch to Top tab
            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)
            table = top_view.query_one("#top-table", DataTable)

            # Assert table structure is correct (5 columns)
            assert len(table.columns) == 5

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_top_view_initial_state(self, mock_client):
        """Test TopView shows stopped state before user starts profiling."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            # Switch to Top tab
            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)
            header = top_view.query_one("#top-header", Static)
            header_text = header.render().plain

            # Should show stopped state (no auto-start)
            assert "Stopped" in header_text or "Top View" in header_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_top_view_footer_text(self, mock_client):
        """Test TopView footer displays keybinding hints."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            # Switch to Top tab
            main_screen.action_switch_tab("top")
            await pilot.pause()

            # Check footer text
            top_view = app.screen.query_one(TopView)
            footer = top_view.query_one("#top-footer", Static)
            footer_text = footer.render().plain

            assert "Start" in footer_text or "reset" in footer_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_top_tab_exists(self, mock_client):
        """Test that Top tab is registered in MainScreen."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            # Assert Top tab exists and can be switched to
            main_screen.action_switch_tab("top")
            await pilot.pause()

            # Should switch without error and TopView should be visible
            top_view = app.screen.query_one(TopView)
            assert top_view is not None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_top_view_set_client(self, mock_client):
        """Test TopView accepts client via set_client without auto-starting."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            # Get TopView and set client
            top_view = app.screen.query_one(TopView)
            top_view.set_client(mock_client)

            # Assert client is set but profiling NOT started
            assert top_view._client is mock_client
            assert top_view._is_profiling is False

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_top_view_widget_hierarchy(self, mock_client):
        """Test TopView has correct widget structure including buttons."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)

            # Assert all required widgets exist
            header = top_view.query_one("#top-header", Static)
            table = top_view.query_one("#top-table", DataTable)
            footer = top_view.query_one("#top-footer", Static)
            start_btn = top_view.query_one("#top-start-btn", Button)
            stop_btn = top_view.query_one("#top-stop-btn", Button)
            reset_btn = top_view.query_one("#top-reset-btn", Button)

            assert header is not None
            assert table is not None
            assert footer is not None
            assert start_btn is not None
            assert stop_btn is not None
            assert reset_btn is not None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_top_view_empty_table_initially(self, mock_client):
        """Test TopView table starts empty before data is fetched."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)
            table = top_view.query_one("#top-table", DataTable)

            # Table should be empty initially (no data fetched yet)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_top_view_button_initial_states(self, mock_client):
        """Test button disabled states before and after client is set."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)
            stop_btn = top_view.query_one("#top-stop-btn", Button)
            reset_btn = top_view.query_one("#top-reset-btn", Button)

            # Stop and Reset should be disabled when not profiling
            assert stop_btn.disabled is True
            assert reset_btn.disabled is True


class TestTopViewDataFlow:
    """Test TopView data flow: start/stop profiling, table updates, reset."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_start_profiling_sends_command(self, mock_client_factory):
        """Clicking Start sends top start command and updates state."""
        client = mock_client_factory(
            responses={
                "top": {
                    "status": "success",
                    "top_id": "top_001",
                },
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)
            # Bypass _connect_own_client (which imports real client)
            top_view._client = client
            top_view._own_client = client
            top_view._update_button_states()
            await pilot.pause()

            top_view._start_profiling()
            await pilot.pause()

            # Verify command sent
            top_cmds = [
                c for c in client.commands_received if c.get("type") == "top"
            ]
            assert len(top_cmds) >= 1
            assert top_cmds[0].get("action") == "start"

            # Verify state updated
            assert top_view._is_profiling is True
            assert top_view._top_id == "top_001"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_start_profiling_updates_header(self, mock_client_factory):
        """After start, header shows 'Profiling...' text."""
        client = mock_client_factory(
            responses={
                "top": {"status": "success", "top_id": "top_002"},
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)
            top_view._client = client
            top_view._own_client = client
            top_view._update_button_states()

            top_view._start_profiling()
            await pilot.pause()

            header = top_view.query_one("#top-header", Static)
            header_text = header.render().plain
            assert "Profiling" in header_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stop_profiling_sends_command(self, mock_client_factory):
        """Stop profiling sends stop command and resets state."""
        client = mock_client_factory(
            responses={
                "top": {"status": "success", "top_id": "top_003"},
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)
            top_view._client = client
            top_view._own_client = client
            top_view._update_button_states()

            # Start first
            top_view._start_profiling()
            await pilot.pause()
            assert top_view._is_profiling is True

            # Stop
            top_view._stop_profiling()
            await pilot.pause()

            # Verify stop command sent
            stop_cmds = [
                c for c in client.commands_received
                if c.get("type") == "top" and c.get("action") == "stop"
            ]
            assert len(stop_cmds) >= 1

            # Verify state reset
            assert top_view._is_profiling is False
            assert top_view._top_id is None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_update_table_populates_data(self, mock_client_factory):
        """_update_table with snapshot data populates DataTable rows."""
        client = mock_client_factory(
            responses={
                "top": {"status": "success", "top_id": "top_004"},
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)

            # Directly call _update_table with snapshot data
            snapshot = {
                "total_samples": 500,
                "sample_interval": 0.01,
                "functions": [
                    {"name": "process", "filename": "app.py", "line": 10, "own_pct": 25.3, "total_pct": 68.2, "own_time": 2.53, "total_time": 6.82},
                    {"name": "parse", "filename": "parser.py", "line": 5, "own_pct": 18.7, "total_pct": 22.1, "own_time": 1.87, "total_time": 2.21},
                    {"name": "query", "filename": "db.py", "line": 88, "own_pct": 15.2, "total_pct": 45.6, "own_time": 1.52, "total_time": 4.56},
                ],
            }
            top_view._update_table(snapshot)
            await pilot.pause()

            table = top_view.query_one("#top-table", DataTable)
            assert table.row_count == 3

            # Verify first row content
            row0 = table.get_row_at(0)
            assert "25.3%" in str(row0)
            assert "process" in str(row0)

            # Verify header updated with sample info
            header = top_view.query_one("#top-header", Static)
            header_text = header.render().plain
            assert "500" in header_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_reset_stats_sends_command_and_clears_table(self, mock_client_factory):
        """action_reset_stats sends reset command and clears table."""
        client = mock_client_factory(
            responses={
                "top": {"status": "success", "top_id": "top_005"},
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)
            top_view._client = client
            top_view._own_client = client
            top_view._update_button_states()

            # Start profiling first (reset requires is_profiling=True)
            top_view._start_profiling()
            await pilot.pause()

            # Add some data to table
            snapshot = {
                "total_samples": 100,
                "sample_interval": 0.01,
                "functions": [
                    {"name": "func", "filename": "f.py", "line": 1, "own_pct": 50.0, "total_pct": 50.0, "own_time": 0.5, "total_time": 0.5},
                ],
            }
            top_view._update_table(snapshot)
            await pilot.pause()

            table = top_view.query_one("#top-table", DataTable)
            assert table.row_count == 1

            # Reset
            top_view.action_reset_stats()
            await pilot.pause()

            # Verify reset command sent
            reset_cmds = [
                c for c in client.commands_received
                if c.get("type") == "top" and c.get("action") == "reset"
            ]
            assert len(reset_cmds) >= 1

            # Verify table cleared
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_start_profiling_error_shows_in_header(self, mock_client_factory):
        """Error response from start command shows error in header."""
        client = mock_client_factory(
            responses={
                "top": {"status": "error", "error": "Profiler already running"},
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)
            top_view._client = client
            top_view._own_client = client
            top_view._update_button_states()

            top_view._start_profiling()
            await pilot.pause()

            # Should NOT be profiling on error
            assert top_view._is_profiling is False

            # Header should show error
            header = top_view.query_one("#top-header", Static)
            header_text = header.render().plain
            assert "Error" in header_text or "error" in header_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_reset_when_not_profiling_shows_warning(self, mock_client_factory):
        """Reset when not profiling shows warning notification."""
        client = mock_client_factory(
            responses={
                "top": {"status": "success"},
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)
            top_view._client = client
            top_view._own_client = client

            # Not profiling — reset should show warning, not send command
            top_view.action_reset_stats()
            await pilot.pause()

            # No reset command should be sent since not profiling
            reset_cmds = [
                c for c in client.commands_received
                if c.get("type") == "top" and c.get("action") == "reset"
            ]
            assert len(reset_cmds) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_button_states_after_start(self, mock_client_factory):
        """After starting profiling, Start is disabled, Stop/Reset are enabled."""
        client = mock_client_factory(
            responses={
                "top": {"status": "success", "top_id": "top_006"},
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("top")
            await pilot.pause()

            top_view = app.screen.query_one(TopView)
            top_view._client = client
            top_view._own_client = client
            top_view._update_button_states()

            top_view._start_profiling()
            await pilot.pause()

            start_btn = top_view.query_one("#top-start-btn", Button)
            stop_btn = top_view.query_one("#top-stop-btn", Button)
            reset_btn = top_view.query_one("#top-reset-btn", Button)

            # Start should be disabled, Stop/Reset enabled
            assert start_btn.disabled is True
            assert stop_btn.disabled is False
            assert reset_btn.disabled is False
