"""
Inspect View - Runtime object inspection interface.
"""

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Input, Button, Tree, Pretty
from textual.widget import Widget


class InspectView(Widget):
    """Inspect view for examining runtime objects."""

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Input(
                    placeholder="module.Class or module.variable",
                    id="inspect-path",
                ),
                Button("Inspect", id="inspect-btn", variant="primary"),
                id="inspect-controls",
            ),
            Horizontal(
                Vertical(
                    Static("Object Tree", classes="section-title"),
                    Tree("Object", id="inspect-tree"),
                    id="inspect-tree-panel",
                ),
                Vertical(
                    Static("Details", classes="section-title"),
                    Pretty("Select an object to inspect", id="inspect-details"),
                    id="inspect-details-panel",
                ),
                id="inspect-content",
            ),
            id="inspect-container",
        )
