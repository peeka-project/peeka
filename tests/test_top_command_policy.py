"""Tests for top command gevent policy metadata."""

import sys
import threading
import time

import pytest

from peeka.core.runtime.compat import (
    BACKEND_FRAME_WALK,
    BACKEND_GREENLET_AWARE_SAMPLING,
)
from peeka.core.runtime.gevent_probe import GeventState


class MockObserver:
    """TopCommand observer stub."""

    def register_watch(self, watch_id, watch_type, params):
        """Accept watch registration."""

    def unregister_watch(self, watch_id):
        """Accept watch unregistration."""


class MockAgent:
    """TopCommand agent stub."""

    def __init__(self):
        self.observer = MockObserver()
        self._observations = []

    def _send_observation(self, observation):
        """Record streaming observations."""
        self._observations.append(observation)


class FakeThreadHandle:
    """Thread handle stub that records the selected sampling target."""

    created = []

    def __init__(self, target, name):
        self.target = target
        self.name = name
        self.ident = 12345 + len(self.created)
        self._alive = True
        self.created.append(self)

    def is_alive(self):
        """Return whether the fake thread is considered alive."""
        return self._alive

    def join(self, timeout=None):
        """Mark the fake thread as stopped."""
        self._alive = False


class FakeGreenletModule:
    """Minimal greenlet module stub with trace callback support."""

    def __init__(self, tracer=None):
        self.tracer = tracer

    def gettrace(self):
        """Return the installed tracer."""
        return self.tracer

    def settrace(self, tracer):
        """Install the tracer."""
        self.tracer = tracer


