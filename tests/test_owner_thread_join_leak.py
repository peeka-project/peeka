# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportArgumentType=false, reportAttributeAccessIssue=false, reportPrivateUsage=false, reportUnannotatedClassAttribute=false, reportUnusedParameter=false
"""Failing reproducer for owner thread join timeout leak."""

import threading
from typing import Any, Dict, Optional

import pytest

from peeka.commands.monitor import MonitorCommand
from peeka.commands.top import TopCommand


class _AlwaysAliveThread:
    """Thread stub that never reports completion."""

    daemon = True

    def start(self) -> None:
        """Match the thread API without doing any work."""

    def join(self, timeout: Optional[float] = None) -> None:
        """Return immediately while the thread remains alive."""

    def is_alive(self) -> bool:
        return True


class _ObserverStub:
    """Minimal observer stub for TopCommand."""

    def unregister_watch(self, watch_id: str) -> None:
        """Accept watch cleanup."""


class _TopAgentStub:
    """Minimal agent stub for TopCommand cleanup tests."""

    def __init__(self) -> None:
        self.observer = _ObserverStub()


class _MonitorAgentStub:
    """Minimal agent stub for MonitorCommand cleanup tests."""

    injector: Any = None


class TestOwnerThreadJoinLeak:
    """Reproducer tests for missing alive-check after thread.join()."""

    def _build_top_command(self) -> TopCommand:
        cmd = TopCommand(_TopAgentStub())
        cmd._top_id = "top_leak"
        cmd._sampling_thread = _AlwaysAliveThread()
        cmd._observation_thread = _AlwaysAliveThread()
        cmd._stop_event = threading.Event()
        return cmd

    def _build_monitor_command(self) -> MonitorCommand:
        cmd = MonitorCommand(_MonitorAgentStub())
        watch_id = "monitor_leak"
        def original() -> None:
            pass

        def wrapper() -> None:
            pass

        owner = type("_Owner", (), {"target": original})()
        cmd._monitors[watch_id] = {
            "pattern": "*",
            "original": original,
            "owned_root_original": None,
            "wrapper": wrapper,
            "parent": owner,
            "attr_name": "target",
            "aliases": [],
            "cycle": 60,
            "cycles": -1,
            "cycle_count": 0,
            "client_session_id": None,
            "job_id": None,
            "stop_event": threading.Event(),
            "timer_thread": _AlwaysAliveThread(),
        }
        return cmd

    @pytest.mark.unit
    def test_top_stop_reports_alive_thread_after_join_timeout(self) -> None:
        """Top cleanup must surface leaked sampling/observation threads."""
        cmd = self._build_top_command()

        result: Dict[str, Any] = cmd.stop_active_resources(pattern="*", reason="detach")

        assert result["errors"], "expected TopCommand to report an alive thread"
        assert any(
            "alive" in error.get("error", "").lower() for error in result["errors"]
        ), result

    @pytest.mark.unit
    def test_monitor_stop_reports_alive_timer_thread_after_join_timeout(self) -> None:
        """Monitor cleanup must surface a timer thread that never exits."""
        cmd = self._build_monitor_command()

        result: Dict[str, Any] = cmd.stop_active_resources(
            pattern="*", reason="detach"
        )

        assert result["errors"], "expected MonitorCommand to report an alive thread"
        assert any(
            "alive" in error.get("error", "").lower() for error in result["errors"]
        ), result
