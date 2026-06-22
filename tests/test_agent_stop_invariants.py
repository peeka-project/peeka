"""Tests for PeekaAgent.stop() invariants: idempotency, full cleanup, SIGTERM/atexit registration.

These tests verify:
- stop() calls shutdown_agent_resources before server.close()
- stop() is idempotent (second call is no-op)
- stop() isolates exceptions per cleanup step
- __init__ registers SIGTERM on main thread only
- __init__ registers atexit handler
- _handle_sigterm chains to previous handler
- _init_agent re-attach registers new agent even when old stop() raises
- stop() with empty command_handlers does not error
- Concurrent stop() calls execute cleanup exactly once
"""

import atexit
import os as _os_module
import signal
import sys
import threading
from typing import Any, Dict, List

import peeka.core.agent as _agent_mod
from peeka.core.agent import PeekaAgent, _init_agent

_SENTINEL = object()


class _MockInjector:
    def __init__(self) -> None:
        self.uninject_all_calls = 0

    def uninject_all(self) -> None:
        self.uninject_all_calls += 1


class _MockObserver:
    def __init__(self) -> None:
        self.clear_all_calls = 0

    def clear_all(self) -> None:
        self.clear_all_calls += 1


class _TestAgent(PeekaAgent):
    def __init__(
        self, session_id: str, *, install_sigterm: bool = True
    ) -> None:
        # Bypass PeekaAgent.__init__ entirely — only set what stop() accesses.
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
        # Required by AgentProbeControlMixin.stop_probe_contexts_by_type
        self._probe_contexts: Dict[str, Any] = {}
        self._probe_context_types: Dict[str, Any] = {}
        self._probe_context_lock: threading.Lock = threading.Lock()
        atexit.register(self.stop)
        if install_sigterm and threading.current_thread() is threading.main_thread():
            try:
                self._prev_sigterm_handler = signal.signal(
                    signal.SIGTERM, self._handle_sigterm
                )
            except (ValueError, OSError):
                self._prev_sigterm_handler = None


def test_stop_calls_helper_before_server_close() -> None:
    call_order: List[str] = []
    original_shutdown = _agent_mod.shutdown_agent_resources

    def _tracking_shutdown(
        agent: Any, logger: Any, probe_types: Any
    ) -> Dict[str, Any]:
        call_order.append("helper")
        return {"steps_run": [], "errors": {}}

    class _MockServer:
        def close(self) -> None:
            call_order.append("server_close")

    _agent_mod.shutdown_agent_resources = _tracking_shutdown  # type: ignore[assignment]
    try:
        agent = _TestAgent("test_stop_order_01")
        agent.server = _MockServer()
        agent.stop()
    finally:
        _agent_mod.shutdown_agent_resources = original_shutdown

    assert "helper" in call_order
    assert "server_close" in call_order
    assert call_order.index("helper") < call_order.index("server_close")


def test_stop_passes_dynamic_probe_types_to_helper() -> None:
    captured_probe_types: List[str] = []
    original_shutdown = _agent_mod.shutdown_agent_resources

    def _tracking_shutdown(
        agent: Any, logger: Any, probe_types: Any
    ) -> Dict[str, Any]:
        captured_probe_types.extend(probe_types)
        return {"steps_run": [], "errors": {}}

    _agent_mod.shutdown_agent_resources = _tracking_shutdown  # type: ignore[assignment]
    try:
        agent = _TestAgent("test_stop_dynamic_probe_types_01")
        agent._probe_context_types = {"sk1": "watch", "sk2": "trace"}
        agent.stop()
    finally:
        _agent_mod.shutdown_agent_resources = original_shutdown

    assert captured_probe_types == ["trace", "watch"]


def test_stop_idempotent_second_call_is_noop() -> None:
    shutdown_count: List[int] = [0]
    original_shutdown = _agent_mod.shutdown_agent_resources

    def _counting_shutdown(
        agent: Any, logger: Any, probe_types: Any
    ) -> Dict[str, Any]:
        shutdown_count[0] += 1
        return {"steps_run": [], "errors": {}}

    _agent_mod.shutdown_agent_resources = _counting_shutdown  # type: ignore[assignment]
    try:
        agent = _TestAgent("test_stop_idempotent_02")
        agent.stop()
        agent.stop()
    finally:
        _agent_mod.shutdown_agent_resources = original_shutdown

    assert shutdown_count[0] == 1


def test_stop_exception_isolation_each_step_runs() -> None:
    class _RaisingInjector:
        def uninject_all(self) -> None:
            raise RuntimeError("injector_boom")

    class _TrackingObserver:
        def __init__(self) -> None:
            self.cleared: bool = False

        def clear_all(self) -> None:
            self.cleared = True

    agent = _TestAgent("test_stop_isolation_03")
    observer = _TrackingObserver()
    agent.injector = _RaisingInjector()
    agent.observer = observer
    agent.stop()

    assert observer.cleared is True


