"""
Watch View - Function observation interface.
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button, RichLog


class WatchView(Container):
    """Watch view for observing function calls."""

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._active_watches: dict = {}

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Input(
                    placeholder="module.Class.method",
                    id="watch-pattern",
                ),
                Input(
                    placeholder="condition (optional)",
                    id="watch-condition",
                ),
                Button("Watch", id="watch-btn", variant="primary"),
                Button("Stop All", id="stop-btn", variant="error"),
                id="watch-controls",
            ),
            Horizontal(
                Vertical(
                    Static("Active Watches", classes="section-title"),
                    DataTable(id="watch-table"),
                    id="watch-list",
                ),
                Vertical(
                    Static("Observations", classes="section-title"),
                    RichLog(id="observations-log", highlight=True, markup=True),
                    id="observations-panel",
                ),
                id="watch-content",
            ),
            id="watch-container",
        )

    def on_mount(self) -> None:
        """Initialize watch table."""
        table = self.query_one("#watch-table", DataTable)
        table.add_columns("ID", "Pattern", "Count", "Status")
        table.cursor_type = "row"

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "watch-btn":
            await self._start_watch()
        elif event.button.id == "stop-btn":
            await self._stop_all_watches()

    async def _start_watch(self) -> None:
        """Start a new watch."""
        pattern = self.query_one("#watch-pattern", Input).value
        condition = self.query_one("#watch-condition", Input).value

        if not pattern:
            self.app.notify("Please enter a pattern", severity="warning")
            return

        # TODO: Send watch command to agent
        self.app.notify(f"Watching: {pattern}")

    async def _stop_all_watches(self) -> None:
        """Stop all active watches."""
        # TODO: Send stop commands to agent
        self.app.notify("Stopped all watches")
