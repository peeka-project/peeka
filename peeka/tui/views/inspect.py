"""
Inspect View - Runtime object inspection interface.
"""

from typing import TYPE_CHECKING, Optional, Any, Dict

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, Input, Button, Tree, Pretty
from textual.widgets.tree import TreeNode

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class InspectView(Container):
    BINDINGS = [
        Binding("enter", "inspect", "Inspect"),
    ]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._current_object: Optional[Dict[str, Any]] = None

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Static("Object Path:", classes="input-label"),
                Input(
                    placeholder="module.Class or module.variable",
                    id="inspect-path",
                ),
                Button("Inspect", id="inspect-btn", variant="primary"),
                id="inspect-controls",
            ),
            Horizontal(
                Vertical(
                    Tree("Object", id="inspect-tree"),
                    id="inspect-tree-panel",
                    classes="panel",
                ),
                Vertical(
                    Pretty("Select an object to inspect", id="inspect-details"),
                    id="inspect-details-panel",
                    classes="panel",
                ),
                id="inspect-content",
            ),
            id="inspect-container",
        )

    def on_mount(self) -> None:
        tree_panel = self.query_one("#inspect-tree-panel", Vertical)
        tree_panel.border_title = "Object Tree"

        details_panel = self.query_one("#inspect-details-panel", Vertical)
        details_panel.border_title = "Details"

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if not self._client:
            self.app.notify("Not connected to agent", severity="warning")
            return

        if event.button.id == "inspect-btn":
            await self._inspect_object()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "inspect-path":
            await self._inspect_object()

    def action_inspect(self) -> None:
        """Inspect object (triggered by Enter key)."""
        self.app.call_later(self._inspect_object)

    async def _inspect_object(self) -> None:
        if not self._client:
            return

        input_widget = self.query_one("#inspect-path", Input)
        target = input_widget.value.strip()

        if not target:
            self.app.notify("Please enter an object path", severity="warning")
            return

        response = self._client.send_command(
            {"type": "vmtool", "action": "get", "target": target, "depth": 3}
        )

        if response.get("status") != "success":
            self.app.notify(
                f"Failed to inspect: {response.get('error', 'Unknown error')}",
                severity="error",
            )
            return

        self._current_object = response

        tree = self.query_one("#inspect-tree", Tree)
        tree.clear()

        root = tree.root
        root.label = f"{target} ({response.get('type', 'unknown')})"

        value = response.get("value")
        self._populate_tree(root, value)

        root.expand()

        pretty = self.query_one("#inspect-details", Pretty)
        pretty.update(value)

        self.app.notify(f"Inspected: {target}", severity="information")

    def _populate_tree(
        self, node: TreeNode, value: Any, max_depth: int = 2, current_depth: int = 0
    ) -> None:
        if current_depth >= max_depth:
            return

        if isinstance(value, dict):
            for key, val in value.items():
                if isinstance(val, (dict, list)):
                    child = node.add(f"{key}: {type(val).__name__}")
                    self._populate_tree(child, val, max_depth, current_depth + 1)
                else:
                    node.add(f"{key}: {self._format_leaf(val)}")
        elif isinstance(value, list):
            for idx, val in enumerate(value):
                if isinstance(val, (dict, list)):
                    child = node.add(f"[{idx}]: {type(val).__name__}")
                    self._populate_tree(child, val, max_depth, current_depth + 1)
                else:
                    node.add(f"[{idx}]: {self._format_leaf(val)}")

    def _format_leaf(self, value: Any) -> str:
        if isinstance(value, str):
            if len(value) > 50:
                return f'"{value[:50]}..."'
            return f'"{value}"'
        return str(value)
