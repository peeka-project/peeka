from __future__ import annotations

import signal
import sys
import threading
from typing import Any, Dict, List, Optional

from peeka.commands.detach import DetachCommand
from peeka.commands.reset import ResetCommand
from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand
from peeka.core.agent_control.lifecycle import shutdown_agent_resources, stop_resource_owners_for_detach
from peeka.core.probes import ProbeContext


import logging
_LOG = logging.getLogger(__name__)


class _MockInjector:
    def __init__(self) -> None:
        self.uninject_all_called = False
        self.uninject_all_error: Optional[Exception] = None

    def uninject_all(self) -> int:
        self.uninject_all_called = True
        if self.uninject_all_error:
            raise self.uninject_all_error
        return 0

    def cleanup_orphan_watches(self) -> int:
        return 0

    def reset(self, pattern: Optional[str] = None) -> Dict[str, Any]:
        return {"status": "success", "enhanced": [], "total": 0}


class _MockObserver:
    def __init__(self) -> None:
        self.cleared = False

    def clear_all(self) -> None:
        self.cleared = True


class _MockProbeRegistry:
    def cleanup(self, older_than_seconds: int = 0, completed_only: bool = True) -> List[str]:
        return []


def _make_agent(handlers: Optional[Dict[str, Any]] = None) -> Any:
    class _Agent:
        def __init__(self) -> None:
            self.command_handlers: Dict[str, Any] = handlers or {}
            self.injector: Any = _MockInjector()
            self.observer: Any = _MockObserver()
            self.probe_registry: Any = _MockProbeRegistry()
            self._probe_contexts: Dict[str, Any] = {}
            self._probe_context_types: Dict[str, Any] = {}
            self._probe_context_lock = threading.Lock()

        def stop_probe_contexts_by_type(self, probe_types: List[str]) -> None:
            pass

    return _Agent()


class _ErrorReturningOwner(ResourceOwningCommand):
    is_resource_owner = True
    cleanup_scope = CleanupScope.DETACH_AND_RESET

    def __init__(self, agent: Any = None) -> None:
        super().__init__(agent=agent)

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "success"}

    def stop_active_resources(self, pattern: Optional[str], reason: str) -> Dict[str, Any]:
        return {"stopped": [], "errors": [{"handler": "ErrorOwner", "error": "partial_fail"}]}

    def list_active_resources(self) -> Dict[str, Any]:
        return {"active": []}


class _RaisingOwner(ResourceOwningCommand):
    is_resource_owner = True
    cleanup_scope = CleanupScope.DETACH_AND_RESET

    def __init__(self, agent: Any = None) -> None:
        super().__init__(agent=agent)

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "success"}

    def stop_active_resources(self, pattern: Optional[str], reason: str) -> Dict[str, Any]:
        raise RuntimeError("kaboom")

    def list_active_resources(self) -> Dict[str, Any]:
        return {"active": []}


class TestT1ErrorAggregation:
    def test_returned_errors_propagate_into_resource_owners_summary(self) -> None:
        agent = _make_agent({"a": _ErrorReturningOwner()})
        result = shutdown_agent_resources(agent, _LOG, [])

        ro = result["resource_owners"]
        assert ro["errors"] == [{"handler": "ErrorOwner", "error": "partial_fail"}]
        assert "ErrorOwner" not in ro["handlers_stopped"]

    def test_exception_in_handler_propagates_into_resource_owners_errors(self) -> None:
        agent = _make_agent({"a": _RaisingOwner()})
        result = shutdown_agent_resources(agent, _LOG, [])

        ro = result["resource_owners"]
        assert len(ro["errors"]) == 1
        assert ro["errors"][0]["handler"] == "_RaisingOwner"
        assert "kaboom" in ro["errors"][0]["error"]

    def test_subsequent_steps_run_after_resource_owner_exception(self) -> None:
        agent = _make_agent({"a": _RaisingOwner()})
        result = shutdown_agent_resources(agent, _LOG, [])

        assert "stop_resource_owners" in result["steps_run"]
        assert "uninject_all" in result["steps_run"]
        assert "clear_all" in result["steps_run"]
        assert result["resource_owners"]["errors"][0]["handler"] == "_RaisingOwner"

    def test_step_exception_recorded_in_step_errors(self) -> None:
        agent = _make_agent()
        agent.injector.uninject_all_error = RuntimeError("injector_err")
        result = shutdown_agent_resources(agent, _LOG, [])

        assert "uninject_all" in result["step_errors"]
        assert "injector_err" in result["step_errors"]["uninject_all"]
        assert "clear_all" in result["steps_run"]

    def test_returned_errors_in_stop_resource_owners_for_detach(self) -> None:
        agent = _make_agent({"a": _ErrorReturningOwner()})
        result = stop_resource_owners_for_detach(agent, _LOG)

        assert len(result["errors"]) == 1
        assert result["errors"][0]["error"] == "partial_fail"


