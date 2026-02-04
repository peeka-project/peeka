"""
Memory View - Memory analysis interface.
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Button, ProgressBar


class MemoryView(Container):
    """Memory view for analyzing process memory."""

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Button("Refresh", id="mem-refresh-btn", variant="primary"),
                Button("Start Tracking", id="mem-track-btn"),
                Button("GC Collect", id="gc-btn"),
                Button("Dump", id="mem-dump-btn"),
                id="memory-controls",
            ),
            Horizontal(
                Vertical(
                    Static("Memory Overview", classes="section-title"),
                    Static("Total: calculating...", id="mem-total"),
                    Static("RSS: calculating...", id="mem-rss"),
                    Static("VMS: calculating...", id="mem-vms"),
                    ProgressBar(id="mem-bar", total=100),
                    id="mem-overview",
                    classes="dashboard-card",
                ),
                Vertical(
                    Static("Top Objects by Size", classes="section-title"),
                    DataTable(id="mem-objects-table"),
                    id="mem-objects",
                    classes="dashboard-card",
                ),
                id="memory-content",
            ),
            id="memory-container",
        )

    def on_mount(self) -> None:
        """Initialize memory objects table."""
        table = self.query_one("#mem-objects-table", DataTable)
        table.add_columns("Type", "Count", "Size")
