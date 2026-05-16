"""
Monitor Manager - Performance statistics collection

This module provides the MonitorManager class that collects performance
statistics for function calls including total calls, successes, failures,
and response time metrics (average, min, max).
"""

from typing import Any, Dict, Optional

from peeka.core.runtime import primitives as _rpl


class MonitorManager:
    """
    Manages performance statistics collection for monitored functions.

    This class tracks per-watch statistics including:
    - total: Total number of calls
    - success: Number of successful calls
    - fail: Number of failed calls
    - sum_rt: Sum of all response times in milliseconds
    - min_rt: Minimum response time in milliseconds
    - max_rt: Maximum response time in milliseconds

    Thread-safe with internal locking for concurrent access.

    Example:
        manager = MonitorManager()
        manager.start_monitor("watch_123")
        manager.record_call("watch_123", success=True, duration_ms=10.5)
        stats = manager.get_stats("watch_123")
    """

    def __init__(self):
        """Initialize the monitor manager."""
        self._stats: Dict[str, Dict[str, Any]] = {}
        self._lock = _rpl.allocate_lock()

    def start_monitor(self, watch_id: str) -> None:
        """
        Start monitoring for a watch.

        Args:
            watch_id: Unique identifier for the watch
        """
        with self._lock:
            self._stats[watch_id] = {
                "total": 0,
                "success": 0,
                "fail": 0,
                "sum_rt": 0.0,
                "min_rt": float("inf"),
                "max_rt": 0.0,
            }

    def stop_monitor(self, watch_id: str) -> Optional[Dict[str, Any]]:
        """
        Stop monitoring and return final stats.

        Args:
            watch_id: Unique identifier for the watch

        Returns:
            Final statistics dict or None if watch not found
        """
        with self._lock:
            if watch_id not in self._stats:
                return None
            return self._stats.pop(watch_id)

    def record_call(self, watch_id: str, success: bool, duration_ms: float) -> None:
        """
        Record a function call.

        Args:
            watch_id: Unique identifier for the watch
            success: True if call succeeded, False if exception
            duration_ms: Duration of call in milliseconds
        """
        with self._lock:
            if watch_id not in self._stats:
                return

            stats = self._stats[watch_id]
            stats["total"] += 1

            if success:
                stats["success"] += 1
            else:
                stats["fail"] += 1

            stats["sum_rt"] += duration_ms
            stats["min_rt"] = min(stats["min_rt"], duration_ms)
            stats["max_rt"] = max(stats["max_rt"], duration_ms)

    def get_stats(self, watch_id: str) -> Optional[Dict[str, Any]]:
        """
        Get current statistics for a watch.

        Calculates derived metrics:
        - fail_rate: fail/total (or 0 if total is 0)
        - rt_avg: sum_rt/total (or 0 if total is 0)
        - rt_min: minimum response time (or 0 if no calls)
        - rt_max: maximum response time

        Args:
            watch_id: Unique identifier for the watch

        Returns:
            Statistics dict with calculated metrics, or None if not found
        """
        with self._lock:
            if watch_id not in self._stats:
                return None

            raw = self._stats[watch_id]
            total = raw["total"]

            # Calculate derived metrics
            fail_rate = (raw["fail"] / total) if total > 0 else 0
            rt_avg = (raw["sum_rt"] / total) if total > 0 else 0

            # Handle min_rt when no calls yet
            rt_min = raw["min_rt"] if raw["min_rt"] != float("inf") else 0

            return {
                "total": total,
                "success": raw["success"],
                "fail": raw["fail"],
                "fail_rate": round(fail_rate, 4),
                "rt_avg": round(rt_avg, 3),
                "rt_min": round(rt_min, 3),
                "rt_max": round(raw["max_rt"], 3),
            }
