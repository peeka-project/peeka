"""Tests for top command gevent policy metadata."""

import threading
import time

import pytest

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


@pytest.mark.unit
class TestTopCommandPolicy:
    """Top command policy metadata tests."""

    @pytest.fixture
    def top_command(self):
        """Create TopCommand with mock agent."""
        from peeka.commands.top import TopCommand

        return TopCommand(MockAgent())

    def test_clean_runtime_start_returns_safe_meta(self, top_command, monkeypatch):
        """Clean runtime top start has safe frame_walk metadata."""
        monkeypatch.setattr("peeka.commands.top.probe", lambda: GeventState.NONE)

        result = top_command.execute({"action": "start", "interval": 0.01})

        try:
            assert result["status"] == "success"
            assert result["meta"] == {
                "gevent_state": "none",
                "backend": "frame_walk",
                "greenlet_blind": False,
                "degraded_reason": None,
            }
        finally:
            top_command.execute({"action": "stop"})

    def test_patched_runtime_start_returns_degraded_meta(
        self, top_command, monkeypatch
    ):
        """Patched gevent runtime marks top as greenlet-blind."""
        monkeypatch.setattr("peeka.commands.top.probe", lambda: GeventState.PATCHED)

        result = top_command.execute({"action": "start", "interval": 0.01})

        try:
            assert result["status"] == "success"
            assert result["meta"]["gevent_state"] == "patched"
            assert result["meta"]["backend"] == "frame_walk"
            assert result["meta"]["greenlet_blind"] is True
            assert isinstance(result["meta"]["degraded_reason"], str)
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

        top_command = TopCommand(MockAgent())
        result = top_command.execute({"action": "start", "interval": 0.01})

        try:
            assert result["status"] == "success"
            assert top_command._sampling_thread is not None
            assert top_command._sampling_thread.is_alive()
        finally:
            top_command.execute({"action": "stop"})
