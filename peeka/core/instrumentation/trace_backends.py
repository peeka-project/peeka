"""Trace backend implementations."""

import sys
import time
from typing import Any, Callable, Dict, List, Tuple


class InjectorTraceBackendsMixin:

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
            Single-node call tree containing the root call.
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
                    "children": [],
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
                    "children": [],
                    "_exception": e,
                }
            ]

    def _trace_with_monitoring(
        self,
        func: Callable[..., Any],
        args: Tuple[Any, ...],
        kwargs: Dict[str, Any],
        max_depth: int,
        skip_builtin: bool,
        min_duration: float,
        call_stack: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Trace function execution using sys.monitoring (Python 3.12+).

        Caller must enforce runtime compatibility before selecting this backend.

        Args:
            func: Function to trace
            args: Function arguments
            kwargs: Function keyword arguments
            max_depth: Maximum call depth
            skip_builtin: Whether to skip built-in functions
            min_duration: Minimum duration in ms to record
            call_stack: Shared call stack for tracking depth

        Returns:
            Call tree as list of dicts
        """
        import sys

        call_stack = []
        completed_calls = []

        def monitoring_callback(code, instruction_offset, *callback_args):
            """Callback for sys.monitoring events."""
            func_name = f"{code.co_filename}:{code.co_name}"

            # Determine event type based on callback args
            if len(callback_args) == 0:
                # PY_START event
                event = "call"
            else:
                # PY_RETURN event
                event = "return"

            if event == "call":
                # Skip if too deep
                if len(call_stack) >= max_depth:
                    return

                # Skip built-in and stdlib if requested
                if skip_builtin:
                    if code.co_filename.startswith("<"):
                        return
                    if (
                        "site-packages" not in code.co_filename
                        and "dist-packages" not in code.co_filename
                    ):
                        import os

                        py_path = os.path.dirname(os.__file__)
                        if code.co_filename.startswith(py_path):
                            return

                call_entry = {
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
                    # Not the expected return (call was skipped by filter)
                    return

                call_stack.pop()
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
                    # Below min_duration: discard but migrate children up
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
                func, args, kwargs, max_depth, skip_builtin, min_duration, call_stack
            )

        try:
            sys.monitoring.set_events(
                tool_id,
                sys.monitoring.events.PY_START | sys.monitoring.events.PY_RETURN,
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

            # Execute function
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Build tree structure from flat list
                children = list(completed_calls)

                # Root node
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
                    "children": children,
                    "_result": result,
                }

                return [root_node]

            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                children = list(completed_calls)
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
                    "children": children,
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
        max_depth: int,
        skip_builtin: bool,
        min_duration: float,
        call_stack: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Trace function execution using sys.settrace (fallback for Python < 3.12).

        Caller must enforce runtime compatibility before selecting this backend.

        Args:
            func: Function to trace
            args: Function arguments
            kwargs: Function keyword arguments
            max_depth: Maximum call depth
            skip_builtin: Whether to skip built-in functions
            min_duration: Minimum duration in ms to record
            call_stack: Shared call stack for tracking depth

        Returns:
            Call tree as list of dicts
        """
        call_tree = []
        current_depth = [0]

        def local_trace(frame, event, arg):
            """Local trace function."""
            if current_depth[0] >= max_depth:
                return None

            if event == "call":
                code = frame.f_code
                func_name = f"{code.co_filename}:{code.co_name}"

                # Skip built-in and stdlib if requested
                if skip_builtin:
                    if code.co_filename.startswith("<"):
                        return None
                    if (
                        "site-packages" not in code.co_filename
                        and "dist-packages" not in code.co_filename
                    ):
                        import os

                        py_path = os.path.dirname(os.__file__)
                        if code.co_filename.startswith(py_path):
                            return None

                current_depth[0] += 1
                start_time = time.perf_counter()

                call_tree.append(
                    {
                        "depth": current_depth[0],
                        "function": func_name,
                        "filename": code.co_filename,
                        "lineno": frame.f_lineno,
                        "start_time": start_time,
                    }
                )
                return local_trace

            elif event == "return":
                if call_tree and call_tree[-1]["depth"] == current_depth[0]:
                    duration_ms = (
                        time.perf_counter() - call_tree[-1]["start_time"]
                    ) * 1000

                    # Only keep if above minimum duration
                    if duration_ms >= min_duration:
                        call_tree[-1]["duration_ms"] = round(duration_ms, 3)
                        del call_tree[-1]["start_time"]
                    else:
                        call_tree.pop()

                current_depth[0] -= 1

            return local_trace

        # Enable trace only during function execution
        sys.settrace(local_trace)
        start_time = time.perf_counter()

        try:
            result = func(*args, **kwargs)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Root node
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
                "children": call_tree,
                "_result": result,
            }

            return [root_node]

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
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
                "children": call_tree,
                "_exception": e,
            }
            return [root_node]

        finally:
            sys.settrace(None)
