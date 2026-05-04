"""
Stack View - Call stack tracing interface.
"""

from typing import Optional, Dict, List, TYPE_CHECKING
import logging
import threading

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Button, Tree
from textual.worker import Worker, get_current_worker

from peeka.tui.activity import make_activity_reporter, make_client_info
from peeka.tui.completion import CompletionSource
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class StackView(Container):
    """Stack view for tracing function call stacks."""

    BINDINGS = [
        Binding("enter", "start_stack", "Stack"),
        Binding("delete", "stop_stacks", "Stop All"),
    ]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._stream_client: Optional["StreamingAgentClient"] = None
        self._stream_client_lock: threading.Lock = threading.Lock()
        self._socket_path: Optional[str] = None
        self._completion_source: Optional[CompletionSource] = None
        self._workers: Dict[str, Worker] = {}
        self._stack_counts: Dict[str, int] = {}
        self._stack_cache: Dict[str, List[dict]] = {}
        self._capture_seq: int = 0
        self._auto_follow: bool = True
        self._log = logging.getLogger(__name__)

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client
        self._socket_path = client.socket_path
        self._completion_source = CompletionSource(client)
        # Defer stream client creation to first use (lazy connection)

    def _connect_own_stream_client(self) -> None:
        """Create a dedicated StreamingAgentClient for streaming observations."""
        if not self._socket_path:
            return
        try:
            from peeka.core.client import StreamingAgentClient

            self._stream_client = StreamingAgentClient(
                self._socket_path,
                activity_reporter=make_activity_reporter(self.app, "stack-stream"),
                client_info=make_client_info(self.app, "stack-stream"),
            )
            result = self._stream_client.connect()
            if result.get("status") != "success":
                self._log.warning("Stack stream client failed: %s", result.get("error"))
                self._stream_client = None
        except Exception as e:
            self._log.warning("Stack stream client error: %s", e)
            self._stream_client = None

    def _ensure_stream_client(self) -> Optional["StreamingAgentClient"]:
        """Lazily create stream client on first use (thread-safe)."""
        if self._stream_client is None:
            with self._stream_client_lock:
                if self._stream_client is None:
                    self._connect_own_stream_client()
        return self._stream_client

    def _get_pattern_completions(self, prefix: str):
        """Get completions for pattern input."""
        if self._completion_source:
            return self._completion_source.get_completions(prefix)
        return []

    async def action_start_stack(self) -> None:
        """Start tracing (triggered by Enter key)."""
        await self._start_stack()

    async def action_stop_stacks(self) -> None:
        """Stop all traces (triggered by Delete key)."""
        await self._stop_all_stacks()

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Static("Pattern:", classes="input-label"),
                AutoCompleteInput(
                    placeholder="module.Class.method",
                    completions_callback=self._get_pattern_completions,
                    id="stack-pattern",
                ),
                Button("Stack", id="stack-btn", variant="success", flat=True),
                Button("Stop", id="stop-stack-btn", variant="error", flat=True),
                id="stack-controls",
                classes="compact-control",
            ),
            Horizontal(
                Vertical(
                    DataTable(id="stack-table"),
                    id="stack-list",
                    classes="panel panel--stream",
                ),
                Vertical(
                    Tree("Stack", id="stack-tree"),
                    id="stack-panel",
                    classes="panel panel--detail",
                ),
                id="stack-content",
            ),
            id="stack-container",
        )

    def on_mount(self) -> None:
        container = self.query_one("#stack-container", Container)
        container.border_title = "Stack"

        table = self.query_one("#stack-table", DataTable)
        table.add_columns(
            ("#", "#"),
            ("Pattern", "Pattern"),
            ("Frames", "Frames"),
            ("Source", "Source"),
        )
        table.cursor_type = "row"

        stack_list = self.query_one("#stack-list", Vertical)
        stack_list.border_title = "Captures"

        stack_panel = self.query_one("#stack-panel", Vertical)
        stack_panel.border_title = "Call Stack"

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Show the stack trace for the selected capture row."""
        table = event.data_table
        if table.id != "stack-table":
            return

        if event.row_key is None:
            return

        # If user selects a row that is NOT the last one, disable auto-follow.
        # If user selects the last row, re-enable auto-follow.
        row_index = event.cursor_row
        self._auto_follow = (row_index == table.row_count - 1)

        capture_key = str(event.row_key.value)
        frames = self._stack_cache.get(capture_key, [])
        self._render_stack_tree(capture_key, frames)

    def _render_stack_tree(self, capture_key: str, frames: List[dict]) -> None:
        """Render stack frames into the Tree widget."""
        tree = self.query_one("#stack-tree", Tree)
        tree.clear()

        root = tree.root
        root.label = f"Stack Trace {capture_key}"

        for frame in frames:
            filename = frame.get("filename", "")
            lineno = frame.get("lineno", 0)
            function = frame.get("function", "")
            code = frame.get("code", "")

            frame_label = f"{function} @ {filename}:{lineno}"
            frame_node = root.add(frame_label)

            if code:
                frame_node.add_leaf(f"  {code}")

        root.expand()

    def on_unmount(self) -> None:
        """Cancel all workers and disconnect stream client when view is unmounted."""
        for worker in self._workers.values():
            if worker:
                worker.cancel()
        if self._stream_client:
            self._stream_client.disconnect()
            self._stream_client = None

    def cleanup_for_exit(self) -> None:
        """Stop all stack traces and reset instrumented functions before TUI exit."""
        if not self._client:
            return

        for watch_id, worker in list(self._workers.items()):
            if worker:
                worker.cancel()

            try:
                self._client.send_command(
                    {
                        "type": "stack",
                        "action": "stop",
                        "watch_id": watch_id,
                    }
                )
            except Exception:
                pass

        try:
            self._client.send_command(
                {
                    "type": "reset",
                    "action": "reset",
                    "pattern": "*",
                }
            )
        except Exception:
            pass

        self._workers.clear()
        self._stack_counts.clear()
        self._stack_cache.clear()
        self._capture_seq = 0
        if self._stream_client:
            self._stream_client.disconnect()
            self._stream_client = None

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "stack-btn":
            await self._start_stack()
        elif event.button.id == "stop-stack-btn":
            await self._stop_all_stacks()

    async def _start_stack(self) -> None:
        if not self._client:
            self.app.notify("Not connected to agent", severity="error")
            return

        pattern_widget = self.query_one("#stack-pattern")
        if isinstance(pattern_widget, AutoCompleteInput):
            pattern = pattern_widget.value.strip()
        else:
            pattern = pattern_widget.value.strip()  # type: ignore

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
        try:
            response = worker.result
        except Exception as e:
            self.app.notify(f"Connection error: {e}", severity="error")
            return

        if response.get("status") != "success":
            self.app.notify(
                f"Stack failed: {response.get('error', 'Unknown error')}",
                severity="error",
            )
            return

        watch_id = response.get("watch_id", "")

        self._stack_counts[watch_id] = 0

        worker = self.run_worker(
            lambda: self._stream_stacks(watch_id, pattern), thread=True, exclusive=False
        )
        self._workers[watch_id] = worker

        self.app.notify(f"Stack trace started: {pattern}", severity="information")

    def _stream_stacks(self, watch_id: str, pattern: str):
        stream = self._ensure_stream_client() or self._client
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
                self._update_stack_ui, watch_id, count, stack_frames, pattern
            )

    def _update_stack_ui(
        self, watch_id: str, count: int, stack_frames: list, pattern: str
    ) -> None:
        """Add a new capture row and cache its stack frames."""
        self._capture_seq += 1
        capture_key = f"#{self._capture_seq}"

        # Cache the stack frames for this capture
        self._stack_cache[capture_key] = stack_frames

        # Update per-watch count
        self._stack_counts[watch_id] = count

        # Determine top frame as source hint
        if stack_frames:
            top = stack_frames[0]
            source = f"{top.get('function', '?')}:{top.get('lineno', '?')}"
        else:
            source = "-"

        # Add a row per capture
        table = self.query_one("#stack-table", DataTable)
        table.add_row(
            capture_key, pattern, str(len(stack_frames)), source, key=capture_key
        )

        # Only auto-scroll to latest row if user hasn't navigated away
        if self._auto_follow:
            table.move_cursor(row=table.row_count - 1)

    async def _stop_all_stacks(self) -> None:
        if not self._workers:
            self.app.notify("No active stack traces", severity="information")
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
        self._stack_counts.clear()

        self.app.notify("All stack traces stopped", severity="information")
