from __future__ import annotations

import atexit
import signal
import sys
import threading
from typing import Any, Dict, List, Optional, cast

import peeka.core.agent as _agent_mod
from peeka.core.agent import PeekaAgent


class _MockInjector:
    def __init__(self) -> None:
        self.uninject_all_calls = 0
        self.orphan_watches_cleaned: bool = False

    def uninject_all(self) -> None:
        self.uninject_all_calls += 1

    def cleanup_orphan_watches(self) -> None:
        self.orphan_watches_cleaned = True


class _MockObserver:
    def __init__(self) -> None:
        self.clear_all_calls = 0

    def clear_all(self) -> None:
        self.clear_all_calls += 1


class _MockProbeRegistry:
    def cleanup(self, older_than_seconds: int = 0, completed_only: bool = False) -> None:
        pass


class _EHTestAgent(PeekaAgent):
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self._stopped: bool = False
        self._stop_lock: threading.Lock = threading.Lock()
        self._prev_sigterm_handler: Any = None
        self._prev_excepthook: Any = None
        self.running: bool = True
        self.server: Any = None
        self.command_handlers: Dict[str, Any] = {}
        self._observation_queues: Dict[Any, Any] = {}
        self._observation_queue_stats: Dict[Any, Any] = {}
        self._observation_queue_lock: threading.Lock = threading.Lock()
        self._observation_flush_event: threading.Event = threading.Event()
        self._flush_thread_running: bool = False
        self.injector: Any = _MockInjector()
        self.observer: Any = _MockObserver()
        self._probe_contexts: Dict[str, Any] = {}
        self._probe_context_types: Dict[str, Any] = {}
        self._probe_context_lock: threading.Lock = threading.Lock()
        self.probe_registry: Any = _MockProbeRegistry()
        atexit.register(self.stop)
        self._prev_excepthook = sys.excepthook

        stop_ref = self.stop

        def _handle_exception(exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
            try:
                if self._prev_excepthook is not None:
                    self._prev_excepthook(exc_type, exc_value, exc_tb)
            finally:
                try:
                    stop_ref()
                except Exception:
                    pass

        sys.excepthook = _handle_exception
        self._peeka_excepthook = _handle_exception


class TestExcepthookInstalled:
    def test_excepthook_is_replaced_on_init(self) -> None:
        original_hook = sys.excepthook
        agent = _EHTestAgent("test_eh_01")
        try:
            assert sys.excepthook is not original_hook, (
                "sys.excepthook must be replaced by PeekaAgent on init"
            )
        finally:
            agent.stop()
            sys.excepthook = original_hook

    def test_prev_excepthook_stored(self) -> None:
        original_hook = sys.excepthook
        agent = _EHTestAgent("test_eh_02")
        try:
            assert agent._prev_excepthook is original_hook, (
                "_prev_excepthook must reference the original hook"
            )
        finally:
            agent.stop()
            sys.excepthook = original_hook


class TestExcepthookChain:
    def test_original_hook_called_when_exception_occurs(self) -> None:
        original_hook = sys.excepthook
        hook_calls: List[Any] = []

        def _fake_hook(exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
            hook_calls.append(exc_type)

        sys.excepthook = _fake_hook
        agent = _EHTestAgent("test_eh_chain_03")
        try:
            sys.excepthook(ValueError, ValueError("test"), None)
            assert hook_calls, "Original excepthook (chained) must be called"
        finally:
            agent.stop()
            sys.excepthook = original_hook

    def test_stop_called_when_exception_occurs(self) -> None:
        original_hook = sys.excepthook
        stop_calls: List[int] = []
        agent = _EHTestAgent("test_eh_stop_04")

        original_stop = agent.stop

        def _counting_stop() -> None:
            stop_calls.append(1)
            original_stop()

        agent.stop = _counting_stop  # type: ignore[method-assign]
        try:
            sys.excepthook(RuntimeError, RuntimeError("boom"), None)
            assert len(stop_calls) >= 1, "agent.stop must be called from excepthook"
        finally:
            sys.excepthook = original_hook


class TestExcepthookRestore:
    def test_excepthook_restored_on_stop(self) -> None:
        original_hook = sys.excepthook
        agent = _EHTestAgent("test_eh_restore_05")
        assert sys.excepthook is not original_hook
        agent.stop()
        try:
            assert sys.excepthook is original_hook or sys.excepthook is agent._prev_excepthook, (
                "sys.excepthook must be restored after agent.stop()"
            )
        finally:
            sys.excepthook = original_hook
