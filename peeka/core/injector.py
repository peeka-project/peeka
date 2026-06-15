"""
Decorator Injector - Runtime function instrumentation

This module provides the DecoratorInjector class that dynamically injects
observation logic into target functions at runtime, enabling function call
monitoring without modifying the original source code.
"""

# pyright: reportImportCycles=false

import inspect
import logging
import time as _time
import uuid
from typing import TYPE_CHECKING, Any, Callable, Dict, Optional, Tuple

from peeka.core.instrumentation.formatting import InjectorFormattingMixin
from peeka.core.instrumentation.registry import InjectorRegistryMixin
from peeka.core.instrumentation.target import InjectorTargetMixin
from peeka.core.instrumentation.trace import InjectorTraceMixin
from peeka.core.instrumentation.trace_backends import InjectorTraceBackendsMixin
from peeka.core.runtime import primitives as _rpl

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class DecoratorInjector(
    InjectorRegistryMixin,
    InjectorTargetMixin,
    InjectorTraceMixin,
    InjectorTraceBackendsMixin,
    InjectorFormattingMixin,
):
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
        self._lock = _rpl.allocate_lock()  # DOMAIN: native_thread (hot path, never gevent lock)
        if not hasattr(agent, "cleanup_orphan_watches"):
            setattr(agent, "cleanup_orphan_watches", self.cleanup_orphan_watches)

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
        alias_bindings = self._find_module_aliases(target_func, parent_obj, attr_name)
        is_coroutine_function = inspect.iscoroutinefunction(target_func)

        # Generate watch ID
        watch_id = self._generate_watch_id()

        # Detect if this is an instance method (parent is a class)
        is_instance_method = inspect.isclass(parent_obj)
        watch_config["_is_instance_method"] = is_instance_method

        # Create wrapper
        wrapper = self._create_wrapper(target_func, watch_id, watch_config)
        stored_config = {
            key: value for key, value in watch_config.items() if key != "_probe_context"
        }

        with self._lock:
            # Store original function info for restoration
            info = {
                "pattern": pattern,
                "original": target_func,
                "wrapper": wrapper,
                "parent": parent_obj,
                "attr_name": attr_name,
                "config": stored_config,
                "count": 0,
                "times_limit": watch_config.get("times", -1),
                "is_coroutine_function": is_coroutine_function,
                "aliases": alias_bindings,
                "client_session_id": watch_config.get("client_session_id"),
            }

            session_id = info.get("client_session_id")
            liveness_hook = getattr(self.agent, "is_client_session_live", None)
            if callable(liveness_hook) and not liveness_hook(session_id):
                info["_orphan_start"] = _time.monotonic()

            shared_group = self._get_active_wrapper_info(target_func)
            if shared_group is None:
                group_key: Tuple[int, str] = (id(parent_obj), str(attr_name))
                root_original = target_func
                previous_wrapper = None
            else:
                group_key = shared_group.get(
                    "wrapper_group_key", (id(parent_obj), str(attr_name))
                )
                root_original = shared_group.get(
                    "root_original", shared_group["original"]
                )
                previous_wrapper = target_func
            info.update(
                {
                    "root_original": root_original,
                    "previous_wrapper": previous_wrapper,
                    "wrapper_group_key": group_key,
                    "watch_group_key": group_key,
                }
            )

            self.instrumented[watch_id] = info

            # Replace the function
            self._replace_function(parent_obj, attr_name, wrapper)
            self._replace_aliases(alias_bindings, wrapper)

        return watch_id

    def _get_watch_wrapper_group(
        self, target_func: Callable[..., Any]
    ) -> Optional[Dict[str, Any]]:
        """Return active watch info when target_func is already a watch wrapper."""
        for watch_id, info in self.instrumented.items():
            if not watch_id.startswith("watch_"):
                continue
            if info.get("wrapper") is target_func:
                return info
        return None

    def _get_active_wrapper_info(
        self, target_func: Callable[..., Any]
    ) -> Optional[Dict[str, Any]]:
        """Return active probe info when target_func is already a probe wrapper."""
        for info in self.instrumented.values():
            if info.get("wrapper") is target_func:
                return info
        return None

    def inject_trace(
        self,
        pattern: str,
        trace_config: Dict[str, Any],
        force_backend: Optional[str] = None,
    ) -> str:
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
            force_backend: Optional backend override. ``wrapper_only`` avoids
                sys.monitoring/sys.settrace and records only the traced root call.

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
        alias_bindings = self._find_module_aliases(target_func, parent_obj, attr_name)

        # Generate watch ID
        watch_id = f"trace_{uuid.uuid4().hex[:8]}"

        # Detect if this is an instance method
        is_instance_method = inspect.isclass(parent_obj)
        trace_config["_is_instance_method"] = is_instance_method
        if force_backend is not None:
            trace_config["_force_backend"] = force_backend

        # Create trace wrapper
        wrapper = self._create_trace_wrapper(target_func, watch_id, trace_config)
        stored_config = {
            key: value for key, value in trace_config.items() if key != "_probe_context"
        }

        with self._lock:
            shared_group = self._get_active_wrapper_info(target_func)
            if shared_group is None:
                group_key = (id(parent_obj), str(attr_name))
                root_original = target_func
                previous_wrapper = None
            else:
                group_key = shared_group.get(
                    "wrapper_group_key", (id(parent_obj), str(attr_name))
                )
                root_original = shared_group.get(
                    "root_original", shared_group["original"]
                )
                previous_wrapper = target_func

            # Store original function info for restoration
            self.instrumented[watch_id] = {
                "pattern": pattern,
                "original": target_func,
                "wrapper": wrapper,
                "parent": parent_obj,
                "attr_name": attr_name,
                "config": stored_config,
                "count": 0,
                "times_limit": trace_config.get("times", -1),
                "root_original": root_original,
                "aliases": alias_bindings,
                "previous_wrapper": previous_wrapper,
                "wrapper_group_key": group_key,
            }

            # Replace the function
            self._replace_function(parent_obj, attr_name, wrapper)
            self._replace_aliases(alias_bindings, wrapper)

        return watch_id

    def _create_wrapper(
        self, func: Callable[..., Any], watch_id: str, config: Dict[str, Any]
    ) -> Callable[..., Any]:
        """Create a wrapper function that captures watch call information."""
        from peeka.core.instrumentation.watch import WatchWrapperFactory

        return WatchWrapperFactory(self, func, watch_id, config).create()
