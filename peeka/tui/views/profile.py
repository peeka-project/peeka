"""Profile View - session management."""

import logging
import tempfile
import threading
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Static
from textual.worker import Worker, get_current_worker

from peeka.tui.activity import make_activity_reporter, make_client_info

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class ProfileView(Container):
    """Profile view displays profiling sessions and allows exporting."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, pid: int) -> None:
        """Initialize ProfileView.

        Args:
            pid: Target process ID
        """
        super().__init__(id="profile-container")
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._own_client: Optional["StreamingAgentClient"] = None
        self._client_lock = threading.Lock()
        self._socket_path: Optional[str] = None
        self._log = logging.getLogger(__name__)
        self._sessions: List[Dict[str, Any]] = []
        self._selected_profile_id: Optional[str] = None
        self._last_export_path: Optional[str] = None
        self._refresh_worker: Optional[Worker] = None
        self._export_worker: Optional[Worker] = None

    def compose(self):
        """Compose the Profile view layout."""
        with Vertical():
            yield Horizontal(
                Static("Profile Sessions", id="profile-header"),
                Static("", classes="spacer"),
                Button("Refresh", id="profile-refresh-btn", variant="primary", flat=True),
                Button("Export", id="profile-export-btn", variant="primary", flat=True, disabled=True),
                id="profile-controls",
                classes="compact-control",
            )
            yield DataTable(id="profile-table")

    def set_client(self, client: "StreamingAgentClient") -> None:
        """Set the agent client.

        Args:
            client: Streaming agent client instance
        """
        self._client = client
        self._socket_path = client.socket_path

    def _connect_own_client(self) -> None:
        """Create a dedicated client for ProfileView."""
        if not self._socket_path:
            return
        try:
            from peeka.core.client import StreamingAgentClient

            try:
                app = self.app
            except Exception:
                app = None

            client = StreamingAgentClient(
                self._socket_path,
                activity_reporter=make_activity_reporter(app, "profile-data"),
                client_info=make_client_info(app, "profile-data"),
            )
            result = client.connect()
            if result.get("status") == "success":
                self._own_client = client
            else:
                self._log.warning(
                    "Profile dedicated client failed: %s", result.get("error")
                )
                try:
                    client.disconnect()
                except Exception:
                    pass
                self._own_client = None
        except Exception as e:
            self._log.warning("Profile dedicated client error: %s", e)
            self._own_client = None

    def _ensure_own_client(self) -> Optional["StreamingAgentClient"]:
        """Lazily create dedicated client on first use."""
        with self._client_lock:
            if self._own_client is None:
                self._connect_own_client()
            return self._own_client or self._client

    def _disconnect_own_client(self) -> None:
        """Disconnect and clear the dedicated client if present."""
        with self._client_lock:
            if self._own_client is not None:
                try:
                    self._own_client.disconnect()
                except Exception:
                    pass
                self._own_client = None

    async def on_mount(self) -> None:
        """Initialize when view is mounted."""
        table = self.query_one("#profile-table", DataTable)
        table.add_columns("profile_id", "backend", "status", "started_at", "sample_count")
        table.cursor_type = "row"
        self.action_refresh()

    def on_unmount(self) -> None:
        """Cancel active workers and disconnect dedicated client."""
        if self._refresh_worker:
            self._refresh_worker.cancel()
            self._refresh_worker = None
        if self._export_worker:
            self._export_worker.cancel()
            self._export_worker = None
        self._disconnect_own_client()

    def cleanup_for_exit(self) -> None:
        """Cleanup resources when exiting the TUI."""
        self.on_unmount()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "profile-refresh-btn":
            self.action_refresh()
        elif event.button.id == "profile-export-btn":
            self._export_selected()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle row selection for export."""
        table = self.query_one("#profile-table", DataTable)
        row_key = event.row_key
        # The first column is profile_id
        profile_id = str(table.get_row(row_key)[0])
        self._selected_profile_id = profile_id
        
        export_btn = self.query_one("#profile-export-btn", Button)
        export_btn.disabled = False

    def action_refresh(self) -> None:
        """Refresh the profile sessions list in a background worker."""
        if not self._client and not self._own_client and not self._socket_path:
            return
        if self._refresh_worker:
            self._refresh_worker.cancel()
        self._refresh_worker = self.run_worker(
            self._refresh_worker_fn,
            thread=True,
            exclusive=True,
            group="profile-refresh",
        )

    def _refresh_worker_fn(self) -> None:
        """Fetch profile sessions on a worker thread."""
        worker = get_current_worker()
        client = self._ensure_own_client()
        if not client or worker.is_cancelled:
            return

        try:
            response = client.send_command({"type": "profile", "action": "list"})
            if worker.is_cancelled:
                return
            if response.get("status") == "success":
                sessions = response.get("sessions", [])
                self.app.call_from_thread(self._update_table, sessions)
            else:
                error = response.get("error", "Unknown error")
                self.app.call_from_thread(
                    self.app.notify, f"Refresh failed: {error}", severity="error"
                )
        except Exception as e:
            if not worker.is_cancelled:
                try:
                    self.app.call_from_thread(
                        self.app.notify, f"Refresh error: {e}", severity="error"
                    )
                except Exception:
                    pass

    def _update_table(self, sessions: List[Dict[str, Any]]) -> None:
        """Update the DataTable with sessions."""
        self._sessions = sessions
        table = self.query_one("#profile-table", DataTable)
        table.clear()
        
        for session in sessions:
            table.add_row(
                str(session.get("profile_id", "")),
                str(session.get("backend", "")),
                str(session.get("status", "")),
                str(session.get("started_at", "")),
                str(session.get("sample_count", "")),
            )
            
        self._selected_profile_id = None
        export_btn = self.query_one("#profile-export-btn", Button)
        export_btn.disabled = True

    def _export_selected(self) -> None:
        """Export the selected profile session in a background worker."""
        profile_id = self._selected_profile_id
        if not profile_id:
            return
        if not self._client and not self._own_client and not self._socket_path:
            return
        if self._export_worker:
            self._export_worker.cancel()
        self._export_worker = self.run_worker(
            lambda: self._export_worker_fn(profile_id),
            thread=True,
            exclusive=True,
            group="profile-export",
        )

    def _export_worker_fn(self, profile_id: str) -> None:
        """Export selected profile session on a worker thread."""
        worker = get_current_worker()
        client = self._ensure_own_client()
        if not client or worker.is_cancelled:
            return

        try:
            response = client.send_command({
                "type": "profile",
                "action": "export",
                "profile_id": profile_id,
                "format": "json",
            })
            if worker.is_cancelled:
                return
            if response.get("status") == "success":
                content = response.get("content")
                format_name = str(response.get("format", "json"))
                suffix = f".{format_name}"
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    suffix=suffix,
                    prefix=f"peeka-profile-{profile_id}-",
                    delete=False,
                    encoding="utf-8",
                ) as export_file:
                    export_file.write(str(content) if content is not None else "")
                    path = export_file.name

                def _finish_export() -> None:
                    self._last_export_path = path
                    self.app.notify(
                        f"Exported {format_name} profile to {path}",
                        severity="information",
                    )

                self.app.call_from_thread(_finish_export)
            else:
                error = response.get("error", "Unknown error")
                self.app.call_from_thread(
                    self.app.notify, f"Export failed: {error}", severity="error"
                )
        except Exception as e:
            if not worker.is_cancelled:
                try:
                    self.app.call_from_thread(
                        self.app.notify, f"Export error: {e}", severity="error"
                    )
                except Exception:
                    pass
