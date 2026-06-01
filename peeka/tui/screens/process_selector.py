"""
Process Selector Screen - List and select Python processes to attach.
"""

import time
from typing import Any, Dict, List, Optional

from rich.markup import escape
from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import DataTable, Header, Footer, Input, RichLog, Static

from peeka.core.attach import AttachProgressEvent
from peeka.core.targets import discover_targets
from peeka.tui.activity import (
    attach_activity_metadata,
    format_attach_activity,
    format_attach_summary,
)


class ProcessSelectorScreen(Screen):
    """Screen for selecting a Python process to attach to."""

    _attaching: bool = False
    MIN_WIDTH: int = 80

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
        Binding("enter", "select", "Select"),
        Binding("y", "copy_attach_log", "Copy Attach Log"),
        Binding("escape", "quit_app", "Quit", priority=True),
        Binding("q", "quit_app", "Quit"),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._attach_generation: int = 0
        self._attach_phase_states: Dict[str, Dict[str, Any]] = {}
        self._attach_activity_events: List[AttachProgressEvent] = []

    def compose(self) -> ComposeResult:
        # Design Contract:
        # 1. Six columns visible at >= 140 cols: Target ID, PID, State, Python, Peeka, Created
        # 2. At < 140 cols: Target ID, State, Created remain; others omitted
        # 3. Alive rows use 'green' text, stale use 'dim red', unknown use 'yellow'
        # 4. Stale/unknown rows are unselectable (Enter/select does nothing) and skip focus interaction
        # 5. Refresh key 'r' triggers reload; status bar shows "Refreshed N targets at HH:MM:SS"
        yield Header()
        selector = Container(
            Input(placeholder="Filter by Target ID, PID, or State...", id="filter", classes="compact-control"),
            DataTable(id="process-table"),
            id="process-selector",
            classes="panel",
        )
        selector.border_title = "Select Process"
        yield selector
        yield Container(
            Static("", id="attach-progress", classes="panel"),
            RichLog(id="attach-log", max_lines=500, wrap=True, highlight=True, markup=True, auto_scroll=True, classes="panel"),
            Static("", id="attach-error", classes="panel panel--danger"),
            id="attach-panel",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the process table."""
        attach_panel = self.query_one("#attach-panel")
        attach_panel.styles.display = "none"
        error_widget = self.query_one("#attach-error")
        error_widget.styles.display = "none"

        # Set border titles for attach panel sections
        progress = self.query_one("#attach-progress", Static)
        progress.border_title = "Progress"
        log = self.query_one("#attach-log", RichLog)
        log.border_title = "Attach Log"

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
        table.cursor_type = "row"
        self._setup_columns(table, self.app.size.width)
        self.refresh_processes()

    def on_resize(self, event: events.Resize) -> None:
        """Handle resize to adjust columns dynamically."""
        table = self.query_one("#process-table", DataTable)
        is_wide = event.size.width >= 140
        current_cols = len(table.columns)
        if (is_wide and current_cols < 6) or (not is_wide and current_cols > 3):
            self._setup_columns(table, event.size.width)
            self.refresh_processes()

    def _setup_columns(self, table: DataTable, width: int) -> None:
        """Setup columns based on available width."""
        table.clear(columns=True)
        if width >= 140:
            table.add_columns("Target ID", "PID", "State", "Python", "Peeka", "Created")
        else:
            table.add_columns("Target ID", "State", "Created")

    def _format_relative_time(self, ts: float) -> str:
        """Format epoch seconds as relative time string."""
        diff = max(0, int(time.time() - ts))
        if diff < 60:
            return f"{diff}s ago"
        elif diff < 3600:
            return f"{diff // 60}m ago"
        elif diff < 86400:
            return f"{diff // 3600}h ago"
        return f"{diff // 86400}d ago"

    def refresh_processes(self) -> None:
        """Refresh the list of discovered targets."""
        table = self.query_one("#process-table", DataTable)
        table.clear()
        
        filter_input = self.query_one("#filter", Input)
        filter_text = filter_input.value.lower()
        targets = discover_targets()
        
        is_wide = len(table.columns) == 6
        for target in targets:
            pid_str = str(target.pid)
            state_str = target.state
            
            # Filtering
            if filter_text and filter_text not in target.target_id.lower() and filter_text not in pid_str and filter_text not in state_str.lower():
                continue

            created_str = self._format_relative_time(target.created_at)

            # Row styling
            style = ""
            if target.state == "alive":
                style = "green"
            elif target.state in ("stale", "failed", "detached"):
                style = "dim red"
            else:
                style = "yellow"

            def _fmt(text: str) -> str:
                return f"[{style}]{escape(text)}[/]" if style else escape(text)

            if is_wide:
                table.add_row(
                    _fmt(target.target_id),
                    _fmt(pid_str),
                    _fmt(state_str),
                    _fmt(target.python_version or "-"),
                    _fmt(target.peeka_version or "-"),
                    _fmt(created_str),
                    key=target.target_id
                )
            else:
                table.add_row(
                    _fmt(target.target_id),
                    _fmt(state_str),
                    _fmt(created_str),
                    key=target.target_id
                )

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter targets based on input."""
        self.refresh_processes()

    def action_refresh(self) -> None:
        """Refresh process list."""
        self.app.call_from_thread(self.refresh_processes)
        targets = discover_targets()
        ts = time.strftime("%H:%M:%S", time.localtime())
        self.notify(f"Refreshed {len(targets)} targets at {ts}", severity="information")

    def action_select(self) -> None:
        """Select the highlighted process."""
        import re
        
        table = self.query_one("#process-table", DataTable)
        if table.cursor_row is not None and len(table.rows) > 0:
            row_key = table.coordinate_to_cell_key((table.cursor_row, 0)).row_key
            row = table.get_row(row_key)
            is_wide = len(table.columns) == 6
            state_idx = 2 if is_wide else 1
            
            state_str = str(row[state_idx])
            if "alive" not in state_str:
                return

            if is_wide:
                pid_str = re.sub(r"\[.*?\]", "", str(row[1]))
                try:
                    pid = int(pid_str)
                    self._attach_to_process(pid)
                except ValueError:
                    pass
            else:
                target_id_str = re.sub(r"\[.*?\]", "", str(row[0]))
                target = next((t for t in discover_targets() if t.target_id == target_id_str), None)
                if target:
                    self._attach_to_process(target.pid)

    def action_copy_attach_log(self) -> None:
        """Copy the current attach log to the terminal clipboard."""
        text = self._attach_log_text()
        if not text:
            self.notify("Attach Log is empty", severity="warning")
            return

        try:
            self.app.copy_to_clipboard(text)
        except Exception as e:
            self.notify(f"Failed to copy Attach Log: {e}", severity="error")
            return

        self.notify("Attach Log copied", severity="information")

    def _attach_log_text(self) -> str:
        """Return visible attach log lines as plain text."""
        log = self.query_one("#attach-log", RichLog)
        lines = []
        for line in log.lines:
            text = getattr(line, "text", str(line)).rstrip()
            if text.strip():
                lines.append(text)
        return "\n".join(lines)

    def _attach_to_process(self, pid: int) -> None:
        """Attach to the selected process in a background worker."""
        if getattr(self, "_attaching", False):
            return
        self._attaching = True
        self._attach_generation += 1
        self._reset_attach_panel()
        self._set_attach_panel_visible(True)
        ts = time.strftime("%H:%M:%S", time.localtime())
        log = self.query_one("#attach-log", RichLog)
        log.write(f"[dim cyan]\\[{ts}][/] Attaching to process {pid}...")
        self._disable_interaction()
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
                real_error = attacher.get_last_error()
                error_details = f"Error: {real_error}\n\n" if real_error else ""
                error_message = (
                    f"Failed to attach to process {pid}\n\n"
                    f"{error_details}"
                    "This could be due to:\n"
                    "- Permission issues (ptrace_scope)\n"
                    "- Python version mismatch\n"
                    "- GDB/LLDB not available\n"
                    "- Process already has an agent attached"
                )
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
        self._attach_activity_events.clear()

    def _on_progress(self, gen: int, event: AttachProgressEvent) -> None:
        """Handle progress event from attachment worker. Drops stale generations."""
        if gen != self._attach_generation:
            return

        self._attach_activity_events.append(event)
        self._record_attach_activity(event)
        self._set_attach_panel_visible(True)

        try:
            log = self.query_one("#attach-log", RichLog)
        except Exception:
            return

        ts = time.strftime("%H:%M:%S", time.localtime(event.timestamp or time.time()))
        activity_entry = format_attach_activity(event)
        if event.phase == "attach_log":
            log_message = event.message
        else:
            log_message = activity_entry[1] if activity_entry else event.message
        safe_msg = escape(log_message)

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

        formatted_msg = f"[dim cyan]\\[{ts}][/] [{color}]{status_icon}[/] {safe_msg}"

        log.write(formatted_msg)
        self._render_attach_progress()

    def _record_attach_activity(self, event: AttachProgressEvent) -> None:
        """Mirror attach progress into the app-level client activity buffer."""
        recorder = getattr(self.app, "record_client_activity", None)
        if not callable(recorder):
            return

        formatted = format_attach_activity(event)
        if formatted is not None:
            level, message = formatted
            recorder(
                level,
                message,
                source="attach",
                timestamp=event.timestamp,
                metadata=attach_activity_metadata(event),
            )

        summary = format_attach_summary(self._attach_activity_events)
        if summary is not None:
            level, message, metadata = summary
            recorder(
                level,
                message,
                source="attach",
                timestamp=event.timestamp,
                metadata=metadata,
            )

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
        self.action_select()

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
