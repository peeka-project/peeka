"""
Top Command - Function-level sampling profiler
"""

import logging
import os
import sys
import uuid
from typing import cast
from typing import Any, Callable, ClassVar, Dict, Optional, Set, TYPE_CHECKING

from peeka.commands.base import BaseCommand
from peeka.core.probes import ProbeContext
from peeka.core.runtime import primitives as _rpl
from peeka.core.runtime.compat import (
    BACKEND_FRAME_WALK,
    BACKEND_GREENLET_AWARE_SAMPLING,
    get_policy,
    policy_meta,
)
from peeka.core.runtime.gevent_probe import GeventState, probe

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent

logger = logging.getLogger(__name__)


class _NativeThreadHandle:
    """Small handle around RPL native threads with Thread-like test hooks."""

    def __init__(self, target: Callable[[], None], name: str):
        self._done_event = _rpl.create_event()
        self.ident = _rpl.start_thread(self._run, args=(target,), name=name)

    def _run(self, target: Callable[[], None]) -> None:
        try:
            target()
        finally:
            self._done_event.set()

    def is_alive(self) -> bool:
        return not self._done_event.is_set()

    def join(self, timeout: Optional[float] = None) -> None:
        self._done_event.wait(timeout=timeout)


class TopCommand(BaseCommand):
    """Sampling profiler that collects CPU profiling statistics."""

    category: ClassVar[str] = "snapshot"
    allows_concurrent: ClassVar[bool] = False

    def __init__(self, agent: Optional["PeekaAgent"] = None):
        super().__init__(agent)

        # Statistics storage: key = "funcname (file:line)", value = {name, filename, line, own_count, total_count}
        self._stats: Dict[str, Dict[str, Any]] = {}
        self._total_samples: int = 0

        # Threading
        self._stop_event: Any = _rpl.create_event()
        self._sampling_thread: Optional[_NativeThreadHandle] = None
        self._observation_thread: Optional[_NativeThreadHandle] = None
        self._lock: Any = _rpl.allocate_lock()

        # Configuration
        self._top_id: Optional[str] = None
        self._interval: float = 0.01  # 10ms default
        self._stream: bool = False
        self._filter_peeka: bool = True
        self._meta: Dict[str, Any] = policy_meta(
            GeventState.NONE, get_policy("top", GeventState.NONE)
        )
        self._client_session_id: Optional[str] = None
        self._job_id: Optional[str] = None
        self._greenlet_switch_counts: Dict[int, int] = {}
        self._greenlet_throw_count: int = 0

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

    def _supports_probe_instrumentation(self) -> bool:
        return self.agent is not None and hasattr(self.agent, "probe_registry")

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
                    "meta": dict(self._meta),
                }

            gevent_state = probe()
            policy = get_policy("top", gevent_state)
            self._meta = policy_meta(gevent_state, policy)
            sampling_target = self._sampling_loop
            if policy.backend == BACKEND_GREENLET_AWARE_SAMPLING:
                if self._greenlet_module_available():
                    sampling_target = self._sampling_loop_greenlet_aware
                else:
                    self._apply_greenlet_fallback_meta(
                        "greenlet module unavailable; fell back to frame_walk sampling"
                    )
                    logger.warning(
                        "top greenlet-aware sampling requested but greenlet is unavailable; "
                        "falling back to frame_walk"
                    )

            # Generate unique top_id
            self._top_id = f"top_{uuid.uuid4().hex[:8]}"
            self._interval = params.get("interval", 0.01)
            self._stream = params.get("stream", False)
            self._filter_peeka = params.get("filter_peeka", True)
            self._client_session_id = params.get("client_session_id")
            self._job_id = params.get("job_id")

            # Reset state
            self._stats.clear()
            self._total_samples = 0
            self._greenlet_switch_counts.clear()
            self._greenlet_throw_count = 0
            self._stop_event.clear()

            # Register watch
            if self.agent:
                self.agent.observer.register_watch(
                    self._top_id,
                    "top",
                    {"interval": self._interval, "stream": self._stream},
                )

            # Start sampling thread
            self._sampling_thread = _NativeThreadHandle(
                target=sampling_target,
                name=f"peeka-top-{self._top_id}",
            )

            # Start observation thread if streaming
            if self._stream and self.agent:
                observation_target = self._send_periodic_observations_with_probe
                if not self._supports_probe_instrumentation():
                    observation_target = self._send_periodic_observations_legacy
                self._observation_thread = _NativeThreadHandle(
                    target=observation_target,
                    name=f"peeka-top-obs-{self._top_id}",
                )

            return {
                "status": "success",
                "top_id": self._top_id,
                "interval": self._interval,
                "stream": self._stream,
                "meta": dict(self._meta),
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
            self._client_session_id = None
            self._job_id = None

        return {
            "status": "success",
            "top_id": top_id,
            "snapshot": snapshot,
            "meta": dict(self._meta),
        }

    def _snapshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get current statistics snapshot without stopping.

        Returns:
            Dict with current statistics
        """
        snapshot = self._build_snapshot()
        return {"status": "success", "snapshot": snapshot, "meta": dict(self._meta)}

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
                    # Skip peeka's own threads (if filtering enabled)
                    if self._filter_peeka and self._is_peeka_thread(thread_id, frame):
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

    def _greenlet_module_available(self) -> bool:
        """Return True when greenlet is already loaded with trace hooks."""
        greenlet_module = sys.modules.get("greenlet")
        if greenlet_module is None:
            return False
        return callable(getattr(greenlet_module, "gettrace", None)) and callable(
            getattr(greenlet_module, "settrace", None)
        )

    def _apply_greenlet_fallback_meta(self, reason: str) -> None:
        """Mark top metadata when greenlet-aware sampling must fall back."""
        meta = dict(self._meta)
        existing_reason = meta.get("degraded_reason")
        if existing_reason:
            reason = f"{existing_reason}; {reason}"
        meta["backend"] = BACKEND_FRAME_WALK
        meta["greenlet_blind"] = True
        meta["degraded_reason"] = reason
        self._meta = meta

    def _record_greenlet_event(self, event: str, args: Any) -> None:
        """Record best-effort greenlet switch/throw counters."""
        try:
            if event == "switch":
                target = args[1]
                with self._lock:
                    target_id = id(target)
                    current = self._greenlet_switch_counts.get(target_id, 0)
                    self._greenlet_switch_counts[target_id] = current + 1
            elif event == "throw":
                with self._lock:
                    self._greenlet_throw_count += 1
        except Exception:
            logger.debug("failed to record greenlet trace event", exc_info=True)

    def _sampling_loop_greenlet_aware(self) -> None:
        """Run top sampling with a chained greenlet switch tracer installed."""
        greenlet_module = sys.modules.get("greenlet")
        gettrace = getattr(greenlet_module, "gettrace", None)
        settrace = getattr(greenlet_module, "settrace", None)
        if greenlet_module is None or not callable(gettrace) or not callable(settrace):
            self._apply_greenlet_fallback_meta(
                "greenlet trace hooks unavailable; fell back to frame_walk sampling"
            )
            logger.warning(
                "top greenlet-aware sampling requested but greenlet trace hooks "
                "are unavailable; falling back to frame_walk"
            )
            self._sampling_loop()
            return

        prev_tracer = cast(Optional[Callable[[Any, Any], None]], gettrace())

        def our_tracer(event, args):
            self._record_greenlet_event(event, args)
            if prev_tracer is not None:
                try:
                    prev_tracer(event, args)
                except Exception:
                    logger.debug(
                        "previous greenlet trace callback failed", exc_info=True
                    )

        settrace(our_tracer)
        try:
            self._sampling_loop()
        finally:
            settrace(prev_tracer)

    def _send_periodic_observations_with_probe(self) -> None:
        """Background thread that sends periodic top snapshots via ProbeContext."""
        if self.agent is None or self._top_id is None:
            return

        probe_config = {
            "interval": self._interval,
            "stream": self._stream,
            "filter_peeka": self._filter_peeka,
        }

        with ProbeContext(
            self.agent.probe_registry,
            target_id=self.agent._target_id_for_jobs(),
            client_session_id=self._client_session_id,
            job_id=self._job_id,
            type="top",
            pattern=None,
            config=probe_config,
        ) as probe:
            self.agent.track_probe_context(self._top_id, probe, "top")
            try:
                self._send_periodic_observations(probe)
            finally:
                self.agent.untrack_probe_context(self._top_id)

    def _send_periodic_observations(self, probe: ProbeContext) -> None:
        """Background loop that sends periodic observation updates."""
        observation_interval = 1.0

        while not self._stop_event.is_set():
            if probe.should_stop():
                break

            snapshot = self._build_snapshot()
            event = probe.record_event(snapshot)
            if event is not None:
                snapshot["event_id"] = event.event_id
                snapshot["probe_id"] = event.probe_id

            if self.agent:
                self.agent._send_observation(snapshot)

            if self._stop_event.wait(timeout=observation_interval):
                break

    def _send_periodic_observations_legacy(self) -> None:
        """Legacy best-effort streaming path for agents without ProbeRegistry."""
        observation_interval = 1.0

        while not self._stop_event.is_set():
            try:
                snapshot = self._build_snapshot()
                if self.agent:
                    self.agent._send_observation(snapshot)
            except Exception:
                pass

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
            greenlet_switch_counts = dict(self._greenlet_switch_counts)
            greenlet_throw_count = self._greenlet_throw_count

        snapshot = {
            "type": "top_snapshot",
            "top_id": top_id,
            "total_samples": total_samples,
            "sample_interval": interval,
            "functions": functions,
            "meta": dict(self._meta),
        }
        if self._meta.get("backend") == BACKEND_GREENLET_AWARE_SAMPLING:
            snapshot["greenlet_events"] = {
                "switch_counts": {
                    str(greenlet_id): count
                    for greenlet_id, count in greenlet_switch_counts.items()
                },
                "throw_count": greenlet_throw_count,
            }
        return snapshot

    def _is_peeka_thread(self, thread_id: int, frame) -> bool:
        """
        Check if a thread belongs to peeka (should be excluded from profiling).

        Args:
            thread_id: Thread ID
            frame: Current frame

        Returns:
            True if this is a peeka thread
        """
        # Check if the thread being examined is the sampling thread itself
        if (
            self._sampling_thread
            and self._sampling_thread.ident == thread_id
        ):
            return True

        if (
            self._observation_thread
            and self._observation_thread.ident == thread_id
        ):
            return True

        # Check if frame is in peeka package code (not just any path containing 'peeka/')
        if frame:
            fname = frame.f_code.co_filename
            if fname.startswith(self._peeka_pkg_dir):
                return True

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