def test_init_registers_handlers_on_main_thread() -> None:
    agent = PeekaAgent("test_init_main_04")
    try:
        assert agent._stopped is False
        assert type(agent._stop_lock) is type(threading.Lock())
        assert agent._prev_sigterm_handler is not None
    finally:
        agent.stop()


def test_init_skips_sigterm_off_main_thread() -> None:
    result: List[Any] = [None]

    def _make_agent() -> None:
        result[0] = PeekaAgent("test_sigterm_offmain_05")

    t = threading.Thread(target=_make_agent)
    t.start()
    t.join(timeout=10)

    agent = result[0]
    try:
        assert agent._prev_sigterm_handler is None
    finally:
        agent.stop()


def test_sigterm_handler_chains_previous() -> None:
    _real_kill = _os_module.kill
    kill_calls: List[Any] = []

    def _fake_kill(pid: int, sig: int) -> None:
        kill_calls.append((pid, sig))

    class _MockCallable:
        def __init__(self) -> None:
            self.calls: List[Any] = []

        def __call__(self, signum: int, frame: Any) -> None:
            self.calls.append((signum, frame))

    pre_test_sigterm = signal.getsignal(signal.SIGTERM)
    agent = _TestAgent("test_sigterm_chain_06")
    try:
        _os_module.kill = _fake_kill

        # Subtest 1: callable prev — forwarded, no os.kill
        kill_calls.clear()
        mock_handler = _MockCallable()
        agent._prev_sigterm_handler = mock_handler
        agent._handle_sigterm(15, None)
        assert mock_handler.calls == [(15, None)]
        assert kill_calls == []

        # Subtest 2: SIG_DFL — must call os.kill(pid, 15)
        kill_calls.clear()
        agent._prev_sigterm_handler = signal.SIG_DFL
        agent._handle_sigterm(15, None)
        assert kill_calls == [(_os_module.getpid(), 15)]

        # Subtest 3: SIG_IGN — must NOT call os.kill
        kill_calls.clear()
        agent._prev_sigterm_handler = signal.SIG_IGN
        agent._handle_sigterm(15, None)
        assert kill_calls == []

        # Subtest 4: None (registration failed) — treated as SIG_DFL, must call os.kill(pid, 15)
        kill_calls.clear()
        agent._prev_sigterm_handler = None
        agent._handle_sigterm(15, None)
        assert kill_calls == [(_os_module.getpid(), 15)]
    finally:
        _os_module.kill = _real_kill
        try:
            signal.signal(signal.SIGTERM, pre_test_sigterm)
        except (ValueError, OSError):
            pass


def test_init_agent_reattach_new_agent_registered_when_old_stop_raises() -> None:
    class _RaisingOldAgent:
        session_id = "old_raise_07"

        def stop(self) -> None:
            raise RuntimeError("old stop failed")

        def _emit_log(self, *args: Any, **kwargs: Any) -> None:
            pass

    original_agents = getattr(sys, "_peeka_agents", _SENTINEL)
    sys._peeka_agents = {"old_raise_07": _RaisingOldAgent()}  # type: ignore[attr-defined]

    original_start = PeekaAgent.start

    def _noop_start(self: "PeekaAgent") -> bool:
        return True

    PeekaAgent.start = _noop_start  # type: ignore[method-assign]
    try:
        _init_agent("new_session_reattach_07", None, 0, True)
        registered = getattr(sys, "_peeka_agents", {})
        assert "new_session_reattach_07" in registered
    finally:
        PeekaAgent.start = original_start  # type: ignore[method-assign]
        final_agents: Dict[str, Any] = getattr(sys, "_peeka_agents", {})
        new_agent = final_agents.get("new_session_reattach_07")
        if new_agent is not None:
            new_agent.stop()
        if original_agents is _SENTINEL:
            if hasattr(sys, "_peeka_agents"):
                delattr(sys, "_peeka_agents")
        else:
            sys._peeka_agents = original_agents  # type: ignore[attr-defined]


def test_stop_with_empty_command_handlers_is_noop() -> None:
    agent = _TestAgent("test_stop_empty_handlers_08")
    agent.command_handlers = {}
    agent.stop()

    assert agent._stopped is True


def test_concurrent_stop_calls_only_execute_once() -> None:
    shutdown_count: List[int] = [0]
    original_shutdown = _agent_mod.shutdown_agent_resources

    def _counting_shutdown(
        agent: Any, logger: Any, probe_types: Any
    ) -> Dict[str, Any]:
        shutdown_count[0] += 1
        return {"steps_run": [], "errors": {}}

    _agent_mod.shutdown_agent_resources = _counting_shutdown  # type: ignore[assignment]
    try:
        agent = _TestAgent("test_concurrent_stop_09")
        threads = [threading.Thread(target=agent.stop) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
    finally:
        _agent_mod.shutdown_agent_resources = original_shutdown

    assert shutdown_count[0] == 1
