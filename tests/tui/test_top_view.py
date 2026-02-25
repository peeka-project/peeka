"""Tests for Top view (function-level profiling table)."""

import pytest
from textual.widgets import DataTable, Static

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
        """Test TopView shows initialization message before data loads."""
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

            # Before profiling starts, header shows initialization message
            assert "Initializing" in header_text or "Top View" in header_text

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

            assert "Press r to reset stats" in footer_text or "F8" in footer_text

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
        """Test TopView accepts client via set_client method."""
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

            # Assert client is set
            assert top_view._client is mock_client

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_top_view_widget_hierarchy(self, mock_client):
        """Test TopView has correct widget structure."""
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

            assert header is not None
            assert table is not None
            assert footer is not None

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
