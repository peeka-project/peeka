"""Tests for TraceView - streaming, call tree, and error handling."""

import pytest
from textual.widgets import DataTable, Tree, Static, Input

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.trace import TraceView
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput


class TestTraceView:
    """Test TraceView call tree rendering, streaming, and error handling."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_start_trace_sends_command(self, mock_client_factory):
        """Enter pattern and trigger trace, verify trace command sent with correct parameters."""
        client = mock_client_factory(
            responses={
                "trace": {
                    "status": "success",
                    "watch_id": "trace_001",
                }
            }
        )
        client.connect()

        stream_client = mock_client_factory(observations=[])
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            # Set pattern and depth
            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            depth_input = trace_view.query_one("#trace-depth", Input)
            depth_input.value = "3"

            # Start trace
            await trace_view._start_trace()
            await pilot.pause()

            # Verify command sent
            trace_commands = [
                cmd for cmd in client.commands_received if cmd.get("type") == "trace"
            ]
            assert len(trace_commands) == 1
            trace_command = trace_commands[0]
            assert trace_command["action"] == "start"
            assert trace_command["pattern"] == "module.func"
            assert trace_command["depth"] == 3
            assert trace_command["skip_builtin"] is True

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_observation_populates_tree(self, mock_client_factory):
        """Configure mock with observation containing call_tree, verify Tree widget populated."""
        client = mock_client_factory(
            responses={
                "trace": {
                    "status": "success",
                    "watch_id": "trace_001",
                }
            }
        )
        client.connect()

        stream_client = mock_client_factory(
            observations=[
                {
                    "watch_id": "trace_001",
                    "func_name": "module.func",
                    "call_tree": [
                        {
                            "depth": 0,
                            "function": "func",
                            "duration_ms": 10.5,
                            "filename": "module.py",
                            "lineno": 42,
                            "children": [],
                        }
                    ],
                    "total_duration_ms": 10.5,
                    "node_count": 1,
                    "count": 1,
                }
            ]
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()  # Wait for worker to process

            # Verify tree populated
            tree = trace_view.query_one("#call-tree", Tree)
            assert tree.root.children
            assert len(list(tree.root.children)) >= 1

            # Verify node label contains function name and duration
            first_node = list(tree.root.children)[0]
            node_label = str(first_node.label)
            assert "func" in node_label
            assert "10.5" in node_label or "10.50" in node_label

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_call_tree_depth(self, mock_client_factory):
        """Verify nested call_tree nodes with children render at correct depths in Tree."""
        client = mock_client_factory(
            responses={
                "trace": {
                    "status": "success",
                    "watch_id": "trace_001",
                }
            }
        )
        client.connect()

        stream_client = mock_client_factory(
            observations=[
                {
                    "watch_id": "trace_001",
                    "func_name": "module.outer",
                    "call_tree": [
                        {
                            "depth": 0,
                            "function": "outer",
                            "duration_ms": 50.0,
                            "filename": "module.py",
                            "lineno": 10,
                            "children": [
                                {
                                    "depth": 1,
                                    "function": "middle",
                                    "duration_ms": 30.0,
                                    "filename": "module.py",
                                    "lineno": 20,
                                    "children": [
                                        {
                                            "depth": 2,
                                            "function": "inner",
                                            "duration_ms": 10.0,
                                            "filename": "module.py",
                                            "lineno": 30,
                                            "children": [],
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                    "total_duration_ms": 50.0,
                    "node_count": 3,
                    "count": 1,
                }
            ]
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.outer"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            # Verify tree has nested structure
            tree = trace_view.query_one("#call-tree", Tree)
            assert tree.root.children

            # Check first level (outer)
            outer_node = list(tree.root.children)[0]
            outer_label = str(outer_node.label)
            assert "outer" in outer_label
            assert "50" in outer_label

            # Check second level (middle)
            assert outer_node.children
            middle_node = list(outer_node.children)[0]
            middle_label = str(middle_node.label)
            assert "middle" in middle_label
            assert "30" in middle_label

            # Check third level (inner)
            assert middle_node.children
            inner_node = list(middle_node.children)[0]
            inner_label = str(inner_node.label)
            assert "inner" in inner_label
            assert "10" in inner_label

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_duration_display(self, mock_client_factory):
        """Verify total_duration_ms and per-node duration_ms displayed correctly."""
        client = mock_client_factory(
            responses={
                "trace": {
                    "status": "success",
                    "watch_id": "trace_001",
                }
            }
        )
        client.connect()

        stream_client = mock_client_factory(
            observations=[
                {
                    "watch_id": "trace_001",
                    "func_name": "module.func",
                    "call_tree": [
                        {
                            "depth": 0,
                            "function": "slow_func",
                            "duration_ms": 150.25,
                            "filename": "module.py",
                            "lineno": 100,
                            "children": [],
                        }
                    ],
                    "total_duration_ms": 150.25,
                    "node_count": 1,
                    "count": 1,
                }
            ]
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            # Verify tree node has duration
            tree = trace_view.query_one("#call-tree", Tree)
            first_node = list(tree.root.children)[0]
            node_label = str(first_node.label)
            assert "150.25" in node_label or "150" in node_label

            # Verify stats display has total duration
            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = stats.render()
            assert "150.25" in str(stats_text) or "150" in str(stats_text)

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_summary_stats(self, mock_client_factory):
        """Verify DataTable shows node_count and timing stats from observation."""
        client = mock_client_factory(
            responses={
                "trace": {
                    "status": "success",
                    "watch_id": "trace_001",
                }
            }
        )
        client.connect()

        stream_client = mock_client_factory(
            observations=[
                {
                    "watch_id": "trace_001",
                    "func_name": "calculator.compute",
                    "call_tree": [
                        {
                            "depth": 0,
                            "function": "compute",
                            "duration_ms": 25.5,
                            "filename": "calc.py",
                            "lineno": 50,
                            "children": [
                                {
                                    "depth": 1,
                                    "function": "helper",
                                    "duration_ms": 10.0,
                                    "filename": "calc.py",
                                    "lineno": 60,
                                    "children": [],
                                }
                            ],
                        }
                    ],
                    "total_duration_ms": 25.5,
                    "node_count": 2,
                    "count": 1,
                }
            ]
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            # Verify DataTable has trace entry
            table = trace_view.query_one("#trace-table", DataTable)
            assert table.row_count == 1

            # Verify stats display shows node count and duration
            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())
            assert "2" in stats_text  # node_count
            assert "25.5" in stats_text or "25" in stats_text  # total_duration_ms

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_error_response(self, mock_client_factory):
        """Mock returns error, verify error shown and no worker started."""
        client = mock_client_factory(
            responses={
                "trace": {
                    "status": "error",
                    "error": "Pattern not found",
                }
            }
        )
        client.connect()

        stream_client = mock_client_factory(observations=[])
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "invalid.pattern"

            await trace_view._start_trace()
            await pilot.pause()

            # Verify error command sent
            trace_commands = [
                cmd for cmd in client.commands_received if cmd.get("type") == "trace"
            ]
            assert len(trace_commands) == 1

            # Verify no trace added to table
            table = trace_view.query_one("#trace-table", DataTable)
            assert table.row_count == 0

            # Verify no active traces
            assert len(trace_view._active_traces) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_empty_pattern(self, mock_client_factory):
        """Submit empty pattern, verify validation prevents command."""
        client = mock_client_factory(responses={})
        client.connect()

        stream_client = mock_client_factory(observations=[])
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            # Leave pattern empty
            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = ""

            await trace_view._start_trace()
            await pilot.pause()

            # Verify no command sent
            trace_commands = [
                cmd for cmd in client.commands_received if cmd.get("type") == "trace"
            ]
            assert len(trace_commands) == 0

            # Verify no trace in table
            table = trace_view.query_one("#trace-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_invalid_depth(self, mock_client_factory):
        """Submit invalid depth value, verify validation prevents command."""
        client = mock_client_factory(responses={})
        client.connect()

        stream_client = mock_client_factory(observations=[])
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            depth_input = trace_view.query_one("#trace-depth", Input)
            depth_input.value = "invalid"

            await trace_view._start_trace()
            await pilot.pause()

            # Verify no command sent
            trace_commands = [
                cmd for cmd in client.commands_received if cmd.get("type") == "trace"
            ]
            assert len(trace_commands) == 0

            # Verify no trace in table
            table = trace_view.query_one("#trace-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_depth_out_of_range(self, mock_client_factory):
        """Submit depth outside 1-5 range, verify validation."""
        client = mock_client_factory(responses={})
        client.connect()

        stream_client = mock_client_factory(observations=[])
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            # Test depth too high
            depth_input = trace_view.query_one("#trace-depth", Input)
            depth_input.value = "10"

            await trace_view._start_trace()
            await pilot.pause()

            # Verify no command sent
            trace_commands = [
                cmd for cmd in client.commands_received if cmd.get("type") == "trace"
            ]
            assert len(trace_commands) == 0

            # Verify no trace in table
            table = trace_view.query_one("#trace-table", DataTable)
            assert table.row_count == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_multiple_trace_observations(self, mock_client_factory):
        """Multiple observations update count and refresh tree display."""
        client = mock_client_factory(
            responses={
                "trace": {
                    "status": "success",
                    "watch_id": "trace_001",
                }
            }
        )
        client.connect()

        stream_client = mock_client_factory(
            observations=[
                {
                    "watch_id": "trace_001",
                    "func_name": "module.func",
                    "call_tree": [
                        {
                            "depth": 0,
                            "function": "func",
                            "duration_ms": 5.0,
                            "filename": "mod.py",
                            "lineno": 10,
                            "children": [],
                        }
                    ],
                    "total_duration_ms": 5.0,
                    "node_count": 1,
                    "count": 1,
                },
                {
                    "watch_id": "trace_001",
                    "func_name": "module.func",
                    "call_tree": [
                        {
                            "depth": 0,
                            "function": "func",
                            "duration_ms": 7.5,
                            "filename": "mod.py",
                            "lineno": 10,
                            "children": [],
                        }
                    ],
                    "total_duration_ms": 7.5,
                    "node_count": 1,
                    "count": 2,
                },
            ]
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause(0.2)
            await pilot.pause()

            # Verify count updated in table
            table = trace_view.query_one("#trace-table", DataTable)
            assert table.row_count == 1
            row_data = table.get_row_at(0)
            # Count should be 2 after two observations
            assert "2" in str(row_data)

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_wrapper_only_observation_runtime_meta_renders_backend(
        self, mock_client_factory
    ):
        """Wrapper-only trace observations should drive the backend display."""
        client = mock_client_factory(
            responses={
                "trace": {
                    "status": "success",
                    "watch_id": "trace_001",
                }
            }
        )
        client.connect()

        stream_client = mock_client_factory(
            observations=[
                {
                    "watch_id": "trace_001",
                    "func_name": "calculator.compute",
                    "call_tree": [],
                    "total_duration_ms": 25.5,
                    "node_count": 1,
                    "count": 1,
                    "runtime_meta": {
                        "trace": {
                            "startup_backend": "wrapper_only",
                            "effective_backend": "wrapper_only",
                            "downgraded": True,
                            "downgrade_reason": "gevent_patched_runtime",
                            "gevent_patched_now": True,
                        }
                    },
                }
            ]
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())
            assert "Backend: wrapper_only" in stats_text
            assert "Gevent: patched" in stats_text
            assert "Backend: profiler (full)" not in stats_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_runtime_meta_display(self, mock_client_factory):
        """Verify runtime_meta is displayed in the trace stats panel."""
        client = mock_client_factory(
            responses={
                "trace": {
                    "status": "success",
                    "watch_id": "trace_001",
                }
            }
        )
        client.connect()

        # Test with runtime_meta
        stream_client_with_meta = mock_client_factory(
            observations=[
                {
                    "watch_id": "trace_001",
                    "func_name": "calculator.compute",
                    "call_tree": [],
                    "total_duration_ms": 25.5,
                    "node_count": 2,
                    "count": 1,
                    "runtime_meta": {
                        "trace": {
                            "downgraded": True,
                            "effective_backend": "wrapper_only",
                            "gevent_patched_now": True,
                        }
                    },
                }
            ]
        )
        stream_client_with_meta.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client_with_meta

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())
            assert "Backend: wrapper_only" in stats_text
            assert "Backend: profiler (full)" not in stats_text
            assert "Gevent: patched" in stats_text

        # Test without runtime_meta
        stream_client_no_meta = mock_client_factory(
            observations=[
                {
                    "watch_id": "trace_001",
                    "func_name": "calculator.compute",
                    "call_tree": [],
                    "total_duration_ms": 25.5,
                    "node_count": 2,
                    "count": 1,
                }
            ]
        )
        stream_client_no_meta.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client_no_meta

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())
            assert "Backend: profiler (full)" in stats_text
