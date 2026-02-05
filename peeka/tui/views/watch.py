"""
Watch View - Function observation interface.
"""

from typing import Optional

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button, RichLog

from peeka.tui.completion import CompletionSource
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput


class WatchView(Container):
    """Watch view for observing function calls."""

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._active_watches: dict = {}
        self._completion_source: Optional[CompletionSource] = None

    def set_client(self, client) -> None:
        """Set agent client for completion."""
        self._completion_source = CompletionSource(client)

    def _get_pattern_completions(self, prefix: str):
        """Get completions for pattern input."""
        if self._completion_source:
            return self._completion_source.get_completions(prefix)
        return []

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                AutoCompleteInput(
                    placeholder="module.Class.method",
                    completions_callback=self._get_pattern_completions,
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
        pattern_widget = self.query_one("#watch-pattern")
        if isinstance(pattern_widget, AutoCompleteInput):
            pattern = pattern_widget.value
        else:
            pattern = pattern_widget.value  # type: ignore

        condition = self.query_one("#watch-condition", Input).value

        if not pattern:
            self.app.notify("Please enter a pattern", severity="warning")
            return

        self.app.notify(f"Watching: {pattern}")

    async def _stop_all_watches(self) -> None:
        """Stop all active watches."""
        self.app.notify("Stopped all watches")
