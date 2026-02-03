"""
Monitor View - Performance statistics interface.
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button
from textual.widget import Widget


class MonitorView(Widget):
    """Monitor view for performance statistics."""

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Input(
                    placeholder="module.Class.method",
                    id="monitor-pattern",
                ),
                Input(
                    placeholder="interval (seconds)",
                    value="5",
                    id="monitor-interval",
                ),
                Button("Monitor", id="monitor-btn", variant="primary"),
                Button("Stop", id="stop-monitor-btn", variant="error"),
                id="monitor-controls",
            ),
            Vertical(
                Static("Performance Statistics", classes="section-title"),
                DataTable(id="stats-table"),
                id="stats-panel",
            ),
            id="monitor-container",
        )

    def on_mount(self) -> None:
        """Initialize stats table."""
        table = self.query_one("#stats-table", DataTable)
        table.add_columns(
            "Pattern",
            "Calls",
            "Success",
            "Fail",
            "Avg(ms)",
            "Min(ms)",
            "Max(ms)",
            "P95(ms)",
        )
