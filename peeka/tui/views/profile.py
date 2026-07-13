"""Profile View - session management."""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Static

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
        self._socket_path: Optional[str] = None
        self._log = logging.getLogger(__name__)
        self._sessions: List[Dict[str, Any]] = []
        self._selected_profile_id: Optional[str] = None

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
        self._ensure_own_client()

    def _connect_own_client(self) -> None:
        """Create a dedicated client for ProfileView."""
        if not self._socket_path:
            return
        try:
            from peeka.core.client import StreamingAgentClient

            self._own_client = StreamingAgentClient(
                self._socket_path,
                activity_reporter=make_activity_reporter(self.app, "profile-data"),
                client_info=make_client_info(self.app, "profile-data"),
            )
            result = self._own_client.connect()
            if result.get("status") != "success":
                self._log.warning(
                    "Profile dedicated client failed: %s", result.get("error")
                )
                self._own_client = None
        except Exception as e:
            self._log.warning("Profile dedicated client error: %s", e)
            self._own_client = None

    def _ensure_own_client(self) -> None:
        """Lazily create dedicated client on first use."""
        if self._own_client is None:
            self._connect_own_client()

    async def on_mount(self) -> None:
        """Initialize when view is mounted."""
        table = self.query_one("#profile-table", DataTable)
        table.add_columns("profile_id", "backend", "status", "started_at", "sample_count")
        table.cursor_type = "row"
        self.action_refresh()

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
        """Refresh the profile sessions list."""
        self._ensure_own_client()
        client = self._own_client or self._client
        if not client:
            return

        try:
            response = client.send_command({"type": "profile", "action": "list"})
            if response.get("status") == "success":
                sessions = response.get("sessions", [])
                self._update_table(sessions)
            else:
                error = response.get("error", "Unknown error")
                self.app.notify(f"Refresh failed: {error}", severity="error")
        except Exception as e:
            self.app.notify(f"Refresh error: {e}", severity="error")

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
        """Export the selected profile session."""
        if not self._selected_profile_id:
            return
            
        self._ensure_own_client()
        client = self._own_client or self._client
        if not client:
            return

        try:
            response = client.send_command({
                "type": "profile", 
                "action": "export",
                "profile_id": self._selected_profile_id,
                "format": "json"
            })
            if response.get("status") == "success":
                path = response.get("path", "unknown")
                self.app.notify(f"Exported to {path}", severity="information")
            else:
                error = response.get("error", "Unknown error")
                self.app.notify(f"Export failed: {error}", severity="error")
        except Exception as e:
            self.app.notify(f"Export error: {e}", severity="error")
