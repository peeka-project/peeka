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

    def _install_probe(
        self,
        pattern: str,
        watch_id: str,
        raw_config: Dict[str, Any],
        build_wrapper: Callable[[Callable[..., Any], Dict[str, Any]], Callable[..., Any]],
        extra_config: Optional[Callable[[Callable[..., Any], Dict[str, Any]], None]] = None,
        extra_info: Optional[Callable[[Callable[..., Any], Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> str:
        """Resolve target outside the lock, then verify binding and commit under lock."""
        target_info = self._resolve_target(pattern)
        if target_info is None:
            raise ValueError(f"Cannot find target: {pattern}")

        _, parent_obj, attr_name = target_info

        with self._lock:
            target_func = self._read_target_binding(parent_obj, attr_name)
            if target_func is None:
                raise ValueError(f"Cannot find target: {pattern}")

            chain = self._prepare_slot_chain(parent_obj, attr_name, target_func)
            descriptor_kind = chain["root_descriptor_kind"]
            raw_descriptor = chain["root_raw_descriptor"]
            defined_in_dict = chain["root_defined_in_dict"]
            alias_bindings = self._find_module_aliases(
                target_func, parent_obj, attr_name
            )

            is_instance_method = (
                inspect.isclass(parent_obj) and descriptor_kind != "staticmethod"
            )
            config = dict(raw_config)
            config["_is_instance_method"] = is_instance_method
            if extra_config is not None:
                extra_config(target_func, config)

            wrapper = build_wrapper(target_func, config)
            stored_config = {
                key: value for key, value in config.items() if key != "_probe_context"
            }

            group_key: Tuple[int, str] = chain["slot_key"]
            previous_wrapper = target_func if chain["entries"] else None

            info: Dict[str, Any] = {
                "descriptor_kind": descriptor_kind,
                "raw_descriptor": raw_descriptor,
                "defined_in_dict": defined_in_dict,
                "root_descriptor_kind": descriptor_kind,
                "root_raw_descriptor": raw_descriptor,
                "root_defined_in_dict": defined_in_dict,
                "pattern": pattern,
                "original": target_func,
                "wrapper": wrapper,
                "parent": parent_obj,
                "attr_name": attr_name,
                "config": stored_config,
                "count": 0,
                "times_limit": config.get("times", -1),
                "aliases": alias_bindings,
                "root_original": chain["root_original"],
                "previous_wrapper": previous_wrapper,
                "wrapper_group_key": group_key,
                "_chain": chain,
            }
            if extra_info is not None:
                info.update(extra_info(target_func, config))

            self._replace_function(
                parent_obj, attr_name, wrapper, descriptor_kind=descriptor_kind
            )
            self._commit_slot_chain_entry(
                chain, watch_id, "injector", wrapper, alias_bindings
            )
            self.instrumented[watch_id] = info
            self._replace_aliases(alias_bindings, wrapper)

            return watch_id

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
        watch_id = self._generate_watch_id()

        def _extra_info(target_func: Callable[..., Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
            extra: Dict[str, Any] = {
                "is_coroutine_function": inspect.iscoroutinefunction(target_func),
                "client_session_id": cfg.get("client_session_id"),
                "watch_group_key": (id(None), ""),  # placeholder overwritten below
            }
            session_id = extra["client_session_id"]
            liveness_hook = getattr(self.agent, "is_client_session_live", None)
            if callable(liveness_hook) and not liveness_hook(session_id):
                extra["_orphan_start"] = _time.monotonic()
            extra.pop("watch_group_key", None)
            return extra

        result_id = self._install_probe(
            pattern,
            watch_id,
            watch_config,
            lambda target_func, cfg: self._create_wrapper(target_func, watch_id, cfg),
            extra_info=_extra_info,
        )
        with self._lock:
            info = self.instrumented.get(result_id)
            if info is not None:
                info["watch_group_key"] = info["wrapper_group_key"]
        return result_id

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
                - condition_express: str, optional condition expression
                - times: int, max observations (-1 for infinite)
                - skip_builtin: bool, skip built-in and stdlib functions (default: True)
                - min_duration: float, minimum duration in ms for direct-callee
                  aggregation (default: 0)
            force_backend: Optional backend override. ``wrapper_only`` avoids
                sys.monitoring/sys.settrace and records only the traced root call.

        Trace output aggregates direct callees and their timings instead of
        enforcing a trace-depth limit.

        Returns:
            watch_id: Unique identifier for this trace

        Raises:
            ValueError: If target function cannot be found
        """
        watch_id = f"trace_{uuid.uuid4().hex[:8]}"

        def _extra_config(target_func: Callable[..., Any], cfg: Dict[str, Any]) -> None:
            cfg["_is_coroutine_function"] = inspect.iscoroutinefunction(target_func)
            if force_backend is not None:
                cfg["_force_backend"] = force_backend

        return self._install_probe(
            pattern,
            watch_id,
            trace_config,
            lambda target_func, cfg: self._create_trace_wrapper(
                target_func, watch_id, cfg
            ),
            extra_config=_extra_config,
        )

    def _create_wrapper(
        self, func: Callable[..., Any], watch_id: str, config: Dict[str, Any]
    ) -> Callable[..., Any]:
        """Create a wrapper function that captures watch call information."""
        from peeka.core.instrumentation.watch import WatchWrapperFactory

        return WatchWrapperFactory(self, func, watch_id, config).create()
