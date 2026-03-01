"""Tests for ThreadView - thread listing, stack inspection, and periodic refresh."""

import pytest
from textual.widgets import DataTable, Static, Tree

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.thread import ThreadView


# Thread detail response for stack inspection tests
THREAD_DETAIL_RESPONSE = {
    "status": "success",
    "thread": {
        "tid": 1234,
        "name": "MainThread",
        "state": "RUNNABLE",
        "stack": [
            {
                "filename": "/app/main.py",
                "lineno": 42,
                "funcname": "main",
                "locals_keys": ["x", "y", "result"],
            },
            {
                "filename": "/app/calc.py",
                "lineno": 10,
                "funcname": "calculate",
                "locals_keys": [],
            },
            {
                "filename": "/usr/lib/python3.14/threading.py",
                "lineno": 300,
                "funcname": "run",
                "locals_keys": ["self"],
            },
        ],
    },
}


class TestThreadView:
    """Test ThreadView widget population from mock client responses."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_set_client_triggers_refresh(self, mock_client_factory):
        """set_client sends thread list command when view is mounted."""
        client = mock_client_factory(
            responses={
                "thread": {
                    "status": "success",
                    "total": 2,
                    "threads": [
                        {
                            "tid": 1234,
                            "name": "MainThread",
                            "state": "RUNNABLE",
                            "daemon": False,
                            "stack_depth": 5,
                            "top_frame": {
                                "filename": "test.py",
                                "lineno": 10,
                                "funcname": "main",
                            },
                        },
                    ],
                },
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

            thread_view = app.screen.query_one("ThreadView", ThreadView)
            thread_view.set_client(client)
            await pilot.pause()
            await pilot.pause()

            # set_client should trigger _refresh_threads which sends thread list command
            thread_cmds = [
                c for c in client.commands_received if c.get("type") == "thread"
            ]
            assert len(thread_cmds) >= 1
            assert thread_cmds[0].get("action") == "list"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_thread_list_populates_table(self, mock_client_factory):
        """_update_threads_ui populates DataTable with thread rows."""
        client = mock_client_factory(
            responses={
                "thread": {
                    "status": "success",
                    "total": 2,
                    "threads": [
                        {
                            "tid": 1234,
                            "name": "MainThread",
                            "state": "RUNNABLE",
                            "daemon": False,
                            "stack_depth": 5,
                            "top_frame": {
                                "filename": "test.py",
                                "lineno": 10,
                                "funcname": "main",
                            },
                        },
                        {
                            "tid": 5678,
                            "name": "Worker-1",
                            "state": "WAITING",
                            "daemon": True,
                            "stack_depth": 3,
                            "top_frame": {
                                "filename": "threading.py",
                                "lineno": 300,
                                "funcname": "wait",
                            },
                        },
                    ],
                },
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

            thread_view = app.screen.query_one("ThreadView", ThreadView)
            thread_view.set_client(client)
            await pilot.pause()
            await pilot.pause()

            table = thread_view.query_one("#threads-table", DataTable)
            assert table.row_count == 2

            # Verify first row content
            row0 = table.get_row_at(0)
            assert "1234" in str(row0)
            assert "MainThread" in str(row0)

            # Verify second row content
            row1 = table.get_row_at(1)
            assert "5678" in str(row1)
            assert "Worker-1" in str(row1)

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_thread_summary_shows_counts(self, mock_client_factory):
        """Summary shows total, runnable, waiting, daemon counts."""
        client = mock_client_factory(
            responses={
                "thread": {
                    "status": "success",
                    "total": 3,
                    "threads": [
                        {
                            "tid": 1,
                            "name": "Main",
                            "state": "RUNNABLE",
                            "daemon": False,
                            "stack_depth": 1,
                            "top_frame": None,
                        },
                        {
                            "tid": 2,
                            "name": "Worker-1",
                            "state": "WAITING",
                            "daemon": True,
                            "stack_depth": 2,
                            "top_frame": None,
                        },
                        {
                            "tid": 3,
                            "name": "Timer-1",
                            "state": "TIMED_WAITING",
                            "daemon": True,
                            "stack_depth": 3,
                            "top_frame": None,
                        },
                    ],
                },
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

            thread_view = app.screen.query_one("ThreadView", ThreadView)
            thread_view.set_client(client)
            await pilot.pause()
            await pilot.pause()

            summary = thread_view.query_one("#thread-summary", Static)
            summary_text = summary.render().plain

            assert "3 total" in summary_text
            assert "1 runnable" in summary_text
            assert "1 waiting" in summary_text
            assert "1 timed" in summary_text
            assert "2 daemon" in summary_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_thread_detail_populates_stack_tree(self, mock_client_factory):
        """_update_stack_ui populates Tree with stack frames."""
        client = mock_client_factory(
            responses={
                "thread": {
                    "status": "success",
                    "total": 1,
                    "threads": [
                        {
                            "tid": 1234,
                            "name": "MainThread",
                            "state": "RUNNABLE",
                            "daemon": False,
                            "stack_depth": 3,
                            "top_frame": {
                                "filename": "test.py",
                                "lineno": 10,
                                "funcname": "main",
                            },
                        },
                    ],
                },
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

            thread_view = app.screen.query_one("ThreadView", ThreadView)
            thread_view.set_client(client)
            await pilot.pause()

            # Directly call _update_stack_ui with detail data
            thread_data = THREAD_DETAIL_RESPONSE["thread"]
            thread_view._update_stack_ui(thread_data)
            await pilot.pause()

            tree = thread_view.query_one("#thread-stack-tree", Tree)
            root = tree.root

            # Root label should contain thread name/tid/state
            root_label = str(root.label)
            assert "MainThread" in root_label
            assert "1234" in root_label
            assert "RUNNABLE" in root_label

            # Should have 3 frame children
            assert len(root.children) == 3

            # First frame should be main()
            frame0_label = str(root.children[0].label)
            assert "main()" in frame0_label

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stack_tree_shows_locals(self, mock_client_factory):
        """Frame with locals_keys shows locals as leaf node."""
        client = mock_client_factory(
            responses={
                "thread": {
                    "status": "success",
                    "total": 1,
                    "threads": [],
                },
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

            thread_view = app.screen.query_one("ThreadView", ThreadView)
            thread_view.set_client(client)
            await pilot.pause()

            # Call _update_stack_ui with data containing locals
            thread_data = THREAD_DETAIL_RESPONSE["thread"]
            thread_view._update_stack_ui(thread_data)
            await pilot.pause()

            tree = thread_view.query_one("#thread-stack-tree", Tree)
            root = tree.root

            # First frame (main) has locals_keys: ["x", "y", "result"]
            frame0 = root.children[0]
            frame0_children_labels = [str(c.label) for c in frame0.children]
            locals_labels = [l for l in frame0_children_labels if "locals:" in l]
            assert len(locals_labels) >= 1
            assert "x" in locals_labels[0]
            assert "y" in locals_labels[0]
            assert "result" in locals_labels[0]

            # Second frame (calculate) has empty locals_keys → no locals leaf
            frame1 = root.children[1]
            frame1_children_labels = [str(c.label) for c in frame1.children]
            locals_in_frame1 = [l for l in frame1_children_labels if "locals:" in l]
            assert len(locals_in_frame1) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_empty_stack_shows_message(self, mock_client_factory):
        """Thread with no stack frames shows 'No stack frames available'."""
        client = mock_client_factory(
            responses={
                "thread": {
                    "status": "success",
                    "total": 1,
                    "threads": [],
                },
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

            thread_view = app.screen.query_one("ThreadView", ThreadView)
            thread_view.set_client(client)
            await pilot.pause()

            # Call with empty stack
            thread_data = {
                "tid": 999,
                "name": "IdleThread",
                "state": "WAITING",
                "stack": [],
            }
            thread_view._update_stack_ui(thread_data)
            await pilot.pause()

            tree = thread_view.query_one("#thread-stack-tree", Tree)
            root = tree.root

            # Root should show thread info
            root_label = str(root.label)
            assert "IdleThread" in root_label

            # Should have one leaf child with "No stack frames available"
            assert len(root.children) == 1
            leaf_label = str(root.children[0].label)
            assert "No stack frames available" in leaf_label

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_action_refresh(self, mock_client_factory):
        """action_refresh triggers _refresh_threads sending thread list command."""
        client = mock_client_factory(
            responses={
                "thread": {
                    "status": "success",
                    "total": 0,
                    "threads": [],
                },
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

            thread_view = app.screen.query_one("ThreadView", ThreadView)
            thread_view.set_client(client)
            await pilot.pause()
            await pilot.pause()

            initial_cmd_count = len(client.commands_received)

            # Trigger refresh action
            thread_view.action_refresh()
            await pilot.pause()
            await pilot.pause()

            # Should have sent additional thread list command(s)
            new_cmds = client.commands_received[initial_cmd_count:]
            thread_cmds = [c for c in new_cmds if c.get("type") == "thread"]
            assert len(thread_cmds) >= 1
            assert thread_cmds[0].get("action") == "list"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_error_response(self, mock_client_factory):
        """Error response doesn't crash, table stays empty."""
        client = mock_client_factory(
            responses={
                "thread": {"status": "error", "error": "Agent not ready"},
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

            thread_view = app.screen.query_one("ThreadView", ThreadView)
            thread_view.set_client(client)
            await pilot.pause()
            await pilot.pause()

            # Table should stay empty on error
            table = thread_view.query_one("#threads-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_no_client_connected(self):
        """No client set, _refresh_threads does nothing gracefully."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            thread_view = app.screen.query_one("ThreadView", ThreadView)

            # No client set — action_refresh should not crash
            thread_view.action_refresh()
            await pilot.pause()

            table = thread_view.query_one("#threads-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_thread_state_badges(self, mock_client_factory):
        """RUNNABLE/WAITING/TIMED_WAITING states shown with correct markup in table."""
        client = mock_client_factory(
            responses={
                "thread": {
                    "status": "success",
                    "total": 3,
                    "threads": [
                        {
                            "tid": 1,
                            "name": "T1",
                            "state": "RUNNABLE",
                            "daemon": False,
                            "stack_depth": 1,
                            "top_frame": None,
                        },
                        {
                            "tid": 2,
                            "name": "T2",
                            "state": "WAITING",
                            "daemon": False,
                            "stack_depth": 1,
                            "top_frame": None,
                        },
                        {
                            "tid": 3,
                            "name": "T3",
                            "state": "TIMED_WAITING",
                            "daemon": False,
                            "stack_depth": 1,
                            "top_frame": None,
                        },
                    ],
                },
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

            thread_view = app.screen.query_one("ThreadView", ThreadView)
            thread_view.set_client(client)
            await pilot.pause()
            await pilot.pause()

            table = thread_view.query_one("#threads-table", DataTable)
            assert table.row_count == 3

            # Verify state column content (column index 2)
            row0 = table.get_row_at(0)
            row1 = table.get_row_at(1)
            row2 = table.get_row_at(2)

            # Rich markup is rendered in DataTable cells, check plain text
            assert "RUNNABLE" in str(row0)
            assert "WAITING" in str(row1)
            assert "TIMED_WAIT" in str(row2)

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_top_frame_filename_shortened(self, mock_client_factory):
        """Long filenames in top_frame are shortened to basename."""
        client = mock_client_factory(
            responses={
                "thread": {
                    "status": "success",
                    "total": 1,
                    "threads": [
                        {
                            "tid": 1,
                            "name": "Main",
                            "state": "RUNNABLE",
                            "daemon": False,
                            "stack_depth": 1,
                            "top_frame": {
                                "filename": "/very/long/path/to/module.py",
                                "lineno": 42,
                                "funcname": "handler",
                            },
                        },
                    ],
                },
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

            thread_view = app.screen.query_one("ThreadView", ThreadView)
            thread_view.set_client(client)
            await pilot.pause()
            await pilot.pause()

            table = thread_view.query_one("#threads-table", DataTable)
            row0 = table.get_row_at(0)
            row0_str = str(row0)

            # Should show shortened filename, not full path
            assert "module.py" in row0_str
            assert "handler" in row0_str
            # Full path should not appear in row
            assert "/very/long/path/to/" not in row0_str
