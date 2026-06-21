"""Red tests for orphan watch cleanup wiring."""

# pyright: reportAny=false, reportExplicitAny=false, reportDeprecated=false, reportUnannotatedClassAttribute=false

import logging
import threading
from typing import Any, Dict, List

import pytest

from peeka.core.agent_control.lifecycle import shutdown_agent_resources


_LOG = logging.getLogger("test")


class _StubInjector:
    def __init__(self, should_raise: bool = False) -> None:
        self.cleanup_calls: int = 0
        self.should_raise = should_raise

    def cleanup_orphan_watches(self) -> int:
        self.cleanup_calls += 1
        if self.should_raise:
            raise RuntimeError("orphan_err")
        return 0

    def uninject_all(self) -> None:
        return None


class _StubInjectorWithoutCleanup:
    def uninject_all(self) -> None:
        return None


class _StubProbeRegistry:
    def __init__(self) -> None:
        self.cleanup_calls: int = 0

    def cleanup(self) -> None:
        self.cleanup_calls += 1


class _StubObserver:
    def __init__(self) -> None:
        self.clear_calls: int = 0

    def clear_all(self) -> None:
        self.clear_calls += 1


class _StubAgent:
    def __init__(self, injector: Any) -> None:
        self.injector = injector
        self.command_handlers: Dict[str, Any] = {}
        self.probe_registry = _StubProbeRegistry()
        self.observer = _StubObserver()
        self.stop_probe_contexts_calls: List[List[str]] = []

    def stop_probe_contexts_by_type(self, probe_types: List[str]) -> None:
        self.stop_probe_contexts_calls.append(list(probe_types))


@pytest.mark.unit
def test_shutdown_calls_injector_cleanup_orphan_watches() -> None:
    agent = _StubAgent(_StubInjector())

    _ = shutdown_agent_resources(agent, _LOG, [])

    assert agent.injector.cleanup_calls == 1


@pytest.mark.unit
def test_shutdown_records_orphan_watch_sweep_step_in_steps_run() -> None:
    agent = _StubAgent(_StubInjector())

    result = shutdown_agent_resources(agent, _LOG, [])

    assert "orphan_watch_sweep" in result["steps_run"]


@pytest.mark.unit
def test_shutdown_isolates_orphan_watch_cleanup_errors() -> None:
    agent = _StubAgent(_StubInjector(should_raise=True))

    result = shutdown_agent_resources(agent, _LOG, [])

    assert result["errors"]["orphan_watch_sweep"] == "orphan_err"
    assert "clear_all" in result["steps_run"]


@pytest.mark.unit
def test_shutdown_skips_orphan_sweep_when_injector_lacks_method() -> None:
    agent = _StubAgent(_StubInjectorWithoutCleanup())

    result = shutdown_agent_resources(agent, _LOG, [])

    assert "orphan_watch_sweep" in result["errors"]


@pytest.mark.unit
def test_no_daemon_thread_started() -> None:
    thread_names = [thread.name for thread in threading.enumerate()]

    assert all(
        "sweeper" not in name
        and "orphan-sweeper" not in name
        and "daemon-sweep" not in name
        for name in thread_names
    )
