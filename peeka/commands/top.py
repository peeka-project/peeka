"""
Top Command - Function-level sampling profiler
"""

import os
import sys
import threading

import uuid

from typing import Any, Dict, Optional, Set, TYPE_CHECKING

from peeka.commands.base import BaseCommand

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class TopCommand(BaseCommand):
    """Sampling profiler that collects CPU profiling statistics."""

    def __init__(self, agent: Optional["PeekaAgent"] = None):
        super().__init__(agent)

        # Statistics storage: key = "funcname (file:line)", value = {name, filename, line, own_count, total_count}
        self._stats: Dict[str, Dict[str, Any]] = {}
        self._total_samples: int = 0

        # Threading
        self._stop_event: threading.Event = threading.Event()
        self._sampling_thread: Optional[threading.Thread] = None
        self._observation_thread: Optional[threading.Thread] = None
        self._lock: threading.Lock = threading.Lock()

        # Configuration
        self._top_id: Optional[str] = None
        self._interval: float = 0.01  # 10ms default
        self._stream: bool = False

        # Resolve peeka package directory for thread filtering
        self._peeka_pkg_dir: str = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + os.sep

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute top command with specified action.

        Args:
            params: Command parameters with 'action' key

        Returns:
            Dict containing execution results
        """
        try:
            action = params.get("action", "start")

            if action == "start":
                return self._start(params)
            elif action == "stop":
                return self._stop(params)
            elif action == "snapshot":
                return self._snapshot(params)
            elif action == "reset":
                return self._reset(params)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start sampling profiler.

        Args:
            params: Optional 'interval' (float) and 'stream' (bool)

        Returns:
            Dict with top_id and status
        """
        with self._lock:
            # Check if already running
            if self._sampling_thread is not None and self._sampling_thread.is_alive():
                return {
                    "status": "success",
                    "top_id": self._top_id,
                    "message": "Profiler already running",
                }

            # Generate unique top_id
            self._top_id = f"top_{uuid.uuid4().hex[:8]}"
            self._interval = params.get("interval", 0.01)
            self._stream = params.get("stream", False)

            # Reset state
            self._stats.clear()
            self._total_samples = 0
            self._stop_event.clear()

            # Register watch
            if self.agent:
                self.agent.observer.register_watch(
                    self._top_id,
                    "top",
                    {"interval": self._interval, "stream": self._stream},
                )

            # Start sampling thread
            self._sampling_thread = threading.Thread(
                target=self._sampling_loop,
                name=f"peeka-top-{self._top_id}",
                daemon=True,
            )
            self._sampling_thread.start()

            # Start observation thread if streaming
            if self._stream and self.agent:
                self._observation_thread = threading.Thread(
                    target=self._send_periodic_observations,
                    name=f"peeka-top-obs-{self._top_id}",
                    daemon=True,
                )
                self._observation_thread.start()

            return {
                "status": "success",
                "top_id": self._top_id,
                "interval": self._interval,
                "stream": self._stream,
            }

    def _stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Stop sampling profiler and return final snapshot.

        Returns:
            Dict with final statistics snapshot
        """
        with self._lock:
            if self._sampling_thread is None or not self._sampling_thread.is_alive():
                return {"status": "error", "error": "Profiler not running"}

            top_id = self._top_id

            # Signal threads to stop
            self._stop_event.set()

        # Wait for threads to finish (outside lock to avoid deadlock)
        if self._sampling_thread:
            self._sampling_thread.join(timeout=2.0)
        if self._observation_thread:
            self._observation_thread.join(timeout=2.0)

        # Unregister watch
        if self.agent and top_id:
            self.agent.observer.unregister_watch(top_id)

        # Build final snapshot
        snapshot = self._build_snapshot()

        # Clean up
        with self._lock:
            self._sampling_thread = None
            self._observation_thread = None
            self._top_id = None

        return {"status": "success", "top_id": top_id, "snapshot": snapshot}

    def _snapshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get current statistics snapshot without stopping.

        Returns:
            Dict with current statistics
        """
        snapshot = self._build_snapshot()
        return {"status": "success", "snapshot": snapshot}

    def _reset(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Reset accumulated statistics (zero counters).

        Returns:
            Dict with status
        """
        with self._lock:
            self._stats.clear()
            self._total_samples = 0

        return {"status": "success", "message": "Statistics reset"}

    def _sampling_loop(self) -> None:
        """Background thread that periodically samples all thread stacks."""
        while not self._stop_event.is_set():
            try:
                # Sample all thread frames
                frames = sys._current_frames()

                # Track which functions we've seen in this sample (for deduplication)
                seen_in_sample: Set[str] = set()

                # Process each thread
                for thread_id, frame in frames.items():
                    # Skip peeka's own threads
                    if self._is_peeka_thread(thread_id, frame):
                        continue

                    # Walk frame stack from leaf to root
                    current_frame = frame
                    is_leaf = True

                    while current_frame is not None:
                        func_key = self._make_func_key(current_frame)

                        with self._lock:
                            # Initialize function stats if not seen before
                            if func_key not in self._stats:
                                self._stats[func_key] = {
                                    "name": current_frame.f_code.co_name,
                                    "filename": current_frame.f_code.co_filename,
                                    "line": current_frame.f_lineno,
                                    "own_count": 0,
                                    "total_count": 0,
                                }

                            # Increment own_count only for leaf frames
                            if is_leaf:
                                self._stats[func_key]["own_count"] += 1

                            # Increment total_count once per sample (deduplication)
                            if func_key not in seen_in_sample:
                                self._stats[func_key]["total_count"] += 1
                                seen_in_sample.add(func_key)

                        # Move to parent frame
                        current_frame = current_frame.f_back
                        is_leaf = False

                # Increment total sample count
                with self._lock:
                    self._total_samples += 1

            except Exception:
                # Best-effort sampling - ignore errors
                pass

            # Sleep using Event.wait for responsive shutdown
            if self._stop_event.wait(timeout=self._interval):
                break

    def _send_periodic_observations(self) -> None:
        """Background thread that sends periodic observation updates."""
        # Send every 1 second
        observation_interval = 1.0

        while not self._stop_event.is_set():
            try:
                snapshot = self._build_snapshot()
                if self.agent:
                    self.agent._send_observation(snapshot)
            except Exception:
                # Best-effort - ignore errors
                pass

            # Wait using Event for responsive shutdown
            if self._stop_event.wait(timeout=observation_interval):
                break

    def _build_snapshot(self) -> Dict[str, Any]:
        """
        Build snapshot of current statistics.

        Returns:
            Dict with formatted statistics
        """
        with self._lock:
            total_samples = self._total_samples
            interval = self._interval
            top_id = self._top_id

            # Convert stats to list and calculate percentages
            functions = []
            for func_key, stats in self._stats.items():
                own_count = stats["own_count"]
                total_count = stats["total_count"]

                # Calculate percentages and times
                own_pct = (
                    (own_count / total_samples * 100) if total_samples > 0 else 0.0
                )
                total_pct = (
                    (total_count / total_samples * 100) if total_samples > 0 else 0.0
                )
                own_time = own_count * interval
                total_time = total_count * interval

                functions.append(
                    {
                        "name": stats["name"],
                        "filename": stats["filename"],
                        "line": stats["line"],
                        "own_pct": round(own_pct, 2),
                        "total_pct": round(total_pct, 2),
                        "own_time": round(own_time, 6),
                        "total_time": round(total_time, 6),
                        "own_count": own_count,
                        "total_count": total_count,
                    }
                )

            # Sort by own_pct descending
            functions.sort(key=lambda x: x["own_pct"], reverse=True)

        return {
            "type": "top_snapshot",
            "top_id": top_id,
            "total_samples": total_samples,
            "sample_interval": interval,
            "functions": functions,
        }

    def _is_peeka_thread(self, thread_id: int, frame) -> bool:
        """
        Check if a thread belongs to peeka (should be excluded from profiling).

        Args:
            thread_id: Thread ID
            frame: Current frame

        Returns:
            True if this is a peeka thread
        """
        # Check if current thread is the sampling thread itself
        if (
            self._sampling_thread
            and threading.current_thread() == self._sampling_thread
        ):
            return True

        # Check if frame is in peeka package code (not just any path containing 'peeka/')
        if frame:
            fname = frame.f_code.co_filename
            if fname.startswith(self._peeka_pkg_dir):
                return True

        # Check thread name
        try:
            for thread in threading.enumerate():
                if thread.ident == thread_id:
                    thread_name = thread.name or ""
                    if thread_name.startswith("peeka-"):
                        return True
                    break
        except Exception:
            pass

        return False

    def _make_func_key(self, frame) -> str:
        """
        Create unique key for a function from a frame.

        Args:
            frame: Frame object

        Returns:
            String key like "funcname (file:line)"
        """
        return f"{frame.f_code.co_name} ({frame.f_code.co_filename}:{frame.f_lineno})"