class TestT2StopAllBoundary:
    def test_injector_managed_streaming_types_excludes_monitor(self) -> None:
        types = ProbeContext.injector_managed_streaming_types()
        assert "monitor" not in types
        assert "watch" in types
        assert "trace" in types
        assert "stack" in types

    def test_streaming_types_still_includes_monitor(self) -> None:
        assert "monitor" in ProbeContext.streaming_types()

    def test_watch_stop_all_does_not_stop_monitor_probe_context(self) -> None:
        from peeka.commands.watch import WatchCommand

        stopped_types: List[str] = []

        class _FakeInjector:
            def uninject_all(self) -> int:
                return 0

            def cleanup_orphan_watches(self) -> int:
                return 0

        class _FakeObserver:
            def clear_all(self) -> None:
                pass

        class _FakeAgent:
            injector = _FakeInjector()
            observer = _FakeObserver()
            probe_registry = object()
            track_probe_context = object()

            def stop_probe_contexts_by_type(self, probe_types: List[str]) -> None:
                stopped_types.extend(probe_types)

        cmd = WatchCommand(_FakeAgent())  # type: ignore[arg-type]
        cmd._stop_watch({"watch_id": None})

        assert "monitor" not in stopped_types
        assert set(stopped_types) == {"watch", "trace", "stack"}

    def test_trace_stop_all_does_not_stop_monitor_probe_context(self) -> None:
        from peeka.commands.trace import TraceCommand

        stopped_types: List[str] = []

        class _FakeInjector:
            def uninject_all(self) -> int:
                return 0

        class _FakeObserver:
            def clear_all(self) -> None:
                pass

        class _FakeAgent:
            injector = _FakeInjector()
            observer = _FakeObserver()
            probe_registry = object()
            track_probe_context = object()

            def stop_probe_contexts_by_type(self, probe_types: List[str]) -> None:
                stopped_types.extend(probe_types)

        cmd = TraceCommand(_FakeAgent())  # type: ignore[arg-type]
        cmd._stop_trace({"watch_id": None})

        assert "monitor" not in stopped_types


