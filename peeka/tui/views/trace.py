"""
Trace View - Function call tree tracing interface.
"""

import logging
import threading
from collections import deque
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional

from rich.text import Text
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Static, Tree
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
            str, Dict[str, Any]
        ] = {}  # trace_id -> {pattern, count, worker}
        self._completion_source: Optional[CompletionSource] = None
        self._client: Optional["StreamingAgentClient"] = None
        self._stream_client: Optional["StreamingAgentClient"] = None
        self._stream_client_lock: threading.Lock = threading.Lock()
        self._socket_path: Optional[str] = None
        self._observations: Deque[Dict[str, Any]] = deque(maxlen=self.MAX_OBSERVATIONS)
        self._observations_by_pattern: Dict[str, List[Dict[str, Any]]] = {}
        self._selected_pattern: Optional[str] = None
        self._obs_counter: int = 0
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
        obs_table = self.query_one("#trace-obs-table", DataTable)
        obs_table.clear()
        self._observations_by_pattern.clear()
        self._selected_pattern = None
        stats = self.query_one("#trace-stats", Static)
        stats.update("[dim]No trace data yet[/dim]")

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
                    Static("Min Duration (ms):", classes="input-label"),
                    Input(
                        placeholder="0",
                        id="trace-min-duration",
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
            Vertical(
                DataTable(id="trace-obs-table"),
                id="trace-list",
                classes="panel panel--stream",
            ),
            Horizontal(
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
                id="trace-content",
            ),
            id="trace-container",
        )

    def on_mount(self) -> None:
        """Initialize observations table and tree."""
        container = self.query_one("#trace-container", Container)
        container.border_title = "Trace"

        trace_list = self.query_one("#trace-list", Vertical)
        trace_list.border_title = "Active Traces"

        obs_table = self.query_one("#trace-obs-table", DataTable)
        obs_table.clear(columns=True)
        obs_table.add_columns(
            ("Pattern", "Pattern"),
            ("Status", "Status"),
            ("Count", "Count"),
        )
        obs_table.cursor_type = "row"
        obs_table.border_title = "Active Traces"

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
                    reset_response = self._client.send_command(
                        {
                            "type": "reset",
                            "action": "reset",
                            "pattern": pattern,
                        }
                    )
                    cleanup_summary = (
                        reset_response.get("cleanup_summary", {}) if isinstance(reset_response, dict) else {}
                    )
                    cleanup_errors = (
                        cleanup_summary.get("resource_owners", {}).get("errors", [])
                        + cleanup_summary.get("probe_contexts", {}).get("errors", [])
                        + cleanup_summary.get("injector", {}).get("errors", [])
                    )
                    if cleanup_errors:
                        logging.getLogger(__name__).warning(
                            "[peeka TUI] reset cleanup errors for %s: %s", pattern, cleanup_errors
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
        table = event.data_table
        if table.id == "trace-obs-table":
            if event.row_key is not None:
                pattern = str(event.row_key.value)
                self._selected_pattern = pattern
                self._build_observation_tree(pattern)

    def _build_observation_tree(self, pattern: str) -> None:
        tree = self.query_one("#call-tree", Tree)
        tree.clear()
        tree.root.label = f"[bold cyan]{pattern}[/bold cyan]"
        tree.root.expand()

        observations = self._observations_by_pattern.get(pattern, [])
        if not observations:
            stats = self.query_one("#trace-stats", Static)
            stats.update("[dim]No observations yet[/dim]")
            return

        for idx, obs in enumerate(observations):
            n = obs.get("_count", idx + 1)
            total_ms = obs.get("total_duration_ms", 0.0)
            self_ms = obs.get("self_time_ms", 0.0)
            exc = obs.get("exception")
            obs_label = Text(
                f"obs #{n}  total={total_ms:.3f}ms  self={self_ms:.3f}ms"
            )
            if exc:
                exc_type = _extract_exception_type(exc)
                obs_label.append(f" [throws {exc_type}]", style="red bold")
            obs_node = tree.root.add(obs_label, expand=(idx == 0))
            obs_node.data = {"type": "observation", "obs": obs}

            for callee in obs.get("call_tree", []):
                func = callee.get("function", "unknown")
                count = callee.get("count", 0)
                t_ms = callee.get("total_ms", 0.0)
                mn_ms = callee.get("min_ms", 0.0)
                mx_ms = callee.get("max_ms", 0.0)
                filename = callee.get("filename", "")
                lineno = callee.get("lineno", 0)
                short_fn = filename.split("/")[-1] if filename else ""
                loc = f" @ {short_fn}:{lineno}" if short_fn else ""
                exc = callee.get("exception")
                callee_label = Text(
                    f"{func}  count={count}  total={t_ms:.3f}ms"
                    f"  min={mn_ms:.3f}ms  max={mx_ms:.3f}ms{loc}"
                )
                if exc:
                    exc_type = _extract_exception_type(exc)
                    callee_label.append(f" [throws {exc_type}]", style="red bold")
                callee_node = obs_node.add(callee_label)
                callee_node.data = {"type": "callee", "callee": callee, "obs": obs}

        if observations:
            self._update_stats_panel(observations[0])

    def on_tree_node_highlighted(
        self, event: Tree.NodeHighlighted[Any]
    ) -> None:
        node = event.node
        if node.data is None:
            return
        data = node.data
        if data.get("type") == "observation":
            obs = data["obs"]
        elif data.get("type") == "callee":
            obs = data["obs"]  # show parent observation's stats
        else:
            return
        self._update_stats_panel(obs)

    def _update_stats_panel(self, obs: Dict[str, Any]) -> None:
        stats = self.query_one("#trace-stats", Static)
        n = obs.get("_count", "?")
        func_name = obs.get("func_name", "unknown")
        total_ms = obs.get("total_duration_ms", 0.0)
        self_ms = obs.get("self_time_ms", 0.0)
        callee_count = obs.get("callee_count", 0)
        node_count = obs.get("node_count", 0)
        stats_text = (
            f"[cyan]Observation #{n}[/cyan]\n"
            f"total_duration_ms: {total_ms:.3f}\n"
            f"self_time_ms: {self_ms:.3f}\n"
            f"callee_count: {callee_count}\n"
            f"node_count: {node_count}\n"
            f"Function: [yellow]{func_name}[/yellow]"
        )
        exception = obs.get("exception")
        if isinstance(exception, dict):
            exc_type = _extract_exception_type(exception)
            exc_message = exception.get("message", exception.get("msg", ""))
            stats_text += (
                f"\nException: [red bold]{exc_type}: {exc_message}[/red bold]"
            )
        else:
            stats_text += "\nException: [green]-[/green]"
        runtime_meta = obs.get("runtime_meta")
        if isinstance(runtime_meta, dict):
            trace_meta = runtime_meta.get("trace")
            if isinstance(trace_meta, dict):
                backend = trace_meta.get("effective_backend", "unknown")
                gevent_state = (
                    "patched" if trace_meta.get("gevent_patched_now") else "none"
                )
            else:
                backend = runtime_meta.get("backend", "unknown")
                gevent_state = runtime_meta.get("gevent_state", "unknown")
            stats_text += f"\nBackend: {backend}  Gevent: {gevent_state}"
        else:
            stats_text += "\nBackend: profiler (full)"
        stats.update(stats_text)

    async def _start_trace(self) -> None:
        """Start a new trace."""
        if not self._client:
            self.app.notify("Not connected to agent", severity="error")
            return

        pattern_widget = self.query_one("#trace-pattern", AutoCompleteInput)
        pattern = pattern_widget.value

        min_duration_input = self.query_one("#trace-min-duration", Input).value
        condition = self.query_one("#trace-condition", Input).value

        if not pattern:
            self.app.notify("Please enter a pattern", severity="warning")
            return

        # Parse min_duration, default to 0
        try:
            min_duration_ms = int(min_duration_input) if min_duration_input.strip() else 0
            if min_duration_ms < 0:
                self.app.notify("Min duration must be >= 0", severity="warning")
                return
        except ValueError:
            self.app.notify("Invalid min duration value", severity="warning")
            return

        command = {
            "type": "trace",
            "action": "start",
            "pattern": pattern,
            "min_duration": min_duration_ms,
            "times": -1,  # Unlimited observations
            "skip_builtin": True,
            "condition_express": condition if condition else None,
        }

        client = self._client
        worker = self.run_worker(lambda: client.send_command(command), thread=True)
        await worker.wait()
        response = worker.result or {}

        if response.get("status") != "success":
            error_msg = response.get("error", "Trace start failed")
            self.app.notify(f"Trace failed: {error_msg}", severity="error")
            return

        watch_id = response.get("watch_id")
        if not watch_id:
            self.app.notify("No watch_id returned", severity="error")
            return

        obs_table = self.query_one("#trace-obs-table", DataTable)
        try:
            obs_table.update_cell(pattern, "Status", "Running")
        except Exception:
            obs_table.add_row(pattern, "Running", "0", key=pattern)
        self._observations_by_pattern.setdefault(pattern, [])

        self._active_traces[watch_id] = {
            "pattern": pattern,
            "count": 0,
            "worker": None,
        }

        worker = self.run_worker(
            lambda: self._stream_trace_observations(watch_id, pattern),
            thread=True,
            exclusive=False,
        )
        self._active_traces[watch_id]["worker"] = worker

        self.app.notify(
            f"Tracing: {pattern} (min_duration={min_duration_ms}ms)",
            severity="information",
        )

        # Clear inputs
        pattern_widget.value = ""
        self.query_one("#trace-min-duration", Input).value = ""
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
        self, watch_id: str, count: int, observation: Dict[str, Any]
    ) -> None:
        """Store observation and update UI (called from main thread)."""
        self._obs_counter += 1
        row_id = self._obs_counter

        observation["_row_id"] = row_id
        observation["_count"] = count
        self._observations.append(observation)

        pattern = None
        for wid, info in self._active_traces.items():
            if wid == watch_id:
                pattern = info.get("pattern")
                break

        if pattern:
            obs_list = self._observations_by_pattern.setdefault(pattern, [])
            obs_list.insert(0, observation)
            if len(obs_list) > 100:
                obs_list.pop()

            obs_table = self.query_one("#trace-obs-table", DataTable)
            try:
                obs_table.update_cell(pattern, "Count", str(len(obs_list)))
            except Exception:
                pass

            if self._selected_pattern == pattern:
                self._build_observation_tree(pattern)

    async def _stop_all_traces(self) -> None:
        """Stop all active traces."""
        if not self._client:
            self.app.notify("Not connected to agent", severity="error")
            return

        if not self._active_traces:
            self.app.notify("No active traces", severity="information")
            return

        stopped_count = 0

        client = self._client
        for watch_id, trace_info in list(self._active_traces.items()):
            stream_worker = trace_info.get("worker")
            if stream_worker:
                stream_worker.cancel()

            try:
                stop_worker = self.run_worker(
                    lambda wid=watch_id: client.send_command(  # type: ignore[union-attr]
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
                        lambda pat=pattern: client.send_command(  # type: ignore[union-attr]
                            {
                                "type": "reset",
                                "action": "reset",
                                "pattern": pat,
                            }
                        ),
                        thread=True,
                    )
                    await reset_worker.wait()

                    obs_table = self.query_one("#trace-obs-table", DataTable)
                    try:
                        obs_table.update_cell(pattern, "Status", "Stopped")
                    except Exception:
                        pass

                stopped_count += 1
            except Exception:
                pass

        self._active_traces.clear()

        self.app.notify(f"Stopped {stopped_count} trace(s)", severity="information")


def _extract_exception_type(exc: Any) -> str:
    if isinstance(exc, dict):
        for key in ("type", "class", "__class__"):
            val = exc.get(key)
            if val:
                return str(val).split(".")[-1]
    return "Exception"
