"""Reproducer for swallowed probe-context __exit__ failures."""

# pyright: reportDeprecated=false

import threading
from typing import Dict

import pytest

from peeka.commands.reset import ResetCommand
from peeka.core.agent_control.probes import AgentProbeControlMixin


class _FailingExitContext:
    """Probe-context stub whose __exit__ always raises."""

    def __enter__(self) -> "_FailingExitContext":
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        raise RuntimeError("exit blow up")


class _ResetInjector:
    def reset(self, pattern: object = None) -> Dict[str, object]:
        _ = pattern
        return {"status": "success", "enhanced": [], "total": 0}


class _ResetAgent(AgentProbeControlMixin):
    def __init__(self) -> None:
        self.command_handlers: Dict[str, object] = {}
        self.injector: _ResetInjector = _ResetInjector()
        self._probe_context_lock: threading.Lock = threading.Lock()
        self._probe_context_types: Dict[str, str] = {"watch-1": "watch"}
        self._probe_contexts: Dict[str, object] = {"watch-1": _FailingExitContext()}


@pytest.mark.unit
def test_reset_cleanup_summary_exposes_probe_context_exit_failure() -> None:
    """Reset cleanup summary should surface __exit__ failures."""
    agent = _ResetAgent()

    result: Dict[str, object] = ResetCommand(agent).execute(  # pyright: ignore[reportArgumentType]
        {"action": "reset"}
    )

    assert result["status"] == "success"
    cleanup_summary = result["cleanup_summary"]
    assert isinstance(cleanup_summary, dict)
    assert cleanup_summary["probe_contexts"]["errors"] == [
        {"stream_key": "watch-1", "error": "exit blow up"}
    ]
