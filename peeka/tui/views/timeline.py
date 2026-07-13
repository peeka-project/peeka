"""Experimental Timeline View."""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Static, DataTable

from peeka.tui.activity import make_activity_reporter, make_client_info

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class TimelineView(Container):
    """Experimental timeline view for profile sessions."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
    ]

    def __init__(self, pid: int) -> None:
        """Initialize TimelineView.

        Args:
            pid: Target process ID
        """
        super().__init__(id="timeline-container")
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._own_client: Optional["StreamingAgentClient"] = None
        self._socket_path: Optional[str] = None
        self._log = logging.getLogger(__name__)

    def compose(self):
        """Compose the Timeline view layout."""
        with Vertical():
            yield Horizontal(
                Static("Timeline (Experimental)", id="timeline-header"),
                Static("", classes="spacer"),
                Button("Refresh", id="timeline-refresh-btn", variant="primary", flat=True),
                id="timeline-controls",
                classes="compact-control",
            )
            yield DataTable(id="timeline-table")

    def set_client(self, client: "StreamingAgentClient") -> None:
        """Set the agent client.

        Args:
            client: Streaming agent client instance
        """
        self._client = client
        self._socket_path = client.socket_path
        self._ensure_own_client()

    def _connect_own_client(self) -> None:
        """Create a dedicated client for TimelineView."""
        if not self._socket_path:
            return
        try:
            from peeka.core.client import StreamingAgentClient

            self._own_client = StreamingAgentClient(
                self._socket_path,
                activity_reporter=make_activity_reporter(self.app, "timeline-data"),
                client_info=make_client_info(self.app, "timeline-data"),
            )
            result = self._own_client.connect()
            if result.get("status") != "success":
                self._log.warning(
                    "Timeline dedicated client failed: %s", result.get("error")
                )
                self._own_client = None
        except Exception as e:
            self._log.warning("Timeline dedicated client error: %s", e)
            self._own_client = None

    def _ensure_own_client(self) -> None:
        """Lazily create dedicated client on first use."""
        if self._own_client is None:
            self._connect_own_client()

    async def on_mount(self) -> None:
        """Initialize when view is mounted."""
        table = self.query_one("#timeline-table", DataTable)
        table.add_columns("Thread ID", "Thread Name", "Event Count")
        table.cursor_type = "row"
        self.action_refresh()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "timeline-refresh-btn":
            self.action_refresh()

    def action_refresh(self) -> None:
        self._ensure_own_client()
        client = self._own_client or self._client
        if not client:
            return

        try:
            response = client.send_command({"type": "profile", "action": "list"})
            if response.get("status") == "success":
                sessions = response.get("sessions", [])
                if not sessions:
                    self._update_table([])
                    self.app.notify("No profile sessions found", severity="information")
                    return
                
                first_id = sessions[0].get("profile_id")
                self._fetch_and_build_timeline(client, first_id)
            else:
                error = response.get("error", "Unknown error")
                self.app.notify(f"Refresh failed: {error}", severity="error")
        except Exception as e:
            self.app.notify(f"Refresh error: {e}", severity="error")

    def _fetch_and_build_timeline(self, client: "StreamingAgentClient", profile_id: str) -> None:
        try:
            response = client.send_command({
                "type": "profile", 
                "action": "export",
                "profile_id": profile_id,
                "format": "json",
                "include_samples": True
            })
            if response.get("status") == "success":
                path = response.get("path")
                import json
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                from peeka.core.profile.models import ProfileSession
                from peeka.core.profile.processors import BuildTimelineProcessor
                
                session_data = {
                    "profile_id": data.get("profile_id", profile_id),
                    "backend": data.get("backend", "sampling"),
                    "config": {"backend": data.get("backend", "sampling")},
                    "samples": data.get("samples", []),
                    "status": "stopped",
                }
                session = ProfileSession.from_dict(session_data)
                processed = BuildTimelineProcessor().process(session)
                
                if processed.timeline:
                    self._update_table(processed.timeline)
                else:
                    self._update_table([])
            else:
                self.app.notify(f"Failed to export session {profile_id}", severity="error")
        except Exception as e:
            self.app.notify(f"Error processing timeline: {e}", severity="error")
            self._update_table([])

    def _update_table(self, lanes: List[Dict[str, Any]]) -> None:
        """Update the DataTable with timeline lanes."""
        table = self.query_one("#timeline-table", DataTable)
        table.clear()
        
        for lane in lanes:
            table.add_row(
                str(lane.get("thread_id", "")),
                str(lane.get("thread_name", "")),
                str(len(lane.get("events", []))),
            )
