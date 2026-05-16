"""
Observation Manager - Manages observation data flow and statistics

This module provides the ObservationManager class that tracks active watches,
buffers observations, and delivers them to subscribers (streaming clients).
"""

import time
from collections import deque
from typing import Any, Callable, Dict, List, Optional

from peeka.core.runtime import primitives as _rpl


class ObservationManager:
    """
    Manages observation data flow between injector and clients.

    Responsibilities:
    - Track active watches with statistics (count, errors, start_time)
    - Buffer observations in a fixed-size deque
    - Notify subscribers (streaming clients) of new observations
    - Provide aggregated statistics

    Thread-safe: All operations are protected by locks.

    Example:
        observer = ObservationManager()
        observer.register_watch("watch_abc123", "mymodule.func")
        observer.subscribe(my_callback)
        observer.add_observation({"watch_id": "watch_abc123", ...})
    """

    DEFAULT_BUFFER_SIZE = 10000

    def __init__(self, buffer_size: int = DEFAULT_BUFFER_SIZE):
        """
        Initialize the observation manager.

        Args:
            buffer_size: Maximum observations to buffer (default: 10000)
        """
        self._buffer: deque = deque(maxlen=buffer_size)
        self._watches: Dict[str, Dict[str, Any]] = {}
        self._subscribers: List[Callable[[Dict[str, Any]], None]] = []
        self._lock = _rpl.allocate_lock()
        self._stats_lock = _rpl.allocate_lock()

    def register_watch(
            self, watch_id: str, pattern: str, config: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Register a new watch for tracking.

        Args:
            watch_id: Unique watch identifier
            pattern: Function pattern being watched
            config: Optional watch configuration
        """
        with self._lock:
            self._watches[watch_id] = {
                "pattern": pattern,
                "config": config or {},
                "start_time": time.time(),
                "count": 0,
                "error_count": 0,
                "last_observation_time": None,
            }

    def unregister_watch(self, watch_id: str) -> Optional[Dict[str, Any]]:
        """
        Unregister a watch and return its final statistics.

        Args:
            watch_id: Watch identifier to unregister

        Returns:
            Final statistics dict or None if not found
        """
        with self._lock:
            info = self._watches.pop(watch_id, None)
            if info:
                info["end_time"] = time.time()
                info["duration"] = info["end_time"] - info["start_time"]
            return info

    def add_observation(self, observation: Dict[str, Any]) -> None:
        """
        Add an observation to the buffer and notify subscribers.

        This is called by the injector when a watched function is invoked.

        Args:
            observation: Observation data dict with keys:
                - watch_id: str
                - timestamp: float
                - func_name: str
                - args, kwargs, result, etc.
        """
        watch_id = observation.get("watch_id")

        with self._stats_lock:
            if watch_id and watch_id in self._watches:
                watch_info = self._watches[watch_id]
                watch_info["count"] += 1
                watch_info["last_observation_time"] = observation.get("timestamp")
                if not observation.get("success", True):
                    watch_info["error_count"] += 1

        with self._lock:
            self._buffer.append(observation)
            subscribers = list(self._subscribers)

        for callback in subscribers:
            try:
                callback(observation)
            except Exception:
                pass

    def subscribe(
            self, callback: Callable[[Dict[str, Any]], None]
    ) -> Callable[[], None]:
        """
        Subscribe to receive observations.

        Args:
            callback: Function to call with each observation

        Returns:
            Unsubscribe function
        """
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe():
            with self._lock:
                if callback in self._subscribers:
                    self._subscribers.remove(callback)

        return unsubscribe

    def get_watch_stats(self, watch_id: str) -> Optional[Dict[str, Any]]:
        """
        Get statistics for a specific watch.

        Args:
            watch_id: Watch identifier

        Returns:
            Stats dict or None if not found
        """
        with self._lock:
            info = self._watches.get(watch_id)
            if info:
                return {
                    "watch_id": watch_id,
                    "pattern": info["pattern"],
                    "start_time": info["start_time"],
                    "running_time": time.time() - info["start_time"],
                    "count": info["count"],
                    "error_count": info["error_count"],
                    "last_observation_time": info["last_observation_time"],
                }
            return None

    def get_all_stats(self) -> Dict[str, Any]:
        """
        Get aggregated statistics for all watches.

        Returns:
            Dict with global stats and per-watch stats
        """
        with self._lock:
            watches_stats = []
            total_count = 0
            total_errors = 0

            for watch_id, info in self._watches.items():
                watch_stat = {
                    "watch_id": watch_id,
                    "pattern": info["pattern"],
                    "count": info["count"],
                    "error_count": info["error_count"],
                    "running_time": time.time() - info["start_time"],
                }
                watches_stats.append(watch_stat)
                total_count += info["count"]
                total_errors += info["error_count"]

            return {
                "active_watches": len(self._watches),
                "total_observations": total_count,
                "total_errors": total_errors,
                "buffer_size": len(self._buffer),
                "buffer_capacity": self._buffer.maxlen,
                "subscriber_count": len(self._subscribers),
                "watches": watches_stats,
            }

    def get_recent_observations(
            self, count: int = 100, watch_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent observations from buffer.

        Args:
            count: Maximum observations to return
            watch_id: Optional filter by watch_id

        Returns:
            List of recent observations (newest first)
        """
        with self._lock:
            if watch_id:
                filtered = [o for o in self._buffer if o.get("watch_id") == watch_id]
                return list(reversed(filtered[-count:]))
            return list(reversed(list(self._buffer)[-count:]))

    def clear_buffer(self) -> int:
        """
        Clear the observation buffer.

        Returns:
            Number of observations cleared
        """
        with self._lock:
            count = len(self._buffer)
            self._buffer.clear()
            return count

    def clear_all(self) -> Dict[str, int]:
        """
        Clear all watches and buffer.

        Returns:
            Dict with counts of cleared items
        """
        with self._lock:
            watch_count = len(self._watches)
            buffer_count = len(self._buffer)
            self._watches.clear()
            self._buffer.clear()
            return {
                "watches_cleared": watch_count,
                "observations_cleared": buffer_count,
            }
