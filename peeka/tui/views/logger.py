"""
Logger View - Dynamic logger configuration interface.
"""

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button, Select

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class LoggerView(Container):
    """Logger view for managing logger levels."""

    BINDINGS = [
        Binding("r", "refresh", "Refresh"),
    ]

    LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None
        self._log = logging.getLogger(__name__)
        self._mounted = False

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client
        if self._mounted:
            self.app.call_later(self._refresh_loggers)

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Static("Filter:", classes="input-label"),
                Input(placeholder="Filter loggers...", id="logger-filter"),
                Button("Refresh", id="logger-refresh-btn", variant="primary", flat=True),
                id="logger-controls",
                classes="compact-control",
            ),
            Vertical(
                DataTable(id="logger-table"),
                id="logger-list",
                classes="panel",
            ),
            Horizontal(
                Static("Logger:", classes="input-label"),
                Input(placeholder="Logger name", id="logger-name"),
                Select(
                    [(level, level) for level in self.LEVELS],
                    id="logger-level-select",
                    prompt="Select level",
                    compact=True,
                ),
                Button("Set Level", id="set-level-btn", variant="primary", flat=True),
                id="logger-set-controls",
                classes="compact-control",
            ),
            id="logger-container",
        )

    def on_mount(self) -> None:
        container = self.query_one("#logger-container", Container)
        container.border_title = "Logger"

        logger_list = self.query_one("#logger-list", Vertical)
        logger_list.border_title = "Loggers"

        table = self.query_one("#logger-table", DataTable)
        table.add_columns("Logger", "Level", "Handlers")
        table.cursor_type = "row"
        self._mounted = True

        if self._client:
            self._refresh_loggers()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "logger-refresh-btn":
            self._refresh_loggers()
        elif event.button.id == "set-level-btn":
            self._set_logger_level()

    def action_refresh(self) -> None:
        """Refresh logger list (triggered by r key)."""
        self._refresh_loggers()

    def _refresh_loggers(self) -> None:
        """Fetch loggers in thread worker, update table on main thread."""
        if not self._client:
            self.app.notify("Not connected to agent", severity="error")
            return

        filter_input = self.query_one("#logger-filter", Input)
        pattern = filter_input.value.strip() if filter_input.value else ""

        command: Dict[str, Any] = {
            "type": "logger",
            "action": "list",
        }
        if pattern:
            command["pattern"] = pattern

        def worker_fn() -> None:
            if not self._client:
                return
            try:
                response = self._client.send_command(command)
                self.app.call_from_thread(self._update_loggers_ui, response)
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"Connection error: {e}", severity="error"
                )

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _update_loggers_ui(self, response: Dict[str, Any]) -> None:
        """Update logger table with response data (runs on main thread)."""
        if response.get("status") != "success":
            self.app.notify(
                f"Failed to list loggers: {response.get('error', 'Unknown error')}",
                severity="error",
            )
            return

        table = self.query_one("#logger-table", DataTable)
        table.clear()

        loggers = response.get("loggers", [])
        for logger in loggers:
            name = logger.get("name", "")
            level = logger.get("level", "")
            handlers = str(logger.get("handlers", 0))
            table.add_row(name, level, handlers)

        self.app.notify(f"Loaded {len(loggers)} logger(s)", severity="information")

    def _set_logger_level(self) -> None:
        """Set logger level via thread worker."""
        if not self._client:
            self.app.notify("Not connected to agent", severity="error")
            return

        name_input = self.query_one("#logger-name", Input)
        level_select = self.query_one("#logger-level-select", Select)

        logger_name = name_input.value.strip()
        if not logger_name:
            self.app.notify("Please enter logger name", severity="warning")
            return

        if level_select.value is Select.BLANK:
            self.app.notify("Please select log level", severity="warning")
            return

        level = str(level_select.value)

        command: Dict[str, Any] = {
            "type": "logger",
            "action": "set",
            "logger": logger_name,
            "level": level,
        }

        def worker_fn() -> None:
            if not self._client:
                return
            try:
                response = self._client.send_command(command)
                self.app.call_from_thread(
                    self._on_set_level_complete, response, logger_name, level
                )
            except Exception as e:
                self.app.call_from_thread(
                    self.app.notify, f"Connection error: {e}", severity="error"
                )

        self.run_worker(worker_fn, thread=True, exclusive=False)

    def _on_set_level_complete(
        self, response: Dict[str, Any], logger_name: str, level: str
    ) -> None:
        """Handle set level response (runs on main thread)."""
        if response.get("status") != "success":
            self.app.notify(
                f"Failed to set logger level: {response.get('error', 'Unknown error')}",
                severity="error",
            )
            return

        self.app.notify(f"Set {logger_name} to {level}", severity="information")
        self._refresh_loggers()
