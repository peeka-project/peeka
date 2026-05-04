"""
Thread View - Thread listing and stack inspection interface.
Similar to Arthas 'thread' command and py-spy thread listing.
"""

import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Static, DataTable, Tree
from textual.worker import Worker, get_current_worker

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


# State badge styling
_STATE_BADGES = {
    "RUNNABLE": "[green]RUNNABLE[/]",
    "WAITING": "[yellow]WAITING[/]",
    "TIMED_WAITING": "[cyan]TIMED_WAIT[/]",
    "UNKNOWN": "[dim]UNKNOWN[/]",
}


class ThreadView(Container):
    """Thread view for listing threads and inspecting their stacks."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._refresh_worker: Optional[Worker] = None
        self._threads_cache: List[Dict[str, Any]] = []
        self._mounted = False
        self._active = True

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client
        if self._mounted and self._active:
            self._refresh_threads()
            self._start_refresh_worker()

    def set_active(self, active: bool) -> None:
        """Pause periodic refresh while the thread tab is hidden.

        Args:
            active: Whether this view is currently visible.
        """
        if self._active == active:
            return

        self._active = active
        if active:
            if self._mounted and self._client:
                self._refresh_threads()
                self._start_refresh_worker()
        else:
            self._stop_refresh_worker()

    def compose(self) -> ComposeResult:
        yield Horizontal(
            Static(
                "Threads: - total | - runnable | - waiting | - timed | - daemon",
                id="thread-summary",
            ),
            Static("", classes="spacer"),
            Button("Refresh", id="thread-refresh-btn", variant="primary", flat=True),
            id="thread-controls",
            classes="compact-control",
        )
        yield Container(
            Horizontal(
                Vertical(
                    DataTable(id="threads-table"),
                    id="threads-list",
                    classes="panel",
                ),
                Vertical(
                    Tree("Stack Trace", id="thread-stack-tree"),
                    id="thread-stack-panel",
                    classes="panel",
                ),
                id="thread-content",
            ),
            id="thread-container",
        )

    def on_mount(self) -> None:
        container = self.query_one("#thread-container", Container)
        container.border_title = "Threads"

        table = self.query_one("#threads-table", DataTable)
        table.add_columns("TID", "Name", "State", "Daemon", "Depth", "Top Frame")
        table.cursor_type = "row"

        threads_list = self.query_one("#threads-list", Vertical)
        threads_list.border_title = "Thread List"

        stack_panel = self.query_one("#thread-stack-panel", Vertical)
        stack_panel.border_title = "Stack Trace"

        self._mounted = True
        # If set_client was called before on_mount, start fetching now
        if self._active and self._client:
            self._refresh_threads()
            self._start_refresh_worker()

    def on_unmount(self) -> None:
        self._stop_refresh_worker()

    def action_refresh(self) -> None:
        """Refresh thread list."""
        if self._client:
            self._refresh_threads()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "thread-refresh-btn":
            self.action_refresh()
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """When a thread row is highlighted, fetch and show its stack trace."""
        if event.row_key is None:
            return

        tid_str = str(event.row_key.value)
        if not tid_str:
            return

        try:
            tid = int(tid_str)
        except (ValueError, TypeError):
            return

        self._fetch_thread_detail(tid)

    def _start_refresh_worker(self) -> None:
        """Start background periodic refresh of thread list."""
        if not self._active or not self._client or self._refresh_worker:
            return

        self._refresh_worker = self.run_worker(
            lambda: self._periodic_refresh(), thread=True, exclusive=False
        )

    def _stop_refresh_worker(self) -> None:
        """Cancel the periodic thread refresh worker."""
        if self._refresh_worker:
            self._refresh_worker.cancel()
            self._refresh_worker = None

    def _periodic_refresh(self) -> None:
        """Periodically refresh thread data every 3 seconds."""
        worker = get_current_worker()

        while not worker.is_cancelled:
            for _ in range(30):
                if worker.is_cancelled:
                    return
                time.sleep(0.1)

            if self._active:
                self.app.call_from_thread(self._refresh_threads)

    def _refresh_threads(self) -> None:
        """Launch worker to fetch thread list from agent."""
        if not self._active or not self._client:
            return

        def worker_fn():
            response = self._client.send_command(
                {
                    "type": "thread",
                    "action": "list",
                }
            )
            if self._active and response.get("status") == "success":
                self.app.call_from_thread(self._update_threads_ui, response)
            return response

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _update_threads_ui(self, data: Dict[str, Any]) -> None:
        """Update the thread table with fetched data (runs on main thread)."""
        threads = data.get("threads", [])
        self._threads_cache = threads

        table = self.query_one("#threads-table", DataTable)

        # Preserve currently selected row key
        current_key = None
        if table.row_count > 0:
            try:
                current_key = table.coordinate_to_cell_key(
                    table.cursor_coordinate
                ).row_key
            except Exception:
                pass

        table.clear()

        for t in threads:
            tid = t.get("tid", 0)
            name = t.get("name", "?")
            state = t.get("state", "UNKNOWN")
            daemon = t.get("daemon", False)
            stack_depth = t.get("stack_depth", 0)

            # Format top frame
            top_frame = t.get("top_frame")
            if top_frame:
                funcname = top_frame.get("funcname", "?")
                filename = top_frame.get("filename", "?")
                # Shorten filename
                if "/" in filename:
                    filename = filename.rsplit("/", 1)[-1]
                lineno = top_frame.get("lineno", 0)
                top_str = f"{funcname} @ {filename}:{lineno}"
            else:
                top_str = "-"

            state_badge = _STATE_BADGES.get(state, state)
            daemon_str = "✓" if daemon else ""

            table.add_row(
                str(tid),
                name,
                state_badge,
                daemon_str,
                str(stack_depth),
                top_str,
                key=str(tid),
            )

        # Update summary
        total = len(threads)
        runnable = sum(1 for t in threads if t.get("state") == "RUNNABLE")
        waiting = sum(1 for t in threads if t.get("state") == "WAITING")
        timed = sum(1 for t in threads if t.get("state") == "TIMED_WAITING")
        daemon_count = sum(1 for t in threads if t.get("daemon"))

        summary = (
            f"Threads: {total} total | "
            f"[green]{runnable} runnable[/] | "
            f"[yellow]{waiting} waiting[/] | "
            f"[cyan]{timed} timed[/] | "
            f"{daemon_count} daemon"
        )
        self.query_one("#thread-summary", Static).update(summary)

        # Restore selection if possible
        if current_key is not None:
            try:
                row_idx = table.get_row_index(current_key)
                table.move_cursor(row=row_idx)
            except Exception:
                pass

    def _fetch_thread_detail(self, tid: int) -> None:
        """Fetch and display stack trace for a specific thread."""
        if not self._client:
            return

        def worker_fn():
            response = self._client.send_command(
                {
                    "type": "thread",
                    "action": "detail",
                    "tid": tid,
                    "depth": 50,
                }
            )
            if response.get("status") == "success":
                thread_data = response.get("thread", {})
                self.app.call_from_thread(self._update_stack_ui, thread_data)
            return response

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _update_stack_ui(self, thread_data: Dict[str, Any]) -> None:
        """Update the stack tree with thread detail (runs on main thread)."""
        tree = self.query_one("#thread-stack-tree", Tree)
        tree.clear()

        name = thread_data.get("name", "?")
        tid = thread_data.get("tid", 0)
        state = thread_data.get("state", "UNKNOWN")
        stack = thread_data.get("stack", [])

        root = tree.root
        root.label = f"{name} (tid={tid}) [{state}]"

        if not stack:
            root.add_leaf("[dim]No stack frames available[/]")
            root.expand()
            return

        for i, frame in enumerate(stack):
            filename = frame.get("filename", "?")
            lineno = frame.get("lineno", 0)
            funcname = frame.get("funcname", "?")

            # Shorten filename for display
            short_filename = filename
            if "/" in filename:
                short_filename = filename.rsplit("/", 1)[-1]

            frame_label = f"{funcname}() @ {short_filename}:{lineno}"
            frame_node = root.add(frame_label)

            # Show full path as child
            if filename != short_filename:
                frame_node.add_leaf(f"[dim]{filename}[/]")

            # Show local variable names (limited)
            locals_keys = frame.get("locals_keys", [])
            if locals_keys:
                locals_str = ", ".join(locals_keys[:10])
                if len(locals_keys) > 10:
                    locals_str += f" ... (+{len(locals_keys) - 10})"
                frame_node.add_leaf(f"[dim]locals: {locals_str}[/]")

        root.expand()
