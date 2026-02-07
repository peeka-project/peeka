"""
Stack View - Call stack tracing interface.
"""

from typing import Optional, Dict, TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button, Tree
from textual.worker import Worker, get_current_worker

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class StackView(Container):
    """Stack view for tracing function call stacks."""

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._workers: Dict[str, Worker] = {}
        self._trace_counts: Dict[str, int] = {}

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Static("Pattern:", classes="input-label"),
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
        table = self.query_one("#trace-table", DataTable)
        table.add_columns("ID", "Pattern", "Captures", "Status")
        table.cursor_type = "row"

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "trace-btn":
            await self._start_trace()
        elif event.button.id == "stop-trace-btn":
            await self._stop_all_traces()

    async def _start_trace(self) -> None:
        if not self._client:
            self.app.notify("Not connected to agent", severity="error")
            return

        pattern_input = self.query_one("#stack-pattern", Input)
        pattern = pattern_input.value.strip()

        if not pattern:
            self.app.notify("Please enter a function pattern", severity="warning")
            return

        command = {
            "type": "stack",
            "action": "start",
            "pattern": pattern,
            "depth": 10,
            "times": -1,
        }

        response = self._client.send_command(command)

        if response.get("status") != "success":
            self.app.notify(
                f"Trace failed: {response.get('error', 'Unknown error')}",
                severity="error",
            )
            return

        watch_id = response.get("watch_id", "")
        short_id = watch_id[:8] if len(watch_id) > 8 else watch_id

        table = self.query_one("#trace-table", DataTable)
        table.add_row(short_id, pattern, "0", "Running", key=watch_id)

        self._trace_counts[watch_id] = 0

        worker = self.run_worker(
            lambda: self._stream_traces(watch_id, pattern), thread=True, exclusive=False
        )
        self._workers[watch_id] = worker

        self.app.notify(f"Trace started: {pattern}", severity="information")

    def _stream_traces(self, watch_id: str, pattern: str):
        if not self._client:
            return

        worker = get_current_worker()

        for observation in self._client.stream_observations():
            if worker.is_cancelled:
                break

            obs_watch_id = observation.get("watch_id", "")
            if obs_watch_id != watch_id:
                continue

            count = observation.get("count", 0)
            stack_frames = observation.get("stack", [])

            self.app.call_from_thread(
                self._update_trace_ui, watch_id, count, stack_frames
            )

    def _update_trace_ui(self, watch_id: str, count: int, stack_frames: list) -> None:
        table = self.query_one("#trace-table", DataTable)

        try:
            row = table.get_row(watch_id)
            short_id = row[0]
            pattern = row[1]
            table.update_cell_at((watch_id, 2), str(count))
        except Exception:
            return

        tree = self.query_one("#stack-tree", Tree)
        tree.clear()

        root = tree.root
        root.label = f"Stack Trace #{count}"

        for frame in stack_frames:
            filename = frame.get("filename", "")
            lineno = frame.get("lineno", 0)
            function = frame.get("function", "")
            code = frame.get("code", "")

            frame_label = f"{function} @ {filename}:{lineno}"
            frame_node = root.add(frame_label)

            if code:
                frame_node.add_leaf(f"  {code}")

    async def _stop_all_traces(self) -> None:
        if not self._workers:
            self.app.notify("No active traces", severity="information")
            return

        for watch_id, worker in list(self._workers.items()):
            if worker:
                worker.cancel()

            try:
                if self._client:
                    self._client.send_command(
                        {"type": "stack", "action": "stop", "watch_id": watch_id}
                    )
                    self._client.send_command(
                        {"type": "reset", "action": "reset", "pattern": "*"}
                    )
            except Exception:
                pass

        self._workers.clear()
        self._trace_counts.clear()

        table = self.query_one("#trace-table", DataTable)
        table.clear()

        tree = self.query_one("#stack-tree", Tree)
        tree.clear()

        self.app.notify("All traces stopped", severity="information")
