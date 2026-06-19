"""Parameterized tests for agent stream lifecycle — detach/reset probe cleanup.

Verifies that ``detach`` and ``reset`` correctly stop all 5 stream probe types
(watch/trace/stack/monitor/top) via the probe registry.  Symmetric to
``tests/test_cli_streaming.py`` for the CLI side.
"""

import threading
from typing import Any, Dict, List

import pytest

from peeka.commands.detach import DetachCommand
from peeka.commands.reset import ResetCommand


class _MockProbeRun:
    def __init__(self, pattern: str) -> None:
        self.pattern = pattern


class _MockProbeContext:
    """Tracks whether ``__exit__`` was called (simulates ProbeContext)."""

    def __init__(self, probe_pattern: str = "test.func") -> None:
        self.exited = False
        self.probe = _MockProbeRun(pattern=probe_pattern)

    def __exit__(self, *args: Any) -> None:
        self.exited = True


class _MockAgentWithProbes:
    """Minimal agent double with real probe_context tracking."""

    def __init__(self) -> None:
        self._probe_contexts: Dict[str, Any] = {}
        self._probe_context_types: Dict[str, str] = {}
        self._probe_context_lock = threading.Lock()

        self.uninject_all_called = False
        self.clear_all_called = False
        self.stop_called = False
        self.attached_pid = 12345

    def stop_probe_contexts_by_type(self, probe_types: List[str]) -> None:
        """Real implementation — mirrors probes.py."""
        with self._probe_context_lock:
            stream_keys = [
                k for k, t in self._probe_context_types.items()
                if t in probe_types
            ]
        for stream_key in stream_keys:
            self.stop_probe_context(stream_key)

    def stop_probe_context(self, stream_key: str) -> None:
        with self._probe_context_lock:
            ctx = self._probe_contexts.pop(stream_key, None)
            self._probe_context_types.pop(stream_key, None)
        if ctx is not None:
            ctx.__exit__(None, None, None)

    @property
    def injector(self):  # type: ignore[override]
        class _FakeInjector:
            def uninject_all(self_inner) -> int:
                self.uninject_all_called = True
                return 0

            def reset(self_inner, pattern: Any = None) -> Dict[str, Any]:
                return {
                    "status": "success",
                    "action": "reset",
                    "count": 0,
                    "affected": [],
                }

            def list_enhanced(self_inner) -> Dict[str, Any]:
                return {"status": "success", "enhanced": [], "total": 0}

        return _FakeInjector()

    @property
    def observer(self):  # type: ignore[override]
        class _FakeObserver:
            def clear_all(self_inner) -> None:
                self.clear_all_called = True

        return _FakeObserver()

    def stop(self) -> None:
        self.stop_called = True

    def register_stream(
        self,
        stream_key: str,
        probe_type: str,
        pattern: str = "test.func",
    ) -> _MockProbeContext:
        """Register a fake probe context for a given type; returns the context."""
        ctx = _MockProbeContext(probe_pattern=pattern)
        with self._probe_context_lock:
            self._probe_contexts[stream_key] = ctx
            self._probe_context_types[stream_key] = probe_type
        return ctx


@pytest.mark.parametrize("probe_type", ["watch", "trace", "stack", "monitor", "top"])
def test_detach_stops_probe_context_for_all_types(probe_type: str) -> None:  # BRITTLE: fake ProbeContext smoke check only; no real resource-owner verification → REPLACE WITH: detach restores wrappers and stops active probe resources for each stream type
    """Detach calls stop_probe_contexts_by_type and exits each probe context.

    smoke: ProbeContext bookkeeping only
    """
    agent = _MockAgentWithProbes()
    stream_id = f"{probe_type}_test_001"
    ctx = agent.register_stream(stream_id, probe_type)

    result = DetachCommand(agent).execute({})  # type: ignore[arg-type]

    assert result["status"] == "success"
    assert ctx.exited is True, (
        f"[{probe_type}] probe context.__exit__ was not called by detach"
    )
    assert stream_id not in agent._probe_contexts
    assert agent.uninject_all_called
    assert agent.clear_all_called
    assert agent.stop_called


@pytest.mark.parametrize("probe_type", ["watch", "trace", "stack", "monitor", "top"])
def test_reset_stops_matching_probe_context_for_all_types(probe_type: str) -> None:  # BRITTLE: fake ProbeContext smoke check only; no real resource-owner verification → REPLACE WITH: reset stops only matching probe resources and preserves unrelated streams
    """Reset with a matching pattern stops that stream's probe context.

    smoke: ProbeContext bookkeeping only
    """
    agent = _MockAgentWithProbes()
    stream_id = f"{probe_type}_test_002"
    pattern = "mymodule.MyClass.method"
    ctx = agent.register_stream(stream_id, probe_type, pattern=pattern)

    result = ResetCommand(agent).execute(  # type: ignore[arg-type]
        {"action": "reset", "pattern": pattern}
    )

    assert result["status"] == "success"
    assert ctx.exited is True, (
        f"[{probe_type}] probe context.__exit__ was not called by reset with matching pattern"
    )
    assert stream_id not in agent._probe_contexts


@pytest.mark.parametrize("probe_type", ["watch", "trace", "stack", "monitor", "top"])
def test_reset_list_includes_all_probe_context_types(probe_type: str) -> None:
    """reset --list reports all 5 active stream probe types."""
    agent = _MockAgentWithProbes()
    stream_id = f"{probe_type}_test_003"
    agent.register_stream(stream_id, probe_type)

    result = ResetCommand(agent).execute({"action": "list"})  # type: ignore[arg-type]

    assert result["status"] == "success"
    commands_in_list = [item["command"] for item in result["enhanced"]]
    assert probe_type in commands_in_list, (
        f"[{probe_type}] reset --list must include active {probe_type} streams"
    )


def test_reset_non_matching_pattern_does_not_stop_probe_context() -> None:
    """A non-matching pattern must not stop an unrelated probe context."""
    agent = _MockAgentWithProbes()
    ctx = agent.register_stream("watch_keepme", "watch", pattern="other.func")

    ResetCommand(agent).execute(  # type: ignore[arg-type]
        {"action": "reset", "pattern": "mymodule.*"}
    )

    assert ctx.exited is False, "non-matching stream must not be stopped by reset"
    assert "watch_keepme" in agent._probe_contexts


def test_detach_succeeds_when_no_probe_tracking_available() -> None:
    """Detach must work on agents without probe tracking (getattr guard)."""

    class _MinimalAgent:
        attached_pid = 1

        class injector:
            @staticmethod
            def uninject_all() -> int:
                return 0

        class observer:
            @staticmethod
            def clear_all() -> None:
                pass

        def stop(self) -> None:
            pass

    result = DetachCommand(_MinimalAgent()).execute({})  # type: ignore[arg-type]
    assert result["status"] == "success"
