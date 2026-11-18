"""Experimental Timeline View."""

import json
import logging
import threading
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Static
from textual.worker import Worker, get_current_worker

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
        self._client_lock = threading.Lock()
        self._socket_path: Optional[str] = None
        self._refresh_worker: Optional[Worker] = None
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

    def _connect_own_client(self) -> None:
        """Create a dedicated client for TimelineView."""
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
                activity_reporter=make_activity_reporter(app, "timeline-data"),
                client_info=make_client_info(app, "timeline-data"),
            )
            result = client.connect()
            if result.get("status") == "success":
                self._own_client = client
            else:
                self._log.warning(
                    "Timeline dedicated client failed: %s", result.get("error")
                )
                try:
                    client.disconnect()
                except Exception:
                    pass
                self._own_client = None
        except Exception as e:
            self._log.warning("Timeline dedicated client error: %s", e)
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
        table = self.query_one("#timeline-table", DataTable)
        table.add_columns("Thread ID", "Thread Name", "Event Count")
        table.cursor_type = "row"
        self.action_refresh()

    def on_unmount(self) -> None:
        """Cancel active workers and disconnect dedicated client."""
        if self._refresh_worker:
            self._refresh_worker.cancel()
            self._refresh_worker = None
        self._disconnect_own_client()

    def cleanup_for_exit(self) -> None:
        """Cleanup resources when exiting the TUI."""
        self.on_unmount()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "timeline-refresh-btn":
            self.action_refresh()

    def action_refresh(self) -> None:
        """Refresh the timeline in a background worker."""
        if not self._client and not self._own_client and not self._socket_path:
            return
        if self._refresh_worker:
            self._refresh_worker.cancel()
        self._refresh_worker = self.run_worker(
            self._refresh_worker_fn,
            thread=True,
            exclusive=True,
            group="timeline-refresh",
        )

    def _refresh_worker_fn(self) -> None:
        """Fetch sessions and build timeline on a worker thread."""
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
                if not sessions:
                    def _notify_empty() -> None:
                        self._update_table([])
                        self.app.notify(
                            "No profile sessions found", severity="information"
                        )

                    self.app.call_from_thread(_notify_empty)
                    return

                first_id = sessions[0].get("profile_id")
                lanes, error_msg = self._build_timeline_from_export(client, first_id)
                if worker.is_cancelled:
                    return

                def _apply_timeline() -> None:
                    if lanes is not None:
                        self._update_table(lanes)
                    if error_msg:
                        self.app.notify(error_msg, severity="error")

                self.app.call_from_thread(_apply_timeline)
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

    def _build_timeline_from_export(
        self, client: "StreamingAgentClient", profile_id: str
    ) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """Export one profile session and build timeline lanes without touching UI."""
        try:
            response = client.send_command({
                "type": "profile",
                "action": "export",
                "profile_id": profile_id,
                "format": "json",
                "include_samples": True,
            })
            if response.get("status") != "success":
                return None, f"Failed to export session {profile_id}"

            content = response.get("content")
            if content is None:
                return [], f"Failed to export session {profile_id}"

            data = json.loads(str(content))

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
            return list(processed.timeline or []), None
        except Exception as e:
            return [], f"Error processing timeline: {e}"

    def _fetch_and_build_timeline(self, client: "StreamingAgentClient", profile_id: str) -> None:
        lanes, error_msg = self._build_timeline_from_export(client, profile_id)
        if lanes is not None:
            self._update_table(lanes)
        if error_msg:
            self.app.notify(error_msg, severity="error")

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
