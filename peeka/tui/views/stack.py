"""
Stack View - Call stack tracing interface.
"""

from typing import Optional, Dict, TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button, Tree
from textual.worker import Worker, get_current_worker

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class StackView(Container):
    """Stack view for tracing function call stacks."""

    BINDINGS = [
        Binding("enter", "start_trace", "Trace"),
        Binding("delete", "stop_traces", "Stop All"),
    ]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._stream_client: Optional["StreamingAgentClient"] = None
        self._workers: Dict[str, Worker] = {}
        self._trace_counts: Dict[str, int] = {}

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client

    def set_stream_client(self, client: "StreamingAgentClient") -> None:
        self._stream_client = client

    async def action_start_trace(self) -> None:
        """Start tracing (triggered by Enter key)."""
        await self._start_trace()

    async def action_stop_traces(self) -> None:
        """Stop all traces (triggered by Delete key)."""
        await self._stop_all_traces()

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
                    DataTable(id="trace-table"),
                    id="trace-list",
                    classes="panel",
                ),
                Vertical(
                    Tree("Stack", id="stack-tree"),
                    id="stack-panel",
                    classes="panel",
                ),
                id="stack-content",
            ),
            id="stack-container",
        )

    def on_mount(self) -> None:
        table = self.query_one("#trace-table", DataTable)
        table.add_columns("ID", "Pattern", "Captures", "Status")
        table.cursor_type = "row"

        trace_list = self.query_one("#trace-list", Vertical)
        trace_list.border_title = "Active Traces"

        stack_panel = self.query_one("#stack-panel", Vertical)
        stack_panel.border_title = "Call Stack"

    def on_unmount(self) -> None:
        """Cancel all workers when view is unmounted."""
        for worker in self._workers.values():
            if worker:
                worker.cancel()

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

        worker = self.run_worker(
            lambda: self._client.send_command(command),
            thread=True,
        )
        await worker.wait()
        response = worker.result

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
        stream = self._stream_client or self._client
        if not stream:
            return

        worker = get_current_worker()

        for observation in stream.stream_observations():
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
            table.update_cell(watch_id, "Captures", str(count))
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
                    stop_worker = self.run_worker(
                        lambda wid=watch_id: self._client.send_command(
                            {"type": "stack", "action": "stop", "watch_id": wid}
                        ),
                        thread=True,
                    )
                    await stop_worker.wait()

                    reset_worker = self.run_worker(
                        lambda: self._client.send_command(
                            {"type": "reset", "action": "reset", "pattern": "*"}
                        ),
                        thread=True,
                    )
                    await reset_worker.wait()
            except Exception:
                pass

        self._workers.clear()
        self._trace_counts.clear()

        table = self.query_one("#trace-table", DataTable)
        table.clear()

        tree = self.query_one("#stack-tree", Tree)
        tree.clear()

        self.app.notify("All traces stopped", severity="information")
