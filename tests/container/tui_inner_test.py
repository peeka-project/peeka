"""TUI tests that run inside the container via pytest.

These tests use textual's run_test() API to verify PeekaApp behavior.
They are executed by test_tui.py which orchestrates pytest inside the container.
"""

import pytest

from peeka.tui.app import PeekaApp

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
