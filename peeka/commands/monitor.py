"""
Monitor Command - Statistics collection for monitored functions

This command tracks performance metrics (call count, success/fail rate,
response time statistics) for injected functions with periodic output.
"""

import threading
import uuid
from typing import Any, Dict, TYPE_CHECKING

from peeka.commands.base import BaseCommand
from peeka.core.monitor import MonitorManager
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

        target_func, parent_obj, attr_name = target_info

        # Generate watch ID for monitor
        watch_id = f"monitor_{uuid.uuid4().hex[:8]}"

        # Create lightweight wrapper that only records stats
        wrapper = self._create_monitor_wrapper(target_func, watch_id)

        # Start monitoring
        self.manager.start_monitor(watch_id)

        with self._lock:
            # Store monitor info
            self._monitors[watch_id] = {
                "pattern": pattern,
                "original": target_func,
                "wrapper": wrapper,
                "parent": parent_obj,
                "attr_name": attr_name,
                "cycle": cycle,
                "cycles": cycles,
                "cycle_count": 0,
                "stop_event": None,
                "timer_thread": None,
            }

            # Replace the function
            self._replace_function(parent_obj, attr_name, wrapper)  # type: ignore[arg-type]

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
            "pattern": pattern,
            "cycle": cycle,
            "cycles": cycles,
        }

    def _create_monitor_wrapper(self, func, watch_id: str):
        """Create lightweight wrapper that only records statistics."""
        manager = self.manager

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

    def _periodic_output_loop(
        self, watch_id: str, cycle: int, cycles: int, stop_event: threading.Event
    ) -> None:
        """Periodically output statistics."""
        cycle_count = 0

        while True:
            # Wait for cycle interval (interruptible)
            if stop_event.wait(timeout=cycle):
                # Stop event was set, exit
                break

            # Get current statistics
            stats = self.manager.get_stats(watch_id)
            if stats is not None:
                cycle_count += 1

                # Add cycle information to stats
                stats["cycle"] = cycle_count
                stats["watch_id"] = watch_id

                # Send observation
                try:
                    self.agent._send_observation(stats)
                except Exception:
                    pass

                # Update monitor cycle count
                with self._lock:
                    if watch_id in self._monitors:
                        self._monitors[watch_id]["cycle_count"] = cycle_count

            # Check if we've reached cycle limit
            if cycles > 0 and cycle_count >= cycles:
                with self._lock:
                    if watch_id in self._monitors:
                        stop_event = self._monitors[watch_id]["stop_event"]
                        if stop_event:
                            stop_event.set()
                break

    def _stop_monitor(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Stop monitoring and return final statistics."""
        watch_id = params.get("watch_id")

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

            # Restore original function
            try:
                self._replace_function(
                    monitor_info["parent"],
                    monitor_info["attr_name"],
                    monitor_info["original"],
                )
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
        watch_id = params.get("watch_id")

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
