"""Trace backend implementations and shared hook dispatchers."""

import dis
import os
import sys
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from peeka.core.instrumentation.registry import wrapper_call_target
from peeka.core.runtime import primitives as _rpl
from peeka.core.runtime.compat import BACKEND_WRAPPER_ONLY


_DYNAMIC_WATCH_FILENAME_PREFIX = "<peeka-watch:"
_DYNAMIC_WATCH_WRAPPER_SUFFIX = "pk_wrapper"
_PEEKA_PACKAGE_DIR = (
    os.path.realpath(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    )
    + os.sep
)
_INSTRUMENTATION_DIR = os.path.realpath(os.path.dirname(os.path.abspath(__file__)))
_COMMANDS_DIR = os.path.realpath(os.path.join(_PEEKA_PACKAGE_DIR, "commands"))
_WRAPPER_DISPATCH_SPECS: Dict[str, Tuple[str, ...]] = {
    os.path.join(_INSTRUMENTATION_DIR, "trace.py"): ("wrapper", "async_trace_wrapper"),
    os.path.join(_INSTRUMENTATION_DIR, "trace_backends.py"): (
        "_trace_with_monitoring",
        "_trace_with_settrace",
        "_trace_with_wrapper_only",
        "_trace_coroutine",
        "_execute_sync_session",
    ),
    os.path.join(_INSTRUMENTATION_DIR, "watch.py"): (
        "wrapper",
        "_run_coroutine",
        "async_wrapper",
        "generator_wrapper",
        "async_generator_wrapper",
    ),
    os.path.join(_COMMANDS_DIR, "monitor.py"): ("wrapper",),
}
_RESOLVED_FILE_CACHE: Dict[str, str] = {}
_INTERNAL_FILE_CACHE: Dict[str, bool] = {}
_WRAPPER_DISPATCH_CACHE: Dict[Tuple[str, str], bool] = {}
_SENTINEL = object()


def _is_dynamic_watch_filename(filename: str) -> bool:
    """Return True if *filename* belongs to a compiled Peeka watch wrapper."""
    return filename.startswith(_DYNAMIC_WATCH_FILENAME_PREFIX) and filename.endswith(
        ">"
    )


def _is_dynamic_watch_wrapper_name(co_name: str) -> bool:
    """Return True if *co_name* matches watch.py's ``_+pk_wrapper`` convention."""
    suffix = _DYNAMIC_WATCH_WRAPPER_SUFFIX
    return (
        co_name.endswith(suffix)
        and len(co_name) > len(suffix)
        and set(co_name[: -len(suffix)]) == {"_"}
    )


def _resolve_filename(filename: str) -> str:
    """Return canonical realpath for a code filename with bounded caching."""
    cached = _RESOLVED_FILE_CACHE.get(filename)
    if cached is not None:
        return cached
    if len(_RESOLVED_FILE_CACHE) > 4096:
        _RESOLVED_FILE_CACHE.clear()
    resolved = os.path.realpath(filename)
    _RESOLVED_FILE_CACHE[filename] = resolved
    return resolved


def _is_peeka_internal_code(code: Any) -> bool:
    """Return True if *code* belongs to the Peeka package internals."""
    filename = getattr(code, "co_filename", "")
    if not filename:
        return False
    if _is_dynamic_watch_filename(filename):
        return True
    if filename.startswith("<"):
        return False
    cached = _INTERNAL_FILE_CACHE.get(filename)
    if cached is not None:
        return cached
    if len(_INTERNAL_FILE_CACHE) > 4096:
        _INTERNAL_FILE_CACHE.clear()
    is_internal = _resolve_filename(filename).startswith(_PEEKA_PACKAGE_DIR)
    _INTERNAL_FILE_CACHE[filename] = is_internal
    return is_internal


