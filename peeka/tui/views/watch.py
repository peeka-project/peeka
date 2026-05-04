"""
Watch View - Function observation interface.
"""

import json
import logging
import threading
from collections import deque
from typing import TYPE_CHECKING, Any, Deque, Dict, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button, Tree
from textual.widgets.tree import TreeNode
from textual.worker import get_current_worker

from peeka.tui.activity import make_activity_reporter, make_client_info
from peeka.tui.completion import CompletionSource
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient




def _short_repr(value: Any, max_len: int = 35) -> str:
    """Create a short representation of a value for table display."""
    if value is None:
        return "-"
    try:
        s = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        s = repr(value)
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _format_args_summary(params: Any, kwargs: Any, has_target: bool) -> str:
    """Format function args as a short summary string."""
    parts = []

    if isinstance(params, (list, tuple)):
        # Skip 'self' (first arg) if this is an instance method
        start = 1 if has_target and len(params) > 0 else 0
        for arg in params[start : start + 3]:
            parts.append(_short_repr(arg, 25))
        remaining = len(params) - start - 3
        if remaining > 0:
            parts.append(f"…+{remaining}")

    if isinstance(kwargs, dict) and kwargs:
        for k in list(kwargs.keys())[:2]:
            parts.append(f"{k}=…")
        if len(kwargs) > 2:
            parts.append(f"…+{len(kwargs) - 2}")

    return ", ".join(parts) if parts else "-"


def _format_leaf(value: Any, max_len: int = 80) -> str:
    """Format a leaf value for tree display."""
    if value is None:
        return "null"
    if isinstance(value, str):
        if len(value) > max_len:
            return f'"{ value[:max_len] }..."'
        return f'"{value}"'
    try:
        s = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        s = repr(value)
    if len(s) > max_len:
        return s[:max_len - 1] + "…"
    return s


def _populate_value_node(
    node: TreeNode, value: Any, max_depth: int = 4, depth: int = 0
) -> None:
    """Recursively populate a tree node with a JSON-like value."""
    if depth >= max_depth:
        if isinstance(value, dict):
            node.add_leaf(f"{{...}} ({len(value)} keys)")
        elif isinstance(value, (list, tuple)):
            node.add_leaf(f"[...] ({len(value)} items)")
        return

    if isinstance(value, dict):
        for key, val in value.items():
            if isinstance(val, dict):
                child = node.add(f"{key}: {{}} ({len(val)} keys)", expand=False)
                _populate_value_node(child, val, max_depth, depth + 1)
            elif isinstance(val, (list, tuple)):
                child = node.add(f"{key}: [] ({len(val)} items)", expand=False)
                _populate_value_node(child, val, max_depth, depth + 1)
            else:
                node.add_leaf(f"{key}: {_format_leaf(val)}")
    elif isinstance(value, (list, tuple)):
        for idx, val in enumerate(value):
            if isinstance(val, dict):
                child = node.add(f"[{idx}]: {{}} ({len(val)} keys)", expand=False)
                _populate_value_node(child, val, max_depth, depth + 1)
            elif isinstance(val, (list, tuple)):
                child = node.add(f"[{idx}]: [] ({len(val)} items)", expand=False)
                _populate_value_node(child, val, max_depth, depth + 1)
            else:
                node.add_leaf(f"[{idx}]: {_format_leaf(val)}")
    else:
        node.add_leaf(_format_leaf(value))


