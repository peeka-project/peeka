"""
Stack View - Call stack tracing interface.
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button, Tree


class StackView(Container):
    """Stack view for tracing function call stacks."""

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Input(
                    placeholder="module.Class.method",
                    id="stack-pattern",
                ),
                Button("Trace", id="trace-btn", variant="primary"),
                Button("Stop", id="stop-trace-btn", variant="error"),
                id="stack-controls",
            ),
            Horizontal(
                Vertical(
                    Static("Active Traces", classes="section-title"),
                    DataTable(id="trace-table"),
                    id="trace-list",
                ),
                Vertical(
                    Static("Call Stack", classes="section-title"),
                    Tree("Stack", id="stack-tree"),
                    id="stack-panel",
                ),
                id="stack-content",
            ),
            id="stack-container",
        )

    def on_mount(self) -> None:
        """Initialize trace table."""
        table = self.query_one("#trace-table", DataTable)
        table.add_columns("ID", "Pattern", "Captures", "Status")
        table.cursor_type = "row"
