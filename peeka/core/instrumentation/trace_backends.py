"""Trace backend implementations."""

import dis
import os
import sys
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from peeka.core.runtime import primitives as _rpl
from peeka.core.runtime.compat import BACKEND_WRAPPER_ONLY


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

    # sys.monitoring callback does not receive a frame. Infer the module from
    # code.co_filename by matching against loaded modules' __file__ paths.
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
    groups: Dict = defaultdict(list)
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
        import os

        py_path = os.path.dirname(os.__file__)
        if code.co_filename.startswith(py_path):
            return True
    return False


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
        root_frame = getattr(coroutine, "cr_frame", None)
        target_thread_id = _rpl.get_ident()
        pending: Dict[int, Dict[str, Any]] = {}
        completed: List[Dict[str, Any]] = []
        tool_id = None
        prev_trace = None
        settrace_enabled = False

        def on_start(frame):
            if frame.f_back is not root_frame or root_frame is None:
                return
            code = frame.f_code
            if skip_builtin and _is_builtin_or_stdlib(code):
                return
            key = id(frame)
            if key not in pending:
                pending[key] = {
                    "function": _format_trace_function(code, frame),
                    "filename": code.co_filename,
                    "lineno": code.co_firstlineno,
                    "start_time": time.perf_counter(),
                }

        def on_return(frame):
            entry = pending.pop(id(frame), None)
            if entry is not None:
                duration_ms = (time.perf_counter() - entry.pop("start_time")) * 1000
                if duration_ms >= min_duration:
                    entry["duration_ms"] = round(duration_ms, 3)
                    completed.append(entry)

        def monitoring_start(code, offset):
            if _rpl.get_ident() != target_thread_id:
                return
            on_start(sys._getframe(1))

        def monitoring_return(code, offset, value):
            if _rpl.get_ident() != target_thread_id:
                return
            on_return(sys._getframe(1))

        def local_trace(frame, event, arg):
            if event == "call":
                on_start(frame)
            elif event == "return":
                # settrace also reports a return when a coroutine yields.
                opcode = frame.f_code.co_code[frame.f_lasti]
                if dis.opname[opcode] != "YIELD_VALUE":
                    on_return(frame)
            return local_trace

        start_time = time.perf_counter()
        root: Dict[str, Any] = {
            "depth": 0,
            "function": f"{func.__module__}.{func.__qualname__}",
            "filename": getattr(getattr(func, "__code__", None), "co_filename", "unknown"),
            "lineno": getattr(getattr(func, "__code__", None), "co_firstlineno", 0),
        }
        try:
            if effective_backend != BACKEND_WRAPPER_ONLY:
                if use_monitoring:
                    for candidate_id in range(5, -1, -1):
                        try:
                            sys.monitoring.use_tool_id(candidate_id, "peeka-trace")
                            tool_id = candidate_id
                            break
                        except ValueError:
                            continue
                if tool_id is not None:
                    events = sys.monitoring.events
                    sys.monitoring.register_callback(tool_id, events.PY_START, monitoring_start)
                    sys.monitoring.register_callback(tool_id, events.PY_RETURN, monitoring_return)
                    sys.monitoring.register_callback(tool_id, events.PY_UNWIND, monitoring_return)
                    sys.monitoring.set_events(
                        tool_id, events.PY_START | events.PY_RETURN | events.PY_UNWIND
                    )
                else:
                    prev_trace = sys.gettrace()
                    sys.settrace(local_trace)
                    settrace_enabled = True
            try:
                root["_result"] = await coroutine
            except Exception as exc:
                root["_exception"] = exc
        finally:
            if tool_id is not None:
                sys.monitoring.set_events(tool_id, 0)
                sys.monitoring.free_tool_id(tool_id)
            if settrace_enabled:
                sys.settrace(prev_trace)
            root["duration_ms"] = round((time.perf_counter() - start_time) * 1000, 3)
            root["direct_callees"] = _aggregate_callees(completed)
        return [root]

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
        start_time = time.perf_counter()
        try:
            result = func(*args, **kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000
            return [
                {
                    "depth": 0,
                    "function": f"{func.__module__}.{func.__qualname__}",
                    "filename": func.__code__.co_filename
                    if hasattr(func, "__code__")
                    else "unknown",
                    "lineno": func.__code__.co_firstlineno
                    if hasattr(func, "__code__")
                    else 0,
                    "duration_ms": round(duration_ms, 3),
                    "direct_callees": [],
                    "_result": result,
                }
            ]
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            return [
                {
                    "depth": 0,
                    "function": f"{func.__module__}.{func.__qualname__}",
                    "filename": func.__code__.co_filename
                    if hasattr(func, "__code__")
                    else "unknown",
                    "lineno": func.__code__.co_firstlineno
                    if hasattr(func, "__code__")
                    else 0,
                    "duration_ms": round(duration_ms, 3),
                    "direct_callees": [],
                    "_exception": e,
                }
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

        Captures only direct callees of *func* (depth==2) and aggregates
        per-execution.

        Args:
            func: Function to trace
            args: Function arguments
            kwargs: Function keyword arguments
            skip_builtin: Whether to skip built-in and stdlib functions
            min_duration: Minimum duration in ms to record a callee

        Returns:
            Single-element list containing the root node with direct_callees.
        """
        target_thread_id = _rpl.get_ident()
        call_stack: List[Dict[str, Any]] = []
        completed_calls: List[Dict[str, Any]] = []

        def monitoring_callback(code, instruction_offset, *callback_args, is_unwind=False):
            """Callback for sys.monitoring events."""
            if _rpl.get_ident() != target_thread_id:
                return
            # Determine event type based on callback args
            if len(callback_args) == 0:
                # PY_START event
                event = "call"
            else:
                # PY_RETURN event
                event = "return"

            if event == "call":
                # Block grandcallees: func is at len==0 before push (depth=1),
                # direct callees are at len==1 before push (depth=2).
                # len>=2 means we'd be at depth>=3 → skip.
                if len(call_stack) >= 2:
                    return

                # Skip built-in and stdlib if requested.
                # Push a skipped marker to keep depth accurate so that
                # callbacks invoked from inside a stdlib frame
                # (e.g. json.dumps(..., default=user_cb)) are correctly
                # blocked by the depth guard above on their call event.
                if skip_builtin and _is_builtin_or_stdlib(code):
                    call_stack.append({"_code": code, "_skipped": True})
                    return

                func_name = _format_trace_function(code)
                call_entry: Dict[str, Any] = {
                    "depth": len(call_stack) + 1,
                    "function": func_name,
                    "filename": code.co_filename,
                    "lineno": code.co_firstlineno,
                    "start_time": time.perf_counter(),
                    "children": [],
                    "_code": code,
                }
                call_stack.append(call_entry)

            elif event == "return":
                # Find matching entry on the stack by code object.
                # PY_RETURN fires in LIFO order so top of stack should match.
                if not call_stack:
                    return
                call_entry = call_stack[-1]
                if call_entry.get("_code") is not code:
                    # Return for a frame whose call was skipped by a filter
                    return

                if call_entry.get("_skipped"):
                    call_stack.pop()
                    return

                call_stack.pop()
                # On PY_UNWIND (exception exit), discard: pop prevents stale
                # depth but don't record an incomplete call.
                if is_unwind:
                    return
                duration_ms = (time.perf_counter() - call_entry["start_time"]) * 1000

                # Clean up internal keys
                del call_entry["_code"]

                # Only keep if above minimum duration
                if duration_ms >= min_duration:
                    call_entry["duration_ms"] = round(duration_ms, 3)
                    del call_entry["start_time"]

                    # Link to parent's children list
                    if call_stack:
                        call_stack[-1]["children"].append(call_entry)
                    else:
                        completed_calls.append(call_entry)
                else:
                    # Below min_duration: discard. Grandcallees are already
                    # blocked so children is always empty here.
                    if call_entry["children"] and call_stack:
                        call_stack[-1]["children"].extend(call_entry["children"])

        # Register monitoring
        tool_id = None
        for candidate_id in range(5, -1, -1):
            try:
                sys.monitoring.use_tool_id(candidate_id, "peeka-trace")
                tool_id = candidate_id
                break
            except ValueError:
                continue

        if tool_id is None:
            return self._trace_with_settrace(
                func, args, kwargs, skip_builtin, min_duration
            )

        try:
            sys.monitoring.set_events(
                tool_id,
                sys.monitoring.events.PY_START
                | sys.monitoring.events.PY_RETURN
                | sys.monitoring.events.PY_UNWIND,
            )
            sys.monitoring.register_callback(
                tool_id,
                sys.monitoring.events.PY_START,
                lambda code, offset: monitoring_callback(code, offset),
            )
            sys.monitoring.register_callback(
                tool_id,
                sys.monitoring.events.PY_RETURN,
                lambda code, offset, retval: monitoring_callback(code, offset, retval),
            )
            sys.monitoring.register_callback(
                tool_id,
                sys.monitoring.events.PY_UNWIND,
                lambda code, offset, exc: monitoring_callback(
                    code, offset, exc, is_unwind=True
                ),
            )

            # Execute function
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                # completed_calls[0] = func's monitoring entry;
                # its children list holds the raw direct-callee entries.
                func_children = (
                    completed_calls[0]["children"] if completed_calls else []
                )
                direct_callees = _aggregate_callees(func_children)

                root_node: Dict[str, Any] = {
                    "depth": 0,
                    "function": f"{func.__module__}.{func.__qualname__}",
                    "filename": func.__code__.co_filename
                    if hasattr(func, "__code__")
                    else "unknown",
                    "lineno": func.__code__.co_firstlineno
                    if hasattr(func, "__code__")
                    else 0,
                    "duration_ms": round(duration_ms, 3),
                    "direct_callees": direct_callees,
                    "_result": result,
                }

                return [root_node]

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                func_children = (
                    completed_calls[0]["children"] if completed_calls else []
                )
                direct_callees = _aggregate_callees(func_children)
                root_node = {
                    "depth": 0,
                    "function": f"{func.__module__}.{func.__qualname__}",
                    "filename": func.__code__.co_filename
                    if hasattr(func, "__code__")
                    else "unknown",
                    "lineno": func.__code__.co_firstlineno
                    if hasattr(func, "__code__")
                    else 0,
                    "duration_ms": round(duration_ms, 3),
                    "direct_callees": direct_callees,
                    "_exception": e,
                }
                return [root_node]

        finally:
            # Unregister monitoring
            sys.monitoring.set_events(tool_id, 0)
            sys.monitoring.free_tool_id(tool_id)

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

        Captures only direct callees of *func* (depth==2) and aggregates
        per-execution.

        Args:
            func: Function to trace
            args: Function arguments
            kwargs: Function keyword arguments
            skip_builtin: Whether to skip built-in and stdlib functions
            min_duration: Minimum duration in ms to record a callee

        Returns:
            Single-element list containing the root node with direct_callees.
        """
        direct_callee_stack: List[Dict[str, Any]] = []
        completed_direct_callees: List[Dict[str, Any]] = []
        current_depth = [0]

        def local_trace(frame, event, arg):
            """Local trace function tracking depth-2 callees only."""
            code = frame.f_code

            if event == "call":
                current_depth[0] += 1

                # depth==2 means this is a direct callee of func.
                # Always return local_trace so all depth changes are tracked.
                if current_depth[0] == 2:
                    if not (skip_builtin and _is_builtin_or_stdlib(code)):
                        func_name = _format_trace_function(code, frame)
                        direct_callee_stack.append(
                            {
                                "function": func_name,
                                "filename": code.co_filename,
                                "lineno": code.co_firstlineno,
                                "start_time": time.perf_counter(),
                            }
                        )

                return local_trace

            elif event == "return":
                if current_depth[0] == 2 and direct_callee_stack:
                    entry = direct_callee_stack.pop()
                    duration_ms = (time.perf_counter() - entry["start_time"]) * 1000
                    if duration_ms >= min_duration:
                        completed_direct_callees.append(
                            {
                                "function": entry["function"],
                                "filename": entry["filename"],
                                "lineno": entry["lineno"],
                                "duration_ms": round(duration_ms, 3),
                            }
                        )
                current_depth[0] -= 1

            return local_trace

        # Enable trace only during function execution
        prev_trace = sys.gettrace()
        sys.settrace(local_trace)
        start_time = time.perf_counter()

        try:
            result = func(*args, **kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000

            direct_callees = _aggregate_callees(completed_direct_callees)

            root_node: Dict[str, Any] = {
                "depth": 0,
                "function": f"{func.__module__}.{func.__qualname__}",
                "filename": func.__code__.co_filename
                if hasattr(func, "__code__")
                else "unknown",
                "lineno": func.__code__.co_firstlineno
                if hasattr(func, "__code__")
                else 0,
                "duration_ms": round(duration_ms, 3),
                "direct_callees": direct_callees,
                "_result": result,
            }

            return [root_node]

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            direct_callees = _aggregate_callees(completed_direct_callees)
            root_node = {
                "depth": 0,
                "function": f"{func.__module__}.{func.__qualname__}",
                "filename": func.__code__.co_filename
                if hasattr(func, "__code__")
                else "unknown",
                "lineno": func.__code__.co_firstlineno
                if hasattr(func, "__code__")
                else 0,
                "duration_ms": round(duration_ms, 3),
                "direct_callees": direct_callees,
                "_exception": e,
            }
            return [root_node]

        finally:
            sys.settrace(prev_trace)
