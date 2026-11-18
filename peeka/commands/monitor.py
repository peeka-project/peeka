"""
Monitor Command - Statistics collection for monitored functions

This command tracks performance metrics (call count, success/fail rate,
response time statistics) for injected functions with periodic output.
"""

import contextlib
import fnmatch
from functools import wraps
import logging
import uuid
import weakref
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Iterator,
    List,
    Optional,
    Set,
    TYPE_CHECKING,
    Tuple,
    cast,
)

from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand
from peeka.core.instrumentation.registry import (
    commit_slot_chain_entry,
    prepare_slot_chain,
    remove_chain_entry,
    retarget_wrapper_call,
    wrapper_call_target,
)
from peeka.core.instrumentation.target import (
    find_module_aliases,
    read_target_binding,
    replace_aliases,
    replace_function,
    resolve_target,
    restore_aliases_matching,
)
from peeka.core.monitor import MonitorManager
from peeka.core.probes import ProbeContext
from peeka.core.runtime import primitives as _rpl

_logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class _NativeThreadHandle:
    """Small handle around RPL native threads with Thread-like test hooks."""

    def __init__(self, target: Callable[..., None], args: Tuple[Any, ...], name: str):
        self._done_event = _rpl.create_event()
        self.name = name
        self.daemon = True
        self.ident = _rpl.start_thread(self._run, args=(target, args), name=name)

    def _run(self, target: Callable[..., None], args: Tuple[Any, ...]) -> None:
        try:
            target(*args)
        finally:
            self._done_event.set()

    def is_alive(self) -> bool:
        return not self._done_event.is_set()

    def join(self, timeout: Optional[float] = None) -> None:
        self._done_event.wait(timeout=timeout)