class WatchView(Container):
    """Watch view for observing function calls."""

    BINDINGS = [
        Binding("enter", "start_watch", "Watch"),
        Binding("delete", "stop_watches", "Stop All"),
    ]

    MAX_OBSERVATIONS = 1000

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._active_watches: Dict[
            str, dict
        ] = {}  # watch_id -> {pattern, count, worker}
        self._completion_source: Optional[CompletionSource] = None
        self._client: Optional["StreamingAgentClient"] = None
        self._stream_client: Optional["StreamingAgentClient"] = None
        self._stream_client_lock: threading.Lock = threading.Lock()
        self._socket_path: Optional[str] = None
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
                activity_reporter=make_activity_reporter(self.app, "watch-stream"),
                client_info=make_client_info(self.app, "watch-stream"),
            )
            result = self._stream_client.connect()
            if result.get("status") != "success":
                self._log.warning(
                    "Watch stream client failed: %s", result.get("error")
                )
                self._stream_client = None
        except Exception as e:
            self._log.warning("Watch stream client error: %s", e)
            self._stream_client = None

    def _ensure_stream_client(self) -> Optional["StreamingAgentClient"]:
        """Lazily create stream client on first use (thread-safe)."""
        if self._stream_client is None:
            with self._stream_client_lock:
                if self._stream_client is None:
                    self._connect_own_stream_client()
        return self._stream_client

    async def action_start_watch(self) -> None:
        """Start watching (triggered by Enter key)."""
        await self._start_watch()

    async def action_stop_watches(self) -> None:
        """Stop all watches (triggered by Delete key)."""
        await self._stop_all_watches()

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
                    id="watch-pattern",
                ),
                Static("Condition:", classes="input-label"),
                Input(
                    placeholder="condition (optional)",
                    id="watch-condition",
                ),
                Button("Watch", id="watch-btn", variant="success", flat=True),
                Button("Stop", id="stop-btn", variant="error", flat=True),
                id="watch-controls",
                classes="compact-control",
            ),
            Horizontal(
                Vertical(
                    DataTable(id="watch-table"),
                    id="watch-list",
                    classes="panel panel--stream",
                ),
                Vertical(
                    Vertical(
                        DataTable(id="observations-table"),
                        id="observations-panel",
                        classes="panel panel--detail",
                    ),
                    Vertical(
                        Tree("Detail", id="observation-detail"),
                        id="observation-detail-panel",
                        classes="panel panel--detail",
                    ),
                    id="watch-detail-column",
                ),
                id="watch-content",
            ),
            id="watch-container",
        )

    def on_mount(self) -> None:
        """Initialize watch table and observations table."""
        container = self.query_one("#watch-container", Container)
        container.border_title = "Watch"

        # Active watches table
        table = self.query_one("#watch-table", DataTable)
        table.add_columns(
            ("ID", "ID"),
            ("Pattern", "Pattern"),
            ("Count", "Count"),
            ("Status", "Status"),
        )
        table.cursor_type = "row"

        watch_list = self.query_one("#watch-list", Vertical)
        watch_list.border_title = "Active Watches"

        # Observations table
        obs_table = self.query_one("#observations-table", DataTable)
        obs_table.add_columns(
            ("#", "#"),
            ("Function", "Function"),
            ("Args", "Args"),
            ("Result", "Result"),
            ("ms", "ms"),
            ("", "Status"),
        )
        obs_table.cursor_type = "row"

        observations_panel = self.query_one("#observations-panel", Vertical)
        observations_panel.border_title = "Observations"

        # Detail panel title
        detail_panel = self.query_one("#observation-detail-panel", Vertical)
        detail_panel.border_title = "Detail"

        detail = self.query_one("#observation-detail", Tree)
        detail.border_title = "Detail"
        detail.show_root = False

    def on_unmount(self) -> None:
        """Cancel all workers and disconnect stream client when view is unmounted."""
        for watch_info in self._active_watches.values():
            worker = watch_info.get("worker")
            if worker:
                worker.cancel()
        if self._stream_client:
            self._stream_client.disconnect()
            self._stream_client = None

    def cleanup_for_exit(self) -> None:
        """Stop all watches and reset instrumented functions before TUI exit."""
        if not self._client:
            return

        for watch_id, watch_info in list(self._active_watches.items()):
            worker = watch_info.get("worker")
            if worker:
                worker.cancel()

            try:
                self._client.send_command(
                    {
                        "type": "watch",
                        "action": "stop",
                        "watch_id": watch_id,
                    }
                )
            except Exception:
                pass

            pattern = watch_info.get("pattern")
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

        self._active_watches.clear()
        if self._stream_client:
            self._stream_client.disconnect()
            self._stream_client = None

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "watch-btn":
            await self._start_watch()
        elif event.button.id == "stop-btn":
            await self._stop_all_watches()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update detail panel when observation row is selected."""
        table = event.data_table
        if table.id != "observations-table":
            return

        if event.row_key is None:
            return

        # If user selects a row that is NOT the last one, disable auto-follow.
        # If user selects the last row, re-enable auto-follow.
        row_index = event.cursor_row
        self._auto_follow = (row_index == table.row_count - 1)

        # Find the observation by row key
        try:
            row_idx = int(str(event.row_key.value))
        except (ValueError, TypeError):
            return

        # Search in our deque for the matching observation
        for obs in self._observations:
            if obs.get("_row_id") == row_idx:
                self._show_detail(obs)
                break

    def _show_detail(self, observation: dict) -> None:
        """Show full observation details as an interactive tree."""
        tree = self.query_one("#observation-detail", Tree)
        tree.clear()

        func_name = observation.get("func_name", "unknown")
        success = observation.get("success", True)
        cost = observation.get("cost", 0)
        location = observation.get("location", "")
        thread_name = observation.get("thread_name", "")
        thread_id = observation.get("thread_id", "")

        # Header node (always expanded)
        status = "✓ Success" if success else "✗ Exception"
        header = tree.root.add(f"{func_name} [{status}]")
        header.add_leaf(f"Location: {location}")
        header.add_leaf(f"Cost: {cost:.3f}ms")
        if thread_name or thread_id:
            header.add_leaf(f"Thread: {thread_name} ({thread_id})")
        header.expand()

        # Target (self)
        target = observation.get("target")
        if target is not None:
            self_node = tree.root.add("self")
            _populate_value_node(self_node, target)
            self_node.expand()

        # Params
        params = observation.get("params", [])
        if params:
            display_params = (
                params[1:] if target is not None and len(params) > 0 else params
            )
            if display_params:
                args_node = tree.root.add(f"args ({len(display_params)})")
                for i, p in enumerate(display_params):
                    if isinstance(p, (dict, list, tuple)):
                        child = args_node.add(f"[{i}]")
                        _populate_value_node(child, p)
                    else:
                        args_node.add_leaf(f"[{i}]: {_format_leaf(p)}")
                args_node.expand()

        # Kwargs
        kwargs = observation.get("kwargs", {})
        if kwargs:
            kwargs_node = tree.root.add(f"kwargs ({len(kwargs)})")
            _populate_value_node(kwargs_node, kwargs)
            kwargs_node.expand()

        # Return / Exception
        if success:
            ret = observation.get("returnObj")
            if ret is not None:
                ret_node = tree.root.add("return")
                if isinstance(ret, (dict, list, tuple)):
                    _populate_value_node(ret_node, ret)
                else:
                    ret_node.add_leaf(_format_leaf(ret))
                ret_node.expand()
        else:
            exp = observation.get("throwExp")
            if exp:
                exc_node = tree.root.add("exception")
                exc_node.add_leaf(str(exp))
                exc_node.expand()

        # Stack
        stack = observation.get("stack")
        if stack:
            stack_node = tree.root.add(f"stack ({len(stack)} frames)")
            for frame in stack:
                fn = frame.get("function", "?")
                fname = frame.get("filename", "?")
                lineno = frame.get("lineno", "?")
                ctx = frame.get("code_context", "")
                frame_node = stack_node.add(f"{fn} ({fname}:{lineno})")
                if ctx:
                    frame_node.add_leaf(ctx)
            # Stack collapsed by default — user can expand if interested

    async def _start_watch(self) -> None:
        """Start a new watch."""
        if not self._client:
            self.app.notify("Not connected to agent", severity="error")
            return

        pattern_widget = self.query_one("#watch-pattern")
        if isinstance(pattern_widget, AutoCompleteInput):
            pattern = pattern_widget.value
        else:
            pattern = pattern_widget.value  # type: ignore

        condition = self.query_one("#watch-condition", Input).value

        if not pattern:
            self.app.notify("Please enter a pattern", severity="warning")
            return

        command = {
            "type": "watch",
            "action": "start",
            "pattern": pattern,
            "depth": 2,
            "times": -1,
            "before": False,
            "exception": False,
            "success": False,
            "finish": True,
            "condition_express": condition if condition else None,
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
            error_msg = response.get("error", "Watch start failed")
            self.app.notify(f"Watch failed: {error_msg}", severity="error")
            return

        watch_id = response.get("watch_id")
        if not watch_id:
            self.app.notify("No watch_id returned", severity="error")
            return

        table = self.query_one("#watch-table", DataTable)
        table.add_row(watch_id[:8], pattern, "0", "Active", key=watch_id)

        self._active_watches[watch_id] = {
            "pattern": pattern,
            "count": 0,
            "worker": None,
        }

        worker = self.run_worker(
            lambda: self._stream_observations(watch_id, pattern),
            thread=True,
            exclusive=False,
        )
        self._active_watches[watch_id]["worker"] = worker

        self.app.notify(f"Watching: {pattern}", severity="information")

        pattern_widget.value = ""
        self.query_one("#watch-condition", Input).value = ""

    def _stream_observations(self, watch_id: str, pattern: str):
        """Stream observations in background thread."""
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

            local_count += 1
            count = local_count

            if watch_id in self._active_watches:
                self._active_watches[watch_id]["count"] = count

            self.app.call_from_thread(
                self._add_observation, watch_id, count, observation
            )

    def _add_observation(self, watch_id: str, count: int, observation: dict) -> None:
        """Add observation to table and update UI (called from main thread)."""
        self._obs_counter += 1
        row_id = self._obs_counter

        # Store observation with row ID
        observation["_row_id"] = row_id
        self._observations.append(observation)

        func_name = observation.get("func_name", "unknown")
        # Shorten module path: __main__.Calculator.add -> Calculator.add
        if "." in func_name:
            parts = func_name.split(".")
            # Drop __main__ or long module paths
            if parts[0] in ("__main__",) or len(parts) > 3:
                func_name = ".".join(parts[-2:]) if len(parts) >= 2 else parts[-1]

        params = observation.get("params", [])
        kwargs = observation.get("kwargs", {})
        has_target = observation.get("target") is not None
        result = observation.get("returnObj")
        success = observation.get("success", True)
        duration = observation.get("cost", 0)

        args_summary = _format_args_summary(params, kwargs, has_target)
        result_summary = (
            _short_repr(result, 40) if success else observation.get("throwExp", "Error")
        )
        if isinstance(result_summary, str) and len(result_summary) > 40:
            result_summary = result_summary[:39] + "…"

        status_icon = Text("✓", style="green") if success else Text("✗", style="red")

        obs_table = self.query_one("#observations-table", DataTable)

        # Evict oldest row if over limit
        if obs_table.row_count >= self.MAX_OBSERVATIONS:
            try:
                first_key = list(obs_table.rows.keys())[0]
                obs_table.remove_row(first_key)
            except (IndexError, KeyError):
                pass

        obs_table.add_row(
            str(row_id),
            func_name,
            args_summary,
            result_summary,
            f"{duration:.2f}",
            status_icon,
            key=str(row_id),
        )

        # Auto-scroll and auto-show detail only if following latest
        if self._auto_follow:
            obs_table.move_cursor(row=obs_table.row_count - 1, animate=False)

        # Update active watches table count
        watch_table = self.query_one("#watch-table", DataTable)
        try:
            watch_table.update_cell(watch_id, "Count", str(count))
        except Exception:
            pass

        # Auto-show detail for latest observation only if following
        if self._auto_follow:
            self._show_detail(observation)

    async def _stop_all_watches(self) -> None:
        """Stop all active watches."""
        if not self._client:
            self.app.notify("Not connected to agent", severity="error")
            return

        if not self._active_watches:
            self.app.notify("No active watches", severity="information")
            return

        stopped_count = 0

        for watch_id, watch_info in list(self._active_watches.items()):
            stream_worker = watch_info.get("worker")
            if stream_worker:
                stream_worker.cancel()

            try:
                stop_worker = self.run_worker(
                    lambda wid=watch_id: self._client.send_command(
                        {
                            "type": "watch",
                            "action": "stop",
                            "watch_id": wid,
                        }
                    ),
                    thread=True,
                )
                await stop_worker.wait()

                pattern = watch_info.get("pattern")
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

        self._active_watches.clear()

        table = self.query_one("#watch-table", DataTable)
        table.clear()

        self.app.notify(f"Stopped {stopped_count} watch(es)", severity="information")
