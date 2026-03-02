"""
Logger View - Dynamic logger configuration interface.
"""

import logging
from typing import Optional, TYPE_CHECKING

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
        self._own_client: Optional["StreamingAgentClient"] = None
        self._socket_path: Optional[str] = None
        self._log = logging.getLogger(__name__)
        self._mounted = False

    def set_client(self, client: "StreamingAgentClient") -> None:
        self._client = client
        self._socket_path = client.socket_path
        self._connect_own_client()
        if self._mounted:
            self.run_worker(self._refresh_loggers(), thread=False)

    def _connect_own_client(self) -> None:
        """Create a dedicated StreamingAgentClient to avoid socket contention."""
        if not self._socket_path:
            return
        from peeka.core.client import StreamingAgentClient
        self._own_client = StreamingAgentClient(self._socket_path)
        result = self._own_client.connect()
        if result.get("status") != "success":
            self._log.warning("%s dedicated client failed: %s", self.__class__.__name__, result.get("error"))
            self._own_client = None

    def _get_client(self) -> Optional["StreamingAgentClient"]:
        """Return dedicated client if available, else shared client."""
        return self._own_client or self._client

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Static("Filter:", classes="input-label"),
                Input(placeholder="Filter loggers...", id="logger-filter"),
                Button("Refresh", id="logger-refresh-btn", variant="primary", flat=True),
                id="logger-controls",
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
                ),
                Button("Set Level", id="set-level-btn", variant="primary", flat=True),
                id="logger-set-controls",
            ),
            id="logger-container",
        )

    async def on_mount(self) -> None:
        container = self.query_one("#logger-container", Container)
        container.border_title = "Logger"

        logger_list = self.query_one("#logger-list", Vertical)
        logger_list.border_title = "Loggers"

        table = self.query_one("#logger-table", DataTable)
        table.add_columns("Logger", "Level", "Handlers")
        table.cursor_type = "row"
        self._mounted = True

        if self._client:
            await self._refresh_loggers()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "logger-refresh-btn":
            await self._refresh_loggers()
        elif event.button.id == "set-level-btn":
            await self._set_logger_level()

    async def action_refresh(self) -> None:
        """Refresh logger list (triggered by r key)."""
        await self._refresh_loggers()

    async def _refresh_loggers(self) -> None:
        if not self._get_client():
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

        worker = self.run_worker(
            lambda: self._get_client().send_command(command),
            thread=True,
        )
        await worker.wait()
        try:
            response = worker.result
        except Exception as e:
            self.app.notify(f"Connection error: {e}", severity="error")
            return

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
        if not self._get_client():
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

        worker = self.run_worker(
            lambda: self._get_client().send_command(command),
            thread=True,
        )
        await worker.wait()
        try:
            response = worker.result
        except Exception as e:
            self.app.notify(f"Connection error: {e}", severity="error")
            return

        if response.get("status") != "success":
            self.app.notify(
                f"Failed to set logger level: {response.get('error', 'Unknown error')}",
                severity="error",
            )
            return

        self.app.notify(f"Set {logger_name} to {level}", severity="information")

        await self._refresh_loggers()