class MonitorCommand(ResourceOwningCommand):
    is_resource_owner: bool = True
    cleanup_scope: CleanupScope = CleanupScope.DETACH_AND_RESET

    """
    Monitor command - collects performance statistics for functions.

    Statistics include:
    - total: Total number of calls
    - success: Number of successful calls
    - fail: Number of failed calls
    - fail_rate: Failure rate (fail/total)
    - rt_avg: Average response time in milliseconds
    - rt_min: Minimum response time in milliseconds
    - rt_max: Maximum response time in milliseconds

    Parameters for start action:
    - pattern: Function pattern (e.g., "module.Class.method")
    - cycle: Output interval in seconds (default: 60)
    - cycles: Number of cycles to run (-1 for unlimited, default: -1)

    Actions:
    - start: Start monitoring a function
    - stop: Stop monitoring and return final statistics
    - status: Get list of active monitors

    Example:
        monitor start module.func --cycle 10 --cycles 5
        monitor stop <watch_id>
        monitor status
    """

    category: ClassVar[str] = "probe"
    allows_concurrent: ClassVar[bool] = False

    def __init__(self, agent: "PeekaAgent"):
        super().__init__(agent)
        self.agent = agent
        self.manager = MonitorManager()
        self._monitors: Dict[str, Dict[str, Any]] = {}
        self._lock = _rpl.allocate_lock()
        self._register_injector_listener()

    def _register_injector_listener(self) -> None:
        """Follow injector wrapper removals so monitors never call stale wrappers."""
        injector = getattr(self.agent, "injector", None)
        add_listener = getattr(injector, "add_wrapper_removed_listener", None)
        if not callable(add_listener):
            return
        weak_handler = weakref.WeakMethod(self._on_injector_wrapper_removed)

        def listener(removed_wrapper: Any, bypass_target: Any) -> None:
            handler = weak_handler()
            if handler is not None:
                handler(removed_wrapper, bypass_target)

        add_listener(listener)

    def _on_injector_wrapper_removed(
        self, removed_wrapper: Any, bypass_target: Any
    ) -> None:
        """Splice a removed injector wrapper out of active monitor call paths."""
        with self._lock:
            for active_monitor in self._monitors.values():
                monitor_wrapper = active_monitor.get("wrapper")
                if (
                    active_monitor.get("original") is removed_wrapper
                    or wrapper_call_target(monitor_wrapper) is removed_wrapper
                ):
                    retarget_wrapper_call(monitor_wrapper, removed_wrapper, bypass_target)
                    active_monitor["original"] = bypass_target

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = params.get("action", "start")

            if action == "start":
                return self._start_monitor(params)
            elif action == "stop":
                return self._stop_monitor(params)
            elif action == "status":
                return self._get_status(params)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _supports_probe_instrumentation(self) -> bool:
        return hasattr(self.agent, "probe_registry") and hasattr(self.agent, "track_probe_context")

    @contextlib.contextmanager
    def _injector_lock(self) -> Iterator[None]:
        """Hold the injector lock (if any) while reading/mutating ``instrumented``.

        Lock ordering: the injector lock must always be acquired BEFORE
        ``self._lock``. The injector invokes wrapper-removed listeners (which
        take ``self._lock``) outside its own lock, so this order never inverts.
        """
        injector_lock = getattr(getattr(self.agent, "injector", None), "_lock", None)
        if (
            injector_lock is None
            or not hasattr(injector_lock, "__enter__")
            or not hasattr(injector_lock, "__exit__")
        ):
            yield
            return
        with injector_lock:
            yield

    def _chain_owner(self) -> Any:
        """Return the shared slot-chain owner (injector when available, else self)."""
        injector = getattr(self.agent, "injector", None)
        if (
            injector is not None
            and hasattr(injector, "instrumented")
            and hasattr(injector, "_lock")
        ):
            return injector
        return self

    def _start_monitor(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start monitoring a function pattern."""
        self.validate_params(params, ["pattern"])

        pattern = params["pattern"]
        cycle = params.get("cycle", 60)
        cycles = params.get("cycles", -1)

        # Resolve target outside locks to avoid import-time lock reentrancy.
        target_info = self._resolve_target(pattern)
        if target_info is None:
            return {"status": "error", "error": f"Cannot find target: {pattern}"}

        _, parent_obj, attr_name = target_info  # pyright: ignore[reportGeneralTypeIssues]
        watch_id = f"monitor_{uuid.uuid4().hex[:8]}"

        with self._injector_lock(), self._lock:
            target_func = read_target_binding(parent_obj, attr_name)
            if target_func is None:
                return {"status": "error", "error": f"Cannot find target: {pattern}"}

            chain_owner = self._chain_owner()
            chain = prepare_slot_chain(chain_owner, parent_obj, attr_name, target_func)
            descriptor_kind = chain["root_descriptor_kind"]
            owned_root_original = chain["root_original"] if chain["entries"] else None

            injector = getattr(self.agent, "injector", None)
            find_aliases = getattr(injector, "_find_module_aliases", None)
            if callable(find_aliases):
                alias_bindings = cast(
                    List[Dict[str, Any]], find_aliases(target_func, parent_obj, attr_name)
                )
            else:
                alias_bindings = find_module_aliases(target_func, parent_obj, attr_name)

            wrapper = self._create_monitor_wrapper(target_func, watch_id)
            self._replace_function(
                parent_obj,
                attr_name,
                wrapper,
                descriptor_kind=descriptor_kind,
            )

            commit_slot_chain_entry(
                chain_owner, chain, watch_id, "monitor", wrapper, alias_bindings
            )
            self.manager.start_monitor(watch_id)

            stop_event = _rpl.create_event()
            self._monitors[watch_id] = {
                "pattern": pattern,
                "original": target_func,
                "owned_root_original": owned_root_original,
                "descriptor_kind": descriptor_kind,
                "wrapper": wrapper,
                "parent": parent_obj,
                "attr_name": attr_name,
                "aliases": alias_bindings,
                "cycle": cycle,
                "cycles": cycles,
                "cycle_count": 0,
                "client_session_id": params.get("client_session_id"),
                "job_id": params.get("job_id"),
                "stop_event": stop_event,
                "timer_thread": None,
                "_chain_owner": chain_owner,
                "_chain": chain,
            }

            replace_aliases(alias_bindings, wrapper)

            # Start periodic output timer (native RPL primitives so the timer
            # never blocks on gevent/eventlet-patched threading objects).
            timer_thread = _NativeThreadHandle(
                self._periodic_output_loop,
                (watch_id, cycle, cycles, stop_event),
                name=f"peeka-monitor-{watch_id}",
            )
            self._monitors[watch_id]["timer_thread"] = timer_thread

        return {
            "status": "success",
            "watch_id": watch_id,
            "monitor_id": watch_id,
            "pattern": pattern,
            "cycle": cycle,
            "cycles": cycles,
        }

    def _create_monitor_wrapper(self, func, watch_id: str):
        """Create lightweight wrapper that only records statistics."""
        manager = self.manager

        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = _rpl.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (_rpl.perf_counter() - start_time) * 1000
                manager.record_call(watch_id, success=True, duration_ms=duration_ms)
                return result
            except Exception:
                duration_ms = (_rpl.perf_counter() - start_time) * 1000
                manager.record_call(watch_id, success=False, duration_ms=duration_ms)
                raise

        return wrapper

    def _known_peeka_root_for_wrapper(self, target_func: Any) -> Any:
        """Return root original when target_func is a live Peeka injector wrapper.

        Must be called without ``self._lock`` held (acquires the injector lock
        first, then ``self._lock``).
        """
        injector = getattr(self.agent, "injector", None)
        with self._injector_lock():
            instrumented = getattr(injector, "instrumented", {})
            if not isinstance(instrumented, dict):
                return None

            for active_probe in instrumented.values():
                if active_probe.get("wrapper") is target_func:
                    return active_probe.get(
                        "root_original", active_probe.get("original")
                    )

            with self._lock:
                for active_monitor in self._monitors.values():
                    if active_monitor.get("wrapper") is target_func:
                        return active_monitor.get(
                            "owned_root_original",
                            active_monitor.get("original"),
                        )

        return None

    def _nearest_lower_live_wrapper(
        self, monitor_wrapper: Any, all_live_wrappers: Set[Any]
    ) -> Any:
        """Return the nearest still-live Peeka wrapper below monitor_wrapper, or None."""
        candidate = getattr(monitor_wrapper, "__wrapped__", None)
        visited: Set[int] = set()
        for _ in range(32):
            if candidate is None:
                return None
            candidate_id = id(candidate)
            if candidate_id in visited:
                return None
            visited.add(candidate_id)
            if candidate in all_live_wrappers:
                return candidate
            next_candidate = getattr(candidate, "__wrapped__", None)
            if next_candidate is candidate:
                return None
            candidate = next_candidate
        return None

    def _retarget_wrapper_func(
        self, wrapper: Any, old_target: Any, new_target: Any
    ) -> None:
        """Retarget a live Peeka wrapper that directly called a removed wrapper."""
        retarget_wrapper_call(wrapper, old_target, new_target)

    def _auto_stop_expired_monitor(self, watch_id: str) -> None:
        """Uninject a monitor automatically once its cycles limit expires."""
        try:
            result = self._stop_monitor({"monitor_id": watch_id})
            if result.get("status") != "success":
                _logger.debug(
                    "[peeka Monitor] auto-stop after cycles limit for %s: %s",
                    watch_id,
                    result.get("error"),
                )
        except Exception:
            _logger.debug(
                "[peeka Monitor] auto-stop failed for %s",
                watch_id,
                exc_info=True,
            )

    def _retarget_after_monitor_removal(
        self,
        above_entry: Dict[str, Any],
        old_wrapper: Any,
        new_target: Any,
        root_original: Any,
    ) -> None:
        """Keep metadata of the probe above a removed monitor in sync."""
        owner = above_entry.get("owner")
        probe_id = above_entry["probe_id"]
        if owner == "monitor":
            above_mon = self._monitors.get(probe_id)
            if above_mon is None:
                return
            if above_mon.get("original") is old_wrapper:
                above_mon["original"] = new_target
            if above_mon.get("owned_root_original") is old_wrapper:
                above_mon["owned_root_original"] = root_original
            return

        if owner == "injector":
            injector = getattr(self.agent, "injector", None)
            instrumented = getattr(injector, "instrumented", None)
            if not isinstance(instrumented, dict):
                return
            above_probe = instrumented.get(probe_id)
            if above_probe is None:
                return
            for key in ("original", "previous_wrapper"):
                if above_probe.get(key) is old_wrapper:
                    above_probe[key] = new_target

    def _periodic_output_loop(
        self, watch_id: str, cycle: int, cycles: int, stop_event: Any
    ) -> None:
        """Periodically output statistics."""
        if not self._supports_probe_instrumentation():
            self._periodic_output_loop_legacy(watch_id, cycle, cycles, stop_event)
            return

        with self._lock:
            monitor_info = self._monitors.get(watch_id)
            pattern = monitor_info.get("pattern") if monitor_info is not None else None
            client_session_id = (
                monitor_info.get("client_session_id")
                if monitor_info is not None
                else None
            )
            job_id = monitor_info.get("job_id") if monitor_info is not None else None

        probe_config = {"cycle": cycle, "cycles": cycles}
        cycle_count = 0
        cycles_exhausted = False

        with ProbeContext(
            self.agent.probe_registry,
            target_id=self.agent._target_id_for_jobs(),
            client_session_id=client_session_id,
            job_id=job_id,
            type="monitor",
            pattern=pattern,
            config=probe_config,
        ) as probe:
            self.agent.track_probe_context(watch_id, probe, "monitor")
            try:
                while True:
                    if probe.should_stop():
                        break

                    if stop_event.wait(timeout=cycle):
                        break

                    stats = self.manager.get_stats(watch_id)
                    if stats is not None:
                        cycle_count += 1
                        stats["count"] = stats.get("total", 0)
                        stats["call_count"] = stats.get("total", 0)
                        stats["cycle"] = cycle_count
                        stats["watch_id"] = watch_id
                        stats["monitor_id"] = watch_id

                        event = probe.record_event(stats)
                        if event is not None:
                            stats["event_id"] = event.event_id
                            stats["probe_id"] = event.probe_id

                        self.agent._send_observation(stats)

                        with self._lock:
                            if watch_id in self._monitors:
                                self._monitors[watch_id]["cycle_count"] = cycle_count

                    if cycles > 0 and cycle_count >= cycles:
                        with self._lock:
                            if watch_id in self._monitors:
                                current_stop_event = self._monitors[watch_id]["stop_event"]
                                if current_stop_event and not current_stop_event.is_set():
                                    current_stop_event.set()
                                    cycles_exhausted = True
                        break
            finally:
                self.agent.untrack_probe_context(watch_id)

        if cycles_exhausted:
            self._auto_stop_expired_monitor(watch_id)

    def _periodic_output_loop_legacy(
        self, watch_id: str, cycle: int, cycles: int, stop_event: Any
    ) -> None:
        """Legacy best-effort monitor loop for agents without ProbeRegistry."""
        cycle_count = 0
        cycles_exhausted = False

        while True:
            if stop_event.wait(timeout=cycle):
                break

            stats = self.manager.get_stats(watch_id)
            if stats is not None:
                cycle_count += 1
                stats["count"] = stats.get("total", 0)
                stats["call_count"] = stats.get("total", 0)
                stats["cycle"] = cycle_count
                stats["watch_id"] = watch_id
                stats["monitor_id"] = watch_id

                try:
                    self.agent._send_observation(stats)
                except Exception:
                    pass

                with self._lock:
                    if watch_id in self._monitors:
                        self._monitors[watch_id]["cycle_count"] = cycle_count

            if cycles > 0 and cycle_count >= cycles:
                with self._lock:
                    if watch_id in self._monitors:
                        current_stop_event = self._monitors[watch_id]["stop_event"]
                        if current_stop_event and not current_stop_event.is_set():
                            current_stop_event.set()
                            cycles_exhausted = True
                break

        if cycles_exhausted:
            self._auto_stop_expired_monitor(watch_id)

    def _stop_monitor(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Stop monitoring and return final statistics."""
        watch_id = params.get("monitor_id") or params.get("watch_id")

        if not watch_id:
            return {"status": "error", "error": "Missing watch_id"}

        with self._lock:
            monitor_info = self._monitors.get(watch_id)
            if monitor_info is None:
                return {"status": "error", "error": f"Monitor not found: {watch_id}"}
            stop_event = monitor_info.get("stop_event")
            timer_thread = monitor_info.get("timer_thread")
            if stop_event:
                stop_event.set()

        is_self_thread = (
            timer_thread is not None
            and getattr(timer_thread, "ident", None) == _rpl.get_ident()
        )
        timer_thread_alive = False
        if timer_thread and not is_self_thread:
            timer_thread.join(timeout=2)
            timer_thread_alive = timer_thread.is_alive()

        with self._injector_lock(), self._lock:
            if self._monitors.get(watch_id) is not monitor_info:
                return {"status": "error", "error": f"Monitor not found: {watch_id}"}

            chain = monitor_info.get("_chain")
            chain_owner = monitor_info.get("_chain_owner")
            if chain is not None and chain_owner is not None:
                root_original = chain["root_original"]
                try:
                    remove_chain_entry(
                        chain_owner,
                        chain,
                        watch_id,
                        on_retarget=lambda above, old_w, new_t: (
                            self._retarget_after_monitor_removal(
                                above, old_w, new_t, root_original
                            )
                        ),
                    )
                except Exception as exc:
                    return {"status": "error", "error": str(exc)}
            else:
                injector = getattr(self.agent, "injector", None)
                instrumented = getattr(injector, "instrumented", {})

                active_monitor_wrappers: Set[Any] = set()
                for mid, active_monitor in self._monitors.items():
                    if mid != watch_id:
                        active_monitor_wrappers.add(active_monitor.get("wrapper"))

                active_injector_wrappers: Set[Any] = set()
                if isinstance(instrumented, dict):
                    for active_probe in instrumented.values():
                        active_injector_wrappers.add(active_probe.get("wrapper"))

                all_live_wrappers = active_injector_wrappers | active_monitor_wrappers

                lower_live = self._nearest_lower_live_wrapper(
                    monitor_info["wrapper"], all_live_wrappers
                )
                if lower_live is not None:
                    replacement = lower_live
                else:
                    original = monitor_info["original"]
                    if original in all_live_wrappers:
                        replacement = original
                    else:
                        owned_root_original = monitor_info.get("owned_root_original")
                        if (
                            owned_root_original is not None
                            and owned_root_original not in all_live_wrappers
                        ):
                            replacement = owned_root_original
                        else:
                            replacement = original

                current = read_target_binding(
                    monitor_info["parent"], monitor_info["attr_name"]
                )
                if current is monitor_info["wrapper"]:
                    try:
                        self._replace_function(
                            monitor_info["parent"],
                            monitor_info["attr_name"],
                            replacement,
                            descriptor_kind=monitor_info.get("descriptor_kind"),
                        )
                    except Exception as exc:
                        return {"status": "error", "error": str(exc)}

                for mid, active_monitor in self._monitors.items():
                    if mid == watch_id:
                        continue
                    if active_monitor.get("original") is monitor_info["wrapper"]:
                        self._retarget_wrapper_func(
                            active_monitor.get("wrapper"),
                            monitor_info["wrapper"],
                            replacement,
                        )
                        active_monitor["original"] = replacement
                        if active_monitor.get("owned_root_original") is None:
                            active_monitor["owned_root_original"] = monitor_info.get(
                                "owned_root_original"
                            )
                    if (
                        active_monitor.get("owned_root_original")
                        is monitor_info["wrapper"]
                    ):
                        active_monitor["owned_root_original"] = (
                            monitor_info.get("owned_root_original")
                            or monitor_info["original"]
                        )

                if isinstance(instrumented, dict):
                    for active_probe in instrumented.values():
                        for key in ("original", "previous_wrapper", "root_original"):
                            if active_probe.get(key) is monitor_info["wrapper"]:
                                if (
                                    key == "root_original"
                                    and monitor_info["original"]
                                    is active_probe.get("wrapper")
                                ):
                                    continue
                                if key == "root_original":
                                    active_probe[key] = (
                                        monitor_info.get("owned_root_original")
                                        or replacement
                                    )
                                else:
                                    self._retarget_wrapper_func(
                                        active_probe.get("wrapper"),
                                        monitor_info["wrapper"],
                                        replacement,
                                    )
                                    active_probe[key] = replacement

                restore_aliases_matching(
                    monitor_info.get("aliases", []),
                    (monitor_info.get("wrapper"),),
                    replacement,
                )

            self._monitors.pop(watch_id, None)

        # Get final statistics
        if timer_thread_alive:
            return {"status": "error", "error": "timer thread still alive after join timeout"}

        final_stats = self.manager.stop_monitor(watch_id)
        if final_stats is None:
            final_stats = {}

        return {
            "status": "success",
            "watch_id": watch_id,
            "final_stats": final_stats,
        }

    def stop_active_resources(
        self, pattern: Optional[str], reason: str
    ) -> Dict[str, Any]:
        """Stop active monitor resources, optionally filtered by pattern."""
        logger = logging.getLogger(__name__)
        with self._lock:
            monitor_ids = list(self._monitors.keys())

        stopped: List[str] = []
        errors: List[Dict[str, Any]] = []
        skipped: List[str] = []

        for monitor_id in monitor_ids:
            try:
                with self._lock:
                    monitor_info = self._monitors.get(monitor_id)

                if monitor_info is None:
                    skipped.append(monitor_id)
                    continue

                monitor_pattern = monitor_info.get("pattern", "")
                if pattern is not None and not fnmatch.fnmatch(monitor_pattern, pattern):
                    skipped.append(monitor_id)
                    continue

                result = self._stop_monitor({"monitor_id": monitor_id})
                if result.get("status") == "success":
                    stopped.append(monitor_id)
                else:
                    error_message = cast(str, result.get("error", "Unknown error"))
                    with self._lock:
                        still_tracked = monitor_id in self._monitors
                    if not still_tracked and "Monitor not found" in error_message:
                        skipped.append(monitor_id)
                        continue
                    logger.error(
                        "[peeka Monitor] stop_active_resources failed for %s (%s): %s",
                        monitor_id,
                        reason,
                        error_message,
                    )
                    errors.append({"monitor_id": monitor_id, "error": error_message})
            except Exception as exc:
                logger.error(
                    "[peeka Monitor] stop_active_resources failed for %s (%s)",
                    monitor_id,
                    reason,
                    exc_info=True,
                )
                errors.append({"monitor_id": monitor_id, "error": str(exc)})

        return {"stopped": stopped, "errors": errors, "skipped": skipped}

    def list_active_resources(self) -> Dict[str, Any]:
        """List active monitor resources."""
        with self._lock:
            active = [
                {"watch_pattern": monitor.get("pattern"), "alias": monitor_id}
                for monitor_id, monitor in self._monitors.items()
            ]

        return {"active": active}

    def _get_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get list of active monitors."""
        watch_id = params.get("monitor_id") or params.get("watch_id")

        if watch_id:
            with self._lock:
                if watch_id not in self._monitors:
                    return {
                        "status": "error",
                        "error": f"Monitor not found: {watch_id}",
                    }

                monitor = self._monitors[watch_id]
                stats = self.manager.get_stats(watch_id)

                return {
                    "status": "success",
                    "watch_id": watch_id,
                    "monitor_id": watch_id,
                    "pattern": monitor["pattern"],
                    "cycle": monitor["cycle"],
                    "cycles": monitor["cycles"],
                    "cycle_count": monitor["cycle_count"],
                    "stats": stats,
                }

        with self._lock:
            monitors_list = {}
            for wid, monitor in self._monitors.items():
                stats = self.manager.get_stats(wid)
                monitors_list[wid] = {
                    "pattern": monitor["pattern"],
                    "cycle": monitor["cycle"],
                    "cycles": monitor["cycles"],
                    "cycle_count": monitor["cycle_count"],
                    "stats": stats,
                }

        return {
            "status": "success",
            "monitors": monitors_list,
        }

    def _resolve_target(self, pattern: str):
        """
        Resolve pattern to (function, parent_object, attr_name).

        Args:
            pattern: Dotted path like 'module.Class.method' or 'module.function'

        Returns:
            Tuple of (target_func, parent_obj, attr_name) or None if not found
        """
        injector = getattr(self.agent, "injector", None)
        injector_resolve = getattr(injector, "_resolve_target", None)
        if callable(injector_resolve):
            return cast(Optional[Tuple[Any, Any, Any]], injector_resolve(pattern))

        return resolve_target(pattern)

    def _replace_function(
        self,
        parent: Any,
        attr_name: str,
        new_func: Any,
        descriptor_kind: Optional[str] = None,
    ) -> None:
        """Replace a function/method on its parent object."""
        replace_function(parent, attr_name, new_func, descriptor_kind=descriptor_kind)
