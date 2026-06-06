"""Dashboard Activity Log replay and rendering helpers."""

import re
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from rich.text import Text
from textual.widgets import RichLog
from textual.worker import get_current_worker

_SESSION_LOG_PATTERN = re.compile(
    r"^(?P<timestamp>\d+(?:\.\d+)?) (?P<level>[A-Z]+) (?P<message>.*)$"
)

_AGENT_CONNECTION_LIFECYCLE_PATTERN = re.compile(
    r"^\[peeka Agent\] (?:"
    r"client .+ conn#\d+ connected \(|"
    r"client .+ conn#\d+ disconnected\b|"
    r"conn#\d+ disconnected\b"
    r")"
)


class DashboardActivityMixin:

    def action_clear_activity_log(self) -> None:
        """Clear the activity log display."""
        rich_log = self.query_one("#dash-activity-log", RichLog)
        rich_log.clear()
        self._activity_log_entries.clear()


    def action_copy_activity_log(self) -> None:
        """Copy the current activity log entries to the terminal clipboard."""
        text = self._activity_log_text()
        if not text:
            self.notify("Activity Log is empty", severity="warning")
            return

        try:
            self.app.copy_to_clipboard(text)
        except Exception as e:
            self.notify(f"Failed to copy Activity Log: {e}", severity="error")
            return

        self.notify("Activity Log copied", severity="information")


    def _get_session_log_path(self) -> Optional[Path]:
        """Return the persisted session log path when the session is known."""
        if not self._session_id:
            return None
        return Path(tempfile.gettempdir()) / f"peeka_{self._session_id}.log"


    def _register_client_activity_listener(self) -> None:
        """Subscribe to app-level client activity updates."""
        if self._activity_listener_registered:
            return

        app = self._get_optional_app()
        if app is None:
            return

        register = getattr(app, "register_activity_listener", None)
        if not callable(register):
            return

        register(self._handle_client_activity)
        self._activity_listener_registered = True


    def _unregister_client_activity_listener(self) -> None:
        """Unsubscribe from app-level client activity updates."""
        if not self._activity_listener_registered:
            return

        app = self._get_optional_app()
        if app is None:
            self._activity_listener_registered = False
            return

        unregister = getattr(app, "unregister_activity_listener", None)
        if callable(unregister):
            unregister(self._handle_client_activity)
        self._activity_listener_registered = False


    def _load_client_activity_history(self) -> None:
        """Replay buffered client activity emitted before the dashboard mounted."""
        app = self._get_optional_app()
        if app is None:
            return

        getter = getattr(app, "get_client_activity_entries", None)
        if not callable(getter):
            return

        for entry in getter(after_seq=self._last_client_activity_seq):
            self._ingest_client_activity_entry(entry)


    def _handle_client_activity(self, entry: Dict[str, Any]) -> None:
        """Append future client activity entries to the dashboard log."""
        if threading.current_thread() is threading.main_thread():
            self._ingest_client_activity_entry(entry)
            return

        self.app.call_from_thread(self._ingest_client_activity_entry, dict(entry))


    def _record_client_activity(
        self, level: str, message: str, source: str = "dashboard"
    ) -> None:
        """Emit a client-side activity entry when the app supports it."""
        app = self._get_optional_app()
        if app is None:
            return

        recorder = getattr(app, "record_client_activity", None)
        if callable(recorder):
            recorder(level, message, source=source)


    def _get_optional_app(self) -> Optional[Any]:
        """Return the mounted Textual app when one is available."""
        try:
            return self.app
        except Exception:
            return None


    def _ingest_client_activity_entry(self, entry: Dict[str, Any]) -> None:
        """Render one buffered client activity entry into the activity log."""
        seq = int(entry.get("seq", 0))
        if seq <= self._last_client_activity_seq:
            return

        self._last_client_activity_seq = seq
        if not self._should_render_client_activity(entry):
            return

        message = str(entry.get("message", ""))
        source = str(entry.get("source", "client"))
        if source and source not in ("client", "main"):
            message = f"{source}: {message}"

        self._write_activity_entry(
            "client",
            str(entry.get("level", "INFO")),
            message,
            entry.get("timestamp", ""),
        )


    def _should_render_client_activity(self, entry: Dict[str, Any]) -> bool:
        """Return False for low-signal client connection lifecycle entries."""
        level = str(entry.get("level", "INFO")).upper()
        message = str(entry.get("message", ""))
        source = str(entry.get("source", "client"))

        if level == "INFO" and message in ("connected", "disconnected"):
            if source == "main" or source.endswith("-data") or source.endswith("-stream"):
                return False

        return True


    def _load_persisted_activity_history(self) -> None:
        """Replay the persisted session log so late-opened dashboards aren't blank."""
        if self._agent_history_loaded:
            return

        log_path = self._get_session_log_path()
        if not log_path or not log_path.exists():
            return

        last_level = "INFO"
        last_timestamp = ""

        try:
            for raw_line in log_path.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                if not raw_line.strip():
                    continue

                match = _SESSION_LOG_PATTERN.match(raw_line)
                if match:
                    last_timestamp = match.group("timestamp")
                    last_level = match.group("level")
                    message = match.group("message")
                else:
                    message = raw_line

                self._write_activity_entry(
                    "agent", last_level, message, last_timestamp
                )
        except OSError as e:
            self._log.debug("Failed to replay agent session log: %s", e)
            return

        self._agent_history_loaded = True

    # -- UI updates -------------------------------------------------------------


    def _stream_activity_log_messages(self) -> None:
        """Stream agent log messages into the activity log in a background thread."""
        stream = self._stream_client or self._client
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
                self._write_activity_entry, "agent", level, message, timestamp
            )

        if not worker.is_cancelled and self._active:
            self.app.call_from_thread(
                self._handle_dashboard_connection_lost,
                "activity log stream closed by peer",
            )


    def _format_timestamp(self, timestamp: Any) -> str:
        """Format numeric timestamps into a stable human-readable time."""
        if timestamp in ("", None):
            return ""

        try:
            return time.strftime("%H:%M:%S", time.localtime(float(timestamp)))
        except (TypeError, ValueError):
            return str(timestamp)


    def _write_activity_entry(
        self, source: str, level: str, message: str, timestamp: Any
    ) -> None:
        """Add an activity entry to the RichLog widget (runs on main thread).

        Args:
            source: Entry origin label such as ``agent`` or ``client``.
            level: Log level (INFO, WARNING, ERROR, etc.)
            message: Log message text
            timestamp: Optional timestamp or timestamp string
        """
        if not self._should_render_activity_entry(source, level, message):
            return

        entry = {
            "source": source,
            "level": level,
            "message": message,
            "timestamp": timestamp,
        }
        self._activity_log_entries.append(entry)
        if len(self._activity_log_entries) > self.MAX_LOG_LINES:
            self._activity_log_entries = self._activity_log_entries[-self.MAX_LOG_LINES :]

        self._render_activity_entry(entry)


    def _should_render_activity_entry(
        self, source: str, level: str, message: str
    ) -> bool:
        """Return False for verbose activity entries hidden by default."""
        if source == "agent" and str(level).upper() == "INFO":
            if _AGENT_CONNECTION_LIFECYCLE_PATTERN.search(str(message)):
                return False
        return True


    def _activity_log_text(self) -> str:
        """Return visible activity log entries as plain text."""
        lines = [
            self._format_activity_entry_plain(entry)
            for entry in self._activity_log_entries[-self.MAX_LOG_LINES :]
        ]
        return "\n".join(line for line in lines if line)


    def _format_activity_entry_plain(self, entry: Dict[str, Any]) -> str:
        """Format one activity entry as copy-friendly plain text."""
        timestamp = self._format_timestamp(entry.get("timestamp", ""))
        source = str(entry.get("source", "")).upper()
        level = str(entry.get("level", "INFO")).upper()
        message = str(entry.get("message", ""))

        prefix = f"[{timestamp}] " if timestamp else ""
        return f"{prefix}{source} {level} {message}".strip()


    def _activity_log_render_width(self, rich_log: RichLog) -> int:
        """Return the current render width, falling back only before layout."""
        current_width = rich_log.region.width
        if current_width > 0:
            return current_width
        return self.ACTIVITY_LOG_MIN_RENDER_WIDTH


    def _rerender_activity_log(self) -> None:
        """Re-render cached activity entries using the current panel width."""
        if not self.is_mounted:
            return

        rich_log = self.query_one("#dash-activity-log", RichLog)
        rich_log.clear()
        for entry in self._activity_log_entries[-self.MAX_LOG_LINES :]:
            self._render_activity_entry(entry)


    def _render_activity_entry(self, entry: Dict[str, Any]) -> None:
        """Render one cached activity entry to the RichLog."""
        rich_log = self.query_one("#dash-activity-log", RichLog)
        source = str(entry.get("source", ""))
        level = str(entry.get("level", "INFO"))
        message = str(entry.get("message", ""))
        timestamp = entry.get("timestamp", "")

        # Choose color based on log level
        style_map = {
            "DEBUG": "dim blue",
            "INFO": "blue",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "bold red",
        }
        style = style_map.get(level, "white")
        source_style_map = {
            "agent": "magenta",
            "client": "green",
        }
        source_style = source_style_map.get(source, "cyan")

        # Format the entry
        rendered_timestamp = self._format_timestamp(timestamp)
        if rendered_timestamp:
            text = Text(f"[{rendered_timestamp}] ", style="dim")
        else:
            text = Text()

        source_text = Text(f"{source.upper():7} ", style=source_style)
        level_text = Text(f"{level:8} ", style=style)
        message_text = Text(message)

        text.append(source_text)
        text.append(level_text)
        text.append(message_text)

        render_width = self._activity_log_render_width(rich_log)
        rich_log.write(text, width=render_width)
        # Auto-scroll is handled automatically by RichLog when auto_scroll=True
