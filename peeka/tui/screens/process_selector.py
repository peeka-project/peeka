"""
Process Selector Screen - List and select Python processes to attach.
"""

import os
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from rich.markup import escape
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer, Input, RichLog, Static

from peeka.core.attach import AttachProgressEvent


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
        self._attach_generation: int = 0
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
        yield Container(
            Static("", id="attach-progress"),
            RichLog(id="attach-log", max_lines=500, wrap=True, highlight=True, markup=True, auto_scroll=True),
            Static("", id="attach-error"),
            id="attach-panel",
            classes="panel",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the process table."""
        attach_panel = self.query_one("#attach-panel")
        attach_panel.styles.display = "none"
        error_widget = self.query_one("#attach-error")
        error_widget.styles.display = "none"
        error_widget.styles.color = "white"
        error_widget.styles.background = "red"
        error_widget.styles.padding = (0, 1)

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
        self._attach_generation += 1
        self._reset_attach_panel()
        self._set_attach_panel_visible(True)
        self._disable_interaction()
        self.notify(f"Attaching to process {pid}...", severity="information")
        self.run_worker(
            self._do_attach(pid), thread=True, exclusive=True
        )

    async def _do_attach(self, pid: int) -> None:
        """Run attachment in worker thread, then push MainScreen on success."""
        import traceback

        from peeka.core.attach import ProcessAttacher

        # Capture generation BEFORE defining callback closure to avoid race
        gen = self._attach_generation

        def _cb(event: AttachProgressEvent) -> None:
            """Thread-safe callback routing progress events to UI."""
            self.app.call_from_thread(self._on_progress, gen, event)

        attacher = ProcessAttacher(pid, suppress_startup_messages=True, progress_callback=_cb)
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
            pass

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

    def _reset_attach_panel(self) -> None:
        """Clear progress / log / error widgets before a new attach attempt."""
        try:
            progress = self.query_one("#attach-progress", Static)
            progress.update("")
            log = self.query_one("#attach-log", RichLog)
            log.clear()
            error = self.query_one("#attach-error", Static)
            error.update("")
            error.styles.display = "none"
        except Exception:
            pass
        self._attach_phase_states.clear()

    def _on_progress(self, gen: int, event: AttachProgressEvent) -> None:
        """Handle progress event from attachment worker. Drops stale generations."""
        if gen != self._attach_generation:
            return

        self._set_attach_panel_visible(True)

        try:
            log = self.query_one("#attach-log", RichLog)
        except Exception:
            return

        ts = time.strftime("%H:%M:%S", time.localtime(event.timestamp or time.time()))
        safe_msg = escape(event.message)

        if event.phase == "attach_log":
            log.write(f"[dim cyan]\\[{ts}][/] {safe_msg}")
            return

        status_icon_map = {
            "running": "⏳",
            "completed": "✓",
            "done": "✓",
            "failed": "✗",
            "logged": "•",
        }
        status_icon = status_icon_map.get(event.status, "?")

        self._attach_phase_states[event.phase] = {
            "status": event.status,
            "message": event.message,
            "elapsed_ms": event.elapsed_ms,
            "icon": status_icon,
            "level": event.level,
        }

        color_map = {
            "running": "yellow",
            "done": "green",
            "completed": "green",
            "failed": "red",
            "logged": "dim",
        }
        color = color_map.get(event.status, "white")

        formatted_msg = f"[dim cyan]\\[{ts}][/] [{color}]{status_icon}[/] \\[{event.phase}] {safe_msg}"
        if event.elapsed_ms is not None:
            formatted_msg += f" [dim]({int(event.elapsed_ms)}ms)[/]"

        log.write(formatted_msg)
        self._render_attach_progress()

    def _render_attach_progress(self) -> None:
        """Render phase states into #attach-progress Static widget."""
        try:
            progress_widget = self.query_one("#attach-progress", Static)
        except Exception:
            return

        if not self._attach_phase_states:
            return

        lines = []
        for phase, state in self._attach_phase_states.items():
            icon = state.get("icon", "?")
            message = state.get("message", phase)
            elapsed = state.get("elapsed_ms")
            suffix = f" ({int(elapsed)}ms)" if elapsed is not None else ""
            lines.append(f"{icon} {phase}: {message}{suffix}")

        progress_widget.update("\n".join(lines))




    def _show_attach_error(self, error_msg: str) -> None:
        """Show attach error as inline red banner in #attach-error widget."""
        self._attaching = False
        self._enable_interaction()
        try:
            error = self.query_one("#attach-error", Static)
            error.update(f"✗ Attach failed: {error_msg}\n(Press Esc to return)")
            error.styles.display = "block"
        except Exception:
            pass

    def _on_attach_success(self, result: Dict[str, Any]) -> None:
        """Called on main thread after successful attachment."""
        self._attaching = False
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
            panel = self.query_one("#attach-panel")
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
        """Context-aware Esc behavior: reset on error, no-op mid-attach, quit when idle.

        States:
        1. Error visible: Esc → reset panel, hide it, return (no quit)
        2. Attach in progress: Esc → no-op (must wait for result)
        3. Idle: Esc → quit (original behavior)
        """
        # State 1: showing attach error → reset panel, return to idle
        try:
            error = self.query_one("#attach-error", Static)
            if error.styles.display == "block":
                self._reset_attach_panel()
                self._set_attach_panel_visible(False)
                return
        except Exception:
            pass

        # State 2: attach in progress → no-op (must wait for result)
        if self._attaching:
            return

        # State 3: idle → quit
        self.app.exit()
