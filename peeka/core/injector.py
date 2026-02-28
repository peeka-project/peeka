"""
Decorator Injector - Runtime function instrumentation

This module provides the DecoratorInjector class that dynamically injects
observation logic into target functions at runtime, enabling function call
monitoring without modifying the original source code.
"""

import fnmatch
import importlib
import inspect
import sys
import threading
import time
import uuid
from functools import wraps
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

from peeka.core.safeeval.simpleeval import SimpleEval, BASIC_ALLOWED_ATTRS

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class DecoratorInjector:
    """
    Injects observation decorators into target functions at runtime.

    This class is responsible for:
    - Resolving function patterns to actual Python objects
    - Creating wrapper functions that capture call information
    - Replacing original functions with instrumented versions
    - Restoring original functions when observation stops

    Example:
        injector = DecoratorInjector(agent)
        watch_id = injector.inject("mymodule.MyClass.method", {"depth": 2})
        # ... observations happen ...
        injector.uninject(watch_id)
    """

    def __init__(self, agent: "PeekaAgent"):
        """
        Initialize the injector.

        Args:
            agent: Reference to the parent PeekaAgent for sending observations
        """
        self.agent = agent
        self.instrumented: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def inject(self, pattern: str, watch_config: Dict[str, Any]) -> str:
        """
        Inject observation decorator into target function.

        Args:
            pattern: Dotted path to target function (e.g., "mymodule.MyClass.method")
            watch_config: Configuration dict with keys:
                - depth: int, output depth for nested objects (default: 2)
                - condition_express: str, optional condition expression (Arthas compatible)
                - times: int, max observations (-1 for infinite)
                - before: bool, observe before function execution (-b flag)
                - exception: bool, observe on exception (-e flag)
                - success: bool, observe on success return (-s flag)
                - finish: bool, observe after function finish (-f flag, default True)
                - express: str, custom observe expression (like Arthas)

        Returns:
            watch_id: Unique identifier for this observation

        Raises:
            ValueError: If target function cannot be found
        """
        # Resolve target
        target_info = self._resolve_target(pattern)
        if target_info is None:
            raise ValueError(f"Cannot find target: {pattern}")

        target_func, parent_obj, attr_name = target_info

        # Generate watch ID
        watch_id = self._generate_watch_id()

        # Detect if this is an instance method (parent is a class)
        is_instance_method = inspect.isclass(parent_obj)
        watch_config["_is_instance_method"] = is_instance_method

        # Create wrapper
        wrapper = self._create_wrapper(target_func, watch_id, watch_config)

        with self._lock:
            # Store original function info for restoration
            self.instrumented[watch_id] = {
                "pattern": pattern,
                "original": target_func,
                "wrapper": wrapper,
                "parent": parent_obj,
                "attr_name": attr_name,
                "config": watch_config,
                "count": 0,
                "times_limit": watch_config.get("times", -1),
            }

            # Replace the function
            self._replace_function(parent_obj, attr_name, wrapper)

        return watch_id

    def inject_trace(self, pattern: str, trace_config: Dict[str, Any]) -> str:
        """
        Inject trace wrapper into target function.

        Args:
            pattern: Dotted path to target function (e.g., "mymodule.MyClass.method")
            trace_config: Configuration dict with keys:
                - trace_depth: int, max call depth to trace (default: 3)
                - condition_express: str, optional condition expression
                - times: int, max observations (-1 for infinite)
                - skip_builtin: bool, skip built-in and stdlib functions (default: True)
                - min_duration: float, minimum duration in ms to record (default: 0)

        Returns:
            watch_id: Unique identifier for this trace

        Raises:
            ValueError: If target function cannot be found
        """
        # Resolve target
        target_info = self._resolve_target(pattern)
        if target_info is None:
            raise ValueError(f"Cannot find target: {pattern}")

        target_func, parent_obj, attr_name = target_info

        # Generate watch ID
        watch_id = f"trace_{uuid.uuid4().hex[:8]}"

        # Detect if this is an instance method
        is_instance_method = inspect.isclass(parent_obj)
        trace_config["_is_instance_method"] = is_instance_method

        # Create trace wrapper
        wrapper = self._create_trace_wrapper(target_func, watch_id, trace_config)

        with self._lock:
            # Store original function info for restoration
            self.instrumented[watch_id] = {
                "pattern": pattern,
                "original": target_func,
                "wrapper": wrapper,
                "parent": parent_obj,
                "attr_name": attr_name,
                "config": trace_config,
                "count": 0,
                "times_limit": trace_config.get("times", -1),
            }

            # Replace the function
            self._replace_function(parent_obj, attr_name, wrapper)

        return watch_id

    def uninject(self, watch_id: str) -> Dict[str, Any]:
        """
        Remove observation and restore original function.

        Args:
            watch_id: The watch ID returned by inject()

        Returns:
            Dict with observation statistics

        Raises:
            ValueError: If watch_id not found
        """
        with self._lock:
            if watch_id not in self.instrumented:
                raise ValueError(f"Watch not found: {watch_id}")

            info = self.instrumented.pop(watch_id)

            # Restore original function
            self._replace_function(info["parent"], info["attr_name"], info["original"])

            return {
                "watch_id": watch_id,
                "pattern": info["pattern"],
                "count": info["count"],
            }

    def uninject_all(self) -> int:
        """
        Remove all observations and restore all original functions.

        Returns:
            Number of observations removed
        """
        with self._lock:
            count = len(self.instrumented)

            for watch_id, info in list(self.instrumented.items()):
                try:
                    self._replace_function(
                        info["parent"], info["attr_name"], info["original"]
                    )
                except Exception:
                    pass  # Best effort restoration

            self.instrumented.clear()
            return count

    def get_watch_info(self, watch_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about an active watch.

        Args:
            watch_id: The watch ID

        Returns:
            Dict with watch info or None if not found
        """
        with self._lock:
            info = self.instrumented.get(watch_id)
            if info:
                return {
                    "watch_id": watch_id,
                    "pattern": info["pattern"],
                    "count": info["count"],
                    "times_limit": info["times_limit"],
                    "config": info["config"],
                }
            return None

    def list_watches(self) -> list:
        """
        List all active watches.

        Returns:
            List of watch info dicts
        """
        with self._lock:
            return [
                {
                    "watch_id": wid,
                    "pattern": info["pattern"],
                    "count": info["count"],
                    "times_limit": info["times_limit"],
                }
                for wid, info in self.instrumented.items()
            ]

    def reset(self, pattern: Optional[str] = None) -> Dict[str, Any]:
        """
        Reset (uninject) enhancements, optionally filtered by pattern.

        Args:
            pattern: Optional pattern to match against stored patterns. If None, resets all.
                    Supports Unix shell-style wildcards (* and ?).

        Returns:
            Dict with status, action, affected watches, and count of successful resets
        """
        affected = []

        # Collect watch_ids to reset
        watch_ids_to_reset = []
        with self._lock:
            for watch_id, info in list(self.instrumented.items()):
                if pattern is None or self._match_pattern(
                    info.get("pattern", ""), pattern
                ):
                    watch_ids_to_reset.append(watch_id)

        # Reset each
        for watch_id in watch_ids_to_reset:
            try:
                result = self.uninject(watch_id)
                affected.append(
                    {"watch_id": watch_id, "pattern": result.get("pattern", "")}
                )
            except Exception as e:
                affected.append({"watch_id": watch_id, "error": str(e)})

        return {
            "status": "success",
            "action": "reset",
            "affected": affected,
            "count": len([a for a in affected if "error" not in a]),
        }

    def list_enhanced(self) -> Dict[str, Any]:
        """
        List all current enhancements.

        Returns:
            Dict with status, action, list of enhanced watches, and total count
        """
        enhanced = []
        with self._lock:
            for watch_id, info in self.instrumented.items():
                enhanced.append(
                    {
                        "watch_id": watch_id,
                        "pattern": info.get("pattern", "unknown"),
                        "command": info.get("config", {}).get("command", "watch"),
                        "count": info.get("count", 0),
                    }
                )
        return {
            "status": "success",
            "action": "list",
            "enhanced": enhanced,
            "total": len(enhanced),
        }

    def _match_pattern(self, stored_pattern: str, filter_pattern: str) -> bool:
        """
        Match stored pattern against filter using fnmatch wildcards.

        Args:
            stored_pattern: The pattern stored in instrumented data
            filter_pattern: The pattern to filter by (supports * and ?)

        Returns:
            True if patterns match, False otherwise
        """
        return fnmatch.fnmatch(stored_pattern, filter_pattern)

    def _generate_watch_id(self) -> str:
        """Generate unique watch ID."""
        return f"watch_{uuid.uuid4().hex[:8]}"

    def _resolve_target(self, pattern: str) -> Optional[tuple]:
        """
        Resolve pattern to (function, parent_object, attr_name).

        When the target process runs a script as ``python script.py``, the
        module is loaded as ``__main__`` rather than its filename-based name.
        This method detects that situation and transparently redirects
        resolution to ``__main__`` so that users can use the natural
        ``demo.Calculator.add`` pattern without needing to know about
        ``__main__``.

        Args:
            pattern: Dotted path like 'module.Class.method' or 'module.function'

        Returns:
            Tuple of (target_func, parent_obj, attr_name) or None if not found
        """
        parts = pattern.split(".")
        if len(parts) < 2:
            return None

        # Try progressively shorter module prefixes
        for i in range(len(parts) - 1, 0, -1):
            module_name = ".".join(parts[:i])
            attrs = parts[i:]

            # Try to get module from sys.modules first (already imported)
            module = sys.modules.get(module_name)

            if module is None:
                # Try to import it
                try:
                    module = importlib.import_module(module_name)
                except (ImportError, ModuleNotFoundError):
                    continue

            # When a script runs as ``python script.py``, its module lives
            # under ``__main__`` in sys.modules.  If we resolved the module
            # via import (or from sys.modules under a non-__main__ name),
            # the classes/functions we patch there will be *different objects*
            # from the ones the running code actually uses.  Detect this by
            # comparing __file__ paths and prefer __main__ when they match.
            main_module = sys.modules.get("__main__")
            if (
                main_module is not None
                and module is not main_module
                and hasattr(module, "__file__")
                and hasattr(main_module, "__file__")
                and module.__file__
                and main_module.__file__
            ):
                try:
                    from pathlib import Path

                    if (
                        Path(module.__file__).resolve()
                        == Path(main_module.__file__).resolve()
                    ):
                        module = main_module
                except (OSError, TypeError):
                    pass

            # Navigate to the target
            obj = module
            parent = None
            attr_name = None

            for j, attr in enumerate(attrs):
                parent = obj
                attr_name = attr
                try:
                    obj = getattr(obj, attr)
                except AttributeError:
                    obj = None
                    break

            if obj is not None and callable(obj):
                return (obj, parent, attr_name)

        return None

    def _create_wrapper(
        self, func: Callable, watch_id: str, config: Dict[str, Any]
    ) -> Callable:
        """
        Create a wrapper function that captures call information.

        Observation Timing (Arthas-compatible):
        - before (-b):    Observe at function entry (AtEnter)
        - success (-s):   Observe only on successful return (AtExit)
        - exception (-e): Observe only on exception (AtExceptionExit)
        - finish (-f):    Observe both success and exception (default)

        Args:
            func: Original function to wrap
            watch_id: Unique watch identifier
            config: Watch configuration with keys:
                - depth: Output depth for nested objects
                - condition_express: Filter expression
                - times: Observation limit (-1 for unlimited)
                - before: Observe at function entry
                - exception: Observe only on exception
                - success: Observe only on success
                - finish: Observe on both success and exception (default)

        Returns:
            Wrapper function that intercepts calls and sends observations
        """
        depth = config.get("depth", 2)
        condition_express = config.get("condition_express") or config.get("condition")
        times_limit = config.get("times", -1)

        before = config.get("before", False)
        on_exception = config.get("exception", False)
        on_success = config.get("success", False)
        on_finish = config.get("finish", True)

        if not (before or on_exception or on_success or on_finish):
            on_finish = True

        safe_evaluator = None
        if condition_express:
            try:
                safe_evaluator = SimpleEval(
                    allowed_attrs=BASIC_ALLOWED_ATTRS,
                    functions={
                        "len": len,
                        "str": str,
                        "int": int,
                        "float": float,
                        "bool": bool,
                    },
                )
                safe_evaluator.parse(condition_express)
            except SyntaxError as e:
                raise ValueError(f"Invalid condition expression: {e}")
            except Exception as e:
                raise ValueError(f"Condition validation failed: {e}")

        # Reference to self for use in wrapper
        injector = self

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Stage 0: Check if observation is still active
            with injector._lock:
                info = injector.instrumented.get(watch_id)
                if info is None:
                    return func(*args, **kwargs)

                # Check if we've reached the observation limit
                if times_limit > 0 and info["count"] >= times_limit:
                    return func(*args, **kwargs)

            # Extract self object for instance methods (Arthas 'target')
            is_instance_method = config.get("_is_instance_method", False)
            target_self = args[0] if args and is_instance_method else None

            def should_observe(duration_cost=None):
                """
                Evaluate condition expression to determine if this call should be observed.

                Args:
                    duration_cost: Execution time in ms (only available after function completes)
                """
                if not safe_evaluator:
                    return True
                try:
                    local_vars = {
                        "params": args,
                        "kwargs": kwargs,
                        "target": target_self,
                    }
                    # cost variable only available at AtExit/AtExceptionExit
                    if duration_cost is not None:
                        local_vars["cost"] = duration_cost
                    safe_evaluator.names = local_vars
                    return bool(safe_evaluator.eval(condition_express))
                except Exception:
                    return False

            def send_observation(
                location, result_val=None, error_msg=None, duration_ms: float = 0.0
            ):
                """
                Send observation data to agent.

                Args:
                    location: AtEnter/AtExit/AtExceptionExit
                    result_val: Return value (only at AtExit)
                    error_msg: Exception message (only at AtExceptionExit)
                    duration_ms: Execution time in milliseconds
                """
                with injector._lock:
                    info = injector.instrumented.get(watch_id)
                    if info:
                        info["count"] += 1

                observation = {
                    "watch_id": watch_id,
                    "timestamp": time.time(),
                    "location": location,
                    "func_name": f"{func.__module__}.{func.__qualname__}",
                    "params": injector._format_value(args, depth),
                    "kwargs": injector._format_value(kwargs, depth),
                    "target": injector._format_value(target_self, depth)
                    if target_self
                    else None,
                    "returnObj": injector._format_value(result_val, depth)
                    if result_val is not None
                    else None,
                    "success": error_msg is None,
                    "throwExp": error_msg,
                    "cost": round(duration_ms, 3),
                    "thread_id": threading.get_ident(),
                    "thread_name": threading.current_thread().name,
                }

                stack_depth = config.get("stack_depth")
                if stack_depth is not None and location == "AtEnter":
                    stack_frames = inspect.stack()[2 : 2 + stack_depth]
                    observation["stack"] = [
                        {
                            "filename": frame.filename,
                            "lineno": frame.lineno,
                            "function": frame.function,
                            "code_context": frame.code_context[0].strip()
                            if frame.code_context
                            else None,
                        }
                        for frame in stack_frames
                    ]

                try:
                    injector.agent._send_observation(observation)
                except Exception:
                    pass

            # Stage 1: Observe at function entry (AtEnter) if -b flag enabled
            # Available: params, kwargs, target
            # Not available: returnObj (not executed yet), cost (not started)
            if before and should_observe():
                send_observation("AtEnter")

            # Stage 2: Execute the original function and measure time
            start_time = time.perf_counter()
            result = None
            error = None

            try:
                # Call the original function
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Stage 3a: Observe on successful return (AtExit)
                # Available: params, kwargs, target, returnObj, cost
                if on_success and should_observe(duration_ms):
                    # User explicitly specified -s flag
                    send_observation(
                        "AtExit", result_val=result, duration_ms=duration_ms
                    )
                elif on_finish and not on_success and should_observe(duration_ms):
                    # Default -f flag (observe all exits)
                    send_observation(
                        "AtExit", result_val=result, duration_ms=duration_ms
                    )

                return result
            except Exception as e:
                duration_ms = (time.perf_counter() - start_time) * 1000
                error = f"{type(e).__name__}: {str(e)}"

                # Stage 3b: Observe on exception (AtExceptionExit)
                # Available: params, kwargs, target, throwExp, cost
                # Not available: returnObj (exception occurred)
                if on_exception and should_observe(duration_ms):
                    # User explicitly specified -e flag
                    send_observation(
                        "AtExceptionExit", error_msg=error, duration_ms=duration_ms
                    )
                elif on_finish and not on_exception and should_observe(duration_ms):
                    # Default -f flag (observe all exits including exceptions)
                    send_observation(
                        "AtExceptionExit", error_msg=error, duration_ms=duration_ms
                    )

                # Re-raise exception (don't suppress it)
                raise

        return wrapper

    def _create_trace_wrapper(
        self, func: Callable, watch_id: str, config: Dict[str, Any]
    ) -> Callable:
        """
        Create a trace wrapper that captures call tree and timing using sys.monitoring.

        Args:
            func: Original function to wrap
            watch_id: Unique watch identifier
            config: Trace configuration with keys:
                - trace_depth: Max call depth (default: 3)
                - condition_express: Filter expression
                - times: Observation limit (-1 for unlimited)
                - skip_builtin: Skip built-in functions (default: True)
                - min_duration: Minimum duration in ms (default: 0)

        Returns:
            Wrapper function that traces call tree
        """
        trace_depth = config.get("trace_depth", 3)
        condition_express = config.get("condition_express") or config.get("condition")
        times_limit = config.get("times", -1)
        skip_builtin = config.get("skip_builtin", True)
        min_duration = config.get("min_duration", 0)

        safe_evaluator = None
        if condition_express:
            try:
                safe_evaluator = SimpleEval(
                    allowed_attrs=BASIC_ALLOWED_ATTRS,
                    functions={
                        "len": len,
                        "str": str,
                        "int": int,
                        "float": float,
                        "bool": bool,
                    },
                )
                safe_evaluator.parse(condition_express)
            except SyntaxError as e:
                raise ValueError(f"Invalid condition expression: {e}")
            except Exception as e:
                raise ValueError(f"Condition validation failed: {e}")

        # Reference to self for use in wrapper
        injector = self

        # Check if sys.monitoring is available (Python 3.12+)
        use_monitoring = sys.version_info >= (3, 12) and hasattr(sys, "monitoring")

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Stage 0: Check if observation is still active
            with injector._lock:
                info = injector.instrumented.get(watch_id)
                if info is None:
                    return func(*args, **kwargs)

                # Check if we've reached the observation limit
                if times_limit > 0 and info["count"] >= times_limit:
                    return func(*args, **kwargs)

            # Extract self object for instance methods
            is_instance_method = config.get("_is_instance_method", False)
            target_self = args[0] if args and is_instance_method else None

            def should_observe(duration_cost=None):
                """Evaluate condition expression."""
                if not safe_evaluator:
                    return True
                try:
                    local_vars = {
                        "params": args,
                        "kwargs": kwargs,
                        "target": target_self,
                    }
                    if duration_cost is not None:
                        local_vars["cost"] = duration_cost
                    safe_evaluator.names = local_vars
                    return bool(safe_evaluator.eval(condition_express))
                except Exception:
                    return False

            # Build call tree
            call_tree = []
            call_stack = []

            if use_monitoring:
                # Use sys.monitoring for Python 3.12+
                call_tree = injector._trace_with_monitoring(
                    func,
                    args,
                    kwargs,
                    trace_depth,
                    skip_builtin,
                    min_duration,
                    call_stack,
                )
            else:
                # Fallback to sys.settrace for older Python versions
                call_tree = injector._trace_with_settrace(
                    func,
                    args,
                    kwargs,
                    trace_depth,
                    skip_builtin,
                    min_duration,
                    call_stack,
                )

            # Calculate total duration
            total_duration = call_tree[0]["duration_ms"] if call_tree else 0

            # Check condition with cost
            if not should_observe(total_duration):
                # Return or raise based on whether there was an exception
                if call_tree and "_exception" in call_tree[0]:
                    raise call_tree[0]["_exception"]
                return call_tree[0].get("_result") if call_tree else None

            # Count observation
            with injector._lock:
                info = injector.instrumented.get(watch_id)
                if info:
                    info["count"] += 1

            # Send observation
            observation = {
                "watch_id": watch_id,
                "timestamp": time.time(),
                "location": "AtExit",
                "func_name": f"{func.__module__}.{func.__qualname__}",
                "call_tree": call_tree,
                "total_duration_ms": round(total_duration, 3),
                "node_count": injector._count_nodes(call_tree),
                "thread_id": threading.get_ident(),
                "thread_name": threading.current_thread().name,
            }

            try:
                injector.agent._send_observation(observation)
            except Exception:
                pass

            # Return the actual result or raise exception
            if call_tree:
                if "_exception" in call_tree[0]:
                    raise call_tree[0]["_exception"]
                if "_result" in call_tree[0]:
                    return call_tree[0]["_result"]

            return None

        return wrapper

    def _trace_with_monitoring(
        self,
        func: Callable,
        args: tuple,
        kwargs: Dict[str, Any],
        max_depth: int,
        skip_builtin: bool,
        min_duration: float,
        call_stack: list,
    ) -> list:
        """
        Trace function execution using sys.monitoring (Python 3.12+).

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
                duration_ms = (
                    time.perf_counter() - call_entry["start_time"]
                ) * 1000

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
                        call_stack[-1]["children"].extend(
                            call_entry["children"]
                        )
        # Register monitoring
        tool_id = 0
        try:
            sys.monitoring.use_tool_id(tool_id, "peeka-trace")
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
        func: Callable,
        args: tuple,
        kwargs: Dict[str, Any],
        max_depth: int,
        skip_builtin: bool,
        min_duration: float,
        call_stack: list,
    ) -> list:
        """
        Trace function execution using sys.settrace (fallback for Python < 3.12).

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

    def _count_nodes(self, call_tree: list) -> int:
        """
        Count total number of nodes in call tree.

        Args:
            call_tree: Call tree structure

        Returns:
            Total node count
        """
        count = 0
        for node in call_tree:
            count += 1
            if "children" in node:
                count += self._count_nodes(node["children"])
        return count

    def _replace_function(
        self, parent: Any, attr_name: str, new_func: Callable
    ) -> None:
        """
        Replace a function/method on its parent object.

        Args:
            parent: The parent object (module, class, or instance)
            attr_name: Name of the attribute to replace
            new_func: New function to set
        """
        setattr(parent, attr_name, new_func)

    def _format_value(self, value: Any, depth: int) -> Any:
        """
        Format a value for JSON serialization.

        Args:
            value: Value to format
            depth: Maximum depth for nested structures

        Returns:
            JSON-serializable representation
        """
        return self._format_value_recursive(value, depth, 0)

    def _format_value_recursive(
        self, value: Any, max_depth: int, current_depth: int
    ) -> Any:
        """
        Recursively format value for JSON serialization.

        Args:
            value: Value to format
            max_depth: Maximum depth
            current_depth: Current recursion depth

        Returns:
            JSON-serializable value
        """
        if current_depth >= max_depth:
            return self._to_string(value)

        # None
        if value is None:
            return None

        # Primitives
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if isinstance(value, float) and (
                value != value or value == float("inf") or value == float("-inf")
            ):
                # Handle NaN, Inf
                return str(value)
            return value
        if isinstance(value, str):
            # Truncate long strings
            if len(value) > 1000:
                return value[:1000] + f"... ({len(value) - 1000} more chars)"
            return value
        if isinstance(value, bytes):
            if len(value) > 100:
                return f"<bytes len={len(value)}>"
            return value.hex()

        # List/Tuple
        if isinstance(value, (list, tuple)):
            if len(value) > 20:
                items = [
                    self._format_value_recursive(v, max_depth, current_depth + 1)
                    for v in value[:20]
                ]
                items.append(f"... ({len(value) - 20} more)")
                return items
            return [
                self._format_value_recursive(v, max_depth, current_depth + 1)
                for v in value
            ]

        # Dict
        if isinstance(value, dict):
            result = {}
            count = 0
            for k, v in value.items():
                if count >= 20:
                    result["..."] = f"({len(value) - 20} more)"
                    break
                key_str = str(k) if not isinstance(k, str) else k
                result[key_str] = self._format_value_recursive(
                    v, max_depth, current_depth + 1
                )
                count += 1
            return result

        # Set
        if isinstance(value, (set, frozenset)):
            items = list(value)[:20]
            formatted = [
                self._format_value_recursive(v, max_depth, current_depth + 1)
                for v in items
            ]
            if len(value) > 20:
                formatted.append(f"... ({len(value) - 20} more)")
            return {"__set__": formatted}

        # Objects
        return self._format_object(value, max_depth, current_depth)

    def _format_object(self, obj: Any, max_depth: int, current_depth: int) -> Any:
        """
        Format an object for JSON serialization.

        Args:
            obj: Object to format
            max_depth: Maximum depth
            current_depth: Current depth

        Returns:
            JSON-serializable representation
        """
        class_name = obj.__class__.__name__
        module_name = obj.__class__.__module__

        if current_depth >= max_depth:
            return f"<{module_name}.{class_name}>"

        # Try to get __dict__
        try:
            if hasattr(obj, "__dict__") and obj.__dict__:
                attrs = {}
                count = 0
                for k, v in obj.__dict__.items():
                    if count >= 10:
                        attrs["..."] = f"({len(obj.__dict__) - 10} more)"
                        break
                    if not k.startswith("_"):  # Skip private attributes
                        attrs[k] = self._format_value_recursive(
                            v, max_depth, current_depth + 1
                        )
                        count += 1
                return {"__class__": f"{module_name}.{class_name}", "__attrs__": attrs}
        except Exception:
            pass

        # Fallback to string representation
        return self._to_string(obj)

    def _to_string(self, value: Any) -> str:
        """
        Convert value to string safely.

        Args:
            value: Value to convert

        Returns:
            String representation
        """
        try:
            s = repr(value)
            if len(s) > 200:
                return s[:200] + "..."
            return s
        except Exception:
            try:
                return f"<{type(value).__name__}>"
            except Exception:
                return "<unknown>"
