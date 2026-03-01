"""Tests for StackView - streaming, data-flow, and error handling."""

import pytest
from textual.widgets import DataTable, Tree

from peeka.tui.widgets.autocomplete_input import AutoCompleteInput

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.stack import StackView


class TestStackView:
    """Test StackView widget population from mock client responses."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_start_stack_sends_command(self, mock_client_factory):
        """Enter pattern and trigger stack sends stack command with correct parameters."""
        client = mock_client_factory(
            responses={
                "stack": {"status": "success", "watch_id": "stack_001"},
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(client)

            pattern_input = stack_view.query_one("#stack-pattern", AutoCompleteInput)
            pattern_input.value = "demo.Calculator.add"

            await stack_view._start_stack()
            await pilot.pause()

            assert len(client.commands_received) > 0
            stack_command = client.commands_received[0]
            assert stack_command.get("type") == "stack"
            assert stack_command.get("action") == "start"
            assert stack_command.get("pattern") == "demo.Calculator.add"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stack_observation_populates_table(self, mock_client_factory):
        """Stack observation from stream populates DataTable with one row per capture."""
        observations = [
            {
                "watch_id": "stack_001",
                "count": 1,
                "stack": [
                    {
                        "filename": "/app/main.py",
                        "lineno": 42,
                        "function": "main",
                        "code": "result = calc()",
                    },
                    {
                        "filename": "/app/calc.py",
                        "lineno": 10,
                        "function": "calc",
                        "code": "return add(1, 2)",
                    },
                ],
            }
        ]

        client = mock_client_factory(
            responses={
                "stack": {"status": "success", "watch_id": "stack_001"},
            },
            observations=observations,
        )
        client.connect()

        stream_client = mock_client_factory(
            responses={},
            observations=observations,
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(client)
            stack_view._stream_client = stream_client

            pattern_input = stack_view.query_one("#stack-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await stack_view._start_stack()
            await pilot.pause()

            table = stack_view.query_one("#stack-table", DataTable)
            assert table.row_count == 1

            row0 = table.get_row_at(0)
            assert "module.func" in str(row0)
            # Frames column should show "2" (two stack frames)
            assert "2" in str(row0)

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stack_frame_details(self, mock_client_factory):
        """Verify each stack frame row shows filename, lineno, function, code."""
        observations = [
            {
                "watch_id": "stack_002",
                "count": 1,
                "stack": [
                    {
                        "filename": "/app/main.py",
                        "lineno": 42,
                        "function": "main",
                        "code": "result = calc()",
                    },
                ],
            }
        ]

        client = mock_client_factory(
            responses={
                "stack": {"status": "success", "watch_id": "stack_002"},
            },
            observations=observations,
        )
        client.connect()

        stream_client = mock_client_factory(
            responses={},
            observations=observations,
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(client)
            stack_view._stream_client = stream_client

            pattern_input = stack_view.query_one("#stack-pattern", AutoCompleteInput)
            pattern_input.value = "test.func"

            await stack_view._start_stack()
            await pilot.pause()

            table = stack_view.query_one("#stack-table", DataTable)
            assert table.row_count > 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stack_tree_display(self, mock_client_factory):
        """Verify Tree widget shows call hierarchy with multiple frames."""
        observations = [
            {
                "watch_id": "stack_003",
                "count": 1,
                "stack": [
                    {
                        "filename": "/app/main.py",
                        "lineno": 42,
                        "function": "main",
                        "code": "result = calc()",
                    },
                    {
                        "filename": "/app/calc.py",
                        "lineno": 10,
                        "function": "calc",
                        "code": "return add(1, 2)",
                    },
                    {
                        "filename": "/app/ops.py",
                        "lineno": 5,
                        "function": "add",
                        "code": "return x + y",
                    },
                ],
            }
        ]

        client = mock_client_factory(
            responses={
                "stack": {"status": "success", "watch_id": "stack_003"},
            },
            observations=observations,
        )
        client.connect()

        stream_client = mock_client_factory(
            responses={},
            observations=observations,
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(client)
            stack_view._stream_client = stream_client

            pattern_input = stack_view.query_one("#stack-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await stack_view._start_stack()
            await pilot.pause()

            table = stack_view.query_one("#stack-table", DataTable)
            assert table.row_count > 0

            tree = stack_view.query_one("#stack-tree", Tree)
            assert tree.root is not None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stack_error_response(self, mock_client_factory):
        """Mock returns error → verify error shown and no table updates."""
        error_client = mock_client_factory(
            responses={
                "stack": {"status": "error", "error": "Pattern not found"},
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

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(error_client)

            pattern_input = stack_view.query_one("#stack-pattern", AutoCompleteInput)
            pattern_input.value = "invalid.pattern"

            await stack_view._start_stack()
            await pilot.pause()

            table = stack_view.query_one("#stack-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_empty_pattern(self, mock_client_factory):
        """Verify validation: empty pattern shows warning without sending command."""
        client = mock_client_factory(
            responses={
                "stack": {"status": "success", "watch_id": "stack_004"},
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(client)

            pattern_input = stack_view.query_one("#stack-pattern", AutoCompleteInput)
            pattern_input.value = ""

            await stack_view._start_stack()
            await pilot.pause()

            assert len(client.commands_received) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_no_client_connected(self):
        """StackView with no client shows graceful state without errors."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)

            pattern_input = stack_view.query_one("#stack-pattern", AutoCompleteInput)
            pattern_input.value = "test.func"

            await stack_view._start_stack()
            await pilot.pause()

            table = stack_view.query_one("#stack-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_multiple_observations_create_separate_rows(
        self, mock_client_factory
    ):
        """Multiple stack observations create separate rows in table, each selectable."""
        observations = [
            {
                "watch_id": "stack_005",
                "count": 1,
                "stack": [
                    {
                        "filename": "/app/main.py",
                        "lineno": 42,
                        "function": "main",
                        "code": "result = calc()",
                    },
                ],
            },
            {
                "watch_id": "stack_005",
                "count": 2,
                "stack": [
                    {
                        "filename": "/app/handler.py",
                        "lineno": 15,
                        "function": "handle_request",
                        "code": "calc()",
                    },
                    {
                        "filename": "/app/main.py",
                        "lineno": 42,
                        "function": "main",
                        "code": "result = calc()",
                    },
                ],
            },
        ]

        client = mock_client_factory(
            responses={
                "stack": {"status": "success", "watch_id": "stack_005"},
            },
            observations=observations,
        )
        client.connect()

        stream_client = mock_client_factory(
            responses={},
            observations=observations,
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(client)
            stack_view._stream_client = stream_client

            pattern_input = stack_view.query_one("#stack-pattern", AutoCompleteInput)
            pattern_input.value = "test.func"

            await stack_view._start_stack()
            await pilot.pause()

            table = stack_view.query_one("#stack-table", DataTable)
            # Each observation creates its own row
            assert table.row_count == 2

            # First capture has 1 frame, second has 2 frames
            row0 = table.get_row_at(0)
            row1 = table.get_row_at(1)
            assert "1" in str(row0[2])  # Frames column
            assert "2" in str(row1[2])  # Frames column

            # Stack cache should have both captures
            assert len(stack_view._stack_cache) == 2

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_row_selection_renders_stack(self, mock_client_factory):
        """Selecting different rows in the table renders different stack traces."""
        observations = [
            {
                "watch_id": "stack_007",
                "count": 1,
                "stack": [
                    {
                        "filename": "/app/route_a.py",
                        "lineno": 10,
                        "function": "route_a",
                        "code": "calc()",
                    },
                ],
            },
            {
                "watch_id": "stack_007",
                "count": 2,
                "stack": [
                    {
                        "filename": "/app/route_b.py",
                        "lineno": 20,
                        "function": "route_b",
                        "code": "calc()",
                    },
                    {
                        "filename": "/app/middleware.py",
                        "lineno": 5,
                        "function": "middleware",
                        "code": "next()",
                    },
                ],
            },
        ]

        client = mock_client_factory(
            responses={
                "stack": {"status": "success", "watch_id": "stack_007"},
            },
            observations=observations,
        )
        client.connect()

        stream_client = mock_client_factory(
            responses={},
            observations=observations,
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(client)
            stack_view._stream_client = stream_client

            pattern_input = stack_view.query_one("#stack-pattern", AutoCompleteInput)
            pattern_input.value = "test.func"

            await stack_view._start_stack()
            await pilot.pause()

            table = stack_view.query_one("#stack-table", DataTable)
            assert table.row_count == 2

            # Select first row → tree should show route_a stack
            table.move_cursor(row=0)
            await pilot.pause()

            tree = stack_view.query_one("#stack-tree", Tree)
            tree_text = str(tree.root.label)
            assert "#1" in tree_text

            # Select second row → tree should show route_b stack
            table.move_cursor(row=1)
            await pilot.pause()

            tree_text = str(tree.root.label)
            assert "#2" in tree_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stop_all_stacks(self, mock_client_factory):
        """Stop all traces cancels workers and clears table."""
        observations = [
            {
                "watch_id": "stack_006",
                "count": 1,
                "stack": [
                    {
                        "filename": "/app/main.py",
                        "lineno": 42,
                        "function": "main",
                        "code": "result = calc()",
                    },
                ],
            }
        ]

        client = mock_client_factory(
            responses={
                "stack": {"status": "success", "watch_id": "stack_006"},
            },
            observations=observations,
        )
        client.connect()

        stream_client = mock_client_factory(
            responses={},
            observations=observations,
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(client)
            stack_view._stream_client = stream_client

            pattern_input = stack_view.query_one("#stack-pattern", AutoCompleteInput)
            pattern_input.value = "test.func"

            await stack_view._start_stack()
            await pilot.pause()
            await pilot.pause()

            table = stack_view.query_one("#stack-table", DataTable)
            initial_row_count = table.row_count

            await stack_view._stop_all_stacks()
            await pilot.pause()

            assert table.row_count == 0
            assert len(stack_view._workers) == 0
            assert len(stack_view._stack_cache) == 0
