"""Parameterized tests for agent stream lifecycle — detach/reset probe cleanup.

Verifies that ``detach`` and ``reset`` correctly stop all 5 stream probe types
(watch/trace/stack/monitor/top) via the probe registry.  Symmetric to
``tests/test_cli_streaming.py`` for the CLI side.
"""

import threading
from typing import Any, Dict, List, cast

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

    _probe_contexts: Dict[str, Any]
    _probe_context_types: Dict[str, str]
    _probe_context_lock: threading.Lock
    uninject_all_called: bool = False
    clear_all_called: bool = False
    stop_called: bool = False
    attached_pid: int = 12345

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

    def list_tracked_probe_types(self) -> List[str]:
        with self._probe_context_lock:
            return sorted(set(self._probe_context_types.values()))

    def stop_probe_context(self, stream_key: str) -> None:
        with self._probe_context_lock:
            ctx = self._probe_contexts.pop(stream_key, None)
            self._probe_context_types.pop(stream_key, None)
        if ctx is not None:
            ctx.__exit__(None, None, None)

    @property
    def injector(self):  # type: ignore[override]
        class _FakeInjector:
            def __init__(self, outer: _MockAgentWithProbes) -> None:
                self._outer = outer

            def uninject_all(self) -> int:
                self._outer.uninject_all_called = True
                return 0

            def reset(self, pattern: Any = None) -> Dict[str, Any]:
                return {
                    "status": "success",
                    "action": "reset",
                    "count": 0,
                    "affected": [],
                }

            def list_enhanced(self) -> Dict[str, Any]:
                return {"status": "success", "enhanced": [], "total": 0}

        return _FakeInjector(self)

    @property
    def observer(self):  # type: ignore[override]
        class _FakeObserver:
            def __init__(self, outer: _MockAgentWithProbes) -> None:
                self._outer = outer

            def clear_all(self) -> None:
                self._outer.clear_all_called = True

        return _FakeObserver(self)

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
def test_detach_stops_probe_context_for_all_types(probe_type: str) -> None:
    """Detach calls stop_probe_contexts_by_type and exits each probe context.

    smoke: ProbeContext bookkeeping only
    """
    stream_id = f"sk_{probe_type}"

    class _ProbeAwareAgent(_MockAgentWithProbes):
        def list_tracked_probe_types(self) -> List[str]:
            return [probe_type]

    agent = _ProbeAwareAgent()
    ctx = agent.register_stream(stream_id, probe_type)
    with agent._probe_context_lock:
        agent._probe_context_types = {f"sk_{probe_type}": probe_type}

    result = DetachCommand(cast(Any, agent)).execute({})

    assert result["status"] == "success"
    assert ctx.exited is True, (
        f"[{probe_type}] probe context.__exit__ was not called by detach"
    )
    assert stream_id not in agent._probe_contexts
    assert agent.uninject_all_called
    assert agent.clear_all_called
    assert agent.stop_called


@pytest.mark.parametrize("probe_type", ["watch", "trace", "stack", "monitor"])
def test_reset_stops_matching_probe_context_for_all_types(probe_type: str) -> None:  # top is DETACH_ONLY; its probe context survives reset (see test_reset_contract.py:263-297)
    """Reset with a matching pattern stops that stream's probe context.

    smoke: ProbeContext bookkeeping only
    """
    agent = _MockAgentWithProbes()
    stream_id = f"{probe_type}_test_002"
    pattern = "mymodule.MyClass.method"
    ctx = agent.register_stream(stream_id, probe_type, pattern=pattern)

    result = ResetCommand(cast(Any, agent)).execute(
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

    result = ResetCommand(cast(Any, agent)).execute({"action": "list"})

    assert result["status"] == "success"
    commands_in_list = [item["command"] for item in cast(List[Dict[str, Any]], result["enhanced"])]
    assert probe_type in commands_in_list, (
        f"[{probe_type}] reset --list must include active {probe_type} streams"
    )


def test_reset_non_matching_pattern_does_not_stop_probe_context() -> None:
    """A non-matching pattern must not stop an unrelated probe context."""
    agent = _MockAgentWithProbes()
    ctx = agent.register_stream("watch_keepme", "watch", pattern="other.func")

    ResetCommand(cast(Any, agent)).execute(
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

    result = DetachCommand(cast(Any, _MinimalAgent())).execute({})
    assert result["status"] == "success"
