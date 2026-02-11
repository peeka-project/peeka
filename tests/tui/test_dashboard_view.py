"""Tests for DashboardView - data-flow and error handling."""

import pytest
from textual.widgets import Static

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.dashboard import DashboardView


class TestDashboardView:
    """Test DashboardView widget population from mock client responses."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_set_client_triggers_refresh(self, mock_client):
        """set_client() triggers data refresh and populates widgets."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)

            await pilot.pause()
            await pilot.pause()

            assert len(mock_client.commands_received) >= 2
            command_types = [cmd.get("type") for cmd in mock_client.commands_received]
            assert "vmtool" in command_types
            assert "memory" in command_types

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_memory_stats_display(self, mock_client):
        """Memory stats from mock client appear in dashboard widgets."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)

            await pilot.pause()
            await pilot.pause()

            mem_rss_widget = app.screen.query_one("#mem-rss", Static)
            assert "50.0 MB" in mem_rss_widget.render().plain

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_gc_counts_display(self, mock_client):
        """GC counts from mock memory response populate GC widgets."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)

            await pilot.pause()
            await pilot.pause()

            gc_gen0 = app.screen.query_one("#gc-gen0", Static)
            gc_gen1 = app.screen.query_one("#gc-gen1", Static)
            gc_gen2 = app.screen.query_one("#gc-gen2", Static)

            assert "700" in gc_gen0.render().plain
            assert "10" in gc_gen1.render().plain
            assert "1" in gc_gen2.render().plain

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_uptime_display(self, mock_client):
        """Uptime widget displays calculated uptime."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)

            await pilot.pause()
            await pilot.pause()

            uptime_widget = app.screen.query_one("#uptime", Static)
            assert "Uptime:" in uptime_widget.render().plain

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_refresh_action(self, mock_client):
        """Pressing 'r' triggers refresh and sends new commands."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)

            await pilot.pause()
            await pilot.pause()

            initial_command_count = len(mock_client.commands_received)

            dashboard.action_refresh()
            await pilot.pause()
            await pilot.pause()

            assert len(mock_client.commands_received) > initial_command_count

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_client_error_response(self, mock_client_factory):
        """Dashboard handles error responses gracefully without crashing."""
        error_client = mock_client_factory(
            responses={
                "vmtool": {"status": "error", "error": "vmtool failed"},
                "memory": {"status": "error", "error": "memory failed"},
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

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(error_client)

            await pilot.pause()
            await pilot.pause()

            mem_rss_widget = app.screen.query_one("#mem-rss", Static)
            content = mem_rss_widget.render().plain
            assert "detecting" in content or "RSS" in content

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_no_client_connected(self):
        """Dashboard with no client shows initial placeholder text."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)

            python_version = app.screen.query_one("#python-version", Static)
            mem_rss = app.screen.query_one("#mem-rss", Static)
            uptime = app.screen.query_one("#uptime", Static)

            assert "detecting" in python_version.render().plain
            assert "detecting" in mem_rss.render().plain
            assert "Uptime:" in uptime.render().plain