def _is_peeka_wrapper_dispatch_code(code: Any) -> bool:
    """Return True if *code* is a transparent Peeka probe wrapper/dispatcher."""
    filename = getattr(code, "co_filename", "")
    if not filename:
        return False
    co_name = getattr(code, "co_name", "")
    if _is_dynamic_watch_filename(filename):
        return _is_dynamic_watch_wrapper_name(co_name)
    if filename.startswith("<"):
        return False
    key = (filename, co_name)
    cached = _WRAPPER_DISPATCH_CACHE.get(key)
    if cached is not None:
        return cached
    if len(_WRAPPER_DISPATCH_CACHE) > 4096:
        _WRAPPER_DISPATCH_CACHE.clear()
    resolved = _resolve_filename(filename)
    is_dispatch = co_name in _WRAPPER_DISPATCH_SPECS.get(resolved, ())
    _WRAPPER_DISPATCH_CACHE[key] = is_dispatch
    return is_dispatch


def _walk_back_peeka(
    frame: Optional[Any], stop_at: Optional[Any] = None
) -> Optional[Any]:
    """Walk ``f_back`` past transparent Peeka wrapper/dispatch frames."""
    current = frame
    for _ in range(32):
        if current is None or current is stop_at:
            return current
        if not _is_peeka_wrapper_dispatch_code(current.f_code):
            return current
        current = current.f_back
    return current


def _unwrap_peeka_wrappers(func: Any) -> Any:
    """Unwrap stacked Peeka wrappers without unwrapping user decorators."""
    current = func
    seen: Set[int] = set()
    for _ in range(32):
        code = getattr(current, "__code__", None)
        if code is None or not _is_peeka_wrapper_dispatch_code(code):
            break
        nxt = wrapper_call_target(current)
        if nxt is None or id(nxt) in seen:
            break
        seen.add(id(nxt))
        current = nxt
    return current


def _is_gevent_patched() -> bool:
    """Check whether gevent has monkey-patched socket or threading."""
    from peeka.core.instrumentation.trace import _is_gevent_patched_now

    return _is_gevent_patched_now()


def _get_current_greenlet() -> Optional[Any]:
    """Return the active greenlet if greenlet is loaded, else None."""
    greenlet_mod = sys.modules.get("greenlet")
    if greenlet_mod is None:
        return None
    getcurrent = getattr(greenlet_mod, "getcurrent", None)
    if not callable(getcurrent):
        return None
    try:
        return getcurrent()
    except Exception:
        return None


def _is_coroutine_yield_return(frame: Any) -> bool:
    """Return True if a settrace ``return`` event is a coroutine/generator yield."""
    code = frame.f_code.co_code
    offset = frame.f_lasti
    if offset < 0 or offset >= len(code):
        return False
    opcode = dis.opname[code[offset]]
    if opcode == "YIELD_VALUE":
        return True
    if sys.version_info >= (3, 10) and opcode == "YIELD_FROM":
        return True
    # CPython 3.8/3.9 rewinds f_lasti before YIELD_FROM while suspended,
    # whereas an exception unwind at await points directly at YIELD_FROM.
    if (
        sys.version_info < (3, 10)
        and offset + 2 < len(code)
        and dis.opname[code[offset + 2]] == "YIELD_FROM"
    ):
        return True
    return False


def _format_trace_function(code: Any, frame: Optional[Any] = None) -> str:
    """Return a module-qualified function name for a trace callee.

    The returned string is a valid ``module.qualname`` pattern that can be
    passed back to the trace command (via ``_resolve_target``). The original
    ``filename``/``lineno`` are preserved separately in the callee record,
    so this function only needs to produce a dotted import path.

    Args:
        code: The code object of the callee.
        frame: Optional frame (available in sys.settrace backend). When
            provided, the exact module name is read from ``frame.f_globals``.

    Returns:
        Dotted function name such as ``module.func`` or ``__main__.func``.
    """
    func_name = getattr(code, "co_qualname", code.co_name)

    if frame is not None:
        module_name = frame.f_globals.get("__name__", "__main__")
        return f"{module_name}.{func_name}"

    # Fallback when no frame is available: infer module from code.co_filename.
    target_file = os.path.abspath(code.co_filename)
    for mod in list(sys.modules.values()):
        mod_file = getattr(mod, "__file__", None)
        if mod_file and os.path.abspath(mod_file) == target_file:
            module_name = getattr(mod, "__name__", "__main__")
            return f"{module_name}.{func_name}"

    # Fallback: derive a pseudo-module from the filename basename.
    base = os.path.basename(code.co_filename)
    if base.endswith(".py"):
        base = base[:-3]
    return f"{base}.{func_name}"


