"""
Trace View - Function call tree tracing interface.
"""

import logging
import threading
from collections import deque
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Static, Tree
from textual.widgets.tree import TreeNode
from textual.worker import get_current_worker

from peeka.tui.activity import make_activity_reporter, make_client_info
from peeka.tui.completion import CompletionSource
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


_WIDE_TRACE_CONTROLS_MIN_WIDTH = 120


class TraceView(Container):
    """Trace view for visualizing function call trees with timing."""

    BINDINGS = [
        Binding("enter", "start_trace", "Trace"),
        Binding("delete", "stop_traces", "Stop All"),
        Binding("c", "clear_tree", "Clear Tree"),
    ]

    MAX_OBSERVATIONS = 1000

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._active_traces: Dict[
            str, dict
        ] = {}  # trace_id -> {pattern, count, worker}
        self._completion_source: Optional[CompletionSource] = None
        self._client: Optional["StreamingAgentClient"] = None
        self._stream_client: Optional["StreamingAgentClient"] = None
        self._stream_client_lock: threading.Lock = threading.Lock()
        self._socket_path: Optional[str] = None
        self._current_tree_nodes: Dict[str, TreeNode] = {}  # For tree node management
        self._observations: Deque[dict] = deque(maxlen=self.MAX_OBSERVATIONS)
        self._obs_counter: int = 0
        self._auto_follow: bool = True
        self._log = logging.getLogger(__name__)

    def set_client(self, client: "StreamingAgentClient") -> None:
        """Set agent client for commands and completion."""
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
                activity_reporter=make_activity_reporter(self.app, "trace-stream"),
                client_info=make_client_info(self.app, "trace-stream"),
            )
            result = self._stream_client.connect()
            if result.get("status") != "success":
                self._log.warning(
                    "Trace stream client failed: %s", result.get("error")
                )
                self._stream_client = None
        except Exception as e:
            self._log.warning("Trace stream client error: %s", e)
            self._stream_client = None

    def _ensure_stream_client(self) -> Optional["StreamingAgentClient"]:
        """Lazily create stream client on first use (thread-safe)."""
        if self._stream_client is None:
            with self._stream_client_lock:
                if self._stream_client is None:
                    self._connect_own_stream_client()
        return self._stream_client

    async def action_start_trace(self) -> None:
        """Start tracing (triggered by Enter key)."""
        await self._start_trace()

    async def action_stop_traces(self) -> None:
        """Stop all traces (triggered by Delete key)."""
        await self._stop_all_traces()

    def action_clear_tree(self) -> None:
        """Clear the call tree display."""
        tree = self.query_one("#call-tree", Tree)
        tree.clear()
        tree.root.expand()

    def _get_pattern_completions(self, prefix: str):
        """Get completions for pattern input."""
        if self._completion_source:
            return self._completion_source.get_completions(prefix)
        return []

    def compose(self) -> ComposeResult:
        yield Container(
            Container(
                Horizontal(
                    Static("Pattern:", classes="input-label"),
                    AutoCompleteInput(
                        placeholder="module.Class.method",
                        completions_callback=self._get_pattern_completions,
                        id="trace-pattern",
                    ),
                    id="trace-controls",
                    classes="compact-control",
                ),
                Horizontal(
                    Static("Depth:", classes="input-label"),
                    Input(
                        placeholder="3",
                        id="trace-depth",
                    ),
                    Static("Condition:", classes="input-label"),
                    Input(
                        placeholder="cost > 50 (optional)",
                        id="trace-condition",
                    ),
                    id="trace-options-controls",
                    classes="compact-control",
                ),
                Static("", classes="spacer"),
                Horizontal(
                    Button("Trace", id="trace-btn", variant="success", flat=True),
                    Button("Stop", id="stop-trace-btn", variant="error", flat=True),
                    Button("Clear", id="clear-trace-btn", variant="warning", flat=True),
                    id="trace-action-controls",
                    classes="compact-control",
                ),
                id="trace-top-controls",
            ),
            Horizontal(
                Vertical(
                    DataTable(id="trace-table"),
                    DataTable(id="trace-obs-table"),
                    id="trace-list",
                    classes="panel panel--stream",
                ),
                Vertical(
                    Vertical(
                        Tree("Call Tree", id="call-tree"),
                        id="trace-tree-panel",
                        classes="panel panel--detail",
                    ),
                    Vertical(
                        Static(id="trace-stats"),
                        id="trace-stats-panel",
                        classes="panel panel--detail",
                    ),
                    id="trace-detail-column",
                ),
                id="trace-content",
            ),
            id="trace-container",
        )

    def on_mount(self) -> None:
        """Initialize trace table, observations table, and tree."""
        container = self.query_one("#trace-container", Container)
        container.border_title = "Trace"

        # Active traces table
        table = self.query_one("#trace-table", DataTable)
        table.add_columns(
            ("ID", "ID"),
            ("Pattern", "Pattern"),
            ("Count", "Count"),
            ("Status", "Status"),
        )
        table.cursor_type = "row"

        trace_list = self.query_one("#trace-list", Vertical)
        trace_list.border_title = "Active Traces"

        # Observation history table
        obs_table = self.query_one("#trace-obs-table", DataTable)
        obs_table.add_columns(
            ("#", "#"),
            ("Function", "Function"),
            ("Duration", "Duration"),
            ("Nodes", "Nodes"),
        )
        obs_table.cursor_type = "row"
        obs_table.border_title = "Observations"

        # Call tree panel
        trace_tree_panel = self.query_one("#trace-tree-panel", Vertical)
        trace_tree_panel.border_title = "Call Tree"

        stats_panel = self.query_one("#trace-stats-panel", Vertical)
        stats_panel.border_title = "Stats"

        # Initialize tree
        tree = self.query_one("#call-tree", Tree)
        tree.show_root = True
        tree.root.expand()

        # Initialize stats display
        stats = self.query_one("#trace-stats", Static)
        stats.update("[dim]No trace data yet[/dim]")
        self._update_top_controls_layout()

    def on_resize(self, event: events.Resize) -> None:
        """Keep Trace controls compact on narrow terminals."""
        self._update_top_controls_layout(event.size.width)

    def _update_top_controls_layout(self, width: Optional[int] = None) -> None:
        """Use one trace control row on wide terminals and stacked narrow controls.

        Args:
            width: Current app width, or None to read it from the app.
        """
        try:
            top_controls = self.query_one("#trace-top-controls", Container)
        except Exception:
            return

        current_width = width or self.app.size.width
        if current_width >= _WIDE_TRACE_CONTROLS_MIN_WIDTH:
            top_controls.add_class("trace-top-wide")
        else:
            top_controls.remove_class("trace-top-wide")

    def on_unmount(self) -> None:
        """Cancel all workers and disconnect stream client when view is unmounted."""
        for trace_info in self._active_traces.values():
            worker = trace_info.get("worker")
            if worker:
                worker.cancel()
        if self._stream_client:
            self._stream_client.disconnect()
            self._stream_client = None

    def cleanup_for_exit(self) -> None:
        """Stop all traces and reset instrumented functions before TUI exit."""
        if not self._client:
            return

        for watch_id, trace_info in list(self._active_traces.items()):
            worker = trace_info.get("worker")
            if worker:
                worker.cancel()

            try:
                self._client.send_command(
                    {
                        "type": "trace",
                        "action": "stop",
                        "watch_id": watch_id,
                    }
                )
            except Exception:
                pass

            pattern = trace_info.get("pattern")
            if pattern:
                try:
                    self._client.send_command(
                        {
                            "type": "reset",
                            "action": "reset",
                            "pattern": pattern,
                        }
                    )
                except Exception:
                    pass

        self._active_traces.clear()
        if self._stream_client:
            self._stream_client.disconnect()
            self._stream_client = None

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "trace-btn":
            await self._start_trace()
        elif event.button.id == "stop-trace-btn":
            await self._stop_all_traces()
        elif event.button.id == "clear-trace-btn":
            self.action_clear_tree()

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        """Update call tree when an observation row is selected."""
        table = event.data_table
        if table.id != "trace-obs-table":
            return

        if event.row_key is None:
            return

        # If user selects a row that is NOT the last one, disable auto-follow.
        # If user selects the last row, re-enable auto-follow.
        row_index = event.cursor_row
        self._auto_follow = (row_index == table.row_count - 1)

        try:
            row_idx = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return

        # Find the observation by row key
        for obs in self._observations:
            if obs.get("_row_id") == row_idx:
                self._show_trace_detail(obs)
                break

    def _show_trace_detail(self, observation: dict) -> None:
        """Show a stored observation's call tree and stats."""
        call_tree = observation.get("call_tree", [])
        total_duration = observation.get("total_duration_ms", 0)
        node_count = observation.get("node_count", 0)
        func_name = observation.get("func_name", "unknown")
        count = observation.get("_count", 0)

        # Rebuild tree
        tree = self.query_one("#call-tree", Tree)
        tree.clear()
        tree.root.label = f"[bold cyan]#{count} {func_name}[/bold cyan]"
        tree.root.expand()

        if call_tree:
            self._build_call_tree(tree.root, call_tree)

        # Update stats
        stats = self.query_one("#trace-stats", Static)
        stats_text = (
            f"[cyan]Observation #{count}[/cyan]\n"
            f"Total Duration: {self._format_duration(total_duration)}\n"
            f"Node Count: {node_count}\n"
            f"Function: [yellow]{func_name}[/yellow]"
        )
        stats.update(stats_text)

    async def _start_trace(self) -> None:
        """Start a new trace."""
        if not self._client:
            self.app.notify("Not connected to agent", severity="error")
            return

        pattern_widget = self.query_one("#trace-pattern")
        if isinstance(pattern_widget, AutoCompleteInput):
            pattern = pattern_widget.value
        else:
            pattern = pattern_widget.value  # type: ignore

        depth_input = self.query_one("#trace-depth", Input).value
        condition = self.query_one("#trace-condition", Input).value

        if not pattern:
            self.app.notify("Please enter a pattern", severity="warning")
            return

        # Parse depth, default to 3
        try:
            depth = int(depth_input) if depth_input else 3
            if depth < 1 or depth > 5:
                self.app.notify("Depth must be between 1 and 5", severity="warning")
                return
        except ValueError:
            self.app.notify("Invalid depth value", severity="warning")
            return

        command = {
            "type": "trace",
            "action": "start",
            "pattern": pattern,
            "depth": depth,
            "times": -1,  # Unlimited observations
            "skip_builtin": True,
            "condition_express": condition if condition else None,
        }

        worker = self.run_worker(
            lambda: self._client.send_command(command),
            thread=True,
        )
        await worker.wait()
        response = worker.result

        if response.get("status") != "success":
            error_msg = response.get("error", "Trace start failed")
            self.app.notify(f"Trace failed: {error_msg}", severity="error")
            return

        watch_id = response.get("watch_id")
        if not watch_id:
            self.app.notify("No watch_id returned", severity="error")
            return

        table = self.query_one("#trace-table", DataTable)
        table.add_row(watch_id[:8], pattern, "0", "Active", key=watch_id)

        self._active_traces[watch_id] = {
            "pattern": pattern,
            "count": 0,
            "depth": depth,
            "worker": None,
        }

        worker = self.run_worker(
            lambda: self._stream_trace_observations(watch_id, pattern),
            thread=True,
            exclusive=False,
        )
        self._active_traces[watch_id]["worker"] = worker

        self.app.notify(f"Tracing: {pattern} (depth={depth})", severity="information")

        # Clear inputs
        pattern_widget.value = ""
        self.query_one("#trace-depth", Input).value = ""
        self.query_one("#trace-condition", Input).value = ""

    def _stream_trace_observations(self, watch_id: str, pattern: str):
        """Stream trace observations in background thread."""
        stream = self._ensure_stream_client() or self._client
        if not stream:
            return

        worker = get_current_worker()
        local_count = 0

        for observation in stream.stream_observations():
            if worker.is_cancelled:
                break

            obs_watch_id = observation.get("watch_id")
            if obs_watch_id != watch_id:
                continue

            # Skip non-trace observations (no call_tree)
            if "call_tree" not in observation:
                continue

            local_count += 1
            count = local_count

            if watch_id in self._active_traces:
                self._active_traces[watch_id]["count"] = count

            self.app.call_from_thread(
                self._add_trace_observation,
                watch_id,
                count,
                observation,
            )

    def _add_trace_observation(
        self, watch_id: str, count: int, observation: dict
    ) -> None:
        """Store observation and update UI (called from main thread)."""
        self._obs_counter += 1
        row_id = self._obs_counter

        # Store observation with metadata
        observation["_row_id"] = row_id
        observation["_count"] = count
        self._observations.append(observation)

        func_name = observation.get("func_name", "unknown")
        total_duration = observation.get("total_duration_ms", 0)
        node_count = observation.get("node_count", 0)

        # Shorten module path: __main__.Calculator.add -> Calculator.add
        display_name = func_name
        if "." in display_name:
            parts = display_name.split(".")
            if parts[0] in ("__main__",) or len(parts) > 3:
                display_name = (
                    ".".join(parts[-2:]) if len(parts) >= 2 else parts[-1]
                )

        # Update active traces table count
        trace_table = self.query_one("#trace-table", DataTable)
        try:
            trace_table.update_cell(watch_id, "Count", str(count))
        except Exception:
            pass

        # Add row to observation history table
        obs_table = self.query_one("#trace-obs-table", DataTable)

        # Evict oldest row if over limit
        if obs_table.row_count >= self.MAX_OBSERVATIONS:
            try:
                first_key = list(obs_table.rows.keys())[0]
                obs_table.remove_row(first_key)
            except (IndexError, KeyError):
                pass

        obs_table.add_row(
            str(row_id),
            display_name,
            f"{total_duration:.2f}ms",
            str(node_count),
            key=str(row_id),
        )

        # Auto-scroll and auto-show detail only if following latest
        if self._auto_follow:
            obs_table.move_cursor(row=obs_table.row_count - 1, animate=False)
            self._show_trace_detail(observation)

    def _build_call_tree(
        self, parent_node: TreeNode, call_tree: List[Dict[str, Any]]
    ) -> None:
        """Recursively build the tree visualization from call_tree data."""
        if not call_tree:
            return

        for node_data in call_tree:
            depth = node_data.get("depth", 0)
            function = node_data.get("function", "unknown")
            duration_ms = node_data.get("duration_ms", 0)
            filename = node_data.get("filename", "")
            lineno = node_data.get("lineno", 0)
            children = node_data.get("children", [])

            # Format the label with duration and location
            duration_str = self._format_duration(duration_ms)
            location_str = ""
            if filename and lineno:
                # Show only the filename, not full path
                short_filename = filename.split("/")[-1]
                location_str = f" [dim]({short_filename}:{lineno})[/dim]"

            label = f"{duration_str} {function}{location_str}"

            # Add node to tree
            child_node = parent_node.add(label, expand=depth < 2)

            # Recursively add children
            if children:
                self._build_call_tree(child_node, children)

    def _format_duration(self, duration_ms: float) -> str:
        """Format duration with color coding based on time taken."""
        if duration_ms >= 100:
            # Red for slow (>=100ms)
            return f"[red bold]{duration_ms:.2f}ms[/red bold]"
        elif duration_ms >= 10:
            # Yellow for medium (>=10ms)
            return f"[yellow]{duration_ms:.2f}ms[/yellow]"
        else:
            # Green for fast (<10ms)
            return f"[green]{duration_ms:.2f}ms[/green]"

    async def _stop_all_traces(self) -> None:
        """Stop all active traces."""
        if not self._client:
            self.app.notify("Not connected to agent", severity="error")
            return

        if not self._active_traces:
            self.app.notify("No active traces", severity="information")
            return

        stopped_count = 0

        for watch_id, trace_info in list(self._active_traces.items()):
            stream_worker = trace_info.get("worker")
            if stream_worker:
                stream_worker.cancel()

            try:
                stop_worker = self.run_worker(
                    lambda wid=watch_id: self._client.send_command(
                        {
                            "type": "trace",
                            "action": "stop",
                            "watch_id": wid,
                        }
                    ),
                    thread=True,
                )
                await stop_worker.wait()

                pattern = trace_info.get("pattern")
                if pattern:
                    reset_worker = self.run_worker(
                        lambda pat=pattern: self._client.send_command(
                            {
                                "type": "reset",
                                "action": "reset",
                                "pattern": pat,
                            }
                        ),
                        thread=True,
                    )
                    await reset_worker.wait()

                stopped_count += 1
            except Exception:
                pass

        self._active_traces.clear()

        table = self.query_one("#trace-table", DataTable)
        table.clear()

        self.app.notify(f"Stopped {stopped_count} trace(s)", severity="information")
