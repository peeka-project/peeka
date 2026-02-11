"""Tests for LoggerView - data-flow and error handling."""

import pytest
from textual.widgets import DataTable, Button, Input, Select, Static

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.logger import LoggerView


class ActionRoutingLoggerClient:
    """Mock client that routes logger commands by action field."""

    def __init__(self, action_responses):
        self.action_responses = action_responses
        self.connected = False
        self.commands_received = []

    def connect(self):
        self.connected = True
        return {"status": "success"}

    def disconnect(self):
        self.connected = False

    def send_command(self, command):
        if not self.connected:
            return {"status": "error", "error": "Not connected"}
        self.commands_received.append(command)
        if command.get("type") == "logger":
            action = command.get("action")
            if action in self.action_responses:
                return self.action_responses[action]
            return {"status": "error", "error": f"Unknown action: {action}"}
        return {"status": "error", "error": f"Unknown type: {command.get('type')}"}


class TestLoggerView:
    """Test LoggerView widget population from mock client responses."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_refresh_loggers_populates_table(self):
        """Refresh loggers populates DataTable with logger names, levels, and handlers."""
        logger_client = ActionRoutingLoggerClient(
            action_responses={
                "list": {
                    "status": "success",
                    "loggers": [
                        {"name": "root", "level": "INFO", "handlers": 1},
                        {"name": "peeka.core", "level": "DEBUG", "handlers": 2},
                        {"name": "peeka.cli", "level": "WARNING", "handlers": 1},
                    ],
                },
            }
        )
        logger_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            logger_view = app.screen.query_one("LoggerView", LoggerView)
            logger_view.set_client(logger_client)

            logger_view._refresh_loggers()
            await pilot.pause()

            commands = [cmd.get("action") for cmd in logger_client.commands_received]
            assert "list" in commands

            table = logger_view.query_one("#logger-table", DataTable)
            assert table.row_count == 3

            row0 = table.get_row_at(0)
            assert "root" in str(row0)
            assert "INFO" in str(row0)

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_set_logger_level(self):
        """Set logger level sends correct command with name and level params."""
        logger_client = ActionRoutingLoggerClient(
            action_responses={
                "set": {"status": "success", "message": "Logger level set"},
                "list": {
                    "status": "success",
                    "loggers": [
                        {"name": "peeka.core", "level": "DEBUG", "handlers": 1},
                    ],
                },
            }
        )
        logger_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            logger_view = app.screen.query_one("LoggerView", LoggerView)
            logger_view.set_client(logger_client)

            name_input = logger_view.query_one("#logger-name", Input)
            name_input.value = "peeka.core"

            level_select = logger_view.query_one("#logger-level-select", Select)
            level_select.value = "DEBUG"

            await logger_view._set_logger_level()
            await pilot.pause()
            await pilot.pause()

            commands = [
                cmd
                for cmd in logger_client.commands_received
                if cmd.get("action") == "set"
            ]
            assert len(commands) > 0
            set_command = commands[0]
            assert set_command.get("logger") == "peeka.core"
            assert set_command.get("level") == "DEBUG"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_set_level_validates_inputs(self):
        """Set level without logger name or level shows warning."""
        logger_client = ActionRoutingLoggerClient(action_responses={})
        logger_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            logger_view = app.screen.query_one("LoggerView", LoggerView)
            logger_view.set_client(logger_client)

            name_input = logger_view.query_one("#logger-name", Input)
            name_input.value = ""

            await logger_view._set_logger_level()
            await pilot.pause()

            assert len(logger_client.commands_received) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_filter_loggers(self):
        """Filter input sends pattern parameter in list command."""
        logger_client = ActionRoutingLoggerClient(
            action_responses={
                "list": {
                    "status": "success",
                    "loggers": [
                        {"name": "peeka.core", "level": "DEBUG", "handlers": 1},
                    ],
                },
            }
        )
        logger_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            logger_view = app.screen.query_one("LoggerView", LoggerView)
            logger_view.set_client(logger_client)

            filter_input = logger_view.query_one("#logger-filter", Input)
            filter_input.value = "peeka.*"

            logger_view._refresh_loggers()
            await pilot.pause()

            list_commands = [
                cmd
                for cmd in logger_client.commands_received
                if cmd.get("action") == "list"
            ]
            assert len(list_commands) > 0
            assert list_commands[-1].get("pattern") == "peeka.*"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_empty_logger_list(self):
        """Empty logger list from server shows table with zero rows."""
        logger_client = ActionRoutingLoggerClient(
            action_responses={
                "list": {
                    "status": "success",
                    "loggers": [],
                },
            }
        )
        logger_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            logger_view = app.screen.query_one("LoggerView", LoggerView)
            logger_view.set_client(logger_client)

            logger_view._refresh_loggers()
            await pilot.pause()

            table = logger_view.query_one("#logger-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_error_response_handling(self):
        """LoggerView handles error responses gracefully without crashing."""
        error_client = ActionRoutingLoggerClient(
            action_responses={
                "list": {"status": "error", "error": "Logger list failed"},
            }
        )
        error_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            logger_view = app.screen.query_one("LoggerView", LoggerView)
            logger_view.set_client(error_client)

            logger_view._refresh_loggers()
            await pilot.pause()

            table = logger_view.query_one("#logger-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_set_level_error_response(self):
        """Set level with error response shows notification without crashing."""
        error_client = ActionRoutingLoggerClient(
            action_responses={
                "set": {"status": "error", "error": "Set level failed"},
            }
        )
        error_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            logger_view = app.screen.query_one("LoggerView", LoggerView)
            logger_view.set_client(error_client)

            name_input = logger_view.query_one("#logger-name", Input)
            name_input.value = "test.logger"

            level_select = logger_view.query_one("#logger-level-select", Select)
            level_select.value = "ERROR"

            await logger_view._set_logger_level()
            await pilot.pause()

            commands = [cmd.get("action") for cmd in error_client.commands_received]
            assert "set" in commands

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_no_client_connected(self):
        """LoggerView with no client shows graceful state without errors."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            logger_view = app.screen.query_one("LoggerView", LoggerView)

            logger_view._refresh_loggers()
            await pilot.pause()

            table = logger_view.query_one("#logger-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_action_refresh_triggers_list(self):
        """Calling action_refresh() triggers logger list command."""
        logger_client = ActionRoutingLoggerClient(
            action_responses={
                "list": {
                    "status": "success",
                    "loggers": [
                        {"name": "root", "level": "INFO", "handlers": 1},
                    ],
                },
            }
        )
        logger_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            logger_view = app.screen.query_one("LoggerView", LoggerView)
            logger_view.set_client(logger_client)

            initial_count = len(logger_client.commands_received)

            logger_view.action_refresh()
            await pilot.pause()

            assert len(logger_client.commands_received) > initial_count
            commands = [cmd.get("action") for cmd in logger_client.commands_received]
            assert "list" in commands

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_set_level_after_refresh(self):
        """Set level triggers refresh automatically after successful set."""
        logger_client = ActionRoutingLoggerClient(
            action_responses={
                "set": {"status": "success", "message": "Logger level set"},
                "list": {
                    "status": "success",
                    "loggers": [
                        {"name": "test.logger", "level": "ERROR", "handlers": 1},
                    ],
                },
            }
        )
        logger_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            logger_view = app.screen.query_one("LoggerView", LoggerView)
            logger_view.set_client(logger_client)

            name_input = logger_view.query_one("#logger-name", Input)
            name_input.value = "test.logger"

            level_select = logger_view.query_one("#logger-level-select", Select)
            level_select.value = "ERROR"

            await logger_view._set_logger_level()
            await pilot.pause()
            await pilot.pause()

            commands = [cmd.get("action") for cmd in logger_client.commands_received]
            assert "set" in commands
            assert "list" in commands
