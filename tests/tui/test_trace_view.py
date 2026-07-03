"""Tests for TraceView - streaming, call tree, and error handling."""

import pytest
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import DataTable, Input, Static, Tree

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

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            min_duration_input = trace_view.query_one("#trace-min-duration", Input)
            min_duration_input.value = "5"

            await trace_view._start_trace()
            await pilot.pause()

            trace_commands = [
                cmd for cmd in client.commands_received if cmd.get("type") == "trace"
            ]
            assert len(trace_commands) == 1
            trace_command = trace_commands[0]
            assert trace_command["action"] == "start"
            assert trace_command["pattern"] == "module.func"
            assert "depth" not in trace_command
            assert trace_command["min_duration"] == 5
            assert trace_command["skip_builtin"] is True

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_observation_populates_tree(self, mock_client_factory):
        """Configure mock with flat observation, verify obs node in Tree widget."""
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
                    "total_duration_ms": 10.5,
                    "self_time_ms": 1.23,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [
                        {
                            "function": "__main__.func",
                            "filename": "module.py",
                            "lineno": 42,
                            "count": 1,
                            "total_ms": 1.23,
                            "min_ms": 1.23,
                            "max_ms": 1.23,
                        }
                    ],
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
            trace_view._selected_pattern = "module.func"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            assert tree.root.children
            assert len(list(tree.root.children)) >= 1

            first_node = next(n for n in tree.root.children if "obs #" in str(n.label))
            node_label = str(first_node.label)
            assert "obs #" in node_label
            assert "total=" in node_label

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_duration_display(self, mock_client_factory):
        """Verify total_duration_ms displayed correctly in obs node label and stats."""
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
                    "total_duration_ms": 150.25,
                    "self_time_ms": 0.0,
                    "callee_count": 1,
                    "node_count": 1,
                    "call_tree": [
                        {
                            "function": "slow_func",
                            "filename": "module.py",
                            "lineno": 100,
                            "count": 1,
                            "total_ms": 150.25,
                            "min_ms": 150.25,
                            "max_ms": 150.25,
                        }
                    ],
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
            trace_view._selected_pattern = "module.func"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            first_node = next(n for n in tree.root.children if "obs #" in str(n.label))
            node_label = str(first_node.label)
            assert "150.250" in node_label or "150." in node_label

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())
            assert "150.250" in stats_text or "150.25" in stats_text or "150" in stats_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_callee_shows_percentage_of_parent(self, mock_client_factory):
        """Callee node label shows percentage relative to parent observation."""
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
                    "total_duration_ms": 10.0,
                    "self_time_ms": 1.0,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [
                        {
                            "function": "calculator.helper",
                            "filename": "calc.py",
                            "lineno": 20,
                            "count": 1,
                            "total_ms": 3.0,
                            "min_ms": 3.0,
                            "max_ms": 3.0,
                        }
                    ],
                }
            ]
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 32)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client
            trace_view._selected_pattern = "calculator.compute"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            obs_node = next(n for n in tree.root.children if "obs #" in str(n.label))
            callee_node = list(obs_node.children)[0]
            label_text = getattr(callee_node.label, "plain", str(callee_node.label))
            assert "pct=30.0%" in label_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_callee_percentage_color_thresholds(self, mock_client_factory):
        """Callee percentage label uses red and green threshold styling."""
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
                    "total_duration_ms": 100.0,
                    "self_time_ms": 1.0,
                    "callee_count": 2,
                    "node_count": 3,
                    "call_tree": [
                        {
                            "function": "slow_helper",
                            "filename": "calc.py",
                            "lineno": 20,
                            "count": 1,
                            "total_ms": 60.0,
                            "min_ms": 60.0,
                            "max_ms": 60.0,
                        },
                        {
                            "function": "fast_helper",
                            "filename": "calc.py",
                            "lineno": 21,
                            "count": 1,
                            "total_ms": 2.0,
                            "min_ms": 2.0,
                            "max_ms": 2.0,
                        },
                    ],
                }
            ]
        )
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 32)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client
            trace_view._selected_pattern = "calculator.compute"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            obs_node = next(n for n in tree.root.children if "obs #" in str(n.label))
            slow_node = list(obs_node.children)[0]
            fast_node = list(obs_node.children)[1]

            slow_label = getattr(slow_node.label, "plain", str(slow_node.label))
            slow_spans = getattr(slow_node.label, "spans", [])
            assert "pct=60.0%" in slow_label
            assert any("red" in str(span.style).lower() for span in slow_spans)

            fast_label = getattr(fast_node.label, "plain", str(fast_node.label))
            fast_spans = getattr(fast_node.label, "spans", [])
            assert "pct=2.0%" in fast_label
            assert any("green" in str(span.style).lower() for span in fast_spans)

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_exception_nodes_are_highlighted(self, mock_client_factory):
        """Exception-bearing observation and callee nodes show throws markers."""
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
                    "total_duration_ms": 11.0,
                    "self_time_ms": 1.0,
                    "callee_count": 1,
                    "node_count": 2,
                    "exception": {
                        "type": "ValueError",
                        "message": "invalid input",
                    },
                    "call_tree": [
                        {
                            "function": "helper",
                            "filename": "calc.py",
                            "lineno": 60,
                            "count": 1,
                            "total_ms": 10.0,
                            "min_ms": 10.0,
                            "max_ms": 10.0,
                            "exception": {
                                "class": "builtins.KeyError",
                                "message": "missing key",
                            },
                        }
                    ],
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
            trace_view._selected_pattern = "calculator.compute"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            obs_node = next(n for n in tree.root.children if "obs #" in str(n.label))
            obs_label = getattr(obs_node.label, "plain", str(obs_node.label))
            assert "throws ValueError" in obs_label
            obs_spans = getattr(obs_node.label, "spans", [])
            assert any(
                "red" in str(span.style).lower() and "bold" in str(span.style).lower()
                for span in obs_spans
            )

            callee_node = list(obs_node.children)[0]
            callee_label = getattr(callee_node.label, "plain", str(callee_node.label))
            assert "throws KeyError" in callee_label
            callee_spans = getattr(callee_node.label, "spans", [])
            assert any(
                "red" in str(span.style).lower() and "bold" in str(span.style).lower()
                for span in callee_spans
            )

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_stats_show_exception_details(self, mock_client_factory):
        """Stats panel shows exception type and message when present."""
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
                    "total_duration_ms": 25.5,
                    "self_time_ms": 0.5,
                    "callee_count": 1,
                    "node_count": 2,
                    "exception": {
                        "type": "ValueError",
                        "message": "invalid input",
                    },
                    "call_tree": [],
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
            trace_view._selected_pattern = "calculator.compute"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())
            assert "Exception: ValueError: invalid input" in stats_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_stats_show_no_exception_state(self, mock_client_factory):
        """Stats panel shows a green dash when no exception is present."""
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
                    "total_duration_ms": 25.5,
                    "self_time_ms": 0.5,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [],
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
            trace_view._selected_pattern = "calculator.compute"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())
            assert "Exception: -" in stats_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_summary_stats(self, mock_client_factory):
        """Verify DataTable shows trace entry; stats shows node_count and duration."""
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
                    "total_duration_ms": 25.5,
                    "self_time_ms": 0.5,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [
                        {
                            "function": "helper",
                            "filename": "calc.py",
                            "lineno": 60,
                            "count": 1,
                            "total_ms": 10.0,
                            "min_ms": 10.0,
                            "max_ms": 10.0,
                        }
                    ],
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
            trace_view._selected_pattern = "calculator.compute"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            obs_table = trace_view.query_one("#trace-obs-table", DataTable)
            assert obs_table.row_count >= 1

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())
            assert "node_count: 2" in stats_text
            assert "25.5" in stats_text or "25" in stats_text

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

            trace_commands = [
                cmd for cmd in client.commands_received if cmd.get("type") == "trace"
            ]
            assert len(trace_commands) == 1

            obs_table = trace_view.query_one("#trace-obs-table", DataTable)
            assert obs_table.row_count == 0

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

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = ""

            await trace_view._start_trace()
            await pilot.pause()

            trace_commands = [
                cmd for cmd in client.commands_received if cmd.get("type") == "trace"
            ]
            assert len(trace_commands) == 0

            obs_table = trace_view.query_one("#trace-obs-table", DataTable)
            assert obs_table.row_count == 0

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
                    "total_duration_ms": 5.0,
                    "self_time_ms": 0.5,
                    "callee_count": 1,
                    "node_count": 1,
                    "call_tree": [
                        {
                            "function": "func",
                            "filename": "mod.py",
                            "lineno": 10,
                            "count": 1,
                            "total_ms": 5.0,
                            "min_ms": 5.0,
                            "max_ms": 5.0,
                        }
                    ],
                },
                {
                    "watch_id": "trace_001",
                    "func_name": "module.func",
                    "total_duration_ms": 7.5,
                    "self_time_ms": 0.8,
                    "callee_count": 1,
                    "node_count": 1,
                    "call_tree": [
                        {
                            "function": "func",
                            "filename": "mod.py",
                            "lineno": 10,
                            "count": 2,
                            "total_ms": 7.5,
                            "min_ms": 5.0,
                            "max_ms": 7.5,
                        }
                    ],
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

            obs_table = trace_view.query_one("#trace-obs-table", DataTable)
            assert obs_table.row_count >= 1
            row_data = obs_table.get_row_at(0)
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
                    "self_time_ms": 0.0,
                    "callee_count": 0,
                    "node_count": 1,
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
            trace_view._selected_pattern = "calculator.compute"

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

        stream_client_with_meta = mock_client_factory(
            observations=[
                {
                    "watch_id": "trace_001",
                    "func_name": "calculator.compute",
                    "call_tree": [],
                    "total_duration_ms": 25.5,
                    "self_time_ms": 0.0,
                    "callee_count": 0,
                    "node_count": 2,
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
            trace_view._selected_pattern = "calculator.compute"

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

        stream_client_no_meta = mock_client_factory(
            observations=[
                {
                    "watch_id": "trace_001",
                    "func_name": "calculator.compute",
                    "call_tree": [],
                    "total_duration_ms": 25.5,
                    "self_time_ms": 0.0,
                    "callee_count": 0,
                    "node_count": 2,
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
            trace_view._selected_pattern = "calculator.compute"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())
            assert "Backend: profiler (full)" in stats_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_no_depth_widget(self, mock_client_factory):
        """#trace-depth must not exist; #trace-min-duration must exist."""
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

            with pytest.raises(NoMatches):
                trace_view.query_one("#trace-depth", Input)

            min_dur = trace_view.query_one("#trace-min-duration", Input)
            assert min_dur is not None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_min_duration_sent_in_command(self, mock_client_factory):
        """Command dict must include min_duration, must NOT include depth."""
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

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            min_dur_input = trace_view.query_one("#trace-min-duration", Input)
            min_dur_input.value = "5"

            await trace_view._start_trace()
            await pilot.pause()

            trace_commands = [
                c for c in client.commands_received if c.get("type") == "trace"
            ]
            assert len(trace_commands) == 1
            assert "depth" not in trace_commands[0]
            assert trace_commands[0]["min_duration"] == 5

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_active_traces_list_populated(self, mock_client_factory):
        """After starting trace, #trace-obs-table shows pattern row."""
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

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await trace_view._start_trace()
            await pilot.pause()

            obs_table = trace_view.query_one("#trace-obs-table", DataTable)
            assert obs_table.row_count >= 1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_observation_tree_two_levels(self, mock_client_factory):
        """Observation parent node with 1 direct callee child — exactly 2 levels."""
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
                    "total_duration_ms": 10.5,
                    "self_time_ms": 1.23,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [
                        {
                            "function": "__main__.Calculator._validate",
                            "filename": "simple_loop.py",
                            "lineno": 8,
                            "count": 1,
                            "total_ms": 1.23,
                            "min_ms": 1.23,
                            "max_ms": 1.23,
                        }
                    ],
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
            trace_view._selected_pattern = "module.func"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            assert tree.root.children
            obs_node = next(n for n in tree.root.children if "obs #" in str(n.label))
            assert "obs #" in str(obs_node.label)

            callee_nodes = list(obs_node.children)
            assert len(callee_nodes) == 1
            label_str = str(callee_nodes[0].label)
            assert "pct=" in label_str
            assert "total=" in label_str
            assert "count=" not in label_str
            assert len(list(callee_nodes[0].children)) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_callee_label_is_compact_and_abbreviated(self, mock_client_factory):
        """Callee label uses logback-style abbreviated name, pct, total only."""
        client = mock_client_factory(
            responses={"trace": {"status": "success", "watch_id": "trace_001"}}
        )
        client.connect()

        stream_client = mock_client_factory(
            observations=[
                {
                    "watch_id": "trace_001",
                    "func_name": "calculator.compute",
                    "total_duration_ms": 10.0,
                    "self_time_ms": 0.0,
                    "callee_count": 1,
                    "node_count": 1,
                    "call_tree": [
                        {
                            "function": "examples.demo.calculator.add",
                            "filename": "calculator.py",
                            "lineno": 42,
                            "count": 1,
                            "total_ms": 5.0,
                            "min_ms": 5.0,
                            "max_ms": 5.0,
                        }
                    ],
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
            trace_view._selected_pattern = "calculator.compute"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            obs_node = next(n for n in tree.root.children if "obs #" in str(n.label))
            callee_node = list(obs_node.children)[0]
            label_text = getattr(callee_node.label, "plain", str(callee_node.label))

            # abbreviated: examples.demo.calculator.add -> e.d.calculator.add
            assert "e.d.calculator.add" in label_text
            assert "pct=50.0%" in label_text
            assert "total=5.000ms" in label_text
            # old verbose fields must NOT be present
            assert "count=" not in label_text
            assert "min=" not in label_text
            assert "max=" not in label_text
            assert "examples.demo." not in label_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_callee_flat_schema_no_children(self, mock_client_factory):
        """call_tree entries use flat schema: function/count/total_ms — no children."""
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
                    "total_duration_ms": 10.5,
                    "self_time_ms": 1.23,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [
                        {
                            "function": "callee_func",
                            "filename": "mod.py",
                            "lineno": 20,
                            "count": 3,
                            "total_ms": 9.27,
                            "min_ms": 2.5,
                            "max_ms": 4.0,
                        }
                    ],
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
            trace_view._selected_pattern = "module.func"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            obs_node = next(n for n in tree.root.children if "obs #" in str(n.label))
            callee_node = list(obs_node.children)[0]
            assert len(list(callee_node.children)) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_empty_call_tree_shows_observation_only(self, mock_client_factory):
        """Empty call_tree: observation node appears but has no callee children."""
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
                    "total_duration_ms": 5.0,
                    "self_time_ms": 5.0,
                    "callee_count": 0,
                    "node_count": 0,
                    "call_tree": [],
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
            trace_view._selected_pattern = "module.func"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            assert tree.root.children
            obs_node = next(n for n in tree.root.children if "obs #" in str(n.label))
            assert "obs #" in str(obs_node.label)
            assert len(list(obs_node.children)) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stats_panel_shows_four_fields(self, mock_client_factory):
        """Stats panel shows total_duration_ms/self_time_ms/callee_count/node_count after obs."""
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
                    "total_duration_ms": 10.5,
                    "self_time_ms": 1.23,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [
                        {
                            "function": "callee_func",
                            "filename": "mod.py",
                            "lineno": 20,
                            "count": 1,
                            "total_ms": 1.23,
                            "min_ms": 1.23,
                            "max_ms": 1.23,
                        }
                    ],
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
            trace_view._selected_pattern = "module.func"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "module.func"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())
            assert "total_duration_ms" in stats_text
            assert "self_time_ms" in stats_text
            assert "callee_count" in stats_text
            assert "node_count" in stats_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_clear_button_resets_trace_list(self, mock_client_factory):
        """Clear button clears #trace-obs-table and resets _observations_by_pattern."""
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
                    "total_duration_ms": 10.5,
                    "self_time_ms": 1.23,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [],
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

            obs_table = trace_view.query_one("#trace-obs-table", DataTable)
            assert obs_table.row_count >= 1

            await trace_view.action_clear_tree()
            await pilot.pause()

            obs_table = trace_view.query_one("#trace-obs-table", DataTable)
            assert obs_table.row_count == 0
            assert trace_view._selected_pattern is None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_runtime_meta_preserved(self, mock_client_factory):
        """runtime_meta backend/gevent info still appears in stats."""
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
                    "self_time_ms": 0.0,
                    "callee_count": 0,
                    "node_count": 1,
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
            trace_view._selected_pattern = "calculator.compute"

            pattern_input = trace_view.query_one("#trace-pattern", AutoCompleteInput)
            pattern_input.value = "calculator.compute"

            await trace_view._start_trace()
            await pilot.pause()
            await pilot.pause()

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())
            assert "Backend:" in stats_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_list_at_top_height_13(self, mock_client_factory):
        """#trace-list must have height=13 and appear above #trace-content."""
        client = mock_client_factory(responses={})
        client.connect()
        stream_client = mock_client_factory(observations=[])
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(80, 30)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            main_screen.action_switch_tab("trace")
            await pilot.pause()

            trace_list = trace_view.query_one("#trace-list", Vertical)
            assert trace_list.region.height == 13

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_bottom_panel_2to1_ratio(self, mock_client_factory):
        """#trace-tree-panel must be ~2x wider than #trace-stats-panel (±2 px)."""
        client = mock_client_factory(responses={})
        client.connect()
        stream_client = mock_client_factory(observations=[])
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client

            main_screen.action_switch_tab("trace")
            await pilot.pause()

            tree_panel = trace_view.query_one("#trace-tree-panel", Vertical)
            stats_panel = trace_view.query_one("#trace-stats-panel", Vertical)

            assert tree_panel.region.x < stats_panel.region.x
            assert tree_panel.region.y == stats_panel.region.y
            assert abs(tree_panel.region.width - 2 * stats_panel.region.width) <= 2

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_aggregated_callees_group_same_function(self, mock_client):
        mock_client.connect()
        app = PeekaApp()
        async with app.run_test(size=(120, 32)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()
            main_screen.action_switch_tab("trace")
            await pilot.pause()
            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(mock_client)
            trace_view._selected_pattern = "calculator.compute"
            trace_view._observations_by_pattern["calculator.compute"] = [
                {
                    "_count": i,
                    "func_name": "calculator.compute",
                    "total_duration_ms": 10.0,
                    "self_time_ms": 1.0,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [
                        {
                            "function": "calculator.helper",
                            "filename": "calc.py",
                            "lineno": 20,
                            "count": 1,
                            "total_ms": total,
                            "min_ms": total,
                            "max_ms": total,
                        }
                    ],
                }
                for i, total in enumerate([1.0, 2.0, 3.0], start=1)
            ]
            trace_view._build_observation_tree("calculator.compute")
            await pilot.pause()
            tree = app.screen.query_one("#call-tree", Tree)
            agg_root = next(
                n for n in tree.root.children if str(n.label) == "Aggregated Callees"
            )
            agg_root.expand()
            await pilot.pause()
            agg_node = agg_root.children[0]
            label_text = str(agg_node.label)
            assert "pct=" in label_text
            assert "total=6.000ms" in label_text
            assert "count=3" not in label_text
            assert "avg=2.000ms" not in label_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_callee_selection_updates_stats_panel(self, mock_client_factory):
        """Selecting a callee node updates Stats panel with full details."""
        client = mock_client_factory(
            responses={"trace": {"status": "success", "watch_id": "trace_001"}}
        )
        client.connect()

        callee_data = {
            "function": "examples.demo.calculator.add",
            "filename": "calculator.py",
            "lineno": 42,
            "count": 2,
            "total_ms": 5.0,
            "min_ms": 1.0,
            "max_ms": 4.0,
        }
        obs_data = {
            "watch_id": "trace_001",
            "func_name": "calculator.compute",
            "total_duration_ms": 10.0,
            "self_time_ms": 0.0,
            "callee_count": 1,
            "node_count": 1,
            "_count": 1,
            "call_tree": [callee_data],
        }

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._selected_pattern = "calculator.compute"
            trace_view._observations_by_pattern["calculator.compute"] = [obs_data]

            trace_view._build_observation_tree("calculator.compute")
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            obs_node = next(
                n for n in tree.root.children if n.data and n.data.get("type") == "observation"
            )
            callee_node = next(
                n for n in obs_node.children if n.data and n.data.get("type") == "callee"
            )
            event = Tree.NodeHighlighted(callee_node)
            trace_view.on_tree_node_highlighted(event)
            await pilot.pause()

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())

            assert "examples.demo.calculator.add" in stats_text
            assert "Count" in stats_text and "2" in stats_text
            assert "Total" in stats_text and "5.000" in stats_text
            assert "Min" in stats_text and "1.000" in stats_text
            assert "Max" in stats_text and "4.000" in stats_text
            assert "calculator.py:42" in stats_text
            assert "50.0" in stats_text  # percentage

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_aggregated_callee_root_selection_clears_stats(self, mock_client):
        """Selecting the Aggregated Callees root node shows a selection hint."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(mock_client)

            # Build tree with aggregated callees node
            obs = {
                "watch_id": "trace_001",
                "func_name": "calculator.compute",
                "total_duration_ms": 10.0,
                "self_time_ms": 0.0,
                "callee_count": 1,
                "node_count": 1,
                "_count": 1,
                "call_tree": [
                    {
                        "function": "calculator.add",
                        "filename": "calc.py",
                        "lineno": 10,
                        "count": 1,
                        "total_ms": 5.0,
                        "min_ms": 5.0,
                        "max_ms": 5.0,
                    }
                ],
            }
            trace_view._selected_pattern = "calculator.compute"
            trace_view._observations_by_pattern["calculator.compute"] = [obs]
            trace_view._build_observation_tree("calculator.compute")
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            agg_root = next(
                n for n in tree.root.children if str(n.label) == "Aggregated Callees"
            )

            # Simulate selecting the aggregated root node
            event = Tree.NodeHighlighted(agg_root)
            trace_view.on_tree_node_highlighted(event)
            await pilot.pause()

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())
            assert "Select a callee" in stats_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_aggregated_callee_selection_updates_stats_panel(self, mock_client):
        """Selecting an aggregated-callee child node updates Stats with full aggregate details."""
        mock_client.connect()

        obs1 = {
            "watch_id": "trace_001",
            "func_name": "calculator.compute",
            "total_duration_ms": 10.0,
            "self_time_ms": 0.0,
            "callee_count": 1,
            "node_count": 1,
            "_count": 1,
            "call_tree": [
                {
                    "function": "examples.demo.calculator.add",
                    "filename": "calculator.py",
                    "lineno": 42,
                    "count": 2,
                    "total_ms": 4.0,
                    "min_ms": 1.5,
                    "max_ms": 2.5,
                }
            ],
        }
        obs2 = {
            "watch_id": "trace_001",
            "func_name": "calculator.compute",
            "total_duration_ms": 10.0,
            "self_time_ms": 0.0,
            "callee_count": 1,
            "node_count": 1,
            "_count": 2,
            "call_tree": [
                {
                    "function": "examples.demo.calculator.add",
                    "filename": "calculator.py",
                    "lineno": 42,
                    "count": 1,
                    "total_ms": 2.0,
                    "min_ms": 2.0,
                    "max_ms": 2.0,
                }
            ],
        }

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(mock_client)
            trace_view._selected_pattern = "calculator.compute"
            trace_view._observations_by_pattern["calculator.compute"] = [obs1, obs2]
            trace_view._build_observation_tree("calculator.compute")
            await pilot.pause()

            tree = trace_view.query_one("#call-tree", Tree)
            agg_root = next(
                n for n in tree.root.children if str(n.label) == "Aggregated Callees"
            )
            agg_root.expand()
            await pilot.pause()

            agg_child = agg_root.children[0]
            assert agg_child.data is not None
            assert agg_child.data.get("type") == "aggregated_callee"

            # Trigger via the full event dispatch chain
            event = Tree.NodeHighlighted(agg_child)
            trace_view.on_tree_node_highlighted(event)
            await pilot.pause()

            stats = trace_view.query_one("#trace-stats", Static)
            stats_text = str(stats.render())

            assert "examples.demo.calculator.add" in stats_text
            assert "Count" in stats_text
            assert "Total" in stats_text and "6.000" in stats_text
            assert "30.0" in stats_text
            assert "Location" in stats_text and "calculator.py" in stats_text

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_no_aggregated_callees_without_observations(self, mock_client):
        mock_client.connect()
        app = PeekaApp()
        async with app.run_test(size=(120, 32)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()
            main_screen.action_switch_tab("trace")
            await pilot.pause()
            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(mock_client)
            trace_view._selected_pattern = "calculator.compute"
            trace_view._build_observation_tree("calculator.compute")
            await pilot.pause()
            tree = app.screen.query_one("#call-tree", Tree)
            assert not any(
                str(n.label) == "Aggregated Callees" for n in tree.root.children
            )

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_drill_trace_from_callee_node(self, mock_client_factory):
        client = mock_client_factory(
            responses={
                "trace": {"status": "success", "watch_id": "trace_drill_001"},
            }
        )
        client.connect()
        stream_client = mock_client_factory(observations=[])
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 32)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()
            main_screen.action_switch_tab("trace")
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client
            trace_view._selected_pattern = "calculator.compute"
            trace_view._observations_by_pattern["calculator.compute"] = [
                {
                    "_count": 1,
                    "func_name": "calculator.compute",
                    "total_duration_ms": 10.0,
                    "self_time_ms": 1.0,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [
                        {
                            "function": "calculator.helper",
                            "filename": "calc.py",
                            "lineno": 20,
                            "count": 1,
                            "total_ms": 3.0,
                            "min_ms": 3.0,
                            "max_ms": 3.0,
                        }
                    ],
                }
            ]
            trace_view._build_observation_tree("calculator.compute")
            await pilot.pause()

            tree = app.screen.query_one("#call-tree", Tree)
            obs_node = next(
                n for n in tree.root.children if "obs #" in str(n.label)
            )
            callee_node = list(obs_node.children)[0]
            tree.select_node(callee_node)

            await trace_view.action_drill_trace()
            await pilot.pause()

            trace_commands = [
                c
                for c in client.commands_received
                if c.get("type") == "trace" and c.get("action") == "start"
            ]
            assert len(trace_commands) == 1
            assert trace_commands[0]["pattern"] == "calculator.helper"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_drill_trace_from_observation_node_warns(self, mock_client_factory):
        client = mock_client_factory(responses={})
        client.connect()
        stream_client = mock_client_factory(observations=[])
        stream_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 32)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()
            main_screen.action_switch_tab("trace")
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)
            trace_view._stream_client = stream_client
            trace_view._selected_pattern = "calculator.compute"
            trace_view._observations_by_pattern["calculator.compute"] = [
                {
                    "_count": 1,
                    "func_name": "calculator.compute",
                    "total_duration_ms": 10.0,
                    "self_time_ms": 1.0,
                    "callee_count": 1,
                    "node_count": 2,
                    "call_tree": [
                        {
                            "function": "calculator.helper",
                            "filename": "calc.py",
                            "lineno": 20,
                            "count": 1,
                            "total_ms": 3.0,
                            "min_ms": 3.0,
                            "max_ms": 3.0,
                        }
                    ],
                }
            ]
            trace_view._build_observation_tree("calculator.compute")
            await pilot.pause()

            tree = app.screen.query_one("#call-tree", Tree)
            obs_node = next(
                n for n in tree.root.children if "obs #" in str(n.label)
            )
            tree.select_node(obs_node)

            before_count = len(client.commands_received)
            await trace_view.action_drill_trace()
            await pilot.pause()
            after_count = len(client.commands_received)

            assert after_count == before_count

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_clear_action_stops_active_trace(self, mock_client_factory):
        """action_clear_tree stops running trace, empties obs_table and _active_traces."""
        client = mock_client_factory(
            responses={
                "trace": {"status": "success", "watch_id": "trace_001"},
                "reset": {"status": "success"},
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
            pattern_input.value = "module.func"

            await trace_view._start_trace()
            await pilot.pause()

            obs_table = trace_view.query_one("#trace-obs-table", DataTable)
            assert obs_table.row_count >= 1
            assert len(trace_view._active_traces) >= 1

            await trace_view.action_clear_tree()
            await pilot.pause()

            assert trace_view._active_traces == {}
            obs_table = trace_view.query_one("#trace-obs-table", DataTable)
            assert obs_table.row_count == 0
            assert trace_view._observations_by_pattern == {}

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_clear_action_stops_active_trace_c_key_binding_present(self, mock_client_factory):
        """'c' key binding maps to action_clear_tree on TraceView."""
        client = mock_client_factory(responses={})
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)

            bindings = {b.key: b.action for b in trace_view.BINDINGS}
            assert "c" in bindings, "Expected 'c' key binding on TraceView"
            assert bindings["c"] == "clear_tree", (
                f"Expected 'c' → 'clear_tree', got {bindings['c']!r}"
            )

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_clear_with_empty_traces_no_stop_command(self, mock_client_factory):
        """Clear on empty _active_traces clears UI without sending any stop command."""
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

            assert trace_view._active_traces == {}

            await pilot.press("c")
            await pilot.pause()

            stop_commands = [
                cmd for cmd in client.commands_received
                if cmd.get("type") in ("trace", "reset")
            ]
            assert stop_commands == []

            obs_table = trace_view.query_one("#trace-obs-table", DataTable)
            assert obs_table.row_count == 0
            assert trace_view._selected_pattern is None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_count_exceeds_obs_list_cap(self, mock_client_factory):
        """Count in obs_table reflects real cumulative count, not capped obs_list length."""
        client = mock_client_factory(responses={})
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)

            pattern = "some.func"
            watch_id = "wid_count_test"
            obs_table = trace_view.query_one("#trace-obs-table", DataTable)
            obs_table.add_row(pattern, "Running", "0", key=pattern)
            trace_view._active_traces[watch_id] = {
                "pattern": pattern,
                "worker": None,
                "count": 0,
            }

            obs_template = {
                "call_tree": [],
                "total_duration_ms": 1.0,
                "self_time_ms": 0.0,
                "func_name": pattern,
            }
            for i in range(1, 151):
                trace_view._add_trace_observation(
                    watch_id, i, dict(obs_template)
                )

            await pilot.pause()

            cell_value = obs_table.get_cell(pattern, "Count")
            assert cell_value == "150", (
                f"Expected Count='150', got '{cell_value}' — "
                "obs_list cap must not limit the displayed count"
            )
            assert len(trace_view._observations_by_pattern[pattern]) == 100, (
                "obs_list should still be capped at 100 entries"
            )

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_aggregate_preserves_min_ms_zero(self, mock_client_factory):
        """_build_aggregated_callees_node preserves min_ms=0.0 as valid minimum."""
        client = mock_client_factory(responses={})
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(client)

            pattern = "some.func"
            callee_key = {
                "function": "child.fn",
                "filename": "child.py",
                "lineno": 10,
            }

            obs1 = {
                "total_duration_ms": 1.0,
                "self_time_ms": 0.0,
                "func_name": pattern,
                "call_tree": [
                    {**callee_key, "count": 1, "total_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0},
                ],
            }
            obs2 = {
                "total_duration_ms": 6.0,
                "self_time_ms": 0.0,
                "func_name": pattern,
                "call_tree": [
                    {**callee_key, "count": 1, "total_ms": 5.0, "min_ms": 5.0, "max_ms": 5.0},
                ],
            }

            trace_view._observations_by_pattern[pattern] = [obs1, obs2]

            aggregate_root = trace_view._build_aggregated_callees_node(pattern)
            await pilot.pause()

            assert aggregate_root is not None, "_build_aggregated_callees_node returned None"
            aggregates = aggregate_root.data["aggregates"]
            assert len(aggregates) == 1, f"Expected 1 aggregate, got {len(aggregates)}"
            agg = aggregates[0]
            assert agg["min_ms"] == 0.0, (
                f"Expected min_ms=0.0, got {agg['min_ms']} — "
                "min_ms=0.0 must not be treated as 'no data' and discarded"
            )
