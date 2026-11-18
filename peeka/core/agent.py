# pyright: reportImportCycles=false
"""
Agent Code - Runs inside target process
This code is injected into the target process and handles command execution
"""

from collections import deque

import atexit
import fnmatch
import json
import logging
import os
import signal
import socket
import sys
import threading
import time as _time
import traceback
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Set, Tuple, cast

from peeka.core import probes as probes_module
from peeka.core.agent_control.clients import AgentClientControlMixin
from peeka.core.agent_control.consumers import AgentConsumerControlMixin
from peeka.core.agent_control.dispatch import AgentCommandDispatchMixin
from peeka.core.agent_control.dx import AgentDXControlMixin
from peeka.core.agent_control.jobs import AgentJobControlMixin
from peeka.core.agent_control.lifecycle import shutdown_agent_resources
from peeka.core.agent_control.probes import AgentProbeControlMixin
from peeka.core.agent_control.target import AgentTargetControlMixin
from peeka.core.injector import DecoratorInjector
from peeka.core.jobs import job_registry
from peeka.core.observer import ObservationManager
from peeka.core.probes import ProbeContext
from peeka.core.probes import ProbeRegistry
from peeka.core.runtime import primitives as _rpl

# Lazy import to avoid circular dependency issues
_client_registry = None
_consumer_registry = None
_dx_case_registry = None
_pending_signal_restore_callbacks: List[Any] = []
_pending_signal_restore_lock = threading.Lock()


def _restore_signal_handler_if_current(
    signum: int,
    previous_handler: Any,
    expected_handler: Any,
) -> bool:
    """Restore a signal handler only if Peeka's handler is still installed."""
    if previous_handler is None or expected_handler is None:
        return False
    if signal.getsignal(signum) is not expected_handler:
        return False
    signal.signal(signum, previous_handler)
    return True


def _schedule_signal_restore_on_main_thread(
    signum: int,
    previous_handler: Any,
    expected_handler: Any,
) -> bool:
    """Schedule signal restoration for the main thread.

    Python only permits signal.signal() from the main thread. Agent.stop() can
    run on a socket client thread during detach, so use Py_AddPendingCall to run
    the identity-guarded restoration at the next main-thread bytecode boundary.
    """
    if previous_handler is None or expected_handler is None:
        return False
    try:
        import ctypes
    except Exception:
        print(
            f"[peeka Agent] Warning: could not schedule signal {signum} restoration on main thread (ctypes unavailable).",
            flush=True,
        )
        return False

    callback_type = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)
    callback_ref: Any = None

    def _pending_restore(_arg: Any) -> int:
        try:
            try:
                _restore_signal_handler_if_current(
                    signum, previous_handler, expected_handler
                )
            except Exception:
                pass
            return 0
        finally:
            with _pending_signal_restore_lock:
                try:
                    _pending_signal_restore_callbacks.remove(callback_ref)
                except ValueError:
                    pass

    callback_ref = callback_type(_pending_restore)
    try:
        py_add_pending_call = ctypes.pythonapi.Py_AddPendingCall
        py_add_pending_call.argtypes = [callback_type, ctypes.c_void_p]
        py_add_pending_call.restype = ctypes.c_int
        with _pending_signal_restore_lock:
            _pending_signal_restore_callbacks.append(callback_ref)
        if py_add_pending_call(callback_ref, None) == 0:
            return True
    except Exception:
        print(
            f"[peeka Agent] Warning: _schedule_signal_restore_on_main_thread failed for signum={signum}.",
            flush=True,
        )
    with _pending_signal_restore_lock:
        try:
            _pending_signal_restore_callbacks.remove(callback_ref)
        except ValueError:
            pass
    print(
        f"[peeka Agent] Warning: could not schedule signal {signum} restoration on main thread (Py_AddPendingCall unavailable or failed).",
        flush=True,
    )
    return False


def _canonical_agent_module():
    """Return the importable agent module shared by injected scripts."""
    module = sys.modules.get("peeka.core.agent")
    if module is None:
        import importlib
        module = importlib.import_module("peeka.core.agent")
    return module


def _recv_exact(conn: Any, size: int) -> bytes:
    """Read a complete frame segment, returning empty bytes on EOF."""
    chunks = []
    while size:
        chunk = conn.recv(size)
        if not chunk:
            return b""
        chunks.append(chunk)
        size -= len(chunk)
    return b"".join(chunks)


_MAX_COMMAND_FRAME_BYTES = 16 * 1024 * 1024


def _get_client_registry():
    """Lazily initialize and return the global client registry singleton."""
    if __name__ != "peeka.core.agent":
        return _canonical_agent_module()._get_client_registry()
    global _client_registry
    if _client_registry is None:
        from peeka.core.client_sessions import ClientRegistry
        _client_registry = ClientRegistry()
    return _client_registry


def _get_consumer_registry():
    """Lazily initialize and return the global result consumer registry singleton."""
    if __name__ != "peeka.core.agent":
        return _canonical_agent_module()._get_consumer_registry()
    global _consumer_registry
    if _consumer_registry is None:
        from peeka.core.result_consumers import ResultConsumerRegistry
        _consumer_registry = ResultConsumerRegistry()
    return _consumer_registry


def _get_dx_case_registry():
    """Lazily initialize and return the global DX case registry singleton."""
    if __name__ != "peeka.core.agent":
        return _canonical_agent_module()._get_dx_case_registry()
    global _dx_case_registry
    if _dx_case_registry is None:
        from peeka.core.dx_cases import DXCaseRegistry

        _dx_case_registry = DXCaseRegistry()
    return _dx_case_registry


def _get_requesting_client_session_id(command: Dict[str, Any]) -> Optional[str]:
    """Return the explicit client session id associated with a command."""
    client_session_id = command.get("client_session_id")
    if client_session_id in (None, ""):
        return None
    return str(client_session_id)


def _consumer_owner_matches(consumer: Any, requesting_client_session_id: Optional[str]) -> bool:
    """Return True if the requesting client is allowed to access the consumer."""
    owner = consumer.client_session_id
    if owner in (None, ""):
        return requesting_client_session_id is None
    return owner == requesting_client_session_id


def _dx_owner_matches(dx_case: Any, requesting_client_session_id: Optional[str]) -> bool:
    """Return True if the requesting client is allowed to access the DX case."""
    owner = dx_case.client_session_id
    if owner in (None, ""):
        return requesting_client_session_id is None
    return owner == requesting_client_session_id


def _client_success(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a standard success envelope for client namespace handlers."""
    return {"status": "success", "data": data}


def _client_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for client namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
    }


def _job_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for job namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "error": f"{error_code}: {message}",
    }


def _consumer_success(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a standard success envelope for consumer namespace handlers."""
    return {"status": "success", "data": data}


def _consumer_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for consumer namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "error": f"{error_code}: {message}",
    }


