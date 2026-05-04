"""
Agent Log View - Display agent-side log messages from target process.
"""

import logging
import threading
from typing import TYPE_CHECKING, Optional

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import RichLog
from textual.worker import get_current_worker

from peeka.tui.activity import make_activity_reporter

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class AgentLogView(Container):
    """Agent Log view for displaying agent-side log messages from target process."""

    BINDINGS = [
        Binding("c", "clear_log", "Clear"),
    ]

    MAX_LOG_LINES = 1000

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._stream_client: Optional["StreamingAgentClient"] = None
        self._stream_client_lock: threading.Lock = threading.Lock()
        self._socket_path: Optional[str] = None
        self._worker = None
        self._log = logging.getLogger(__name__)

    def set_client(self, client: "StreamingAgentClient") -> None:
        """Set agent client for streaming connection."""
        self._client = client
        self._socket_path = client.socket_path
        # Defer stream client creation to first use (lazy connection)

    def _connect_own_stream_client(self) -> None:
        """Create a dedicated StreamingAgentClient for streaming observations."""
        if not self._socket_path:
            return
        try:
            from peeka.core.client import StreamingAgentClient
            self._stream_client = StreamingAgentClient(
                self._socket_path,
                activity_reporter=make_activity_reporter(self.app, "agent-log-stream"),
            )
            result = self._stream_client.connect()
            if result.get("status") != "success":
                self._log.warning(
                    "Agent log stream client failed: %s", result.get("error")
                )
                self._stream_client = None
        except Exception as e:
            self._log.warning("Agent log stream client error: %s", e)
            self._stream_client = None

    def _ensure_stream_client(self) -> Optional["StreamingAgentClient"]:
        """Lazily create stream client on first use (thread-safe)."""
        if self._stream_client is None:
            with self._stream_client_lock:
                if self._stream_client is None:
                    self._connect_own_stream_client()
                    if self._stream_client:
                        # Start streaming immediately once connected
                        self._worker = self.run_worker(
                            lambda: self._stream_log_messages(),
                            thread=True,
                            exclusive=False,
                        )
        return self._stream_client

    def action_clear_log(self) -> None:
        """Clear the log display."""
        rich_log = self.query_one("#agent-log", RichLog)
        rich_log.clear()

    def compose(self) -> ComposeResult:
        yield Container(
            RichLog(
                id="agent-log",
                highlight=True,
                max_lines=self.MAX_LOG_LINES,
                auto_scroll=True,
            ),
            id="agent-log-container",
        )

    def on_mount(self) -> None:
        """Initialize the view when mounted."""
        container = self.query_one("#agent-log-container", Container)
        container.border_title = "Agent Log"

        # Start connecting on mount to prepare streaming
        self._ensure_stream_client()

    def on_unmount(self) -> None:
        """Cancel worker and disconnect stream client when view is unmounted."""
        if self._worker:
            self._worker.cancel()
        if self._stream_client:
            self._stream_client.disconnect()
            self._stream_client = None

    def cleanup_for_exit(self) -> None:
        """Cleanup before TUI exit."""
        if self._worker:
            self._worker.cancel()
        if self._stream_client:
            self._stream_client.disconnect()
            self._stream_client = None

    def _stream_log_messages(self) -> None:
        """Stream log messages from the agent in background thread."""
        stream = self._ensure_stream_client() or self._client
        if not stream:
            return

        worker = get_current_worker()

        for observation in stream.stream_observations():
            if worker.is_cancelled:
                break

            # Check if this is a log message
            if observation.get("type") != "log":
                continue

            level = observation.get("level", "INFO").upper()
            message = observation.get("message", "")
            timestamp = observation.get("timestamp", "")

            self.app.call_from_thread(
                self._add_log_entry, level, message, timestamp
            )

    def _add_log_entry(self, level: str, message: str, timestamp: str) -> None:
        """Add a log entry to the RichLog widget (runs on main thread).

        Args:
            level: Log level (INFO, WARNING, ERROR, etc.)
            message: Log message text
            timestamp: Optional timestamp string
        """
        rich_log = self.query_one("#agent-log", RichLog)

        # Choose color based on log level
        style_map = {
            "DEBUG": "dim blue",
            "INFO": "blue",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold red",
        }
        style = style_map.get(level, "white")

        # Format the entry
        if timestamp:
            text = Text(f"[{timestamp}] ", style="dim")
        else:
            text = Text()

        level_text = Text(f"{level:8} ", style=style)
        message_text = Text(message, style=style)

        text.append(level_text)
        text.append(message_text)

        rich_log.write(text)
        # Auto-scroll is handled automatically by RichLog when auto_scroll=True
