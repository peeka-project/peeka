"""Trace wrapper and backend helpers."""

import logging
import sys
import threading
import time
from functools import wraps
from typing import Any, Callable, Dict, List

from peeka.core.runtime.compat import (
    BACKEND_SETTRACE,
    BACKEND_SYS_MONITORING,
    BACKEND_WRAPPER_ONLY,
)
from peeka.core.safeeval.simpleeval import BASIC_ALLOWED_ATTRS, SimpleEval

logger = logging.getLogger(__name__)


class InjectorTraceMixin:

    def _create_trace_wrapper(
        self, func: Callable[..., Any], watch_id: str, config: Dict[str, Any]
    ) -> Callable[..., Any]:
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
        force_backend = config.get("_force_backend")

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

        # Check if sys.monitoring is available (Python 3.12+).
        if force_backend == BACKEND_SETTRACE:
            use_monitoring = False
        elif force_backend == BACKEND_SYS_MONITORING:
            use_monitoring = sys.version_info >= (3, 12) and hasattr(sys, "monitoring")
        else:
            use_monitoring = (
                force_backend != BACKEND_WRAPPER_ONLY
                and sys.version_info >= (3, 12)
                and hasattr(sys, "monitoring")
            )

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
            user_args = args[1:] if target_self is not None else args

            def should_observe(duration_cost=None):
                """Evaluate condition expression."""
                if not safe_evaluator:
                    return True
                try:
                    local_vars = {
                        "params": user_args,
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

            if force_backend == BACKEND_WRAPPER_ONLY:
                call_tree = injector._trace_with_wrapper_only(func, args, kwargs)
            elif use_monitoring:
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
            current_count = 0
            with injector._lock:
                info = injector.instrumented.get(watch_id)
                if info:
                    info["count"] += 1
                    current_count = info["count"]

            # Send observation
            observation = {
                "watch_id": watch_id,
                "count": current_count,
                "timestamp": time.time(),
                "location": "AtExit",
                "func_name": f"{func.__module__}.{func.__qualname__}",
                "call_tree": call_tree,
                "total_duration_ms": round(total_duration, 3),
                "node_count": injector._count_nodes(call_tree),
                "thread_id": threading.get_ident(),
                "thread_name": threading.current_thread().name,
            }

            if not injector._record_probe_event(config, observation):
                if call_tree:
                    if "_exception" in call_tree[0]:
                        raise call_tree[0]["_exception"]
                    if "_result" in call_tree[0]:
                        return call_tree[0]["_result"]
                return None

            try:
                injector.agent._send_observation(observation)
            except Exception:
                logger.debug(
                    "Failed to send trace observation for %s", watch_id, exc_info=True
                )

            # Return the actual result or raise exception
            if call_tree:
                if "_exception" in call_tree[0]:
                    raise call_tree[0]["_exception"]
                if "_result" in call_tree[0]:
                    return call_tree[0]["_result"]

            return None

        return wrapper

    def _count_nodes(self, call_tree: List[Dict[str, Any]]) -> int:
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
