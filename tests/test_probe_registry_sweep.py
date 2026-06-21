"""RED tests for probe registry sweep in shutdown_agent_resources."""

# pyright: reportAny=false, reportExplicitAny=false, reportDeprecated=false, reportUnannotatedClassAttribute=false

import logging
import pathlib
from typing import Any, Dict, List, Optional

import pytest

from peeka.core.agent_control.lifecycle import shutdown_agent_resources


_LOG = logging.getLogger("test")
_LIFECYCLE_PATH = (
    pathlib.Path(__file__).resolve().parent.parent
    / "peeka"
    / "core"
    / "agent_control"
    / "lifecycle.py"
)


class _RecordingCleanup:
    def __init__(self, result: Any = None, exc: Optional[Exception] = None) -> None:
        self.calls: List[Dict[str, Any]] = []
        self.result = result
        self.exc = exc

    def cleanup(
        self,
        older_than_seconds: int = 600,
        target_id: Any = None,
        completed_only: bool = True,
    ) -> Any:
        self.calls.append(
            {
                "older_than_seconds": older_than_seconds,
                "target_id": target_id,
                "completed_only": completed_only,
            }
        )
        if self.exc is not None:
            raise self.exc
        return self.result


class _RecordingInjector:
    def uninject_all(self) -> None:
        return None


class _RecordingObserver:
    def clear_all(self) -> None:
        return None


class _StubAgent:
    def __init__(self, probe_registry: Any = None) -> None:
        self.command_handlers: Dict[str, Any] = {}
        self.injector = _RecordingInjector()
        self.observer = _RecordingObserver()
        self.probe_registry = probe_registry

    def stop_probe_contexts_by_type(self, probe_types: List[str]) -> None:
        _ = probe_types


class _StubAgentWithoutProbeRegistry:
    def __init__(self) -> None:
        self.command_handlers: Dict[str, Any] = {}
        self.injector = _RecordingInjector()
        self.observer = _RecordingObserver()

    def stop_probe_contexts_by_type(self, probe_types: List[str]) -> None:
        _ = probe_types


@pytest.mark.unit
def test_shutdown_calls_probe_registry_cleanup_with_zero_grace() -> None:
    cleanup = _RecordingCleanup()
    agent = _StubAgent(probe_registry=type("_ProbeRegistry", (), {"cleanup": cleanup.cleanup})())

    _ = shutdown_agent_resources(agent, _LOG, [])

    assert len(cleanup.calls) == 1
    assert cleanup.calls[0] == {
        "older_than_seconds": 0,
        "target_id": None,
        "completed_only": True,
    }


@pytest.mark.unit
def test_shutdown_records_probe_registry_sweep_step_in_steps_run() -> None:
    cleanup = _RecordingCleanup()
    agent = _StubAgent(probe_registry=type("_ProbeRegistry", (), {"cleanup": cleanup.cleanup})())

    result = shutdown_agent_resources(agent, _LOG, [])

    assert "probe_registry_sweep" in result["steps_run"]


@pytest.mark.unit
def test_shutdown_isolates_probe_registry_cleanup_errors() -> None:
    cleanup = _RecordingCleanup(exc=RuntimeError("boom"))
    agent = _StubAgent(probe_registry=type("_ProbeRegistry", (), {"cleanup": cleanup.cleanup})())

    result = shutdown_agent_resources(agent, _LOG, [])

    assert "probe_registry_sweep" in result["errors"]
    assert "boom" in result["errors"]["probe_registry_sweep"]
    assert "clear_all" in result["steps_run"]


@pytest.mark.unit
def test_shutdown_handles_missing_probe_registry_gracefully() -> None:
    agent = _StubAgentWithoutProbeRegistry()

    result = shutdown_agent_resources(agent, _LOG, [])

    assert "probe_registry_sweep" in result["errors"]


@pytest.mark.unit
def test_probe_registry_cleanup_signature_does_not_use_status_filter() -> None:
    source = _LIFECYCLE_PATH.read_text(encoding="utf-8")

    assert "status_filter=" not in source
