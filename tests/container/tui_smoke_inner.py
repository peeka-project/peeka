"""Plain Python TUI smoke checks for container images without pytest."""

import asyncio
import os

from textual.widgets import TabbedContent, TabPane

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen


os.environ.setdefault("TERM", "xterm-256color")
os.environ.setdefault("COLORTERM", "truecolor")


async def main() -> None:
    """Run a compact TUI smoke suite inside the container."""
    app = PeekaApp()
    async with app.run_test(headless=True) as pilot:
        assert app.is_running

    app = PeekaApp()
    async with app.run_test(headless=True) as pilot:
        await pilot.press("?")
        assert app.is_running

    app = PeekaApp()
    async with app.run_test(headless=True) as pilot:
        app.push_screen(
            MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")
        )
        await pilot.pause()

        tabbed = app.screen.query_one("#main-content", TabbedContent)
        expected = [
            "dashboard",
            "watch",
            "trace",
            "stack",
            "monitor",
            "memory",
            "logger",
            "inspect",
            "threads",
            "top",
        ]
        panes = [pane for pane in tabbed.query(TabPane) if pane.id in expected]
        assert len(panes) == len(expected)
        assert [pane.id for pane in panes] == expected

        for tab_name in expected[1:] + [expected[0]]:
            app.screen.action_switch_tab(tab_name)
            await pilot.pause()
            assert tabbed.active == tab_name


if __name__ == "__main__":
    asyncio.run(main())
