"""Tests for cleanup_for_exit() and on_unmount() in streaming views.

Verifies that watch, trace, stack, and monitor views properly:
- Cancel active workers
- Send stop commands for each active watch/trace/monitor
- Send reset commands to restore instrumented functions (watch/trace/stack)
- Clear internal tracking state
- Disconnect stream clients
"""

import pytest
from unittest.mock import MagicMock
from typing import Any, Dict, List, Optional

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.watch import WatchView
from peeka.tui.views.trace import TraceView
from peeka.tui.views.stack import StackView
from peeka.tui.views.monitor import MonitorView


class TestWatchViewCleanup:
    """Test WatchView.cleanup_for_exit() sends stop+reset and clears state."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_sends_stop_and_reset(self, mock_client_factory):
        """cleanup_for_exit sends stop for each watch_id and reset for each pattern."""
        client = mock_client_factory(
            responses={
                "watch": {"status": "success", "watch_id": "w1"},
                "reset": {"status": "success"},
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

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(client)

            # Simulate active watches with workers
            mock_worker1 = MagicMock()
            mock_worker2 = MagicMock()
            watch_view._active_watches = {
                "w1": {"pattern": "module.func1", "worker": mock_worker1},
                "w2": {"pattern": "module.func2", "worker": mock_worker2},
            }

            # Set up stream client to verify disconnect
            stream_client = mock_client_factory()
            stream_client.connect()
            watch_view._stream_client = stream_client

            # Clear commands from set_client
            client.commands_received.clear()

            watch_view.cleanup_for_exit()

            # Verify workers were cancelled
            mock_worker1.cancel.assert_called_once()
            mock_worker2.cancel.assert_called_once()

            # Verify stop commands sent for each watch_id
            stop_cmds = [
                cmd
                for cmd in client.commands_received
                if cmd.get("type") == "watch" and cmd.get("action") == "stop"
            ]
            assert len(stop_cmds) == 2
            stop_ids = {cmd["watch_id"] for cmd in stop_cmds}
            assert stop_ids == {"w1", "w2"}

            # Verify reset commands sent for each pattern
            reset_cmds = [
                cmd for cmd in client.commands_received if cmd.get("type") == "reset"
            ]
            assert len(reset_cmds) == 2
            reset_patterns = {cmd["pattern"] for cmd in reset_cmds}
            assert reset_patterns == {"module.func1", "module.func2"}

            # Verify state cleared
            assert len(watch_view._active_watches) == 0

            # Verify stream client disconnected
            assert not stream_client.connected
            assert watch_view._stream_client is None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_no_client_is_noop(self, mock_client_factory):
        """cleanup_for_exit does nothing when no client is connected."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            # Don't set client — _client remains None
            watch_view._active_watches = {"w1": {"pattern": "func", "worker": None}}

            # Should not raise
            watch_view.cleanup_for_exit()

            # State should be unchanged (early return before clear)
            assert len(watch_view._active_watches) == 1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_with_no_active_watches(self, mock_client_factory):
        """cleanup_for_exit with empty active watches just disconnects stream."""
        client = mock_client_factory()
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(client)

            stream_client = mock_client_factory()
            stream_client.connect()
            watch_view._stream_client = stream_client

            client.commands_received.clear()

            watch_view.cleanup_for_exit()

            # No commands sent since no active watches
            assert len(client.commands_received) == 0
            # Stream client still disconnected
            assert not stream_client.connected

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_tolerates_send_failure(self, mock_client_factory):
        """cleanup_for_exit swallows exceptions from send_command."""
        client = mock_client_factory(should_fail_send=True)
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(client)

            mock_worker = MagicMock()
            watch_view._active_watches = {
                "w1": {"pattern": "module.func", "worker": mock_worker},
            }

            # Should not raise despite send failures
            watch_view.cleanup_for_exit()

            # Worker still cancelled
            mock_worker.cancel.assert_called_once()
            # State still cleared
            assert len(watch_view._active_watches) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_on_unmount_cancels_workers_and_disconnects(
        self, mock_client_factory
    ):
        """on_unmount cancels workers and disconnects stream client."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)

            mock_worker = MagicMock()
            watch_view._active_watches = {
                "w1": {"pattern": "module.func", "worker": mock_worker},
            }
            stream_client = mock_client_factory()
            stream_client.connect()
            watch_view._stream_client = stream_client

            watch_view.on_unmount()

            mock_worker.cancel.assert_called_once()
            assert not stream_client.connected
            assert watch_view._stream_client is None


class TestTraceViewCleanup:
    """Test TraceView.cleanup_for_exit() sends stop+reset and clears state."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_sends_stop_and_reset(self, mock_client_factory):
        """cleanup_for_exit sends stop for each trace_id and reset for each pattern."""
        client = mock_client_factory(
            responses={
                "trace": {"status": "success"},
                "reset": {"status": "success"},
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

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view._client = client

            mock_worker1 = MagicMock()
            mock_worker2 = MagicMock()
            trace_view._active_traces = {
                "t1": {"pattern": "module.handler", "worker": mock_worker1},
                "t2": {"pattern": "module.process", "worker": mock_worker2},
            }

            stream_client = mock_client_factory()
            stream_client.connect()
            trace_view._stream_client = stream_client

            trace_view.cleanup_for_exit()

            # Workers cancelled
            mock_worker1.cancel.assert_called_once()
            mock_worker2.cancel.assert_called_once()

            # Stop commands
            stop_cmds = [
                cmd
                for cmd in client.commands_received
                if cmd.get("type") == "trace" and cmd.get("action") == "stop"
            ]
            assert len(stop_cmds) == 2
            stop_ids = {cmd["watch_id"] for cmd in stop_cmds}
            assert stop_ids == {"t1", "t2"}

            # Reset commands
            reset_cmds = [
                cmd for cmd in client.commands_received if cmd.get("type") == "reset"
            ]
            assert len(reset_cmds) == 2
            reset_patterns = {cmd["pattern"] for cmd in reset_cmds}
            assert reset_patterns == {"module.handler", "module.process"}

            # State cleared
            assert len(trace_view._active_traces) == 0
            assert not stream_client.connected
            assert trace_view._stream_client is None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_no_client_is_noop(self, mock_client_factory):
        """cleanup_for_exit does nothing when no client is connected."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view._active_traces = {"t1": {"pattern": "func", "worker": None}}

            trace_view.cleanup_for_exit()

            # Early return — state unchanged
            assert len(trace_view._active_traces) == 1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_tolerates_send_failure(self, mock_client_factory):
        """cleanup_for_exit swallows exceptions from send_command."""
        client = mock_client_factory(should_fail_send=True)
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view._client = client

            mock_worker = MagicMock()
            trace_view._active_traces = {
                "t1": {"pattern": "module.func", "worker": mock_worker},
            }

            trace_view.cleanup_for_exit()

            mock_worker.cancel.assert_called_once()
            assert len(trace_view._active_traces) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_on_unmount_cancels_workers_and_disconnects(
        self, mock_client_factory
    ):
        """on_unmount cancels workers and disconnects stream client."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)

            mock_worker = MagicMock()
            trace_view._active_traces = {
                "t1": {"pattern": "module.func", "worker": mock_worker},
            }
            stream_client = mock_client_factory()
            stream_client.connect()
            trace_view._stream_client = stream_client

            trace_view.on_unmount()

            mock_worker.cancel.assert_called_once()
            assert not stream_client.connected
            assert trace_view._stream_client is None


class TestStackViewCleanup:
    """Test StackView.cleanup_for_exit() sends stop+global reset and clears state."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_sends_stop_and_global_reset(self, mock_client_factory):
        """cleanup_for_exit sends stop for each watch_id and a global reset '*'."""
        client = mock_client_factory(
            responses={
                "stack": {"status": "success"},
                "reset": {"status": "success"},
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
            stack_view._client = client

            mock_worker1 = MagicMock()
            mock_worker2 = MagicMock()
            stack_view._workers = {"s1": mock_worker1, "s2": mock_worker2}
            stack_view._trace_counts = {"s1": 5, "s2": 3}

            stream_client = mock_client_factory()
            stream_client.connect()
            stack_view._stream_client = stream_client

            stack_view.cleanup_for_exit()

            # Workers cancelled
            mock_worker1.cancel.assert_called_once()
            mock_worker2.cancel.assert_called_once()

            # Stop commands for each watch_id
            stop_cmds = [
                cmd
                for cmd in client.commands_received
                if cmd.get("type") == "stack" and cmd.get("action") == "stop"
            ]
            assert len(stop_cmds) == 2
            stop_ids = {cmd["watch_id"] for cmd in stop_cmds}
            assert stop_ids == {"s1", "s2"}

            # Single global reset with pattern "*"
            reset_cmds = [
                cmd for cmd in client.commands_received if cmd.get("type") == "reset"
            ]
            assert len(reset_cmds) == 1
            assert reset_cmds[0]["pattern"] == "*"

            # State cleared
            assert len(stack_view._workers) == 0
            assert len(stack_view._trace_counts) == 0
            assert not stream_client.connected
            assert stack_view._stream_client is None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_no_client_is_noop(self, mock_client_factory):
        """cleanup_for_exit does nothing when no client is connected."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            mock_worker = MagicMock()
            stack_view._workers = {"s1": mock_worker}

            stack_view.cleanup_for_exit()

            # Early return — worker NOT cancelled, state unchanged
            mock_worker.cancel.assert_not_called()
            assert len(stack_view._workers) == 1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_tolerates_send_failure(self, mock_client_factory):
        """cleanup_for_exit swallows exceptions from send_command."""
        client = mock_client_factory(should_fail_send=True)
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view._client = client

            mock_worker = MagicMock()
            stack_view._workers = {"s1": mock_worker}

            stack_view.cleanup_for_exit()

            mock_worker.cancel.assert_called_once()
            assert len(stack_view._workers) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_on_unmount_cancels_workers_and_disconnects(
        self, mock_client_factory
    ):
        """on_unmount cancels workers and disconnects stream client."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)

            mock_worker = MagicMock()
            stack_view._workers = {"s1": mock_worker}
            stream_client = mock_client_factory()
            stream_client.connect()
            stack_view._stream_client = stream_client

            stack_view.on_unmount()

            mock_worker.cancel.assert_called_once()
            assert not stream_client.connected
            assert stack_view._stream_client is None


class TestMonitorViewCleanup:
    """Test MonitorView.cleanup_for_exit() sends stop and clears state (no reset)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_sends_stop_no_reset(self, mock_client_factory):
        """cleanup_for_exit sends stop for each monitor but no reset commands."""
        client = mock_client_factory(
            responses={
                "monitor": {"status": "success"},
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

            monitor_view = app.screen.query_one("MonitorView", MonitorView)
            monitor_view._client = client

            mock_worker1 = MagicMock()
            mock_worker2 = MagicMock()
            monitor_view._workers = {"m1": mock_worker1, "m2": mock_worker2}

            stream_client = mock_client_factory()
            stream_client.connect()
            monitor_view._stream_client = stream_client

            monitor_view.cleanup_for_exit()

            # Workers cancelled
            mock_worker1.cancel.assert_called_once()
            mock_worker2.cancel.assert_called_once()

            # Stop commands for each monitor
            stop_cmds = [
                cmd
                for cmd in client.commands_received
                if cmd.get("type") == "monitor" and cmd.get("action") == "stop"
            ]
            assert len(stop_cmds) == 2
            stop_ids = {cmd["watch_id"] for cmd in stop_cmds}
            assert stop_ids == {"m1", "m2"}

            # NO reset commands (monitor doesn't send reset)
            reset_cmds = [
                cmd for cmd in client.commands_received if cmd.get("type") == "reset"
            ]
            assert len(reset_cmds) == 0

            # State cleared
            assert len(monitor_view._workers) == 0
            assert not stream_client.connected
            assert monitor_view._stream_client is None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_no_client_is_noop(self, mock_client_factory):
        """cleanup_for_exit does nothing when no client is connected."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            monitor_view = app.screen.query_one("MonitorView", MonitorView)
            mock_worker = MagicMock()
            monitor_view._workers = {"m1": mock_worker}

            monitor_view.cleanup_for_exit()

            mock_worker.cancel.assert_not_called()
            assert len(monitor_view._workers) == 1

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_cleanup_tolerates_send_failure(self, mock_client_factory):
        """cleanup_for_exit swallows exceptions from send_command."""
        client = mock_client_factory(should_fail_send=True)
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            monitor_view = app.screen.query_one("MonitorView", MonitorView)
            monitor_view._client = client

            mock_worker = MagicMock()
            monitor_view._workers = {"m1": mock_worker}

            monitor_view.cleanup_for_exit()

            mock_worker.cancel.assert_called_once()
            assert len(monitor_view._workers) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_on_unmount_cancels_workers_and_disconnects(
        self, mock_client_factory
    ):
        """on_unmount cancels workers and disconnects stream client."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            monitor_view = app.screen.query_one("MonitorView", MonitorView)

            mock_worker = MagicMock()
            monitor_view._workers = {"m1": mock_worker}
            stream_client = mock_client_factory()
            stream_client.connect()
            monitor_view._stream_client = stream_client

            monitor_view.on_unmount()

            mock_worker.cancel.assert_called_once()
            assert not stream_client.connected
            assert monitor_view._stream_client is None
