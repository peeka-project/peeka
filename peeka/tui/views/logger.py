"""
Logger View - Dynamic logger configuration interface.
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button, Select
from textual.widget import Widget


class LoggerView(Widget):
    """Logger view for managing logger levels."""

    LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Input(placeholder="Filter loggers...", id="logger-filter"),
                Button("Refresh", id="logger-refresh-btn", variant="primary"),
                id="logger-controls",
            ),
            Vertical(
                Static("Loggers", classes="section-title"),
                DataTable(id="logger-table"),
                id="logger-list",
            ),
            Horizontal(
                Input(placeholder="Logger name", id="logger-name"),
                Select(
                    [(level, level) for level in self.LEVELS],
                    id="logger-level-select",
                    prompt="Select level",
                ),
                Button("Set Level", id="set-level-btn", variant="primary"),
                id="logger-set-controls",
            ),
            id="logger-container",
        )

    def on_mount(self) -> None:
        """Initialize logger table."""
        table = self.query_one("#logger-table", DataTable)
        table.add_columns("Logger", "Level", "Handlers")
        table.cursor_type = "row"
