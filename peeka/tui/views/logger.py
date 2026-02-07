"""
Logger View - Dynamic logger configuration interface.
"""

from typing import Optional, TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import Static, DataTable, Input, Button, Select

if TYPE_CHECKING:
    from peeka.core.client import StreamingAgentClient


class LoggerView(Container):
    """Logger view for managing logger levels."""

    LEVELS = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

    def __init__(self, pid: int) -> None:
        super().__init__()
        self.pid = pid
        self._client: Optional["StreamingAgentClient"] = None

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Static("Filter:", classes="input-label"),
                Input(placeholder="Filter loggers...", id="logger-filter"),
                Button("Refresh", id="logger-refresh-btn", variant="primary"),
                id="logger-controls",
            ),
            Vertical(
                Static("Loggers", classes="section-title"),
                DataTable(id="logger-table"),
                id="logger-list",
            ),
            Horizontal(
                Static("Logger:", classes="input-label"),
                Input(placeholder="Logger name", id="logger-name"),
                Select(
                    [(level, level) for level in self.LEVELS],
                    id="logger-level-select",
                    prompt="Select level",
                ),
                Button("Set Level", id="set-level-btn", variant="primary"),
                id="logger-set-controls",
            ),
            id="logger-container",
        )

    def on_mount(self) -> None:
        table = self.query_one("#logger-table", DataTable)
        table.add_columns("Logger", "Level", "Handlers")
        table.cursor_type = "row"

        if self._client:
            self._refresh_loggers()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "logger-refresh-btn":
            self._refresh_loggers()
        elif event.button.id == "set-level-btn":
            await self._set_logger_level()

    def _refresh_loggers(self) -> None:
        if not self._client:
            self.app.notify("Not connected to agent", severity="error")
            return

        filter_input = self.query_one("#logger-filter", Input)
        pattern = filter_input.value.strip() if filter_input.value else ""

        command = {
            "type": "logger",
            "action": "list",
        }
        if pattern:
            command["pattern"] = pattern

        response = self._client.send_command(command)

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

    async def _set_logger_level(self) -> None:
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

        command = {
            "type": "logger",
            "action": "set",
            "logger": logger_name,
            "level": level,
        }

        response = self._client.send_command(command)

        if response.get("status") != "success":
            self.app.notify(
                f"Failed to set logger level: {response.get('error', 'Unknown error')}",
                severity="error",
            )
            return

        self.app.notify(f"Set {logger_name} to {level}", severity="information")

        self._refresh_loggers()