def _dx_success(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a standard success envelope for dx namespace handlers."""
    return {"status": "success", "data": data}


def _dx_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for dx namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "error": f"{error_code}: {message}",
    }


def _probe_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for probe namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "error": f"{error_code}: {message}",
    }


def _response_message(response: Dict[str, Any], fallback: str) -> str:
    """Return the most specific human-readable message in a response."""
    message = response.get("message") or response.get("error")
    if message:
        return str(message)
    return fallback


class _ObservationQueue(deque):  # pyright: ignore[reportMissingTypeArgument]
    """Bounded FIFO queue for observations destined to one stream client."""

    @property
    def maxsize(self) -> Optional[int]:
        """Return the configured capacity using queue.Queue-compatible naming."""
        return self.maxlen

    def put_nowait(self, item: Any) -> None:
        """Append an item without blocking, dropping the oldest item when full."""
        self.append(item)

    def get_nowait(self) -> Any:
        """Pop the oldest item without blocking."""
        return self.popleft()

    def empty(self) -> bool:
        """Return True when the queue has no pending observations."""
        return len(self) == 0


def _write_session_log(
    session_id: str, level: str, message: str, details: Optional[str] = None
) -> None:
    """Persist agent diagnostics without touching the target process stdio."""
    try:
        log_path = Path(f"/tmp/peeka_{session_id}.log")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{_time.time():.3f} {level} {message}\n")
            if details:
                log_file.write(details.rstrip() + "\n")
    except OSError:
        pass


class _NativeCondition:
    """Condition variable built exclusively on RPL native locks and events."""

    def __init__(self, lock: Any) -> None:
        self._lock = lock
        self._waiters: List[Any] = []

    def wait(self, timeout: Optional[float] = None) -> bool:
        """Release ``lock``, wait for notify_all or timeout, and reacquire ``lock``."""
        waiter = _rpl.create_event()
        self._waiters.append(waiter)
        self._lock.release()
        try:
            return bool(waiter.wait(timeout=timeout))
        finally:
            self._lock.acquire()
            try:
                self._waiters.remove(waiter)
            except ValueError:
                pass

    def wait_for(self, predicate: Any, timeout: Optional[float] = None) -> bool:
        """Wait until ``predicate()`` is true or ``timeout`` elapses."""
        deadline = _rpl.perf_counter() + timeout if timeout is not None else None
        while not predicate():
            if deadline is not None:
                remaining = deadline - _rpl.perf_counter()
                if remaining <= 0:
                    return False
                self.wait(timeout=remaining)
            else:
                self.wait(timeout=None)
        return True

    def notify_all(self) -> None:
        """Wake all threads currently waiting on this condition."""
        waiters = list(self._waiters)
        self._waiters.clear()
        for waiter in waiters:
            waiter.set()


class _InflightCommand:
    """Tracks one in-flight command execution for stop/reset coordination."""

    def __init__(
        self,
        cmd_id: int,
        cmd_type: str,
        action: str,
        pattern: Optional[str],
        is_reset_scoped: bool,
        handler: Any,
        thread_id: int,
        reset_epoch: int,
    ) -> None:
        self.cmd_id = cmd_id
        self.cmd_type = cmd_type
        self.action = action
        self.pattern = pattern
        self.is_reset_scoped = is_reset_scoped
        self.handler = handler
        self.thread_id = thread_id
        self.reset_epoch = reset_epoch
        self.cancelled_by_stop: bool = False
        self.superseded_by_reset: bool = False
        self.reset_patterns: List[Optional[str]] = []


class PeekaAgent(
    AgentTargetControlMixin,
    AgentProbeControlMixin,
    AgentClientControlMixin,
    AgentJobControlMixin,
    AgentConsumerControlMixin,
    AgentDXControlMixin,
    AgentCommandDispatchMixin,
):
    """Agent running inside target process"""

    _get_client_registry = staticmethod(_get_client_registry)
    _get_consumer_registry = staticmethod(_get_consumer_registry)
    _get_dx_case_registry = staticmethod(_get_dx_case_registry)
    _job_registry = staticmethod(lambda: job_registry)
    _get_requesting_client_session_id = staticmethod(_get_requesting_client_session_id)
    _consumer_owner_matches = staticmethod(_consumer_owner_matches)
    _sigterm_handler_ref: Any = None
    _dx_owner_matches = staticmethod(_dx_owner_matches)
    _client_success = staticmethod(_client_success)
    _client_error = staticmethod(_client_error)
    _job_error = staticmethod(_job_error)
    _consumer_success = staticmethod(_consumer_success)
    _consumer_error = staticmethod(_consumer_error)
    _dx_success = staticmethod(_dx_success)
    _dx_error = staticmethod(_dx_error)
    _probe_error = staticmethod(_probe_error)
    _response_message = staticmethod(_response_message)

    _OBS_STREAM_COMMANDS = {
        "watch": {"", "start"},
        "trace": {"", "start"},
        "stack": {"", "start"},
        "monitor": {"", "start"},
        "top": {"", "start"},
    }

    # Seconds a log broadcast may wait on one client before evicting it.
    _LOG_SEND_TIMEOUT = 1.0
    _STOP_DRAIN_TIMEOUT = 0.15
    _STOP_OBSERVATION_DRAIN_TIMEOUT = 0.3
    _STOP_CONCURRENT_WAIT_TIMEOUT = 5.0
    _SIGNAL_STOP_WATCHDOG_TIMEOUT = 1.0
    _RESET_DRAIN_TIMEOUT = 0.05
    _START_RESET_WAIT_TIMEOUT = 1.0
    _DETACH_RESPONSE_TIMEOUT = 2.0

    _QUIET_COMMAND_ACTIONS = {
        ("complete", ""),
        ("logger", "get"),
        ("logger", "list"),
        ("memory", "gc"),
        ("memory", "overview"),
        ("memory", "top"),
        ("monitor", "status"),
        ("reset", "list"),
        ("sc", ""),
        ("sm", ""),
        ("stack", "status"),
        ("target", "hello"),
        ("target", "status"),
        ("thread", "detail"),
        ("thread", "list"),
        ("top", "snapshot"),
        ("trace", "status"),
        ("vmtool", "count"),
        ("vmtool", "get"),
        ("vmtool", "instances"),
        ("watch", "status"),
    }

    # Lazy command registry: (module_path, class_name) tuples.
    # Commands are imported and instantiated on first dispatch,
    # dramatically reducing startup time under GDB injection.
    _COMMAND_REGISTRY: Dict[str, Tuple[str, str]] = {
        "complete": ("peeka.commands.complete", "CompleteCommand"),
        "watch": ("peeka.commands.watch", "WatchCommand"),
        "trace": ("peeka.commands.trace", "TraceCommand"),
        "stack": ("peeka.commands.stack", "StackCommand"),
        "logger": ("peeka.commands.logger", "LoggerCommand"),
        "sc": ("peeka.commands.search", "SearchClassCommand"),
        "sm": ("peeka.commands.search", "SearchMethodCommand"),
        "monitor": ("peeka.commands.monitor", "MonitorCommand"),
        "memory": ("peeka.commands.memory", "MemoryCommand"),
        "reset": ("peeka.commands.reset", "ResetCommand"),
        "vmtool": ("peeka.commands.vmtool", "VMToolCommand"),
        "detach": ("peeka.commands.detach", "DetachCommand"),
        "thread": ("peeka.commands.thread", "ThreadCommand"),
        "top": ("peeka.commands.top", "TopCommand"),
        "patch-status": ("peeka.commands.patch_status", "PatchStatusCommand"),
        "profile": ("peeka.commands.profile", "ProfileCommand"),
    }

    def __init__(
        self,
        session_id: str,
        attached_pid: Optional[int] = None,
        notify_port: int = 0,
        suppress_startup_messages: bool = False,
        agent_mode: Optional[str] = None,
        injection_mode: Optional[str] = None,
    ):
        self.session_id = session_id
        self.attached_pid = attached_pid
        self.running = True
        self.suppress_startup_messages = suppress_startup_messages
        self.sock_path = f"/tmp/peeka_{session_id}.sock"
        self.server: Optional[socket.socket] = None
        self.command_handlers: Dict[str, Any] = {}
        self._client_connections: Set[Any] = set()
        self._client_connection_kinds: Dict[socket.socket, str] = {}
        self._client_write_locks: Dict[socket.socket, Any] = {}
        self._connections_lock = _rpl.allocate_lock()  # DOMAIN: native_thread
        self._observation_queues: Dict[Any, Deque[Any]] = {}
        self._observation_queue_stats: Dict[Any, Dict[str, int]] = {}
        self._observation_queue_flushers: Dict[Any, Any] = {}
        self._observation_queue_lock = _rpl.allocate_lock()
        self._observation_sequence = 0
        self._observation_flush_event = _rpl.create_event()
        self._flush_lock = _rpl.allocate_lock()
        self._flush_thread_running = False
        self._flush_thread_id: Optional[int] = None
        self._mutation_lock = _rpl.allocate_rlock()  # DOMAIN: mixed (command orchestration)

        self._client_counter = 0
        self.observer = ObservationManager()
        self.injector = DecoratorInjector(self)  # pyright: ignore[reportArgumentType]
        self.watch_orphan_grace_seconds = 3600.0
        self.probe_registry: ProbeRegistry = probes_module.probe_registry
        self._probe_contexts: Dict[str, ProbeContext] = {}
        self._probe_context_types: Dict[str, str] = {}
        self._probe_context_lock = _rpl.allocate_lock()  # DOMAIN: mixed (probe lifecycle)

        self._notify_port = notify_port
        
        # Target identification fields (transitional: default from runtime)
        self.agent_mode = agent_mode or "injected"
        if injection_mode:
            self.injection_mode = injection_mode
        else:
            # Default from Python version: PEP 768 for 3.14+ else GDB fallback
            self.injection_mode = "pep768" if sys.version_info >= (3, 14) else "gdb_dlopen"
        
        # Error ring buffer for target.status (last 5 errors)
        self._recent_errors: List[Dict[str, Any]] = []
        self._error_ring_lock = _rpl.allocate_lock()  # DOMAIN: native_thread
        self._stopped: bool = False
        self._stopping: bool = False
        self._stop_owner_tid: Optional[int] = None
        self._stop_done_event: Any = _rpl.create_event()
        self._stop_lock = _rpl.allocate_lock()
        self._handlers_lock = _rpl.allocate_lock()
        self._gate_lock = _rpl.allocate_lock()
        self._gate_cond = _NativeCondition(self._gate_lock)
        self._inflight_commands: Dict[int, _InflightCommand] = {}
        self._inflight_seq: int = 0
        self._active_reset_count: int = 0
        self._reset_epoch: int = 0
        self._detaching_connections: Set[Any] = set()
        self._thread_connections: Dict[int, Any] = {}
        self._last_cleanup_summary: Dict[str, Any] = {}
        self._prev_sigterm_handler: Any = None
        self._sigterm_handler_ref: Any = None
        self._prev_sigint_handler: Any = None
        self._sigint_handler_ref: Any = None
        self._prev_sighup_handler: Any = None
        self._sighup_handler_ref: Any = None
        self._prev_excepthook: Any = None
        self._prev_threading_excepthook: Any = None
        self._peeka_excepthook_ref: Any = None
        self._threading_excepthook_ref: Any = None
        self._signal_cleanup_worker_active: bool = False
        self._fatal_watchdog_active: bool = False
        self._pending_fatal_signal: Optional[int] = None
        atexit.register(self.stop)
        self._install_exit_hooks()
        self._last_seen_at = _time.time()

    @staticmethod
    def _exit_signal_specs() -> List[Tuple[int, str, str, str]]:
        """Return (signum, handler_attr, prev_attr, ref_attr) tuples for exit signals."""
        specs: List[Tuple[int, str, str, str]] = [
            (
                signal.SIGTERM,
                "_handle_sigterm",
                "_prev_sigterm_handler",
                "_sigterm_handler_ref",
            ),
            (
                signal.SIGINT,
                "_handle_sigint",
                "_prev_sigint_handler",
                "_sigint_handler_ref",
            ),
        ]
        sighup = getattr(signal, "SIGHUP", None)
        if sighup is not None:
            specs.append(
                (
                    sighup,
                    "_handle_sighup",
                    "_prev_sighup_handler",
                    "_sighup_handler_ref",
                )
            )
        return specs

    def _install_signal_hook(
        self,
        signum: int,
        handler_attr: str,
        prev_attr: str,
        ref_attr: str,
    ) -> None:
        """Install one exit signal hook while preserving SIG_IGN and existing installs."""
        existing_ref = getattr(self, ref_attr, None)
        try:
            current = signal.getsignal(signum)
        except (ValueError, OSError):
            return
        if existing_ref is not None and current is existing_ref:
            return
        if current is signal.SIG_IGN:
            setattr(self, prev_attr, signal.SIG_IGN)
            setattr(self, ref_attr, None)
            return
        handler_ref = getattr(self, handler_attr)
        try:
            prev = signal.signal(signum, handler_ref)
        except (ValueError, OSError):
            setattr(self, prev_attr, None)
            setattr(self, ref_attr, None)
            return
        setattr(self, prev_attr, prev)
        setattr(self, ref_attr, handler_ref)

    def _install_exit_hooks(self) -> None:
        if threading.current_thread() is threading.main_thread():
            for signum, handler_attr, prev_attr, ref_attr in self._exit_signal_specs():
                self._install_signal_hook(signum, handler_attr, prev_attr, ref_attr)

        _self_ref = self
        existing_excepthook_ref = getattr(self, "_peeka_excepthook_ref", None)
        if (
            existing_excepthook_ref is None
            or sys.excepthook is not existing_excepthook_ref
        ):
            self._prev_excepthook = sys.excepthook

            def _peeka_excepthook(exc_type: Any, exc_value: Any, exc_tb: Any) -> None:
                try:
                    if _self_ref._prev_excepthook is not None:
                        _self_ref._prev_excepthook(exc_type, exc_value, exc_tb)
                finally:
                    try:
                        _self_ref.stop()
                    except Exception:
                        pass

            sys.excepthook = _peeka_excepthook
            self._peeka_excepthook_ref = _peeka_excepthook

        # threading.excepthook — chained (Python 3.8+)
        if hasattr(threading, "excepthook"):
            existing_thread_hook_ref = getattr(self, "_threading_excepthook_ref", None)
            if (
                existing_thread_hook_ref is None
                or threading.excepthook is not existing_thread_hook_ref
            ):
                _prev_threading_hook = threading.excepthook

                def _peeka_threading_excepthook(args: Any) -> None:
                    try:
                        if _prev_threading_hook is not None:
                            _prev_threading_hook(args)
                    finally:
                        try:
                            _self_ref.stop()
                        except Exception:
                            pass

                threading.excepthook = _peeka_threading_excepthook
                self._prev_threading_excepthook = _prev_threading_hook
                self._threading_excepthook_ref = _peeka_threading_excepthook

    def _deliver_pending_fatal_signal(self, signum: int) -> None:
        """Deliver a pending SIG_DFL terminating signal and clear it if os.kill returns."""
        try:
            os.kill(os.getpid(), signum)
        except OSError:
            pass
        if getattr(self, "_pending_fatal_signal", None) == signum:
            self._pending_fatal_signal = None

    def _start_fatal_signal_watchdog(self) -> None:
        """Start a bounded watchdog so SIG_DFL termination never hangs on a locked main thread."""
        if getattr(self, "_fatal_watchdog_active", False):
            return
        timeout = float(getattr(self, "_SIGNAL_STOP_WATCHDOG_TIMEOUT", 1.0))

        def _watchdog() -> None:
            try:
                done_event = self._get_stop_done_event()
                completed = bool(done_event.wait(timeout=max(0.0, timeout)))
                if not completed:
                    pending_sig = getattr(self, "_pending_fatal_signal", None)
                    if pending_sig is not None:
                        self._deliver_pending_fatal_signal(pending_sig)
            except Exception:
                pass
            finally:
                self._fatal_watchdog_active = False

        try:
            self._fatal_watchdog_active = True
            _rpl.start_thread(_watchdog, name="peeka-signal-watchdog")
        except Exception:
            self._fatal_watchdog_active = False

    def _schedule_signal_cleanup(self, fatal_signum: Optional[int]) -> bool:
        """Schedule agent.stop() off the interrupted signal thread without acquiring Peeka locks."""
        if fatal_signum is not None:
            self._pending_fatal_signal = fatal_signum
            self._start_fatal_signal_watchdog()

        if getattr(self, "_signal_cleanup_worker_active", False):
            return True

        def _cleanup_worker() -> None:
            try:
                self.stop()
            except Exception:
                pass
            finally:
                self._signal_cleanup_worker_active = False
                pending_sig = getattr(self, "_pending_fatal_signal", None)
                if pending_sig is not None:
                    self._deliver_pending_fatal_signal(pending_sig)

        try:
            self._signal_cleanup_worker_active = True
            _rpl.start_thread(_cleanup_worker, name="peeka-signal-stop")
            return True
        except Exception:
            self._signal_cleanup_worker_active = False
            return False

    def _handle_exit_signal(
        self,
        signum: int,
        frame: Any,
        prev_attr: str,
        ref_attr: str,
    ) -> None:
        """Handle SIGTERM/SIGINT/SIGHUP without acquiring Peeka locks on the signal thread."""
        prev = getattr(self, prev_attr, None)
        expected_ref = getattr(self, ref_attr, None)
        if expected_ref is not None and prev is expected_ref:
            prev = signal.SIG_DFL

        restore_target = prev if prev is not None else signal.SIG_DFL
        try:
            if expected_ref is None or signal.getsignal(signum) is expected_ref:
                signal.signal(signum, restore_target)
        except (ValueError, OSError):
            pass

        if prev is signal.SIG_IGN:
            return

        done_event = getattr(self, "_stop_done_event", None)
        cleanup_done = bool(
            getattr(self, "_stopped", False)
            and done_event is not None
            and done_event.is_set()
        )
        is_callable_prev = callable(prev) and prev is not signal.SIG_DFL
        is_sigint_none = signum == signal.SIGINT and prev is None

        if cleanup_done:
            if is_callable_prev:
                prev(signum, frame)
                return
            if is_sigint_none:
                raise KeyboardInterrupt
            try:
                os.kill(os.getpid(), signum)
            except OSError:
                pass
            return

        if is_callable_prev or is_sigint_none:
            self._schedule_signal_cleanup(fatal_signum=None)
            if is_callable_prev:
                prev(signum, frame)
                return
            raise KeyboardInterrupt

        self._pending_fatal_signal = signum
        dispatched = self._schedule_signal_cleanup(fatal_signum=signum)
        if not dispatched:
            self._deliver_pending_fatal_signal(signum)

    def _handle_sigterm(self, signum: int, frame: Any) -> None:
        self._handle_exit_signal(
            signum, frame, "_prev_sigterm_handler", "_sigterm_handler_ref"
        )

    def _handle_sigint(self, signum: int, frame: Any) -> None:
        self._handle_exit_signal(
            signum, frame, "_prev_sigint_handler", "_sigint_handler_ref"
        )

    def _handle_sighup(self, signum: int, frame: Any) -> None:
        self._handle_exit_signal(
            signum, frame, "_prev_sighup_handler", "_sighup_handler_ref"
        )

    # ------------------------------------------------------------------ #
    #  Lazy command handler loading & command gate                       #
    # ------------------------------------------------------------------ #

    def _get_handlers_lock(self) -> Any:
        lock = getattr(self, "_handlers_lock", None)
        if lock is None:
            lock = _rpl.allocate_lock()
            self._handlers_lock = lock
        return lock

    def _get_stop_done_event(self) -> Any:
        event = getattr(self, "_stop_done_event", None)
        if event is None:
            event = _rpl.create_event()
            self._stop_done_event = event
        return event

    def _ensure_gate_state(self) -> Tuple[Any, _NativeCondition]:
        lock = getattr(self, "_gate_lock", None)
        cond = getattr(self, "_gate_cond", None)
        if lock is None or cond is None:
            lock = _rpl.allocate_lock()
            cond = _NativeCondition(lock)
            self._gate_lock = lock
            self._gate_cond = cond
        if not hasattr(self, "_inflight_commands"):
            self._inflight_commands = {}
        if not hasattr(self, "_inflight_seq"):
            self._inflight_seq = 0
        if not hasattr(self, "_active_reset_count"):
            self._active_reset_count = 0
        if not hasattr(self, "_reset_epoch"):
            self._reset_epoch = 0
        if not hasattr(self, "_stopping"):
            self._stopping = bool(getattr(self, "_stopped", False))
        return lock, cond

    def _mark_detaching_connection(self, conn: Any) -> None:
        conn_lock = getattr(self, "_connections_lock", None)
        if conn_lock is not None:
            with conn_lock:
                detaching = getattr(self, "_detaching_connections", None)
                if detaching is None:
                    detaching = set()
                    self._detaching_connections = detaching
                detaching.add(conn)

    def _unmark_detaching_connection(self, conn: Any) -> None:
        conn_lock = getattr(self, "_connections_lock", None)
        if conn_lock is not None:
            with conn_lock:
                detaching = getattr(self, "_detaching_connections", None)
                if detaching is not None:
                    detaching.discard(conn)

    def _get_handler(self, cmd_type: str) -> Optional[Any]:
        """Return the handler for *cmd_type*, importing lazily if needed."""
        handler = self.command_handlers.get(cmd_type)
        if handler is not None:
            return handler

        spec = self._COMMAND_REGISTRY.get(cmd_type)
        if spec is None:
            return None

        module_path, class_name = spec
        try:
            import importlib

            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            candidate = cls(self)  # type: ignore[abstract]
            with self._get_handlers_lock():
                existing = self.command_handlers.get(cmd_type)
                if existing is not None:
                    return existing
                self.command_handlers[cmd_type] = candidate
                return candidate
        except Exception:
            self._emit_log(
                "ERROR",
                f"[peeka Agent] Failed to load handler for {cmd_type}",
                traceback.format_exc(),
            )
            return None

    @staticmethod
    def _is_reset_scoped_command(handler: Any, command: Dict[str, Any]) -> bool:
        """Return True when a command starts resources torn down by reset."""
        if handler is None:
            return False
        action = str(command.get("action") or "")
        if action not in ("", "start"):
            return False
        if getattr(handler, "is_resource_owner", False) is True:
            scope = getattr(handler, "cleanup_scope", None)
            return getattr(scope, "value", None) == "detach_and_reset"
        return getattr(type(handler), "category", None) == "probe"

    @staticmethod
    def _reset_pattern_matches(
        reset_patterns: List[Optional[str]], cmd_pattern: Optional[str]
    ) -> bool:
        """Return True if any recorded reset pattern covers ``cmd_pattern``."""
        for reset_pattern in reset_patterns:
            if reset_pattern is None:
                return True
            if cmd_pattern is None or fnmatch.fnmatch(cmd_pattern, reset_pattern):
                return True
        return False

    def _finish_cancelled_command_job(self, result: Any) -> None:
        """Move any job started by a rolled-back command to a terminal state."""
        if not isinstance(result, dict):
            return
        job_id = result.get("job_id")
        if not job_id:
            return
        try:
            job_reg = self._job_registry()
            job = job_reg.get(job_id)
            if job is not None:
                from peeka.core.jobs import TERMINAL_STATUSES

                if job.status not in TERMINAL_STATUSES:
                    job_reg.set_status(
                        job_id,
                        "cancelled",
                        last_error={
                            "code": "COMMAND_ROLLED_BACK",
                            "message": "Command rolled back due to concurrent stop or reset",
                        },
                    )
                if job.foreground and job.client_session_id:
                    self._get_client_registry().clear_foreground_job(
                        job.client_session_id,
                        expected_job_id=job_id,
                    )
        except Exception:
            pass

    def _rollback_inflight_for_stop(
        self, token: _InflightCommand, result: Any
    ) -> Dict[str, Any]:
        """Roll back any runtime state created by a command that finished after stop."""
        from peeka.core.agent_control.lifecycle import _is_resource_owner

        if token.handler is not None and _is_resource_owner(token.handler):
            try:
                token.handler.stop_active_resources(pattern=None, reason="detach")
            except Exception:
                pass

        if isinstance(result, dict):
            watch_id = result.get("watch_id")
            if watch_id:
                try:
                    self.stop_probe_context(watch_id)
                except Exception:
                    pass
                try:
                    self.injector.uninject(watch_id)
                except Exception:
                    pass
                try:
                    self.observer.unregister_watch(watch_id)
                except Exception:
                    pass
            probe_id = result.get("probe_id")
            if probe_id and hasattr(self, "probe_registry"):
                try:
                    from peeka.core.probes import TERMINAL_STATUSES as PROBE_TERMINAL

                    probe = self.probe_registry.get(probe_id)
                    if probe is not None and probe.status not in PROBE_TERMINAL:
                        self.probe_registry.set_status(probe_id, "stopped")
                    self._finish_probe_job(probe_id, "cancelled")
                except Exception:
                    pass

        try:
            self.stop_probe_contexts_by_type(self.list_tracked_probe_types())
        except Exception:
            pass
        try:
            self.injector.uninject_all()
        except Exception:
            pass
        try:
            self.observer.clear_all()
        except Exception:
            pass
        try:
            self.probe_registry.cleanup(older_than_seconds=0, completed_only=True)
        except Exception:
            pass
        self._finish_cancelled_command_job(result)
        return {
            "status": "error",
            "error_code": "AGENT_STOPPING",
            "message": "Agent stopped while command was in flight",
            "error": "AGENT_STOPPING: Agent stopped while command was in flight",
        }

    def _rollback_inflight_for_reset(
        self, token: _InflightCommand, result: Any
    ) -> Dict[str, Any]:
        """Roll back any reset-scoped state installed by a superseded start command."""
        from peeka.core.agent_control.lifecycle import _is_resource_owner

        watch_id = result.get("watch_id") if isinstance(result, dict) else None
        if token.handler is not None and _is_resource_owner(token.handler):
            try:
                if watch_id:
                    token.handler.execute({"action": "stop", "watch_id": watch_id})
                else:
                    stop_pattern = token.pattern
                    if stop_pattern is None and token.reset_patterns:
                        stop_pattern = token.reset_patterns[-1]
                    token.handler.stop_active_resources(
                        pattern=stop_pattern, reason="reset"
                    )
            except Exception:
                pass

        if watch_id:
            try:
                self.stop_probe_context(watch_id)
            except Exception:
                pass
            try:
                self.injector.uninject(watch_id)
            except Exception:
                pass
            try:
                self.observer.unregister_watch(watch_id)
            except Exception:
                pass

        if isinstance(result, dict):
            probe_id = result.get("probe_id")
            if probe_id and hasattr(self, "probe_registry"):
                try:
                    from peeka.core.probes import TERMINAL_STATUSES as PROBE_TERMINAL

                    probe = self.probe_registry.get(probe_id)
                    if probe is not None and probe.status not in PROBE_TERMINAL:
                        self.probe_registry.set_status(probe_id, "stopped")
                    self._finish_probe_job(probe_id, "cancelled")
                except Exception:
                    pass

        self._finish_cancelled_command_job(result)
        return {
            "status": "error",
            "error_code": "RESET_IN_PROGRESS",
            "message": "Command superseded by concurrent reset",
            "error": "RESET_IN_PROGRESS: Command superseded by concurrent reset",
        }

    def _is_agent_stopped(self) -> bool:
        """Return True when the agent is stopped or shutting down."""
        return bool(
            getattr(self, "_stopping", False)
            or getattr(self, "_stopped", False)
            or not getattr(self, "running", True)
        )

    def track_probe_context(
        self,
        stream_key: str,
        probe_context: ProbeContext,
        probe_type: str,
    ) -> None:
        """Track an active probe context unless the agent is stopping/stopped."""
        if self._is_agent_stopped():
            cleanup = getattr(self, "_cleanup_orphaned_probe_context", None)
            if callable(cleanup):
                cleanup(stream_key, probe_context, probe_type)
            else:
                try:
                    probe_context.__exit__(None, None, None)
                except Exception:
                    pass
            return
        super().track_probe_context(stream_key, probe_context, probe_type)

    def _execute_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a command behind stop and reset-vs-start coordination gates."""
        cmd_type = str(command.get("type", "") or "")
        action = str(command.get("action") or "")

        if cmd_type == "detach":
            return super()._execute_command(command)

        gate_lock, gate_cond = self._ensure_gate_state()
        is_reset = cmd_type == "reset" and action != "list"
        handler = None if ("command" in command and command.get("command") == "ping") else self._get_handler(cmd_type)
        is_reset_scoped = (not is_reset) and self._is_reset_scoped_command(handler, command)
        raw_pattern = command.get("pattern")
        pattern = raw_pattern if isinstance(raw_pattern, str) else None
        tid = _rpl.get_ident()

        with gate_lock:
            if getattr(self, "_stopping", False) or getattr(self, "_stopped", False):
                return {
                    "status": "error",
                    "error_code": "AGENT_STOPPING",
                    "message": "Agent is stopping",
                    "error": "AGENT_STOPPING: Agent is stopping",
                }

            if is_reset_scoped and self._active_reset_count > 0:
                gate_cond.wait_for(
                    lambda: (
                        self._active_reset_count == 0
                        or getattr(self, "_stopping", False)
                        or getattr(self, "_stopped", False)
                    ),
                    timeout=self._START_RESET_WAIT_TIMEOUT,
                )
                if getattr(self, "_stopping", False) or getattr(self, "_stopped", False):
                    return {
                        "status": "error",
                        "error_code": "AGENT_STOPPING",
                        "message": "Agent is stopping",
                        "error": "AGENT_STOPPING: Agent is stopping",
                    }
                if self._active_reset_count > 0:
                    return {
                        "status": "error",
                        "error_code": "RESET_IN_PROGRESS",
                        "message": "Reset is in progress",
                        "error": "RESET_IN_PROGRESS: Reset is in progress",
                    }

            if is_reset:
                self._active_reset_count += 1
                self._reset_epoch += 1
                reset_epoch = self._reset_epoch
                pre_existing_starts = [
                    tok
                    for tok in self._inflight_commands.values()
                    if tok.is_reset_scoped and tok.reset_epoch < reset_epoch
                ]
                if pre_existing_starts:
                    gate_cond.wait_for(
                        lambda: (
                            all(
                                tok.cmd_id not in self._inflight_commands
                                for tok in pre_existing_starts
                            )
                            or getattr(self, "_stopping", False)
                            or getattr(self, "_stopped", False)
                        ),
                        timeout=self._RESET_DRAIN_TIMEOUT,
                    )
                    if getattr(self, "_stopping", False) or getattr(self, "_stopped", False):
                        self._active_reset_count = max(0, self._active_reset_count - 1)
                        gate_cond.notify_all()
                        return {
                            "status": "error",
                            "error_code": "AGENT_STOPPING",
                            "message": "Agent is stopping",
                            "error": "AGENT_STOPPING: Agent is stopping",
                        }
                    for tok in pre_existing_starts:
                        if tok.cmd_id in self._inflight_commands:
                            tok.superseded_by_reset = True
                            tok.reset_patterns.append(pattern)

            self._inflight_seq += 1
            token = _InflightCommand(
                cmd_id=self._inflight_seq,
                cmd_type=cmd_type,
                action=action,
                pattern=pattern,
                is_reset_scoped=is_reset_scoped,
                handler=handler,
                thread_id=tid,
                reset_epoch=self._reset_epoch,
            )
            self._inflight_commands[token.cmd_id] = token

        result: Any = None
        try:
            result = super()._execute_command(command)
        finally:
            with gate_lock:
                self._inflight_commands.pop(token.cmd_id, None)
                if is_reset:
                    self._active_reset_count = max(0, self._active_reset_count - 1)
                gate_cond.notify_all()
                stopped_during_call = (
                    token.cancelled_by_stop
                    or getattr(self, "_stopping", False)
                    or getattr(self, "_stopped", False)
                )
                superseded_by_reset = token.superseded_by_reset

        if stopped_during_call:
            return self._rollback_inflight_for_stop(token, result)
        if superseded_by_reset and self._reset_pattern_matches(
            token.reset_patterns, token.pattern
        ):
            return self._rollback_inflight_for_reset(token, result)
        return result

    def _emit_log(
        self, level: str, message: str, details: Optional[str] = None
    ) -> None:
        """Send diagnostics through side channels only."""
        self._send_log(level, message)
        _write_session_log(self.session_id, level, message, details)

    def _add_recent_error(self, error_entry: Dict[str, Any]) -> None:
        """Add an error entry to the ring buffer (max 5)."""
        with self._error_ring_lock:
            self._recent_errors.append(error_entry)
            if len(self._recent_errors) > 5:
                self._recent_errors.pop(0)

    def is_client_session_live(self, client_session_id: Optional[str]) -> bool:
        """Return True when a client session is still registered as live."""
        if client_session_id in (None, ""):
            return False
        try:
            return self._get_client_registry().get(str(client_session_id)) is not None
        except Exception:
            return True  # Fail-open: registry lookup error must not trigger orphan cleanup.

    def cleanup_orphan_watches(self, now: Optional[float] = None) -> int:
        """Sweep abandoned watch probes after owner-loss grace expires."""
        return self.injector.cleanup_orphan_watches(now=now)
    







    def _register_handlers(self) -> None:
        """Eagerly import and register ALL command handlers.

        Used by `start()` after the socket is ready so that commands
        are available immediately.  Runs on the agent thread so it
        does not block GIL during GDB injection.
        """
        for cmd_type in list(self._COMMAND_REGISTRY):
            self._get_handler(cmd_type)

    @staticmethod
    def _normalize_action(command: Dict[str, Any]) -> str:
        """Return a normalized action name for logging decisions."""
        action = command.get("action")
        if action is None:
            return ""
        return str(action).lower()

    def _should_log_command(self, command: Dict[str, Any]) -> bool:
        """Return True when a command is worth surfacing in agent activity logs."""
        cmd_type = str(command.get("type", "unknown"))
        action = self._normalize_action(command)
        return (cmd_type, action) not in self._QUIET_COMMAND_ACTIONS

    @staticmethod
    def _sanitize_client_field(value: Any, default: str) -> str:
        """Normalize client identity fields before placing them in logs."""
        text = str(value if value not in (None, "") else default)
        sanitized = []
        for char in text[:48]:
            if char.isalnum() or char in ("-", "_", "."):
                sanitized.append(char)
            else:
                sanitized.append("_")
        return "".join(sanitized) or default

    def _extract_client_info(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Extract sanitized client metadata from a command payload."""
        raw_info = command.get("_client")
        if not isinstance(raw_info, dict):
            return {}

        info: Dict[str, Any] = {
            "id": self._sanitize_client_field(raw_info.get("id"), "anonymous"),
            "source": self._sanitize_client_field(raw_info.get("source"), "unknown"),
            "kind": self._sanitize_client_field(raw_info.get("kind"), "client"),
        }
        pid = raw_info.get("pid")
        if isinstance(pid, int) or (isinstance(pid, str) and pid.isdigit()):
            info["pid"] = str(pid)
        if raw_info.get("observations") is False:
            info["observations"] = False
        return info

    @staticmethod
    def _strip_client_info(command: Dict[str, Any]) -> Dict[str, Any]:
        """Remove transport metadata before command dispatch."""
        if "_client" not in command:
            return command
        stripped = dict(command)
        stripped.pop("_client", None)
        return stripped

    def _is_client_hello(self, command: Dict[str, Any]) -> bool:
        """Return True for client identity frames handled by the transport layer."""
        cmd_type = str(command.get("type", ""))
        action = self._normalize_action(command)
        return cmd_type == "client" and action == "hello"

    @staticmethod
    def _client_info_requests_stream(client_info: Dict[str, Any]) -> bool:
        """Return True when client metadata identifies a stream-only connection."""
        source = str(client_info.get("source", ""))
        kind = str(client_info.get("kind", ""))
        return kind == "stream" or source.endswith("-stream")

    @staticmethod
    def _client_info_declines_observations(client_info: Dict[str, Any]) -> bool:
        """Return True when a control connection asked never to receive OBS frames.

        Clients that read observations on a dedicated stream connection (the
        TUI) send start commands over a control connection that nobody reads
        between RPCs. Promoting it to a stream connection would fill its socket
        buffer, get it evicted as a slow client, and break every later command.
        """
        return client_info.get("observations") is False

    @staticmethod
    def _format_client_label(client_id: int, client_info: Dict[str, Any]) -> str:
        """Return a readable stable client label for activity logs."""
        instance_id = client_info.get("id")
        source = client_info.get("source")
        if instance_id and source:
            return f"client {instance_id}/{source} conn#{client_id}"
        return f"conn#{client_id}"

    def _summarize_command(self, command: Dict[str, Any]) -> str:
        """Build a concise command summary for agent-side diagnostics."""
        cmd_type = str(command.get("type", "unknown"))
        action = self._normalize_action(command) or "execute"
        details = []

        for key in ("pattern", "watch_id", "top_id", "logger", "level", "target"):
            value = command.get(key)
            if value not in (None, ""):
                details.append(f"{key}={value}")

        if "interval" in command:
            details.append(f"interval={command.get('interval')}")
        if "times" in command:
            details.append(f"times={command.get('times')}")

        summary = f"{cmd_type}/{action}"
        if details:
            summary += " " + " ".join(details[:4])
        return summary

    @staticmethod
    def _summarize_result(result: Dict[str, Any]) -> str:
        """Build a concise result summary for command completion logs."""
        details = []
        for key in ("watch_id", "top_id", "message", "observation_count"):
            value = result.get(key)
            if value not in (None, "", []):
                details.append(f"{key}={value}")

        if not details:
            return "success"
        return "success " + " ".join(details[:3])

    def start(self) -> bool:
        if getattr(self, "_stopping", False) or getattr(self, "_stopped", False):
            return False
        try:
            self.server = _rpl.create_socket("AF_UNIX", "SOCK_STREAM")

            if Path(self.sock_path).exists():
                Path(self.sock_path).unlink()

            assert self.server is not None
            self.server.bind(self.sock_path)
            try:
                os.chmod(self.sock_path, 0o600)
            except OSError:
                pass
            self.server.listen(5)
            # Set a timeout so accept() doesn't block forever,
            # allowing the accept loop to check self.running periodically.
            self.server.settimeout(1.0)

            # Start the accept loop with a native low-level thread. Do not use
            # target-process threading primitives here: frameworks such as
            # gevent may monkey-patch threading.Event/Thread and make blocking
            # waits illegal in the injection callback.
            _rpl.start_thread(self._accept_loop)

            # Signal readiness via TCP reverse-connect (preferred) and
            # .ready file (fallback / backward compatibility).
            self._notify_ready()
            Path(f"/tmp/peeka_{self.session_id}.ready").touch()
            msg_start = "[peeka Agent] Started and listening for connections"
            msg_ready = "[peeka Agent] Ready for commands"
            self._emit_log("INFO", msg_start)
            self._emit_log("INFO", msg_ready)

            # Eagerly load all command handlers now that the socket is
            # ready.  This runs on the agent thread (not GIL-blocking).
            self._register_handlers()
            self._start_flush_thread()
            return True

        except Exception as e:
            self.running = False
            self._signal_observation_queue_drain()
            if self.server:
                try:
                    self.server.close()
                except OSError:
                    pass
                self.server = None
            self._cleanup_session_files()
            try:
                atexit.unregister(self.stop)
            except Exception:
                pass
            self._uninstall_exit_hooks()
            msg = f"[peeka Agent] Start failed: {e}"
            self._emit_log("ERROR", msg, traceback.format_exc())
            return False

    def _accept_loop(self) -> None:
        while (
            self.running
            and not getattr(self, "_stopping", False)
            and not getattr(self, "_stopped", False)
        ):
            try:
                if self.server is None:
                    break
                conn, _ = _rpl.native_accept(self.server)
                if (
                    not self.running
                    or getattr(self, "_stopping", False)
                    or getattr(self, "_stopped", False)
                ):
                    try:
                        conn.close()
                    except Exception:
                        pass
                    break
                self._client_counter += 1
                _rpl.start_thread(self._handle_client, (conn, self._client_counter))
            except socket.timeout:
                # Periodic wakeup to re-check self.running
                continue
            except OSError:
                # Server socket closed (stop() called) — exit cleanly
                break
            except Exception as e:
                if self.running and not getattr(self, "_stopping", False):
                    msg = f"[peeka Agent] Accept error: {e}"
                    self._emit_log("ERROR", msg, traceback.format_exc())

    def _register_client_connection(
        self, conn: socket.socket, kind: str = "control"
    ) -> int:
        """Track a live client connection and initialize its write lock."""
        with self._connections_lock:
            self._client_connections.add(conn)
            self._client_connection_kinds[conn] = kind
            self._client_write_locks[conn] = _rpl.allocate_lock()
            connection_count = len(self._client_connections)
        if kind == "stream":
            self._get_or_create_connection_queue(conn)
            self._start_flush_thread()
        return connection_count

    @staticmethod
    def _new_observation_queue_stats() -> Dict[str, int]:
        """Return a fresh stats dictionary for one observation queue."""
        return {
            "enqueued": 0,
            "delivered": 0,
            "dropped": 0,
            "dropped_count": 0,
            "encode_dropped_count": 0,
            "oversize_dropped_count": 0,
            "drain_dropped": 0,
            "drain_dropped_count": 0,
            "slow_evicted_count": 0,
            "evicted_count": 0,
        }

    def _get_or_create_connection_queue(self, conn: socket.socket) -> Deque[Any]:
        """Return the bounded observation queue for a stream connection.

        Args:
            conn: Client connection that receives observation frames.

        Returns:
            The per-connection FIFO observation queue.
        """
        with self._observation_queue_lock:
            queue = self._observation_queues.get(conn)
            if queue is None:
                queue = _ObservationQueue(maxlen=1024)
                self._observation_queues[conn] = queue
                self._observation_queue_stats[conn] = self._new_observation_queue_stats()
                if self._flush_thread_id is not None:
                    self._observation_queue_flushers[conn] = self._flush_thread_id
            return queue

    def _enqueue_observation(self, conn: socket.socket, item: Any) -> None:
        """Enqueue an observation for a stream connection and track overflow."""
        with self._observation_queue_lock:
            queue = self._observation_queues.get(conn)
            if queue is None:
                queue = _ObservationQueue(maxlen=1024)
                self._observation_queues[conn] = queue
                self._observation_queue_stats[conn] = self._new_observation_queue_stats()
                if self._flush_thread_id is not None:
                    self._observation_queue_flushers[conn] = self._flush_thread_id

            stats = self._observation_queue_stats[conn]
            if queue.maxlen is not None and len(queue) == queue.maxlen:
                stats["dropped"] += 1
                stats["dropped_count"] += 1

            queue.append(item)
            stats["enqueued"] += 1

    def _set_client_connection_kind(self, conn: socket.socket, kind: str) -> None:
        """Update the broadcast kind for a live client connection."""
        with self._connections_lock:
            if conn in self._client_connections:
                self._client_connection_kinds[conn] = kind
        if kind == "stream":
            self._get_or_create_connection_queue(conn)
            self._start_flush_thread()

    def _unregister_client_connection(self, conn: socket.socket) -> int:
        """Forget a client connection, write lock, and observation queue."""
        with self._connections_lock:
            if conn in self._client_connections:
                self._client_connections.remove(conn)
            self._client_connection_kinds.pop(conn, None)
            self._client_write_locks.pop(conn, None)
            connection_count = len(self._client_connections)
        with self._observation_queue_lock:
            self._observation_queues.pop(conn, None)
            self._observation_queue_stats.pop(conn, None)
            self._observation_queue_flushers.pop(conn, None)
        return connection_count

    def _get_flush_lock(self) -> Any:
        """Return the lock serializing observation queue flush passes."""
        lock = getattr(self, "_flush_lock", None)
        if lock is None:
            lock = _rpl.allocate_lock()
            self._flush_lock = lock
        return lock

    def _start_flush_thread(self) -> None:
        """Start the observation queue flush worker on a native thread."""
        if self._flush_thread_id is not None:
            return
        if getattr(self, "_stopping", False) or getattr(self, "_stopped", False):
            return
        self._get_flush_lock()
        self._flush_thread_running = True
        try:
            thread_id = _rpl.start_thread(
                self._flush_loop,
                name="peeka-observation-flusher",
            )
        except Exception:
            self._flush_thread_running = False
            self._flush_thread_id = None
            return
        self._flush_thread_id = thread_id
        with self._observation_queue_lock:
            for conn in self._observation_queues:
                self._observation_queue_flushers[conn] = thread_id

    def _flush_loop(self) -> None:
        """Flush queued observations to stream sockets until the agent stops."""
        flush_lock = self._get_flush_lock()
        while self._flush_thread_running:
            try:
                self._observation_flush_event.wait(timeout=0.05)
                self._observation_flush_event.clear()
                if not self._flush_thread_running:
                    break
                while self._flush_thread_running:
                    with flush_lock:
                        if not self._flush_thread_running:
                            break
                        has_more = self._flush_all_connections()
                    if not has_more:
                        break
            except Exception:
                self._emit_log(
                    "ERROR",
                    "[peeka Agent] Observation flush loop error",
                    traceback.format_exc(),
                )

    @staticmethod
    def _close_connection_quietly(conn: Any) -> None:
        """Best-effort shutdown and close for a client socket or mock."""
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    def _flush_all_connections(
        self,
        *,
        send_timeout: float = 0.1,
        skip_conns: Optional[Set[Any]] = None,
    ) -> bool:
        """Drain pending observation batches for all stream connections.

        Returns:
            True when any remaining stream connection still has queued items.
        """
        dead_connections = []
        with self._observation_queue_lock:
            conn_list = [
                conn
                for conn in self._observation_queues.keys()
                if skip_conns is None or conn not in skip_conns
            ]

        for conn in conn_list:
            ok = (
                self._flush_connection(conn)
                if send_timeout == 0.1
                else self._flush_connection(conn, send_timeout=send_timeout)
            )
            if not ok:
                dead_connections.append(conn)

        is_stopping = bool(getattr(self, "_stopping", False))
        detaching_connections = set(
            getattr(self, "_detaching_connections", ()) or ()
        )
        for conn in dead_connections:
            if skip_conns is not None:
                skip_conns.add(conn)
            if is_stopping:
                if conn not in detaching_connections:
                    self._close_connection_quietly(conn)
            else:
                self._evict_client_connection(conn)

        with self._observation_queue_lock:
            return any(
                len(queue) > 0
                for conn, queue in self._observation_queues.items()
                if skip_conns is None or conn not in skip_conns
            )

    def _encode_observation_frame(self, observation: Any) -> Optional[bytes]:
        """Encode one queued observation as an OBS frame."""
        if isinstance(observation, bytes):
            if observation.startswith(b"OBS:"):
                return observation
            return None
        try:
            payload = json.dumps(observation).encode("utf-8")
        except (TypeError, ValueError):
            return None
        return b"OBS:" + len(payload).to_bytes(4, "big") + payload

    def _flush_connection(
        self, conn: socket.socket, send_timeout: float = 0.1
    ) -> bool:
        """Flush a bounded batch for one connection; return False if dead."""
        max_batch_count = 64
        max_batch_bytes = 256 * 1024
        frames = bytearray()
        encoded_count = 0
        dropped_count = 0
        encode_dropped_count = 0
        oversize_dropped_count = 0
        processed_count = 0

        while processed_count < max_batch_count:
            with self._observation_queue_lock:
                queue = self._observation_queues.get(conn)
                if queue is None:
                    break
                if not queue:
                    break
                observation = queue.popleft()

            frame = self._encode_observation_frame(observation)
            if frame is None:
                dropped_count += 1
                encode_dropped_count += 1
                processed_count += 1
                continue

            if len(frame) > max_batch_bytes:
                dropped_count += 1
                oversize_dropped_count += 1
                processed_count += 1
                continue

            if len(frames) + len(frame) > max_batch_bytes:
                with self._observation_queue_lock:
                    queue = self._observation_queues.get(conn)
                    if queue is not None:
                        queue.appendleft(observation)
                break

            frames.extend(frame)
            encoded_count += 1
            processed_count += 1

        if dropped_count:
            with self._observation_queue_lock:
                stats = self._observation_queue_stats.get(conn)
                if stats is not None:
                    stats["dropped"] += dropped_count
                    stats["dropped_count"] += dropped_count
                    stats["encode_dropped_count"] = (
                        stats.get("encode_dropped_count", 0) + encode_dropped_count
                    )
                    stats["oversize_dropped_count"] = (
                        stats.get("oversize_dropped_count", 0) + oversize_dropped_count
                    )

        if not frames:
            return True

        send_ok = (
            self._send_observation_frames_with_timeout(conn, bytes(frames))
            if send_timeout == 0.1
            else self._send_observation_frames_with_timeout(
                conn, bytes(frames), timeout=send_timeout
            )
        )
        if not send_ok:
            if getattr(self, "_stopping", False):
                self._record_drain_dropped(conn, encoded_count)
            else:
                self._record_slow_client_eviction(conn)
            return False

        with self._observation_queue_lock:
            stats = self._observation_queue_stats.get(conn)
            if stats is not None:
                stats["delivered"] += encoded_count
        return True

    def _record_drain_dropped(self, conn: Any, count: int) -> None:
        """Record observations that could not be drained before stop timeout."""
        if count <= 0:
            return
        with self._observation_queue_lock:
            stats = self._observation_queue_stats.get(conn)
            if stats is not None:
                stats["drain_dropped"] = stats.get("drain_dropped", 0) + count
                stats["drain_dropped_count"] = (
                    stats.get("drain_dropped_count", 0) + count
                )

    def _record_slow_client_eviction(self, conn: socket.socket) -> None:
        """Increment slow-client eviction counters for a stream connection."""
        with self._observation_queue_lock:
            stats = self._observation_queue_stats.get(conn)
            if stats is not None:
                stats["slow_evicted_count"] = stats.get("slow_evicted_count", 0) + 1
                stats["evicted_count"] = stats.get("evicted_count", 0) + 1

    def _send_fallback_frames_with_timeout(
        self,
        conn: socket.socket,
        frames: bytes,
        write_lock: Optional[Any],
        timeout: float,
    ) -> bool:
        """Bounded fallback write for mock/wrapper transports without fileno()."""
        done = _rpl.create_event()
        result: Dict[str, bool] = {"ok": False}

        def _worker() -> None:
            acquired = True
            if write_lock is not None:
                acquired = bool(write_lock.acquire(True, timeout))
            if not acquired:
                done.set()
                return
            try:
                conn.sendall(frames)
                result["ok"] = True
            except Exception:
                pass
            finally:
                if write_lock is not None:
                    write_lock.release()
                done.set()

        try:
            _rpl.start_thread(_worker, name="peeka-observation-send-fallback")
        except Exception:
            return False
        if not done.wait(timeout=timeout):
            return False
        return result["ok"]

    def _send_observation_frames_with_timeout(
        self, conn: socket.socket, frames: bytes, timeout: float = 0.1
    ) -> bool:
        """Send observation frames with a bounded per-connection timeout."""
        deadline = _rpl.perf_counter() + timeout
        with self._connections_lock:
            write_lock = self._client_write_locks.get(conn)
        try:
            conn.fileno()
            send = conn.send
        except (AttributeError, TypeError, OSError):
            return self._send_fallback_frames_with_timeout(
                conn, frames, write_lock, timeout
            )

        if write_lock is not None and not write_lock.acquire(True, timeout):
            return False
        try:
            view = memoryview(frames)
            sent = 0
            use_fallback = False
            while sent < len(view):
                remaining = deadline - _rpl.perf_counter()
                if remaining <= 0 or not _rpl.wait_writable(conn, remaining):
                    return False
                try:
                    count = send(view[sent:], socket.MSG_DONTWAIT)
                except (BlockingIOError, InterruptedError):
                    continue
                except TypeError:
                    if sent:
                        return False
                    use_fallback = True
                    break
                if not count:
                    return False
                sent += count
            if not use_fallback:
                return True
        except Exception:
            return False
        finally:
            if write_lock is not None:
                write_lock.release()

        remaining = max(0.001, deadline - _rpl.perf_counter())
        return self._send_fallback_frames_with_timeout(
            conn, frames, write_lock, remaining
        )

    def _signal_observation_queue_drain(self) -> None:
        """Signal the flush worker to stop and wake any pending wait."""
        self._flush_thread_running = False
        try:
            self._observation_flush_event.set()
        except Exception:
            pass

    def _snapshot_client_connections(
        self, kind: Optional[str] = None
    ) -> List[socket.socket]:
        """Return a snapshot of currently tracked client sockets."""
        with self._connections_lock:
            if kind is not None:
                return [
                    conn
                    for conn in self._client_connections
                    if self._client_connection_kinds.get(conn, "control") == kind
                ]
            return list(self._client_connections)

    @classmethod
    def _command_opens_observation_stream(cls, command: Dict[str, Any]) -> bool:
        """Return True when a command should receive future OBS broadcasts."""
        cmd_type = str(command.get("type", ""))
        action = str(command.get("action", ""))
        allowed_actions = cls._OBS_STREAM_COMMANDS.get(cmd_type)
        if allowed_actions is None:
            return False
        return action in allowed_actions

    def _send_frame_to_connection(self, conn: socket.socket, frame: bytes) -> bool:
        """Send one framed message to a tracked connection.

        Returns:
            True when the frame is written successfully, else False.
        """
        with self._connections_lock:
            write_lock = self._client_write_locks.get(conn)
        if write_lock is None:
            return False

        try:
            with write_lock:
                conn.sendall(frame)
            return True
        except Exception:
            return False

    def _handle_client(self, conn: socket.socket, client_id: int) -> None:
        connection_total = self._register_client_connection(conn)

        client_info: Dict[str, Any] = {}
        identified = False
        client_label = self._format_client_label(client_id, client_info)

        try:
            while (
                getattr(self, "running", True)
                and not getattr(self, "_stopping", False)
                and not getattr(self, "_stopped", False)
            ):
                length_bytes = _recv_exact(conn, 4)
                if not length_bytes:
                    break

                length = int.from_bytes(length_bytes, "big")
                if length <= 0 or length > _MAX_COMMAND_FRAME_BYTES:
                    break
                data = b""
                while len(data) < length:
                    chunk = conn.recv(min(length - len(data), 4096))
                    if not chunk:
                        break
                    data += chunk

                if len(data) < length:
                    break

                raw_command = json.loads(data.decode("utf-8"))
                extracted_info = self._extract_client_info(raw_command)
                if extracted_info:
                    client_info = extracted_info
                    client_label = self._format_client_label(client_id, client_info)
                    if self._client_info_requests_stream(client_info):
                        self._set_client_connection_kind(conn, "stream")
                    if not identified:
                        pid = client_info.get("pid")
                        pid_suffix = f" pid={pid}" if pid else ""
                        kind = client_info.get("kind", "client")
                        self._emit_log(
                            "INFO",
                            (
                                f"[peeka Agent] {client_label} connected "
                                f"({connection_total} total) kind={kind}{pid_suffix}"
                            ),
                        )
                        identified = True

                command = self._strip_client_info(raw_command)
                is_detach = str(command.get("type", "") or "") == "detach"
                if self._is_client_hello(command):
                    result = {"status": "success", "client": client_label}
                else:
                    should_log = self._should_log_command(command)
                    command_summary = self._summarize_command(command)
                    if should_log:
                        self._emit_log(
                            "INFO",
                            f"[peeka Agent] {client_label} -> {command_summary}",
                        )
                    if is_detach:
                        self._mark_detaching_connection(conn)
                    result = self._execute_command(command)

                    if (
                        not is_detach
                        and result.get("status") == "success"
                        and self._command_opens_observation_stream(command)
                        and not self._client_info_declines_observations(client_info)
                    ):
                        self._set_client_connection_kind(conn, "stream")

                    if result.get("status") == "error":
                        self._emit_log(
                            "ERROR",
                            f"[peeka Agent] {client_label} {command_summary} failed: "
                            f"{result.get('error', 'unknown error')}",
                            result.get("traceback"),
                        )
                    elif should_log:
                        self._emit_log(
                            "INFO",
                            f"[peeka Agent] {client_label} {command_summary} "
                            f"{self._summarize_result(result)}",
                        )

                response = json.dumps(result).encode("utf-8")
                response_frame = len(response).to_bytes(4, "big") + response
                if is_detach:
                    self._send_observation_frames_with_timeout(
                        conn, response_frame, timeout=self._DETACH_RESPONSE_TIMEOUT
                    )
                    break
                if not self._send_frame_to_connection(conn, response_frame):
                    break

        except Exception as e:
            msg = f"[peeka Agent] Client error: {e}"
            self._emit_log("ERROR", msg, traceback.format_exc())
        finally:
            self._unmark_detaching_connection(conn)
            connection_total = self._unregister_client_connection(conn)
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass
            self._emit_log(
                "INFO",
                f"[peeka Agent] {client_label} disconnected ({connection_total} total)",
            )


    def _send_observation(self, observation: Dict[str, Any]) -> None:
        """Called by injector when a watched function is invoked."""
        observation["type"] = "observation"
        with self._observation_queue_lock:
            self._observation_sequence += 1
            seq = self._observation_sequence
        observation["seq"] = seq
        self.observer.add_observation(observation)

        # Enqueue raw observation dict (no JSON encoding here).
        # JSON encoding and frame building happen in the flush thread.
        for conn in self._snapshot_client_connections(kind="stream"):
            self._enqueue_observation(conn, observation)

        if self._observation_flush_event is not None:
            try:
                self._observation_flush_event.set()
            except Exception:
                pass

    def _send_log(self, level: str, message: str) -> None:
        """Send a log message from Agent to all connected host clients."""
        log_msg = {
            "type": "log",
            "level": level,
            "message": message,
            "timestamp": _time.time(),
        }
        obs_json = json.dumps(log_msg).encode("utf-8")
        frame = b"LOG:" + len(obs_json).to_bytes(4, "big") + obs_json

        # Only stream connections read continuously; a control connection
        # reads only while waiting for its own reply and would just discard
        # these frames, so an idle one would fill up with logs.
        #
        # Every handler thread logs, so a blocking write here would let one
        # client that stopped reading (full socket buffer) freeze the whole
        # agent, including new clients' handshakes. Bound the write and evict
        # a client that cannot take a small frame in time.
        stalled_connections = []
        for conn in self._snapshot_client_connections(kind="stream"):
            if self._send_frame_bounded(conn, frame, self._LOG_SEND_TIMEOUT) is False:
                stalled_connections.append(conn)

        for conn in stalled_connections:
            self._evict_client_connection(conn)

    def _send_frame_bounded(
        self, conn: socket.socket, frame: bytes, timeout: float
    ) -> Optional[bool]:
        """Write a whole frame to a client without blocking past ``timeout``.

        Args:
            conn: Tracked client connection.
            frame: Complete framed message.
            timeout: Maximum seconds to spend on this connection.

        Returns:
            True when the frame was written; None when it was skipped without
            touching the socket (unknown connection, or another writer held the
            connection for the whole timeout); False when the client did not
            accept the frame in time or the socket failed. After False the
            stream may hold a partial frame, so the connection must be dropped.
        """
        with self._connections_lock:
            write_lock = self._client_write_locks.get(conn)
        if write_lock is None:
            return None

        deadline = _rpl.perf_counter() + timeout
        if not write_lock.acquire(True, timeout):
            return None
        try:
            view = memoryview(frame)
            sent = 0
            while sent < len(view):
                remaining = deadline - _rpl.perf_counter()
                if remaining <= 0 or not _rpl.wait_writable(conn, remaining):
                    return False
                try:
                    sent += conn.send(view[sent:], socket.MSG_DONTWAIT)
                except (BlockingIOError, InterruptedError):
                    continue
            return True
        except Exception:
            return False
        finally:
            write_lock.release()

    def _evict_client_connection(self, conn: socket.socket) -> None:
        """Drop a client that stopped reading.

        Shutting the socket down wakes its handler thread, which then runs
        the normal disconnect path; the client sees the connection close.
        """
        self._unregister_client_connection(conn)
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass

    def _notify_ready(self) -> None:
        """Notify the attacher that the agent is ready via TCP."""
        if self._notify_port <= 0:
            return
        try:
            s = _rpl.create_socket("AF_INET", "SOCK_STREAM")
            s.settimeout(5.0)
            s.connect(("127.0.0.1", self._notify_port))
            s.sendall(b"READY")
            s.close()
        except Exception:
            # Non-fatal: attacher will fall back to .ready file polling.
            pass

    def _close_gate_and_drain_inflight(self, current_tid: int) -> None:
        """Close command entry and wait boundedly for in-flight commands to finish."""
        gate_lock, gate_cond = self._ensure_gate_state()
        with gate_lock:
            self._stopping = True
            gate_cond.notify_all()
            pending = [
                tok
                for tok in self._inflight_commands.values()
                if tok.thread_id != current_tid and tok.cmd_type != "detach"
            ]
            if pending:
                gate_cond.wait_for(
                    lambda: all(
                        tok.cmd_id not in self._inflight_commands for tok in pending
                    ),
                    timeout=self._STOP_DRAIN_TIMEOUT,
                )
                for tok in pending:
                    if tok.cmd_id in self._inflight_commands:
                        tok.cancelled_by_stop = True

    def _drain_observation_queues_for_stop(self, timeout: float = 0.3) -> None:
        """Synchronously drain pending and in-flight observation batches within a bound."""
        deadline = _rpl.perf_counter() + max(0.0, timeout)
        flush_lock = self._get_flush_lock()
        remaining = max(0.0, deadline - _rpl.perf_counter())
        if remaining > 0:
            acquired = bool(flush_lock.acquire(True, remaining))
        else:
            acquired = bool(flush_lock.acquire(False))

        failed_conns: Set[Any] = set()
        if acquired:
            try:
                while _rpl.perf_counter() < deadline:
                    remaining = deadline - _rpl.perf_counter()
                    if remaining <= 0:
                        break
                    per_conn_timeout = min(0.1, remaining)
                    has_more = self._flush_all_connections(
                        send_timeout=per_conn_timeout,
                        skip_conns=failed_conns,
                    )
                    if not has_more:
                        break
            finally:
                flush_lock.release()

        with self._observation_queue_lock:
            for conn, queue in list(self._observation_queues.items()):
                remaining_items = len(queue)
                if remaining_items <= 0:
                    continue
                stats = self._observation_queue_stats.get(conn)
                if stats is not None:
                    stats["drain_dropped"] = (
                        stats.get("drain_dropped", 0) + remaining_items
                    )
                    stats["drain_dropped_count"] = (
                        stats.get("drain_dropped_count", 0) + remaining_items
                    )
                queue.clear()

    def _close_remaining_client_connections(self) -> None:
        """Close non-detaching client connections kept open for observation draining."""
        conn_lock = getattr(self, "_connections_lock", None)
        if conn_lock is not None:
            with conn_lock:
                connections = list(getattr(self, "_client_connections", ()))
                detaching_connections = set(
                    getattr(self, "_detaching_connections", ()) or ()
                )
        else:
            connections = list(getattr(self, "_client_connections", ()))
            detaching_connections = set(
                getattr(self, "_detaching_connections", ()) or ()
            )
        queue_lock = getattr(self, "_observation_queue_lock", None)
        if queue_lock is not None:
            with queue_lock:
                connections += list(getattr(self, "_observation_queues", {}))
        else:
            connections += list(getattr(self, "_observation_queues", {}))

        seen: Set[Any] = set()
        for conn in connections:
            if conn in seen or conn in detaching_connections:
                continue
            seen.add(conn)
            self._close_connection_quietly(conn)

    def stop(self, timeout: Optional[float] = None) -> bool:
        """Stop the agent and clean up all resources once.

        Args:
            timeout: Optional maximum seconds to wait if another thread is
                already running cleanup. Defaults to
                ``_STOP_CONCURRENT_WAIT_TIMEOUT``.

        Returns:
            True when cleanup has truly completed; False when cleanup is still
            in progress (either because waiting for an active stop owner timed
            out or because stop() was reentered on the active owner thread).
        """
        current_tid = _rpl.get_ident()
        done_event = getattr(self, "_stop_done_event", None)
        if (
            getattr(self, "_stopped", False)
            and done_event is not None
            and done_event.is_set()
        ):
            pending_sig = getattr(self, "_pending_fatal_signal", None)
            if (
                pending_sig is not None
                and threading.current_thread() is threading.main_thread()
            ):
                self._deliver_pending_fatal_signal(pending_sig)
            return True

        stop_lock = getattr(self, "_stop_lock", None)
        if stop_lock is None:
            stop_lock = _rpl.allocate_lock()
            self._stop_lock = stop_lock

        wait_for_owner = False
        with stop_lock:
            done_event = self._get_stop_done_event()
            if getattr(self, "_stopped", False):
                if done_event.is_set():
                    pending_sig = getattr(self, "_pending_fatal_signal", None)
                    if (
                        pending_sig is not None
                        and threading.current_thread() is threading.main_thread()
                    ):
                        self._deliver_pending_fatal_signal(pending_sig)
                    return True
                owner_tid = getattr(self, "_stop_owner_tid", None)
                if owner_tid == current_tid:
                    return False
                if owner_tid is None:
                    # _stopped was set externally without an active stop() owner.
                    return True
                wait_for_owner = True
            else:
                self._stopped = True
                self._stopping = True
                self._stop_owner_tid = current_tid

        if wait_for_owner:
            wait_timeout = (
                self._STOP_CONCURRENT_WAIT_TIMEOUT if timeout is None else timeout
            )
            wait_timeout = max(0.0, float(wait_timeout))
            completed = bool(done_event.wait(timeout=wait_timeout))
            finished = completed or bool(done_event.is_set())
            if finished:
                pending_sig = getattr(self, "_pending_fatal_signal", None)
                if (
                    pending_sig is not None
                    and threading.current_thread() is threading.main_thread()
                ):
                    self._deliver_pending_fatal_signal(pending_sig)
            return finished

        try:
            self.running = False
            self._close_gate_and_drain_inflight(current_tid)

            logger = logging.getLogger(__name__)
            # probe types discovered dynamically from agent state — do not hardcode
            self._last_cleanup_summary = shutdown_agent_resources(
                self, logger, self.list_tracked_probe_types()
            )

            self._signal_observation_queue_drain()
            self._drain_observation_queues_for_stop(
                timeout=getattr(self, "_STOP_OBSERVATION_DRAIN_TIMEOUT", 0.3)
            )
            self._close_remaining_client_connections()
            if self.server:
                try:
                    self.server.close()
                except OSError:
                    pass

            self._cleanup_session_files()

            # Remove self from the global agent registry
            agents = cast(
                Optional[Dict[str, "PeekaAgent"]], getattr(sys, "_peeka_agents", None)
            )
            if agents is not None:
                keys_to_remove = [k for k, v in agents.items() if v is self]
                for k in keys_to_remove:
                    del agents[k]

            self._uninstall_exit_hooks()
            if getattr(self, "_pending_fatal_signal", None) is None:
                try:
                    atexit.unregister(self.stop)
                except Exception:
                    pass
        finally:
            with stop_lock:
                self._stop_owner_tid = None
                done_event.set()
        pending_sig = getattr(self, "_pending_fatal_signal", None)
        if (
            pending_sig is not None
            and threading.current_thread() is threading.main_thread()
        ):
            self._deliver_pending_fatal_signal(pending_sig)
        return True

    def _uninstall_exit_hooks(self) -> None:
        is_main = threading.current_thread() is threading.main_thread()
        for signum, _handler_attr, prev_attr, ref_attr in self._exit_signal_specs():
            prev_handler = getattr(self, prev_attr, None)
            handler_ref = getattr(self, ref_attr, None)
            if prev_handler is None or handler_ref is None:
                continue
            if is_main:
                try:
                    _restore_signal_handler_if_current(
                        signum, prev_handler, handler_ref
                    )
                except (ValueError, OSError):
                    pass
            else:
                try:
                    if signal.getsignal(signum) is not handler_ref:
                        continue
                except (ValueError, OSError):
                    pass
                _schedule_signal_restore_on_main_thread(
                    signum, prev_handler, handler_ref
                )
        prev_excepthook = getattr(self, "_prev_excepthook", None)
        peeka_excepthook_ref = getattr(self, "_peeka_excepthook_ref", None)
        if (
            prev_excepthook is not None
            and peeka_excepthook_ref is not None
            and sys.excepthook is peeka_excepthook_ref
        ):
            try:
                sys.excepthook = prev_excepthook
            except Exception:
                pass
        if (
            hasattr(threading, "excepthook")
            and getattr(self, "_prev_threading_excepthook", None) is not None
            and getattr(self, "_threading_excepthook_ref", None) is not None
            and threading.excepthook is self._threading_excepthook_ref
        ):
            try:
                threading.excepthook = self._prev_threading_excepthook
            except Exception:
                pass

    def _cleanup_session_files(self) -> None:
        """Remove .sock, .ready, and .pid files for this session.

        Called on stop/detach so that stale files don't trick
        _check_existing_attachment() into reporting a live agent.
        """
        for suffix in (".sock", ".ready", ".pid"):
            p = Path(f"/tmp/peeka_{self.session_id}{suffix}")
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def _init_agent(
    session_id: str,
    attached_pid: Optional[int] = None,
    notify_port: int = 0,
    suppress_startup_messages: bool = False,
) -> None:
    try:
        # Stop ALL existing agents from previous sessions to prevent thread leaks.
        # Each sys.remote_exec() call creates a new agent; without this cleanup,
        # old accept-loop and client-handler threads accumulate indefinitely.
        agents = cast(Optional[Dict[str, PeekaAgent]], getattr(sys, "_peeka_agents", None))
        if agents is not None:
            old_agents = list(agents.values())
            for old_agent in old_agents:
                try:
                    stopped = old_agent.stop()
                    if stopped is False:
                        msg = (
                            f"[peeka Agent] Timed out waiting for previous agent "
                            f"to finish stopping: {old_agent.session_id}"
                        )
                        old_agent._emit_log("WARNING", msg)
                    else:
                        summary = getattr(old_agent, "_last_cleanup_summary", {})
                        msg = (
                            f"[peeka Agent] Stopped previous agent: {old_agent.session_id}"
                            f" cleanup={summary}"
                        )
                        old_agent._emit_log("INFO", msg)
                except Exception:
                    pass
            agents.clear()

        agent = PeekaAgent(
            session_id,
            attached_pid,
            notify_port=notify_port,
            suppress_startup_messages=suppress_startup_messages,
        )
        if agent.start():
            agents = cast(Optional[Dict[str, PeekaAgent]], getattr(sys, "_peeka_agents", None))
            if agents is None:
                agents = {}
                setattr(sys, "_peeka_agents", agents)
            agents[session_id] = agent
        else:
            msg = "[peeka Agent] Start failed; session not registered"
            _write_session_log(session_id, "ERROR", msg)

    except Exception as e:
        msg = f"[peeka Agent] Initialization failed: {e}"
        _write_session_log(session_id, "ERROR", msg, traceback.format_exc())


# Auto-initialize when injected via sys.remote_exec() or GDB
# {{SESSION_ID}}, {{ATTACHED_PID}}, and {{NOTIFY_PORT}} are replaced by
# ProcessAttacher before injection.
# This runs both when imported (PEP 768) and when exec'd (GDB fallback)
_session_id = "{{SESSION_ID}}"
_attached_pid_str = "{{ATTACHED_PID}}"
_notify_port_str = "{{NOTIFY_PORT}}"
_suppress_startup = "{{SUPPRESS_STARTUP_MESSAGES}}"
_attached_pid = int(_attached_pid_str) if _attached_pid_str.isdigit() else None
_notify_port = int(_notify_port_str) if _notify_port_str.isdigit() else 0
_suppress_startup_messages = _suppress_startup == "True"
if not _session_id.startswith("{{"):
    _init_agent(
        _session_id,
        _attached_pid,
        notify_port=_notify_port,
        suppress_startup_messages=_suppress_startup_messages,
    )


# ================================================================ #
# PEP 562 Module-level Deprecation Shim                            #
# ================================================================ #
# Backward-compatible access to relocated _NATIVE_* aliases.
# This shim coexists with the eager-capture block (lines 6-77)
# until T8 removes the eager block.


def __getattr__(name: str) -> Any:
    """PEP 562 module-level deprecation shim for relocated _NATIVE_* helpers."""
    _deprecated_aliases = {
        "_NATIVE_SOCKET": "_NATIVE_SOCKET",
        "_NATIVE_START_NEW_THREAD": "_NATIVE_START_NEW_THREAD",
        "_NATIVE_ALLOCATE_LOCK": "_NATIVE_ALLOCATE_LOCK",
        "_NATIVE_RLOCK": "_NATIVE_RLOCK",
        "_NATIVE_EVENT": "_NATIVE_EVENT",
        "_NATIVE_TIME": "_NATIVE_TIME",
        "_NATIVE_PERF_COUNTER": "_NATIVE_PERF_COUNTER",
        "_NATIVE_GET_IDENT": "_NATIVE_GET_IDENT",
        "_start_native_thread": "start_thread",
        "_native_accept": "native_accept",
        "_get_original_runtime_attr": "_get_original_runtime_attr",
    }

    if name in _deprecated_aliases:
        import warnings

        from peeka.core.runtime import primitives as _rpl

        warnings.warn(
            f"peeka.core.agent.{name} is deprecated; import from peeka.core.runtime.primitives instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(_rpl, _deprecated_aliases[name])
    raise AttributeError(f"module 'peeka.core.agent' has no attribute {name!r}")
