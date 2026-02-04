"""
Process Selector Screen - List and select Python processes to attach.
"""

import os
import subprocess
from typing import List, Tuple

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer, Static, Input


class ProcessSelectorScreen(Screen):
    """Screen for selecting a Python process to attach to."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "select", "Select"),
        Binding("escape", "quit_app", "Quit", priority=True),
        Binding("q", "quit_app", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Container(
            Static("Select a Python process to attach:", id="title"),
            Input(placeholder="Filter by PID or command...", id="filter"),
            DataTable(id="process-table"),
            id="process-selector",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the process table."""
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
        """Attach to the selected process and show main screen."""
        from peeka.tui.screens.main import MainScreen

        self.app.push_screen(MainScreen(pid))

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection with Enter key."""
        row = self.query_one("#process-table", DataTable).get_row(event.row_key)
        pid = int(row[0])
        self._attach_to_process(pid)

    def action_quit_app(self) -> None:
        """Quit the application."""
        self.app.exit()