@pytest.mark.unit
class TestTopCommandPolicy:
    """Top command policy metadata tests."""

    @pytest.fixture
    def top_command(self):
        """Create TopCommand with mock agent."""
        from peeka.commands.top import TopCommand

        cmd = TopCommand(MockAgent())
        yield cmd
        # Ensure any lingering sampling thread is stopped between tests.
        cmd.stop_active_resources(pattern=None, reason="test teardown")

    def test_clean_runtime_start_returns_safe_meta(self, top_command, monkeypatch):
        """Clean runtime top start has safe frame_walk metadata."""
        monkeypatch.setattr("peeka.commands.top.probe", lambda: GeventState.NONE)

        result = top_command.execute({"action": "start", "interval": 0.01})

        try:
            assert result["status"] == "success"
            assert result["meta"] == {
                "gevent_state": "none",
                "backend": BACKEND_FRAME_WALK,
                "greenlet_blind": False,
                "degraded_reason": None,
            }
        finally:
            top_command.execute({"action": "stop"})

    def test_none_state_uses_frame_walk_sampling_target(
        self, top_command, monkeypatch
    ):
        """NONE state starts the existing frame-walk sampling loop."""
        FakeThreadHandle.created = []
        monkeypatch.setattr("peeka.commands.top.probe", lambda: GeventState.NONE)
        monkeypatch.setattr("peeka.commands.top._NativeThreadHandle", FakeThreadHandle)

        result = top_command.execute({"action": "start", "interval": 0.01})

        try:
            assert result["status"] == "success"
            assert FakeThreadHandle.created[0].target.__name__ == "_sampling_loop"
            assert result["meta"]["backend"] == BACKEND_FRAME_WALK
        finally:
            top_command.execute({"action": "stop"})

    def test_patched_runtime_uses_greenlet_aware_sampling_target(
        self, top_command, monkeypatch
    ):
        """PATCHED state starts the greenlet-aware sampling backend."""
        FakeThreadHandle.created = []
        monkeypatch.setattr("peeka.commands.top.probe", lambda: GeventState.PATCHED)
        monkeypatch.setitem(sys.modules, "greenlet", FakeGreenletModule())
        monkeypatch.setattr("peeka.commands.top._NativeThreadHandle", FakeThreadHandle)

        result = top_command.execute({"action": "start", "interval": 0.01})

        try:
            assert result["status"] == "success"
            assert result["meta"]["gevent_state"] == "patched"
            assert result["meta"]["backend"] == BACKEND_GREENLET_AWARE_SAMPLING
            assert result["meta"]["greenlet_blind"] is True
            assert isinstance(result["meta"]["degraded_reason"], str)
            assert (
                FakeThreadHandle.created[0].target.__name__
                == "_sampling_loop_greenlet_aware"
            )
        finally:
            top_command.execute({"action": "stop"})

    def test_snapshot_includes_current_meta(self, top_command, monkeypatch):
        """Snapshots include the policy metadata selected at start."""
        monkeypatch.setattr(
            "peeka.commands.top.probe", lambda: GeventState.ACTIVE_HUB
        )
        top_command.execute({"action": "start", "interval": 0.01})
        time.sleep(0.02)

        try:
            result = top_command.execute({"action": "snapshot"})
            assert result["status"] == "success"
            assert result["meta"]["gevent_state"] == "active_hub"
            assert result["snapshot"]["meta"]["greenlet_blind"] is True
        finally:
            top_command.execute({"action": "stop"})

    def test_double_start_preserves_existing_meta(self, top_command, monkeypatch):
        """Starting twice returns metadata for the active profiler."""
        monkeypatch.setattr("peeka.commands.top.probe", lambda: GeventState.PATCHED)
        first = top_command.execute({"action": "start", "interval": 0.01})

        try:
            monkeypatch.setattr("peeka.commands.top.probe", lambda: GeventState.NONE)
            second = top_command.execute({"action": "start", "interval": 0.01})
            assert second["status"] == "success"
            assert second["top_id"] == first["top_id"]
            assert second["meta"]["gevent_state"] == "patched"
        finally:
            top_command.execute({"action": "stop"})

    def test_greenlet_tracer_chains_previous_callback(self, top_command, monkeypatch):
        """greenlet-aware sampler calls the previous trace callback."""
        calls = []

        def prev_tracer(event, args):
            calls.append((event, args))

        fake_greenlet = FakeGreenletModule(prev_tracer)
        monkeypatch.setitem(sys.modules, "greenlet", fake_greenlet)

        def sample_once():
            fake_greenlet.tracer("switch", ("source", "target"))

        monkeypatch.setattr(top_command, "_sampling_loop", sample_once)

        top_command._sampling_loop_greenlet_aware()

        assert calls == [("switch", ("source", "target"))]
        assert fake_greenlet.gettrace() is prev_tracer

    def test_greenlet_tracer_isolates_previous_callback_errors(
        self, top_command, monkeypatch
    ):
        """previous greenlet tracer exceptions do not propagate."""
        def prev_tracer(event, args):
            raise RuntimeError("host tracer failed")

        fake_greenlet = FakeGreenletModule(prev_tracer)
        monkeypatch.setitem(sys.modules, "greenlet", fake_greenlet)

        def sample_once():
            fake_greenlet.tracer("throw", ("source", "target"))

        monkeypatch.setattr(top_command, "_sampling_loop", sample_once)

        top_command._sampling_loop_greenlet_aware()

        assert fake_greenlet.gettrace() is prev_tracer
        assert top_command._greenlet_throw_count == 1

    def test_greenlet_tracer_restores_previous_callback_on_error(
        self, top_command, monkeypatch
    ):
        """greenlet trace callback is restored in finally."""
        def prev_tracer(event, args):
            return None

        fake_greenlet = FakeGreenletModule(prev_tracer)
        monkeypatch.setitem(sys.modules, "greenlet", fake_greenlet)

        def fail_sampling():
            raise RuntimeError("sampling failed")

        monkeypatch.setattr(top_command, "_sampling_loop", fail_sampling)

        with pytest.raises(RuntimeError):
            top_command._sampling_loop_greenlet_aware()

        assert fake_greenlet.gettrace() is prev_tracer

    def test_greenlet_missing_falls_back_to_frame_walk(
        self, top_command, monkeypatch, caplog
    ):
        """Missing greenlet module falls back to frame walk and updates meta."""
        called = []
        monkeypatch.delitem(sys.modules, "greenlet", raising=False)
        top_command._meta = {
            "gevent_state": "patched",
            "backend": BACKEND_GREENLET_AWARE_SAMPLING,
            "greenlet_blind": True,
            "degraded_reason": "gevent active",
        }

        def fallback_sampling():
            called.append(True)

        monkeypatch.setattr(top_command, "_sampling_loop", fallback_sampling)

        top_command._sampling_loop_greenlet_aware()

        assert called == [True]
        assert top_command._meta["backend"] == BACKEND_FRAME_WALK
        assert "fell back to frame_walk" in top_command._meta["degraded_reason"]
        assert "falling back to frame_walk" in caplog.text

    def test_start_uses_native_thread_primitives(self, monkeypatch):
        """Top start survives a patched threading module."""
        from peeka.commands.top import TopCommand

        def fail_thread(*args, **kwargs):
            raise AssertionError("patched threading.Thread should not be used")

        def fail_event(*args, **kwargs):
            raise AssertionError("patched threading.Event should not be used")

        monkeypatch.setattr(threading, "Thread", fail_thread)
        monkeypatch.setattr(threading, "Event", fail_event)
        monkeypatch.setattr("peeka.commands.top.probe", lambda: GeventState.PATCHED)
        monkeypatch.setitem(sys.modules, "greenlet", FakeGreenletModule())

        top_command = TopCommand(MockAgent())
        result = top_command.execute({"action": "start", "interval": 0.01})

        try:
            assert result["status"] == "success"
            assert top_command._sampling_thread is not None
            assert top_command._sampling_thread.is_alive()
        finally:
            top_command.execute({"action": "stop"})
