"""Streaming views close their stream connection once everything is stopped.

An idle stream socket that nobody reads would keep collecting agent log
frames until its buffer fills; the agent then has to evict it.
"""

import pytest

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen

from tests.tui.conftest import MockStreamingAgentClient


async def _no_connect(self) -> None:
    """Skip the real agent connection in tests."""


# view class name, stop-all coroutine, how to register one active item
STOP_ALL_CASES = [
    ("WatchView", "_stop_all_watches", lambda v: v._active_watches.update({"w1": {"worker": None, "pattern": "m.f"}})),
    ("TraceView", "_stop_all_traces", lambda v: v._active_traces.update({"t1": {"worker": None, "pattern": "m.f"}})),
    ("StackView", "_stop_all_stacks", lambda v: v._workers.update({"s1": None})),
    ("MonitorView", "_stop_all_monitors", lambda v: v._workers.update({"m1": None})),
]


class TestStopAllClosesIdleStream:
    @pytest.mark.asyncio
    @pytest.mark.tui
    @pytest.mark.parametrize("view_name,stop_all,add_active", STOP_ALL_CASES)
    async def test_stop_all_disconnects_stream_client(self, monkeypatch, view_name, stop_all, add_active):
        monkeypatch.setattr(MainScreen, "_connect", _no_connect)
        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = MainScreen(pid=12345, session_id="test-session", socket_path="/tmp/test.sock")
            await app.push_screen(main_screen)
            await pilot.pause()

            view = main_screen.query_one(view_name)
            control = MockStreamingAgentClient(responses={})
            control.connect()
            view._client = control

            stream = MockStreamingAgentClient()
            stream.connect()
            view._stream_client = stream
            add_active(view)

            await getattr(view, stop_all)()
            await pilot.pause()

            assert stream.connected is False
            assert view._stream_client is None
