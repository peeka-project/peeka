"""
Watch View - Function observation interface.
"""

from typing import TYPE_CHECKING, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button, RichLog
from textual.worker import Worker, get_current_worker

from peeka.tui.completion import CompletionSource
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class WatchView(Container):
    """Watch view for observing function calls."""

    BINDINGS = [
        Binding("enter", "start_watch", "Watch"),
        Binding("delete", "stop_watches", "Stop All"),
    ]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._active_watches: dict[
            str, dict
        ] = {}  # watch_id -> {pattern, count, worker}
        self._completion_source: Optional[CompletionSource] = None
        self._client: Optional["StreamingAgentClient"] = None
        self._stream_client: Optional["StreamingAgentClient"] = None

    def set_client(self, client: "StreamingAgentClient") -> None:
        """Set agent client for commands and completion."""
        self._client = client
        self._completion_source = CompletionSource(client)

    def set_stream_client(self, client: "StreamingAgentClient") -> None:
        self._stream_client = client

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
                Button("Watch", id="watch-btn", variant="primary"),
                Button("Stop", id="stop-btn", variant="error"),
                id="watch-controls",
            ),
            Horizontal(
                Vertical(
                    DataTable(id="watch-table"),
                    id="watch-list",
                    classes="panel",
                ),
                Vertical(
                    RichLog(id="observations-log", highlight=True, markup=True),
                    id="observations-panel",
                    classes="panel",
                ),
                id="watch-content",
            ),
            id="watch-container",
        )

    def on_mount(self) -> None:
        """Initialize watch table."""
        table = self.query_one("#watch-table", DataTable)
        table.add_columns("ID", "Pattern", "Count", "Status")
        table.cursor_type = "row"

        watch_list = self.query_one("#watch-list", Vertical)
        watch_list.border_title = "Active Watches"

        observations_panel = self.query_one("#observations-panel", Vertical)
        observations_panel.border_title = "Observations"

    def on_unmount(self) -> None:
        """Cancel all workers when view is unmounted."""
        for watch_info in self._active_watches.values():
            worker = watch_info.get("worker")
            if worker:
                worker.cancel()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "watch-btn":
            await self._start_watch()
        elif event.button.id == "stop-btn":
            await self._stop_all_watches()

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
        response = worker.result

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

            local_count += 1
            count = local_count

            if watch_id in self._active_watches:
                self._active_watches[watch_id]["count"] = count

            func_name = observation.get("func_name", "unknown")
            # Agent sends "params" (list), "returnObj", and "cost" (ms)
            args = observation.get("params", [])
            kwargs = observation.get("kwargs", {})
            result = observation.get("returnObj", None)
            duration = observation.get("cost", 0)
            success = observation.get("success", True)

            args_str = ", ".join(repr(a) for a in args[:3])
            if len(args) > 3:
                args_str += ", ..."
            if kwargs:
                kwargs_preview = ", ".join(f"{k}=..." for k in list(kwargs.keys())[:2])
                if args_str:
                    args_str += ", " + kwargs_preview
                else:
                    args_str = kwargs_preview

            if success:
                result_str = f"[green]→ {repr(result)[:50]}[/green]"
            else:
                result_str = f"[red]✗ {repr(result)[:50]}[/red]"

            log_line = (
                f"[cyan]#{count}[/cyan] "
                f"[yellow]{func_name}[/yellow]({args_str}) "
                f"{result_str} "
                f"[dim][{duration:.2f}ms][/dim]"
            )

            self.app.call_from_thread(
                self._update_observation, watch_id, count, log_line
            )

    def _update_observation(self, watch_id: str, count: int, log_line: str) -> None:
        """Update UI with new observation (called from main thread)."""
        log = self.query_one("#observations-log", RichLog)
        log.write(log_line)

        table = self.query_one("#watch-table", DataTable)
        try:
            table.update_cell(watch_id, "Count", str(count))
        except Exception:
            pass

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
