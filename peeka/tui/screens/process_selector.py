"""
Process Selector Screen - List and select Python processes to attach.
"""

import os
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

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._attach_phase_states: Dict[str, Dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        yield Header()
        selector = Container(
            Input(placeholder="Filter by PID or command...", id="filter", classes="compact-control"),
            DataTable(id="process-table"),
            id="process-selector",
            classes="panel",
        )
        selector.border_title = "Select Process"
        yield selector
        yield Static("Attaching...", id="attach-panel", classes="panel")
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
                    if (
                        "python" in cmd.lower()
                        and self._is_python_process(pid)
                        and not self._is_peeka_process(pid, cmd)
                    ):
                        processes.append((pid, user, cpu, mem, cmd))
        except Exception:
            pass
        return processes

    @staticmethod
    def _is_python_process(pid: str) -> bool:
        """Return True when the PID's real executable is a Python interpreter."""
        exe_path = f"/proc/{pid}/exe"
        try:
            exe_name = os.path.basename(os.readlink(exe_path)).lower()
            return exe_name.startswith("python")
        except OSError:
            # /proc/<pid>/exe is Linux-specific and may be unavailable on other
            # platforms or for short-lived processes. Fall back to cmdline-only
            # filtering in those cases.
            return True

    @staticmethod
    def _is_peeka_process(pid: str, cmd: str) -> bool:
        """Return True for the current Peeka process or explicit Peeka commands."""
        if pid == str(os.getpid()):
            return True

        normalized = cmd.lower()
        peeka_markers = (
            " -m peeka",
            " peeka-cli",
            " peeka-tui",
            "/peeka-cli",
            "/peeka-tui",
        )
        return any(marker in normalized for marker in peeka_markers)

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
        import traceback

        from peeka.core.attach import ProcessAttacher

        attacher = ProcessAttacher(pid, suppress_startup_messages=True)
        result: Optional[Dict[str, Any]] = None
        error_message: Optional[str] = None

        try:
            if attacher.attach():
                socket_path = attacher.get_socket_path()
                connection_error = self._validate_agent_connection(socket_path)
                if connection_error:
                    error_message = (
                        f"Attached to process {pid}, but the agent connection is not usable.\n\n"
                        f"Error: {connection_error}\n\n"
                        "The TUI will stay on the process selector so it does not "
                        "enter a disconnected main screen."
                    )
                else:
                    result = {
                        "pid": pid,
                        "session_id": attacher.session_id,
                        "socket_path": socket_path,
                    }
            else:
                error_message = f"Failed to attach to process {pid}\n\nThis could be due to:\n- Permission issues (ptrace_scope)\n- Python version mismatch\n- GDB/LLDB not available\n- Process already has an agent attached"
        except Exception as e:
            tb = traceback.format_exc()
            error_message = f"Failed to attach to process {pid}\n\nError: {e}\n\nDetails:\n{tb}"
        finally:
            # Do NOT call attacher.cleanup() here — sys.remote_exec() is
            # fire-and-forget and the target process may not have read the
            # agent script yet. The script is a small temp file in /tmp and
            # will be cleaned up on reboot or by a future attach session.
            self._attaching = False

        if result:
            self.app.call_from_thread(self._on_attach_success, result)
        elif error_message:
            self.app.call_from_thread(self._show_attach_error, error_message)

    def _validate_agent_connection(self, socket_path: str) -> Optional[str]:
        """Probe the agent with a client hello before entering MainScreen."""
        from peeka.core.client import StreamingAgentClient
        from peeka.tui.activity import make_client_info

        client = StreamingAgentClient(
            socket_path,
            timeout=2.0,
            client_info=make_client_info(self.app, "process-selector"),
        )
        try:
            result = client.connect()
            if result.get("status") == "success":
                return None
            return str(result.get("error", "unknown connection error"))
        finally:
            client.disconnect()

    def _show_attach_error(self, error_msg: str) -> None:
        """Show detailed attach error in a modal dialog."""
        self._set_attach_panel_visible(False)
        self._enable_interaction()

        # Create a simple error modal
        from textual.containers import Container
        from textual.widgets import Markdown, Button
        from textual.screen import Screen

        class ErrorModal(Screen):
            CSS = """
            ErrorModal {
                align: center middle;
            }

            #error-container {
                background: $surface;
                border: thick $error;
                padding: 1;
                width: 80%;
                height: 80%;
                max-width: 100;
                max-height: 40;
            }

            #error-title {
                background: $error;
                color: white;
                padding: 1;
                text-align: center;
                margin-bottom: 1;
            }

            #error-content {
                height: 80%;
                overflow-y: scroll;
                margin-bottom: 1;
            }

            #error-dismiss {
                align: center bottom;
            }
            """

            def __init__(self, error_msg: str) -> None:
                super().__init__()
                self.error_msg = error_msg

            def compose(self) -> ComposeResult:
                yield Container(
                    Static("⚠️ Attach Failed", id="error-title"),
                    Markdown(self.error_msg, id="error-content"),
                    Container(
                        Button("Dismiss", variant="default", id="error-dismiss"),
                        id="error-controls",
                    ),
                    id="error-container",
                )

            def on_button_pressed(self, event: Button.Pressed) -> None:
                if event.button.id == "error-dismiss":
                    self.dismiss()

        self.app.push_screen(ErrorModal(error_msg))

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

    def _set_attach_panel_visible(self, visible: bool) -> None:
        """Show or hide the attach progress panel."""
        try:
            panel = self.query_one("#attach-panel", Static)
            if visible:
                panel.styles.display = "block"
            else:
                panel.styles.display = "none"
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