def _aggregate_callees(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str, int], List[float]] = defaultdict(list)
    for entry in entries:
        key = (entry["function"], entry["filename"], entry["lineno"])
        groups[key].append(entry["duration_ms"])
    result = []
    for (func_name, filename, lineno), durations in groups.items():
        result.append(
            {
                "function": func_name,
                "filename": filename,
                "lineno": lineno,
                "count": len(durations),
                "total_ms": round(sum(durations), 3),
                "min_ms": round(min(durations), 3),
                "max_ms": round(max(durations), 3),
            }
        )
    return result


def _is_builtin_or_stdlib(code: Any) -> bool:
    if code.co_filename.startswith("<"):
        return True
    if (
        "site-packages" not in code.co_filename
        and "dist-packages" not in code.co_filename
    ):
        py_path = os.path.dirname(os.__file__)
        if code.co_filename.startswith(py_path):
            return True
    return False


def _build_root_node(
    func: Callable[..., Any],
    root_code: Optional[Any],
    duration_ms: float,
    direct_callees: List[Dict[str, Any]],
    result: Any = _SENTINEL,
    exception: Optional[BaseException] = None,
    downgraded_backend: Optional[str] = None,
    downgrade_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Construct the root call-tree node dictionary."""
    node: Dict[str, Any] = {
        "depth": 0,
        "function": f"{func.__module__}.{func.__qualname__}",
        "filename": root_code.co_filename if root_code is not None else "unknown",
        "lineno": root_code.co_firstlineno if root_code is not None else 0,
        "duration_ms": round(duration_ms, 3),
        "direct_callees": direct_callees,
    }
    if result is not _SENTINEL:
        node["_result"] = result
    if exception is not None:
        node["_exception"] = exception
    if downgraded_backend is not None:
        node["_downgraded_backend"] = downgraded_backend
    if downgrade_reason is not None:
        node["_downgrade_reason"] = downgrade_reason
    return node


class _TraceSession:
    """Isolated per-invocation trace session shared across hook dispatchers."""

    def __init__(
        self,
        thread_id: int,
        target_greenlet: Optional[Any],
        skip_builtin: bool,
        min_duration: float,
        outer_frame: Optional[Any] = None,
        root_frame: Optional[Any] = None,
        root_code: Optional[Any] = None,
        ignore_yield: bool = False,
        record_on_unwind: bool = True,
        format_root: bool = False,
    ) -> None:
        self.thread_id = thread_id
        self.target_greenlet = target_greenlet
        self.skip_builtin = skip_builtin
        self.min_duration = min_duration
        self.outer_frame = outer_frame
        self.root_frame = root_frame
        self.root_code = root_code
        self.ignore_yield = ignore_yield
        self.record_on_unwind = record_on_unwind
        self.format_root = format_root
        self.pending: Dict[int, Dict[str, Any]] = {}
        self.completed: List[Dict[str, Any]] = []

    def matches_context(self, thread_id: int, greenlet: Optional[Any]) -> bool:
        """Return True only when the event executes in the owning thread & greenlet."""
        if thread_id != self.thread_id:
            return False
        if self.target_greenlet is not None:
            return greenlet is self.target_greenlet
        if greenlet is not None:
            return getattr(greenlet, "parent", None) is None
        return True

    def on_call(
        self, frame: Any, thread_id: int, greenlet: Optional[Any]
    ) -> None:
        """Record entry of a direct business callee of this session's root."""
        if not self.matches_context(thread_id, greenlet):
            return
        code = frame.f_code
        if self.root_frame is None:
            if self.outer_frame is None:
                return
            if _is_peeka_internal_code(code) and code is not self.root_code:
                return
            if (
                _walk_back_peeka(frame.f_back, stop_at=self.outer_frame)
                is not self.outer_frame
            ):
                return
            self.root_frame = frame
            if self.format_root:
                _format_trace_function(code, frame)
            return

        if frame is self.root_frame:
            return
        if _is_peeka_internal_code(code):
            return
        if (
            _walk_back_peeka(frame.f_back, stop_at=self.root_frame)
            is not self.root_frame
        ):
            return
        if self.skip_builtin and _is_builtin_or_stdlib(code):
            return
        key = id(frame)
        if key not in self.pending:
            self.pending[key] = {
                "function": _format_trace_function(code, frame),
                "filename": code.co_filename,
                "lineno": code.co_firstlineno,
                "start_time": time.perf_counter(),
            }

    def on_return(
        self,
        frame: Any,
        thread_id: int,
        greenlet: Optional[Any],
        is_unwind: bool = False,
        from_settrace: bool = False,
    ) -> None:
        """Record exit of a previously started direct callee."""
        if not self.matches_context(thread_id, greenlet):
            return
        if from_settrace and self.ignore_yield and _is_coroutine_yield_return(frame):
            return
        entry = self.pending.pop(id(frame), None)
        if entry is None:
            return
        if is_unwind and not self.record_on_unwind:
            return
        duration_ms = (time.perf_counter() - entry.pop("start_time")) * 1000
        if duration_ms >= self.min_duration:
            entry["duration_ms"] = round(duration_ms, 3)
            self.completed.append(entry)


class _MonitoringDispatcher:
    """Process-wide single-slot sys.monitoring dispatcher for concurrent trace sessions."""

    def __init__(self) -> None:
        self._lock = _rpl.allocate_lock()
        self._tool_id: Optional[int] = None
        self._sessions_by_thread: Dict[int, Tuple[_TraceSession, ...]] = {}
        self._total_sessions = 0

    def acquire(self, session: _TraceSession) -> bool:
        """Attach *session* to the shared monitoring tool slot, or return False if full."""
        if not hasattr(sys, "monitoring"):
            return False
        with self._lock:
            if self._tool_id is None:
                tool_id: Optional[int] = None
                for candidate_id in range(5, -1, -1):
                    try:
                        sys.monitoring.use_tool_id(candidate_id, "peeka-trace")
                        tool_id = candidate_id
                        break
                    except ValueError:
                        continue
                if tool_id is None:
                    return False

                events = sys.monitoring.events
                try:
                    sys.monitoring.register_callback(
                        tool_id, events.PY_START, self._on_py_start
                    )
                    sys.monitoring.register_callback(
                        tool_id, events.PY_RETURN, self._on_py_return
                    )
                    sys.monitoring.register_callback(
                        tool_id, events.PY_UNWIND, self._on_py_unwind
                    )
                    sys.monitoring.set_events(
                        tool_id,
                        events.PY_START | events.PY_RETURN | events.PY_UNWIND,
                    )
                except Exception:
                    try:
                        sys.monitoring.set_events(tool_id, 0)
                        sys.monitoring.free_tool_id(tool_id)
                    except ValueError:
                        pass
                    raise
                self._tool_id = tool_id

            existing = self._sessions_by_thread.get(session.thread_id, ())
            self._sessions_by_thread[session.thread_id] = existing + (session,)
            self._total_sessions += 1
            return True

    def release(self, session: _TraceSession) -> None:
        """Detach *session* and free the shared monitoring tool when no sessions remain."""
        with self._lock:
            existing = self._sessions_by_thread.get(session.thread_id, ())
            if session not in existing:
                return
            remaining = tuple(s for s in existing if s is not session)
            if remaining:
                self._sessions_by_thread[session.thread_id] = remaining
            else:
                self._sessions_by_thread.pop(session.thread_id, None)
            self._total_sessions = max(0, self._total_sessions - 1)

            if self._total_sessions == 0 and self._tool_id is not None:
                tool_id = self._tool_id
                self._tool_id = None
                try:
                    sys.monitoring.set_events(tool_id, 0)
                except ValueError:
                    pass
                try:
                    sys.monitoring.free_tool_id(tool_id)
                except ValueError:
                    pass

    def _on_py_start(self, _code: Any, _offset: int) -> None:
        tid = _rpl.get_ident()
        sessions = self._sessions_by_thread.get(tid)
        if not sessions:
            return
        try:
            frame = sys._getframe(1)
        except ValueError:
            return
        greenlet = _get_current_greenlet()
        for session in sessions:
            session.on_call(frame, tid, greenlet)

    def _on_py_return(self, _code: Any, _offset: int, _retval: Any) -> None:
        tid = _rpl.get_ident()
        sessions = self._sessions_by_thread.get(tid)
        if not sessions:
            return
        try:
            frame = sys._getframe(1)
        except ValueError:
            return
        greenlet = _get_current_greenlet()
        for session in sessions:
            session.on_return(frame, tid, greenlet, is_unwind=False)

    def _on_py_unwind(self, _code: Any, _offset: int, _exc: Any) -> None:
        tid = _rpl.get_ident()
        sessions = self._sessions_by_thread.get(tid)
        if not sessions:
            return
        try:
            frame = sys._getframe(1)
        except ValueError:
            return
        greenlet = _get_current_greenlet()
        for session in sessions:
            session.on_return(frame, tid, greenlet, is_unwind=True)


class _ThreadSettraceDispatcher:
    """Per-OS-thread shared sys.settrace dispatcher preserving any pre-existing tracer."""

    def __init__(self, thread_id: int) -> None:
        self.thread_id = thread_id
        self._sessions: Tuple[_TraceSession, ...] = ()
        self._prev_global_trace: Any = None
        self._installed = False
        self._global_trace_fn = self._global_trace
        self._local_trace_fn = self._local_trace

    def add_session(self, session: _TraceSession) -> None:
        """Install the dispatcher if needed and register *session*."""
        if not self._installed:
            current = sys.gettrace()
            if current is not self._global_trace_fn:
                self._prev_global_trace = current
            self._sessions = (session,)
            self._installed = True
            sys.settrace(self._global_trace_fn)
        else:
            self._sessions = self._sessions + (session,)

    def remove_session(self, session: _TraceSession) -> bool:
        """Unregister *session* and restore the previous tracer when empty.

        Returns:
            True if the dispatcher is now empty and uninstalled.
        """
        if session not in self._sessions:
            return not self._installed
        self._sessions = tuple(s for s in self._sessions if s is not session)
        if not self._sessions and self._installed:
            self._installed = False
            prev = self._prev_global_trace
            self._prev_global_trace = None
            if (
                _rpl.get_ident() == self.thread_id
                and sys.gettrace() is self._global_trace_fn
            ):
                sys.settrace(prev)
            return True
        return False

    def _local_trace(
        self, frame: Any, event: str, _arg: Any
    ) -> Optional[Callable[..., Any]]:
        """Fast-path local trace function when no pre-existing tracer was installed."""
        sessions = self._sessions
        if not sessions:
            return None
        if event == "return":
            greenlet = _get_current_greenlet()
            for session in sessions:
                session.on_return(
                    frame, self.thread_id, greenlet, from_settrace=True
                )
        return self._local_trace_fn

    def _global_trace(
        self, frame: Any, event: str, arg: Any
    ) -> Optional[Callable[..., Any]]:
        """Thread-global settrace entrypoint chaining to any pre-existing tracer."""
        if event != "call":
            return None
        sessions = self._sessions
        prev_global = self._prev_global_trace
        if prev_global is None:
            if not sessions:
                return None
            frame.f_trace_lines = False
            greenlet = _get_current_greenlet()
            for session in sessions:
                session.on_call(frame, self.thread_id, greenlet)
            return self._local_trace_fn

        prev_local = prev_global(frame, event, arg)
        if not sessions:
            return prev_local
        greenlet = _get_current_greenlet()
        for session in sessions:
            session.on_call(frame, self.thread_id, greenlet)
        if prev_local is None:
            frame.f_trace_lines = False
            return self._local_trace_fn

        def chained_local_trace(
            cur_frame: Any, cur_event: str, cur_arg: Any
        ) -> Optional[Callable[..., Any]]:
            nonlocal prev_local
            if prev_local is not None:
                prev_local = prev_local(cur_frame, cur_event, cur_arg)
            active = self._sessions
            if active:
                if cur_event == "return":
                    cur_greenlet = _get_current_greenlet()
                    for session in active:
                        session.on_return(
                            cur_frame,
                            self.thread_id,
                            cur_greenlet,
                            from_settrace=True,
                        )
                return chained_local_trace
            return prev_local

        return chained_local_trace


class _SettraceCoordinator:
    """Thread-safe coordinator managing per-thread settrace dispatchers."""

    def __init__(self) -> None:
        self._lock = _rpl.allocate_lock()
        self._dispatchers: Dict[int, _ThreadSettraceDispatcher] = {}

    def acquire(self, session: _TraceSession) -> None:
        """Register *session* on its owning thread's shared settrace dispatcher."""
        with self._lock:
            dispatcher = self._dispatchers.get(session.thread_id)
            if dispatcher is None:
                dispatcher = _ThreadSettraceDispatcher(session.thread_id)
                self._dispatchers[session.thread_id] = dispatcher
            dispatcher.add_session(session)

    def release(self, session: _TraceSession) -> None:
        """Unregister *session* and clean up empty dispatchers."""
        with self._lock:
            dispatcher = self._dispatchers.get(session.thread_id)
            if dispatcher is None:
                return
            if dispatcher.remove_session(session):
                self._dispatchers.pop(session.thread_id, None)


_MONITORING_DISPATCHER = _MonitoringDispatcher()
_SETTRACE_COORDINATOR = _SettraceCoordinator()


class InjectorTraceBackendsMixin:

    async def _trace_coroutine(
        self,
        func: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        skip_builtin: bool,
        min_duration: float,
        effective_backend: Optional[str],
        use_monitoring: bool,
    ) -> List[Dict[str, Any]]:
        """Await a root coroutine while collecting its direct Python callees.

        Match the actual parent frame rather than a global depth counter: the
        event loop can run unrelated tasks while the root is suspended. Keep
        suspended callee frames until their final return so await time is included.
        """
        coroutine = func(*args, **kwargs)
        initial_root_frame = getattr(coroutine, "cr_frame", None)
        root_callable = _unwrap_peeka_wrappers(func)
        root_code = getattr(root_callable, "__code__", None)
        target_thread_id = _rpl.get_ident()
        target_greenlet = _get_current_greenlet()

        if initial_root_frame is not None and _is_peeka_internal_code(
            initial_root_frame.f_code
        ):
            session = _TraceSession(
                thread_id=target_thread_id,
                target_greenlet=target_greenlet,
                skip_builtin=skip_builtin,
                min_duration=min_duration,
                outer_frame=initial_root_frame,
                root_frame=None,
                root_code=root_code,
                ignore_yield=True,
                record_on_unwind=True,
            )
        else:
            session = _TraceSession(
                thread_id=target_thread_id,
                target_greenlet=target_greenlet,
                skip_builtin=skip_builtin,
                min_duration=min_duration,
                outer_frame=None,
                root_frame=initial_root_frame,
                root_code=root_code,
                ignore_yield=True,
                record_on_unwind=True,
            )

        monitoring_acquired = False
        settrace_acquired = False
        downgraded_backend: Optional[str] = None
        downgrade_reason: Optional[str] = None

        start_time = time.perf_counter()
        result: Any = _SENTINEL
        caught_exc: Optional[BaseException] = None
        try:
            if effective_backend != BACKEND_WRAPPER_ONLY:
                if use_monitoring:
                    monitoring_acquired = _MONITORING_DISPATCHER.acquire(session)
                    if not monitoring_acquired:
                        if _is_gevent_patched():
                            downgraded_backend = BACKEND_WRAPPER_ONLY
                            downgrade_reason = "monitoring_slots_exhausted"
                        else:
                            _SETTRACE_COORDINATOR.acquire(session)
                            settrace_acquired = True
                else:
                    _SETTRACE_COORDINATOR.acquire(session)
                    settrace_acquired = True
            try:
                result = await coroutine
            except Exception as exc:
                caught_exc = exc
        finally:
            if monitoring_acquired:
                _MONITORING_DISPATCHER.release(session)
            if settrace_acquired:
                _SETTRACE_COORDINATOR.release(session)

        duration_ms = (time.perf_counter() - start_time) * 1000
        direct_callees = _aggregate_callees(session.completed)
        return [
            _build_root_node(
                func=func,
                root_code=root_code,
                duration_ms=duration_ms,
                direct_callees=direct_callees,
                result=result,
                exception=caught_exc,
                downgraded_backend=downgraded_backend,
                downgrade_reason=downgrade_reason,
            )
        ]

    def _trace_with_wrapper_only(
        self,
        func: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Trace only the wrapped root call without global tracing APIs.

        Args:
            func: Function to trace
            args: Function arguments
            kwargs: Function keyword arguments

        Returns:
            Single-node call tree containing the root call with empty direct_callees.
        """
        root_callable = _unwrap_peeka_wrappers(func)
        root_code = getattr(root_callable, "__code__", None)
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000
            return [
                _build_root_node(
                    func=func,
                    root_code=root_code,
                    duration_ms=duration_ms,
                    direct_callees=[],
                    result=result,
                )
            ]
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return [
                _build_root_node(
                    func=func,
                    root_code=root_code,
                    duration_ms=duration_ms,
                    direct_callees=[],
                    exception=e,
                )
            ]

    def _execute_sync_session(
        self,
        func: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        session: _TraceSession,
        root_code: Optional[Any],
        release_fn: Callable[[_TraceSession], None],
    ) -> List[Dict[str, Any]]:
        """Execute a synchronous call under an acquired trace session."""
        start_time = time.perf_counter()
        result: Any = _SENTINEL
        caught_exc: Optional[BaseException] = None
        try:
            try:
                result = func(*args, **kwargs)
            except Exception as exc:
                caught_exc = exc
        finally:
            release_fn(session)

        duration_ms = (time.perf_counter() - start_time) * 1000
        direct_callees = _aggregate_callees(session.completed)
        return [
            _build_root_node(
                func=func,
                root_code=root_code,
                duration_ms=duration_ms,
                direct_callees=direct_callees,
                result=result,
                exception=caught_exc,
            )
        ]

    def _trace_with_monitoring(
        self,
        func: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        skip_builtin: bool,
        min_duration: float,
    ) -> List[Dict[str, Any]]:
        """
        Trace function execution using sys.monitoring (Python 3.12+).

        Captures only direct callees of *func* and aggregates per-execution.

        Args:
            func: Function to trace
            args: Function arguments
            kwargs: Function keyword arguments
            skip_builtin: Whether to skip built-in and stdlib functions
            min_duration: Minimum duration in ms to record a callee

        Returns:
            Single-element list containing the root node with direct_callees.
        """
        root_callable = _unwrap_peeka_wrappers(func)
        root_code = getattr(root_callable, "__code__", None)
        session = _TraceSession(
            thread_id=_rpl.get_ident(),
            target_greenlet=_get_current_greenlet(),
            skip_builtin=skip_builtin,
            min_duration=min_duration,
            outer_frame=sys._getframe(0),
            root_frame=None,
            root_code=root_code,
            ignore_yield=False,
            record_on_unwind=False,
            format_root=True,
        )

        if not _MONITORING_DISPATCHER.acquire(session):
            if _is_gevent_patched():
                nodes = self._trace_with_wrapper_only(func, args, kwargs)
                if nodes:
                    nodes[0]["_downgraded_backend"] = BACKEND_WRAPPER_ONLY
                    nodes[0]["_downgrade_reason"] = "monitoring_slots_exhausted"
                return nodes
            return self._trace_with_settrace(
                func, args, kwargs, skip_builtin, min_duration
            )

        return self._execute_sync_session(
            func, args, kwargs, session, root_code, _MONITORING_DISPATCHER.release
        )

    def _trace_with_settrace(
        self,
        func: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        skip_builtin: bool,
        min_duration: float,
    ) -> List[Dict[str, Any]]:
        """
        Trace function execution using sys.settrace (fallback for Python < 3.12).

        Captures only direct callees of *func* and aggregates per-execution.

        Args:
            func: Function to trace
            args: Function arguments
            kwargs: Function keyword arguments
            skip_builtin: Whether to skip built-in and stdlib functions
            min_duration: Minimum duration in ms to record a callee

        Returns:
            Single-element list containing the root node with direct_callees.
        """
        root_callable = _unwrap_peeka_wrappers(func)
        root_code = getattr(root_callable, "__code__", None)
        session = _TraceSession(
            thread_id=_rpl.get_ident(),
            target_greenlet=_get_current_greenlet(),
            skip_builtin=skip_builtin,
            min_duration=min_duration,
            outer_frame=sys._getframe(0),
            root_frame=None,
            root_code=root_code,
            ignore_yield=False,
            record_on_unwind=True,
            format_root=False,
        )

        _SETTRACE_COORDINATOR.acquire(session)
        return self._execute_sync_session(
            func, args, kwargs, session, root_code, _SETTRACE_COORDINATOR.release
        )
