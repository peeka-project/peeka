"""
TUI Component Tests using Textual's testing framework.

Tests verify:
1. ProcessSelectorScreen renders and ESC quits
2. MainScreen renders and ESC goes back
3. Tab switching works without translate AttributeError
4. All View components render inside TabPane
"""

import pytest

from peeka.tui.app import PeekaApp
from peeka.tui.screens.process_selector import ProcessSelectorScreen
from peeka.tui.screens.main import MainScreen


class TestProcessSelectorScreen:
    """Tests for ProcessSelectorScreen."""

    @pytest.mark.asyncio
    async def test_screen_renders(self):
        """Test that ProcessSelectorScreen renders without error."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            # Should start with ProcessSelectorScreen
            assert isinstance(app.screen, ProcessSelectorScreen)

    @pytest.mark.asyncio
    async def test_escape_quits(self):
        """Test that ESC key quits the application."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            await pilot.press("escape")
            await pilot.pause()
            # App should be exiting
            assert app._exit

    @pytest.mark.asyncio
    async def test_refresh_action(self):
        """Test that R key refreshes process list."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            # Verify we're on ProcessSelectorScreen
            assert isinstance(app.screen, ProcessSelectorScreen)
            # Press 'r' to refresh
            await pilot.press("r")
            await pilot.pause()
            # Should not crash, still on same screen
            assert isinstance(app.screen, ProcessSelectorScreen)


class TestMainScreen:
    """Tests for MainScreen."""

    @pytest.mark.asyncio
    async def test_main_screen_renders(self):
        """Test that MainScreen renders with a PID."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            # Push MainScreen with test parameters (no real connection)
            app.push_screen(
                MainScreen(
                    pid=12345, session_id="test-session", socket_path="/tmp/fake.sock"
                )
            )
            await pilot.pause()
            assert isinstance(app.screen, MainScreen)
            assert app.screen.pid == 12345

    @pytest.mark.asyncio
    async def test_escape_goes_back(self):
        """Test that ESC key goes back to process selector."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            # Start with ProcessSelectorScreen
            assert isinstance(app.screen, ProcessSelectorScreen)
            # Push MainScreen
            app.push_screen(
                MainScreen(
                    pid=12345, session_id="test-session", socket_path="/tmp/fake.sock"
                )
            )
            await pilot.pause()
            assert isinstance(app.screen, MainScreen)
            # Press ESC to go back
            await pilot.press("escape")
            await pilot.pause()
            # Should be back to ProcessSelectorScreen
            assert isinstance(app.screen, ProcessSelectorScreen)

    @pytest.mark.asyncio
    async def test_tab_switching(self):
        """Test tab switching with keyboard shortcuts."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(
                    pid=12345, session_id="test-session", socket_path="/tmp/fake.sock"
                )
            )
            await pilot.pause()

            # Test switching tabs with different keys
            # Each key should switch to corresponding tab without errors
            for key in ["d", "w", "s", "m", "e", "l", "i"]:
                await pilot.press(key)
                await pilot.pause()
                # Should still be on MainScreen after tab switch
                assert isinstance(app.screen, MainScreen)


class TestViews:
    """Tests for individual views."""

    @pytest.mark.asyncio
    async def test_dashboard_view_in_tabpane(self):
        """Test DashboardView renders inside TabPane without translate AttributeError."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(
                    pid=12345, session_id="test-session", socket_path="/tmp/fake.sock"
                )
            )
            await pilot.pause()
            # Press 'd' to switch to dashboard view
            await pilot.press("d")
            await pilot.pause()
            # Should not raise translate AttributeError
            # If we get here without exception, test passes
            assert isinstance(app.screen, MainScreen)

    @pytest.mark.asyncio
    async def test_watch_view_button_press(self):
        """Test WatchView button interactions without errors."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            app.push_screen(
                MainScreen(
                    pid=12345, session_id="test-session", socket_path="/tmp/fake.sock"
                )
            )
            await pilot.pause()
            # Press 'w' to switch to watch tab
            await pilot.press("w")
            await pilot.pause()
            # Should render without AttributeError
            # If we get here without exception, test passes
            assert isinstance(app.screen, MainScreen)
