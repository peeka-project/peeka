"""
Process Selector Screen - List and select Python processes to attach.
"""

import subprocess
from typing import Any, Dict, List, Optional, Tuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer, Input, Static


class ProcessSelectorScreen(Screen):
    """Screen for selecting a Python process to attach to."""

    _attaching: bool = False
    MIN_WIDTH: int = 80

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "select", "Select"),
        Binding("escape", "quit_app", "Quit", priority=True),
        Binding("q", "quit_app", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        selector = Container(
            Input(placeholder="Filter by PID or command...", id="filter"),
            DataTable(id="process-table"),
            id="process-selector",
            classes="panel",
        )
        selector.border_title = "Select Process"
        yield selector
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the process table."""
        if self.app.size.width < self.MIN_WIDTH:
            warning = Static(
                f" ⚠ Terminal width ({self.app.size.width} cols) is below "
                f"recommended {self.MIN_WIDTH}. Some views may not display properly.",
                id="width-warning",
            )
            selector = self.query_one("#process-selector")
            filter_input = self.query_one("#filter")
            selector.mount(warning, before=filter_input)
        table = self.query_one("#process-table", DataTable)
        table.add_columns("PID", "User", "CPU%", "MEM%", "Command")
        table.cursor_type = "row"
        self.refresh_processes()

    def refresh_processes(self) -> None:
        """Refresh the list of Python processes."""
        table = self.query_one("#process-table", DataTable)
        table.clear()

        for proc in self._get_python_processes():
            pid, user, cpu, mem, cmd = proc
            table.add_row(pid, user, cpu, mem, cmd, key=pid)

    def _get_python_processes(self) -> List[Tuple[str, str, str, str, str]]:
        """Get list of running Python processes."""
        processes = []
        try:
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines()[1:]:
                parts = line.split(None, 10)
                if len(parts) >= 11:
                    user, pid, cpu, mem = parts[0], parts[1], parts[2], parts[3]
                    cmd = parts[10]
                    if "python" in cmd.lower():
                        processes.append((pid, user, cpu, mem, cmd[:60]))
        except Exception:
            pass
        return processes

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter processes based on input."""
        filter_text = event.value.lower()
        table = self.query_one("#process-table", DataTable)
        table.clear()

        for proc in self._get_python_processes():
            pid, user, cpu, mem, cmd = proc
            if filter_text in pid or filter_text in cmd.lower():
                table.add_row(pid, user, cpu, mem, cmd, key=pid)

    def action_refresh(self) -> None:
        """Refresh process list."""
        self.refresh_processes()

    def action_select(self) -> None:
        """Select the highlighted process."""
        table = self.query_one("#process-table", DataTable)
        if table.cursor_row is not None and len(table.rows) > 0:
            row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
            row = table.get_row(row_key)
            pid = int(row[0])
            self._attach_to_process(pid)

    def _attach_to_process(self, pid: int) -> None:
        """Attach to the selected process in a background worker."""
        if getattr(self, "_attaching", False):
            return
        self._attaching = True
        self._disable_interaction()
        self.notify(f"Attaching to process {pid}...", severity="information")
        self.run_worker(
            self._do_attach(pid), thread=True, exclusive=True
        )

    async def _do_attach(self, pid: int) -> None:
        """Run attachment in worker thread, then push MainScreen on success."""
        import asyncio

        from peeka.core.attach import ProcessAttacher

        attacher = ProcessAttacher(pid)
        result: Optional[Dict[str, Any]] = None

        try:
            if attacher.attach():
                result = {
                    "pid": pid,
                    "session_id": attacher.session_id,
                    "socket_path": attacher.get_socket_path(),
                }
            else:
                self.app.call_from_thread(
                    self.notify, f"Failed to attach to process {pid}", severity="error"
                )
        except Exception as e:
            self.app.call_from_thread(
                self.notify, f"Attach error: {e}", severity="error"
            )
        finally:
            # Do NOT call attacher.cleanup() here — sys.remote_exec() is
            # fire-and-forget and the target process may not have read the
            # agent script yet. The script is a small temp file in /tmp and
            # will be cleaned up on reboot or by a future attach session.
            self._attaching = False

        if result:
            self.app.call_from_thread(self._on_attach_success, result)

    def _on_attach_success(self, result: Dict[str, Any]) -> None:
        """Called on main thread after successful attachment."""
        from peeka.tui.screens.main import MainScreen

        self.notify(
            f"Successfully attached to PID {result['pid']}", severity="information"
        )
        self._enable_interaction()
        self.app.push_screen(
            MainScreen(result["pid"], result["session_id"], result["socket_path"])
        )

    def _disable_interaction(self) -> None:
        """Disable table and input to prevent double-attach."""
        try:
            table = self.query_one("#process-table", DataTable)
            table.disabled = True
            filter_input = self.query_one("#filter", Input)
            filter_input.disabled = True
        except Exception:
            pass

    def _enable_interaction(self) -> None:
        """Re-enable table and input after attach completes."""
        try:
            table = self.query_one("#process-table", DataTable)
            table.disabled = False
            filter_input = self.query_one("#filter", Input)
            filter_input.disabled = False
        except Exception:
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection with Enter key."""
        row = self.query_one("#process-table", DataTable).get_row(event.row_key)
        pid = int(row[0])
        self._attach_to_process(pid)

    def action_quit_app(self) -> None:
        """Quit the application."""
        self.app.exit()
