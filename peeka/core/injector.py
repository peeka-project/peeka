"""
Decorator Injector - Runtime function instrumentation

This module provides the DecoratorInjector class that dynamically injects
observation logic into target functions at runtime, enabling function call
monitoring without modifying the original source code.
"""

import importlib
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
                - condition: str, optional condition expression
                - times: int, max observations (-1 for infinite)

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

    def _generate_watch_id(self) -> str:
        """Generate unique watch ID."""
        return f"watch_{uuid.uuid4().hex[:8]}"

    def _resolve_target(self, pattern: str) -> Optional[tuple]:
        """
        Resolve pattern to (function, parent_object, attr_name).

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

        Args:
            func: Original function to wrap
            watch_id: Unique watch identifier
            config: Watch configuration

        Returns:
            Wrapper function
        """
        depth = config.get("depth", 2)
        condition = config.get("condition")
        times_limit = config.get("times", -1)

        safe_evaluator = None
        if condition:
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
                safe_evaluator.parse(condition)
            except SyntaxError as e:
                raise ValueError(f"Invalid condition expression: {e}")
            except Exception as e:
                raise ValueError(f"Condition validation failed: {e}")

        # Reference to self for use in wrapper
        injector = self

        @wraps(func)
        def wrapper(*args, **kwargs):
            # Check times limit
            with injector._lock:
                info = injector.instrumented.get(watch_id)
                if info is None:
                    # Watch was removed, call original
                    return func(*args, **kwargs)

                if times_limit > 0 and info["count"] >= times_limit:
                    # Limit reached, call original without observation
                    return func(*args, **kwargs)

            if safe_evaluator:
                try:
                    local_vars = {"params": args, "kwargs": kwargs}
                    safe_evaluator.names = local_vars
                    if not safe_evaluator.eval(condition):
                        return func(*args, **kwargs)
                except Exception:
                    return func(*args, **kwargs)

            # Capture timing
            start_time = time.perf_counter()

            success = True
            error_msg = None
            result = None

            try:
                result = func(*args, **kwargs)
            except Exception as e:
                success = False
                error_msg = f"{type(e).__name__}: {str(e)}"
                raise
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Update count
                with injector._lock:
                    info = injector.instrumented.get(watch_id)
                    if info:
                        info["count"] += 1

                # Build observation
                observation = {
                    "watch_id": watch_id,
                    "timestamp": time.time(),
                    "func_name": f"{func.__module__}.{func.__qualname__}",
                    "args": injector._format_value(args, depth),
                    "kwargs": injector._format_value(kwargs, depth),
                    "result": injector._format_value(result, depth)
                    if success
                    else None,
                    "success": success,
                    "error": error_msg,
                    "duration_ms": round(duration_ms, 3),
                    "thread_id": threading.get_ident(),
                    "thread_name": threading.current_thread().name,
                }

                # Send to agent
                try:
                    injector.agent._send_observation(observation)
                except Exception:
                    pass  # Don't let observation failure affect the function

            return result

        return wrapper

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