class TestT3HookRestorationGuards:
    def test_sigterm_guard_does_not_overwrite_target_handler(self) -> None:
        from peeka.core.agent import PeekaAgent

        class _TestAgent(PeekaAgent):
            def __init__(self) -> None:
                self.session_id = "test_hook_guard_01"
                self._stopped = False
                self._stop_lock = threading.Lock()
                self._last_cleanup_summary: Dict[str, Any] = {}
                self._prev_sigterm_handler: Any = None
                self._prev_excepthook: Any = None
                self._peeka_excepthook_ref: Any = None
                self.running = True
                self.server = None
                self.command_handlers: Dict[str, Any] = {}
                self._observation_queues: Dict[Any, Any] = {}
                self._observation_queue_stats: Dict[Any, Any] = {}
                self._observation_queue_lock = threading.Lock()
                self._observation_flush_event = threading.Event()
                self._flush_thread_running = False
                self.injector: Any = _MockInjector()
                self.observer: Any = _MockObserver()
                self._probe_contexts: Dict[str, Any] = {}
                self._probe_context_types: Dict[str, Any] = {}
                self._probe_context_lock = threading.Lock()
                self.probe_registry: Any = _MockProbeRegistry()
                if threading.current_thread() is threading.main_thread():
                    try:
                        self._prev_sigterm_handler = signal.signal(signal.SIGTERM, self._handle_sigterm)
                    except (ValueError, OSError):
                        self._prev_sigterm_handler = None

        agent = _TestAgent()
        try:
            def target_handler(signum: int, frame: Any) -> None:
                pass

            signal.signal(signal.SIGTERM, target_handler)
            agent.stop()
            assert signal.getsignal(signal.SIGTERM) is target_handler
        finally:
            signal.signal(signal.SIGTERM, signal.SIG_DFL)

    def test_excepthook_guard_does_not_overwrite_target_hook(self) -> None:
        from peeka.core.agent import PeekaAgent

        class _TestAgent2(PeekaAgent):
            def __init__(self) -> None:
                self.session_id = "test_hook_guard_02"
                self._stopped = False
                self._stop_lock = threading.Lock()
                self._last_cleanup_summary: Dict[str, Any] = {}
                self._prev_sigterm_handler: Any = None
                self._prev_excepthook: Any = sys.excepthook
                self.running = True
                self.server = None
                self.command_handlers: Dict[str, Any] = {}
                self._observation_queues: Dict[Any, Any] = {}
                self._observation_queue_stats: Dict[Any, Any] = {}
                self._observation_queue_lock = threading.Lock()
                self._observation_flush_event = threading.Event()
                self._flush_thread_running = False
                self.injector: Any = _MockInjector()
                self.observer: Any = _MockObserver()
                self._probe_contexts: Dict[str, Any] = {}
                self._probe_context_types: Dict[str, Any] = {}
                self._probe_context_lock = threading.Lock()
                self.probe_registry: Any = _MockProbeRegistry()

                def _peeka_hook(exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                    pass

                sys.excepthook = _peeka_hook
                self._peeka_excepthook_ref: Any = _peeka_hook

        original = sys.excepthook
        agent = _TestAgent2()
        try:
            def target_hook(exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
                pass

            sys.excepthook = target_hook
            agent.stop()
            assert sys.excepthook is target_hook
        finally:
            sys.excepthook = original


class TestT4CleanupContractShape:
    def test_detach_response_includes_cleanup_summary(self) -> None:
        class _FakeAgent:
            attached_pid = 42
            _last_cleanup_summary = {
                "steps_run": ["stop_resource_owners"],
                "step_errors": {},
                "resource_owners": {"handlers_stopped": [], "errors": []},
            }

            def stop(self) -> None:
                pass

        result = DetachCommand(_FakeAgent()).execute({})  # type: ignore[arg-type]
        assert result["status"] == "success"
        assert "cleanup_summary" in result
        assert result["cleanup_summary"]["steps_run"] == ["stop_resource_owners"]

    def test_reset_response_includes_layered_cleanup_summary(self) -> None:
        class _StubInjector:
            def reset(self, pattern: Optional[str] = None) -> Dict[str, Any]:
                return {"status": "success", "enhanced": [], "total": 0}

        class _StubAgent:
            command_handlers: Dict[str, Any] = {}
            injector = _StubInjector()
            _probe_contexts: Dict[str, Any] = {}
            _probe_context_types: Dict[str, Any] = {}
            _probe_context_lock = threading.Lock()

        result = ResetCommand(_StubAgent()).execute({"action": "reset"})  # type: ignore[arg-type]
        assert result["status"] == "success"
        summary = result["cleanup_summary"]
        assert "resource_owners" in summary
        assert "probe_contexts" in summary
        assert "injector" in summary

    def test_reset_cleanup_summary_captures_probe_context_count(self) -> None:
        class _StubInjector:
            def reset(self, pattern: Optional[str] = None) -> Dict[str, Any]:
                return {"status": "success", "enhanced": [], "total": 0}

        stopped: List[str] = []

        class _StubAgent:
            command_handlers: Dict[str, Any] = {}
            injector = _StubInjector()
            _probe_context_lock = threading.Lock()
            _probe_context_types = {"w1": "watch", "w2": "trace"}
            _probe_contexts: Dict[str, Any] = {"w1": None, "w2": None}

            def stop_probe_context(self, stream_key: str) -> None:
                stopped.append(stream_key)

        result = ResetCommand(_StubAgent()).execute({"action": "reset"})  # type: ignore[arg-type]
        summary = result["cleanup_summary"]
        assert summary["probe_contexts"]["stopped_count"] == 2
        assert summary["probe_contexts"]["errors"] == []
