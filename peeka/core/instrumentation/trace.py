"""Trace wrapper and backend helpers."""

import logging
import sys
import threading
import time
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

from peeka.core.runtime.compat import (
    BACKEND_SETTRACE,
    BACKEND_SYS_MONITORING,
    BACKEND_WRAPPER_ONLY,
)
from peeka.core.safeeval.simpleeval import BASIC_ALLOWED_ATTRS, SimpleEval

logger = logging.getLogger(__name__)


_GEVENT_PATCHED_CACHE: Optional[bool] = None


def _is_gevent_patched_now() -> bool:
    """Return True when gevent has monkey-patched socket or threading.

    Uses module-level cache with monotonic state while gevent.monkey remains
    loaded: once patched, gevent never un-patches, so we cache True. Returns
    False quickly when gevent.monkey is not present in sys.modules at all.

    Does NOT call gevent_probe.probe() to avoid coupling with top/patch-status
    commands and to preserve the single-direction cache semantic.

    Args: None

    Returns:
        True if gevent.monkey has patched socket or threading, False otherwise.
    """
    global _GEVENT_PATCHED_CACHE
    if _GEVENT_PATCHED_CACHE:
        if "gevent.monkey" not in sys.modules:
            _GEVENT_PATCHED_CACHE = None  # pyright: ignore[reportConstantRedefinition]
            return False
        return True
    monkey = sys.modules.get("gevent.monkey")
    if monkey is None:
        return False
    is_patched = getattr(monkey, "is_module_patched", None)
    if not callable(is_patched):
        return False
    try:
        patched = bool(is_patched("socket")) or bool(is_patched("threading"))
    except Exception:
        return False
    if patched:
        _GEVENT_PATCHED_CACHE = True  # pyright: ignore[reportConstantRedefinition]
    return patched


def _sanitize_call_tree_node(node: Dict[str, Any]) -> Dict[str, Any]:
    """Return a sanitized copy of a call-tree root node for use in observations.

    Strips internal fields that must not leave the wrapper:
    - ``_result``: raw return value (may be non-serialisable or very large)
    - ``_exception``: raw exception object (not JSON-serialisable)
    - ``_code``: code object reference from sys.monitoring backend

    The ``_exception`` field is converted to a serialisable
    ``{"type": ..., "message": ...}`` dict stored under ``exception``.

    Only the root node is processed.  Children never contain these fields,
    so recursion is intentionally absent.

    Args:
        node: A single call-tree node dict as returned by a trace backend.

    Returns:
        A shallow copy of the node with internal fields removed/converted.
    """
    sanitized = dict(node)
    sanitized.pop("_result", None)
    sanitized.pop("_code", None)
    exc = sanitized.pop("_exception", None)
    if exc is not None:
        sanitized["exception"] = {
            "type": type(exc).__name__,
            "message": str(exc),
        }
    return sanitized


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
                - condition_express: Filter expression
                - times: Observation limit (-1 for unlimited)
                - skip_builtin: Skip built-in functions (default: True)
                - min_duration: Minimum duration in ms (default: 0)

        Returns:
            Wrapper function that traces call tree
        """
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
        injector: Any = self

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

            # Runtime gevent check: if gevent was lazy-loaded after injection and
            # we are using the global sys.settrace tracer, force downgrade to
            # wrapper_only to avoid sys.settrace / greenlet hub conflicts.
            # sys.monitoring is per-tool and does not need this protection.
            effective_backend = force_backend
            if (
                not use_monitoring
                and effective_backend != BACKEND_WRAPPER_ONLY
                and _is_gevent_patched_now()
            ):
                effective_backend = BACKEND_WRAPPER_ONLY

            if effective_backend == BACKEND_WRAPPER_ONLY:
                call_tree = injector._trace_with_wrapper_only(func, args, kwargs)
            elif use_monitoring:
                # Use sys.monitoring for Python 3.12+
                call_tree = injector._trace_with_monitoring(
                    func,
                    args,
                    kwargs,
                    skip_builtin,
                    min_duration,
                )
            else:
                # Fallback to sys.settrace for older Python versions
                call_tree = injector._trace_with_settrace(
                    func,
                    args,
                    kwargs,
                    skip_builtin,
                    min_duration,
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

            # Sanitize call_tree root node before building observation
            # (strips _result / _exception / _code that must not be serialised).
            # The original call_tree is preserved unchanged for the return/raise below.
            sanitized_root = _sanitize_call_tree_node(call_tree[0]) if call_tree else None
            direct_callees = (
                sanitized_root.get("direct_callees", []) if sanitized_root is not None else []
            )

            runtime_meta = None
            dynamic_settrace_downgrade = (
                effective_backend == BACKEND_WRAPPER_ONLY
                and force_backend == BACKEND_SETTRACE
                and _is_gevent_patched_now()
            )
            if dynamic_settrace_downgrade:
                runtime_meta = {
                    "trace": {
                        "startup_backend": force_backend if force_backend else "auto",
                        "effective_backend": effective_backend,
                        "downgraded": True,
                        "downgrade_reason": "gevent_patched_runtime",
                        "gevent_patched_now": True,
                    }
                }
                with injector._lock:
                    info = injector.instrumented.get(watch_id)
                    if info:
                        info["runtime_meta"] = runtime_meta
                        info.setdefault("config", {})["runtime_meta"] = runtime_meta

            # Send observation
            observation = {
                "watch_id": watch_id,
                "count": current_count,
                "timestamp": time.time(),
                "location": "AtExit",
                "func_name": f"{func.__module__}.{func.__qualname__}",
                "call_tree": direct_callees,
                "total_duration_ms": round(total_duration, 3),
                "self_time_ms": round(
                    max(
                        0.0,
                        total_duration
                        - sum(c.get("total_ms", 0.0) for c in direct_callees),
                    ),
                    3,
                ),
                "callee_count": len(direct_callees),
                "node_count": 1 + len(direct_callees),
                "thread_id": threading.get_ident(),
                "thread_name": threading.current_thread().name,
            }
            if sanitized_root is not None and "exception" in sanitized_root:
                observation["exception"] = sanitized_root["exception"]

            if runtime_meta is not None:
                observation["runtime_meta"] = runtime_meta

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
        """Count nodes in call tree: 1 (root) + number of direct callees."""
        if not call_tree:
            return 0
        return 1 + len(call_tree[0].get("direct_callees", []))
