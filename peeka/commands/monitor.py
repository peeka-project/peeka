"""
Monitor Command - Statistics collection for monitored functions

This command tracks performance metrics (call count, success/fail rate,
response time statistics) for injected functions with periodic output.
"""

from functools import wraps
import threading
import uuid
from typing import Any, ClassVar, Dict, List, Set, TYPE_CHECKING, Tuple, cast

from peeka.commands.base import BaseCommand
from peeka.core.monitor import MonitorManager
from peeka.core.probes import ProbeContext
from peeka.core.runtime import primitives as _rpl

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class MonitorCommand(BaseCommand):
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
        super().__init__()
        self.agent = agent
        self.manager = MonitorManager()
        self._monitors: Dict[str, Dict[str, Any]] = {}
        self._lock = _rpl.allocate_lock()

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

    def _start_monitor(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start monitoring a function pattern."""
        self.validate_params(params, ["pattern"])

        pattern = params["pattern"]
        cycle = params.get("cycle", 60)
        cycles = params.get("cycles", -1)

        # Resolve target function
        target_info = self._resolve_target(pattern)
        if target_info is None:
            return {"status": "error", "error": f"Cannot find target: {pattern}"}

        target_func, parent_obj, attr_name = target_info  # pyright: ignore[reportGeneralTypeIssues]

        alias_bindings: List[Dict[str, Any]] = []
        injector = getattr(self.agent, "injector", None)
        find_aliases = getattr(injector, "_find_module_aliases", None)
        if callable(find_aliases):
            alias_bindings = cast(
                List[Dict[str, Any]], find_aliases(target_func, parent_obj, attr_name)
            )

        watch_id = f"monitor_{uuid.uuid4().hex[:8]}"

        wrapper = self._create_monitor_wrapper(target_func, watch_id)
        owned_root_original = self._known_peeka_root_for_wrapper(target_func)

        # Start monitoring
        self.manager.start_monitor(watch_id)

        with self._lock:
            # Store monitor info
            self._monitors[watch_id] = {
                "pattern": pattern,
                "original": target_func,
                "owned_root_original": owned_root_original,
                "wrapper": wrapper,
                "parent": parent_obj,
                "attr_name": attr_name,
                "aliases": alias_bindings,
                "cycle": cycle,
                "cycles": cycles,
                "cycle_count": 0,
                "client_session_id": params.get("client_session_id"),
                "job_id": params.get("job_id"),
                "stop_event": None,
                "timer_thread": None,
            }

            self._replace_function(parent_obj, attr_name, wrapper)  # type: ignore[arg-type]
            for alias in alias_bindings:
                try:
                    setattr(alias["parent"], alias["attr_name"], wrapper)
                except Exception:
                    pass

            # Start periodic output timer
            stop_event = threading.Event()
            timer_thread = threading.Thread(
                target=self._periodic_output_loop,
                args=(watch_id, cycle, cycles, stop_event),
                name=f"peeka-monitor-{watch_id}",
                daemon=True,
            )
            timer_thread.start()

            self._monitors[watch_id]["stop_event"] = stop_event
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
        """Return root original when target_func is a live Peeka injector wrapper."""
        injector = getattr(self.agent, "injector", None)
        instrumented = getattr(injector, "instrumented", {})
        if not isinstance(instrumented, dict):
            return None

        for active_probe in instrumented.values():
            if active_probe.get("wrapper") is target_func:
                return active_probe.get("root_original", active_probe.get("original"))

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

    def _periodic_output_loop(
        self, watch_id: str, cycle: int, cycles: int, stop_event: threading.Event
    ) -> None:
        """Periodically output statistics."""
        if not self._supports_probe_instrumentation():
            self._periodic_output_loop_legacy(watch_id, cycle, cycles, stop_event)
            return

        monitor_info = self._monitors.get(watch_id)
        pattern = None
        client_session_id = None
        job_id = None
        if monitor_info is not None:
            pattern = monitor_info.get("pattern")
            client_session_id = monitor_info.get("client_session_id")
            job_id = monitor_info.get("job_id")

        probe_config = {"cycle": cycle, "cycles": cycles}
        cycle_count = 0

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
                                if current_stop_event:
                                    current_stop_event.set()
                        break
            finally:
                self.agent.untrack_probe_context(watch_id)

    def _periodic_output_loop_legacy(
        self, watch_id: str, cycle: int, cycles: int, stop_event: threading.Event
    ) -> None:
        """Legacy best-effort monitor loop for agents without ProbeRegistry."""
        cycle_count = 0

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
                        if current_stop_event:
                            current_stop_event.set()
                break

    def _stop_monitor(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Stop monitoring and return final statistics."""
        watch_id = params.get("monitor_id") or params.get("watch_id")

        if not watch_id:
            return {"status": "error", "error": "Missing watch_id"}

        with self._lock:
            if watch_id not in self._monitors:
                return {"status": "error", "error": f"Monitor not found: {watch_id}"}

            monitor_info = self._monitors.pop(watch_id)

            # Signal stop to timer thread
            stop_event = monitor_info.get("stop_event")
            if stop_event:
                stop_event.set()

            # Wait for timer thread to finish (short timeout)
            timer_thread = monitor_info.get("timer_thread")
            if timer_thread:
                timer_thread.join(timeout=2)

            for active_monitor in self._monitors.values():
                if active_monitor.get("original") is monitor_info["wrapper"]:
                    active_monitor["original"] = monitor_info["original"]
                    if active_monitor.get("owned_root_original") is None:
                        active_monitor["owned_root_original"] = monitor_info.get(
                            "owned_root_original"
                        )
                elif active_monitor.get("owned_root_original") is monitor_info[
                    "wrapper"
                ]:
                    active_monitor["owned_root_original"] = (
                        monitor_info.get("owned_root_original")
                        or monitor_info["original"]
                    )

            injector = getattr(self.agent, "injector", None)
            instrumented = getattr(injector, "instrumented", {})
            if isinstance(instrumented, dict):
                for active_probe in instrumented.values():
                    for key in ("original", "previous_wrapper", "root_original"):
                        if active_probe.get(key) is monitor_info["wrapper"]:
                            if (
                                key == "root_original"
                                and monitor_info["original"] is active_probe.get("wrapper")
                            ):
                                continue
                            if key == "root_original":
                                active_probe[key] = (
                                    monitor_info.get("owned_root_original")
                                    or monitor_info["original"]
                                )
                            else:
                                active_probe[key] = monitor_info["original"]

            active_monitor_wrappers = set()
            for active_monitor in self._monitors.values():
                active_monitor_wrappers.add(active_monitor.get("wrapper"))

            active_injector_wrappers = set()
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
                replacement = monitor_info["original"]
                owned_root_original = monitor_info.get("owned_root_original")
                if replacement not in all_live_wrappers and owned_root_original is not None:
                    replacement = owned_root_original

            try:
                current = getattr(monitor_info["parent"], monitor_info["attr_name"])
                if current is monitor_info["wrapper"]:
                    self._replace_function(
                        monitor_info["parent"],
                        monitor_info["attr_name"],
                        replacement,
                    )
            except Exception:
                pass

            for alias in monitor_info.get("aliases", []):
                try:
                    if getattr(alias["parent"], alias["attr_name"], None) is monitor_info["wrapper"]:
                        setattr(alias["parent"], alias["attr_name"], replacement)
                except Exception:
                    pass

        # Get final statistics
        final_stats = self.manager.stop_monitor(watch_id)
        if final_stats is None:
            final_stats = {}

        return {
            "status": "success",
            "watch_id": watch_id,
            "final_stats": final_stats,
        }

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
            target_info = cast(
                Tuple[Any, Any, Any], injector_resolve(pattern)
            )
            if target_info is not None:
                return target_info

        import importlib
        import sys

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

    def _replace_function(self, parent, attr_name, new_func) -> None:
        """Replace a function/method on its parent object."""
        setattr(parent, attr_name, new_func)
