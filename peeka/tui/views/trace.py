"""
Trace View - Function call tree tracing interface.
"""

import logging
from typing import TYPE_CHECKING, Optional, Dict, Any, List

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button, Tree
from textual.widgets.tree import TreeNode
from textual.worker import Worker, get_current_worker

from peeka.tui.completion import CompletionSource
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class TraceView(Container):
    """Trace view for visualizing function call trees with timing."""

    BINDINGS = [
        Binding("enter", "start_trace", "Trace"),
        Binding("delete", "stop_traces", "Stop All"),
        Binding("c", "clear_tree", "Clear Tree"),
    ]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._active_traces: dict[
            str, dict
        ] = {}  # trace_id -> {pattern, count, worker}
        self._completion_source: Optional[CompletionSource] = None
        self._client: Optional["StreamingAgentClient"] = None
        self._stream_client: Optional["StreamingAgentClient"] = None
        self._socket_path: Optional[str] = None
        self._current_tree_nodes: Dict[str, TreeNode] = {}  # For tree node management
        self._log = logging.getLogger(__name__)

    def set_client(self, client: "StreamingAgentClient") -> None:
        """Set agent client for commands and completion."""
        self._client = client
        self._socket_path = client.socket_path
        self._completion_source = CompletionSource(client)
        self._connect_own_stream_client()

    def _connect_own_stream_client(self) -> None:
        """Create a dedicated StreamingAgentClient for streaming observations."""
        if not self._socket_path:
            return
        try:
            from peeka.core.client import StreamingAgentClient
            self._stream_client = StreamingAgentClient(self._socket_path)
            result = self._stream_client.connect()
            if result.get("status") != "success":
                self._log.warning(
                    "Trace stream client failed: %s", result.get("error")
                )
                self._stream_client = None
        except Exception as e:
            self._log.warning("Trace stream client error: %s", e)
            self._stream_client = None

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
            Horizontal(
                Static("Pattern:", classes="input-label"),
                AutoCompleteInput(
                    placeholder="module.Class.method",
                    completions_callback=self._get_pattern_completions,
                    id="trace-pattern",
                ),
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
                Button("Trace", id="trace-btn", variant="primary", flat=True),
                Button("Stop", id="stop-trace-btn", variant="error", flat=True),
                Button("Clear", id="clear-trace-btn", variant="warning", flat=True),
                id="trace-controls",
            ),
            Horizontal(
                Vertical(
                    DataTable(id="trace-table"),
                    id="trace-list",
                    classes="panel",
                ),
                Vertical(
                    Tree("Call Tree", id="call-tree"),
                    Static(id="trace-stats", classes="panel"),
                    id="trace-tree-panel",
                    classes="panel",
                ),
                id="trace-content",
            ),
            id="trace-container",
        )

    def on_mount(self) -> None:
        """Initialize trace table and tree."""
        container = self.query_one("#trace-container", Container)
        container.border_title = "Trace"

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

        trace_tree_panel = self.query_one("#trace-tree-panel", Vertical)
        trace_tree_panel.border_title = "Call Tree & Stats"

        # Initialize tree
        tree = self.query_one("#call-tree", Tree)
        tree.show_root = True
        tree.root.expand()

        # Initialize stats display
        stats = self.query_one("#trace-stats", Static)
        stats.update("[dim]No trace data yet[/dim]")

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
        stream = self._stream_client or self._client
        if not stream:
            return

        worker = get_current_worker()
        local_count = 0

        for observation in stream.stream_observations():
            if worker.is_cancelled:
                break

            obs_watch_id = observation.get("watch_id")
            if obs_watch_id and obs_watch_id != watch_id:
                continue

            # Skip non-trace observations (no call_tree)
            if "call_tree" not in observation:
                continue

            local_count += 1
            count = local_count

            if watch_id in self._active_traces:
                self._active_traces[watch_id]["count"] = count

            # Extract trace data
            call_tree = observation.get("call_tree", [])
            total_duration = observation.get("total_duration_ms", 0)
            node_count = observation.get("node_count", 0)
            func_name = observation.get("func_name", "unknown")

            self.app.call_from_thread(
                self._update_trace_display,
                watch_id,
                count,
                func_name,
                call_tree,
                total_duration,
                node_count,
            )

    def _update_trace_display(
        self,
        watch_id: str,
        count: int,
        func_name: str,
        call_tree: List[Dict[str, Any]],
        total_duration: float,
        node_count: int,
    ) -> None:
        """Update UI with new trace observation (called from main thread)."""
        # Update table count
        table = self.query_one("#trace-table", DataTable)
        try:
            table.update_cell(watch_id, "Count", str(count))
        except Exception:
            pass

        # Update tree visualization
        tree = self.query_one("#call-tree", Tree)
        tree.clear()
        tree.root.label = f"[bold cyan]#{count} {func_name}[/bold cyan]"
        tree.root.expand()

        # Build tree from call_tree data
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
