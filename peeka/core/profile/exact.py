"""Capability-gated exact profile backend."""

import sys
import threading
from types import FrameType
from typing import Any, Callable, Dict, Optional, Tuple

from peeka.core.profile.models import SampleRecord, StackRecord
from peeka.core.profile.registry import ProfileRegistry
from peeka.core.runtime import primitives as _rpl


class ExactProfileSampler:
    """Bounded exact profiler built on Python call events.

    The backend is experimental and deliberately opt-in. It records only call
    events and stops itself once the configured event bound is reached.
    """

    def __init__(
        self,
        profile_id: str,
        registry: ProfileRegistry,
        max_events: int = 10000,
        on_stop: Optional[Callable[[str], None]] = None,
    ):
        self.profile_id = profile_id
        self.registry = registry
        self.max_events = max(1, int(max_events))
        self._on_stop = on_stop
        self._lock = _rpl.allocate_lock()
        self._active = False
        self._cancelled = False
        self._installing = False
        self._install_thread_id: Optional[int] = None
        self._install_done: Optional[Any] = None
        self._releasing = False
        self._release_thread_id: Optional[int] = None
        self._release_done: Optional[Any] = None
        self._overflow = False
        self._overflow_stopped = False
        self._accepted_events = 0
        self._dropped_events = 0
        self._backend_name: Optional[str] = None
        self._monitoring_tool_id: Optional[int] = None
        self._callback_state = threading.local()

    def check_capability(self) -> Dict[str, Any]:
        """Return whether exact profiling is safe in the current runtime.

        Returns:
            Capability payload with availability, refusal reason, and selected
            backend name.
        """
        if self._is_gevent_patched():
            return {
                "available": False,
                "reason": "gevent incompatibility",
                "backend_name": None,
            }

        if sys.getprofile() is not None or self._threading_profile() is not None:
            return {
                "available": False,
                "reason": "another profiler is already installed",
                "backend_name": None,
            }

        if not self._monitoring_supported():
            # Thread-local sys.setprofile cannot be cleared by stop() from
            # another thread (such as a duration timer or RPC stop), and
            # setprofile_all_threads clobbers existing thread profilers.
            return {
                "available": False,
                "reason": (
                    "exact profiling requires sys.monitoring (Python 3.12+) to "
                    "protect existing thread profilers and clear hooks across threads"
                ),
                "backend_name": None,
            }

        if self._find_free_monitoring_tool_id() is not None:
            return {
                "available": True,
                "reason": None,
                "backend_name": "sys_monitoring",
            }

        return {
            "available": False,
            "reason": (
                "cannot protect existing thread profilers without an "
                "available sys.monitoring tool id"
            ),
            "backend_name": None,
        }

    def start(self) -> None:
        """Install the exact profile hook."""
        with self._lock:
            if self._cancelled or self._active or self._installing:
                return

        capability = self.check_capability()
        if not capability["available"]:
            raise RuntimeError(str(capability["reason"]))

        backend_name = capability["backend_name"]
        if backend_name != "sys_monitoring":
            raise RuntimeError(
                str(capability["reason"] or "exact profiling requires sys.monitoring")
            )

        self._start_monitoring()

    def _start_monitoring(self) -> None:
        monitoring = sys.monitoring
        events = monitoring.events
        install_done = _rpl.create_event()
        current_tid = _rpl.get_ident()
        tool_id: Optional[int] = None

        with self._lock:
            if self._cancelled or self._active or self._installing:
                return
            self._installing = True
            self._install_thread_id = current_tid
            self._install_done = install_done

        try:
            tool_id = self._claim_monitoring_tool_id()
            if tool_id is None:
                raise RuntimeError(
                    "cannot protect existing thread profilers without an available "
                    "sys.monitoring tool id"
                )

            with self._lock:
                if self._cancelled:
                    self._active = False
                    self._monitoring_tool_id = None
                    self._backend_name = None
                    cancelled_early = True
                else:
                    self._backend_name = "sys_monitoring"
                    self._monitoring_tool_id = tool_id
                    cancelled_early = False
            if cancelled_early:
                self._release_monitoring_tool_id(tool_id)
                tool_id = None
                return

            monitoring.register_callback(
                tool_id, events.PY_START, self._on_monitoring_start
            )

            with self._lock:
                if self._cancelled:
                    self._active = False
                    self._monitoring_tool_id = None
                    self._backend_name = None
                    cancelled_mid = True
                else:
                    # Publish _active right before enabling events without
                    # holding _lock across set_events so synchronous or
                    # cross-thread overflow callbacks cannot self-deadlock.
                    self._active = True
                    cancelled_mid = False
            if cancelled_mid:
                self._release_monitoring_tool_id(tool_id)
                tool_id = None
                return

            monitoring.set_events(tool_id, events.PY_START)

            with self._lock:
                cancelled_after = self._cancelled
                if cancelled_after:
                    self._active = False
                    if self._monitoring_tool_id == tool_id:
                        self._monitoring_tool_id = None
            if cancelled_after:
                self._release_monitoring_tool_id(tool_id)
                tool_id = None
                return
        except Exception:
            with self._lock:
                self._active = False
                if tool_id is not None and self._monitoring_tool_id == tool_id:
                    self._monitoring_tool_id = None
                if self._backend_name == "sys_monitoring":
                    self._backend_name = None
            if tool_id is not None:
                self._release_monitoring_tool_id(tool_id)
                tool_id = None
            raise
        finally:
            with self._lock:
                self._installing = False
                self._install_thread_id = None
                if self._install_done is install_done:
                    self._install_done = None
            install_done.set()

    def stop(self) -> None:
        """Remove the exact profile hook."""
        current_tid = _rpl.get_ident()
        release_done_to_wait: Optional[Any] = None
        release_done_to_signal: Optional[Any] = None

        with self._lock:
            self._cancelled = True
            self._active = False
            if self._installing:
                if self._install_thread_id == current_tid:
                    # Re-entrant stop from the installing thread (e.g. callback
                    # during set_events): let _start_monitoring roll back.
                    return
                install_done = self._install_done
                tool_id = None
            else:
                install_done = None
                tool_id = self._monitoring_tool_id
                self._monitoring_tool_id = None
                if tool_id is not None:
                    release_done_to_signal = _rpl.create_event()
                    self._releasing = True
                    self._release_thread_id = current_tid
                    self._release_done = release_done_to_signal
                elif self._releasing and self._release_thread_id != current_tid:
                    release_done_to_wait = self._release_done

        if install_done is not None:
            install_done.wait()
            with self._lock:
                tool_id = self._monitoring_tool_id
                self._monitoring_tool_id = None
                self._active = False
                if tool_id is not None:
                    release_done_to_signal = _rpl.create_event()
                    self._releasing = True
                    self._release_thread_id = current_tid
                    self._release_done = release_done_to_signal
                elif self._releasing and self._release_thread_id != current_tid:
                    release_done_to_wait = self._release_done

        if tool_id is not None and release_done_to_signal is not None:
            try:
                self._release_monitoring_tool_id(tool_id)
            finally:
                with self._lock:
                    self._releasing = False
                    self._release_thread_id = None
                    if self._release_done is release_done_to_signal:
                        self._release_done = None
                release_done_to_signal.set()
        elif release_done_to_wait is not None:
            release_done_to_wait.wait()

    def _on_monitoring_start(self, code: Any, instruction_offset: int) -> None:  # noqa: ARG002
        """Bridge sys.monitoring PY_START callbacks into ``_on_event``."""
        if not self._active or self._cancelled:
            return
        if getattr(self._callback_state, "active", False):
            return
        try:
            frame = sys._getframe(1)
        except ValueError:
            return
        self._on_event(frame, "call", None)

    def _on_event(self, frame: FrameType, event: str, arg: Any) -> None:  # noqa: ARG002
        """Record one call-event sample and stop after the configured bound."""
        if event != "call":
            return
        if getattr(self._callback_state, "active", False):
            return
        if self._is_peeka_frame(frame):
            return
        with self._lock:
            if self._overflow:
                self._dropped_events += 1
                return
            if self._cancelled:
                return
            if self._accepted_events >= self.max_events:
                self._overflow = True
                self._dropped_events += 1
                return
            self._accepted_events += 1
            accepted = self._accepted_events

        self._callback_state.active = True
        try:
            count = self.registry.add_sample(self.profile_id, self._build_sample(frame))
            if count < 0:
                return
            if count >= self.max_events or accepted >= self.max_events:
                with self._lock:
                    self._overflow = True
                    should_stop = not self._overflow_stopped
                    self._overflow_stopped = True
                if should_stop:
                    self._stop_for_overflow()
        finally:
            self._callback_state.active = False

    @property
    def overflow(self) -> bool:
        """Return whether this sampler stopped after hitting its event bound."""
        return self._overflow

    def _stop_for_overflow(self) -> None:
        """Uninstall hooks and finalize the registry session after max_events."""
        self.stop()
        with self._lock:
            dropped_events = self._dropped_events
        try:
            _ = self.registry.stop(
                self.profile_id,
                overflow=True,
                dropped_events=dropped_events,
            )
        except KeyError:
            return
        if self._on_stop is not None:
            self._on_stop(self.profile_id)

    @property
    def dropped_events(self) -> int:
        """Return the number of call events ignored after overflow."""
        return self._dropped_events

    @property
    def active(self) -> bool:
        """Return whether the exact hook is currently installed."""
        return self._active

    def _build_sample(self, frame: FrameType) -> SampleRecord:
        stack = []
        current: Optional[FrameType] = frame
        while current is not None:
            code = current.f_code
            module = current.f_globals.get("__name__")
            stack.append(
                StackRecord(
                    filename=code.co_filename,
                    lineno=current.f_lineno,
                    name=code.co_name,
                    module=module if isinstance(module, str) else None,
                )
            )
            current = current.f_back
        stack.reverse()

        thread = threading.current_thread()
        return SampleRecord(
            timestamp=_rpl.time_now(),
            thread_id=_rpl.get_ident(),
            thread_name=thread.name,
            stack=stack,
            lane="exact",
        )

    def _is_peeka_frame(self, frame: FrameType) -> bool:
        """Return whether any frame on the stack belongs to peeka itself.

        Skipping every call made while peeka code is on the stack keeps the
        agent's own work out of the profile and guarantees the hook never runs
        (and never reaches ``on_stop``) while a peeka command holds its locks.
        """
        current: Optional[FrameType] = frame
        while current is not None:
            module = current.f_globals.get("__name__")
            if isinstance(module, str) and (module == "peeka" or module.startswith("peeka.")):
                return True
            current = current.f_back
        return False

    def _threading_profile(self) -> Any:
        getprofile = getattr(threading, "getprofile", None)
        if getprofile is None:
            return getattr(threading, "_profile_hook", None)
        return getprofile()

    def _monitoring_supported(self) -> bool:
        return sys.version_info >= (3, 12) and hasattr(sys, "monitoring")

    def _monitoring_candidate_ids(self) -> Tuple[int, ...]:
        monitoring = sys.monitoring
        profiler_id = getattr(monitoring, "PROFILER_ID", 2)
        ordered = [profiler_id, 4, 3, 5, 1, 0]
        seen = []
        for candidate_id in ordered:
            if candidate_id not in seen:
                seen.append(candidate_id)
        return tuple(seen)

    def _find_free_monitoring_tool_id(self) -> Optional[int]:
        monitoring = sys.monitoring
        for candidate_id in self._monitoring_candidate_ids():
            try:
                if monitoring.get_tool(candidate_id) is None:
                    return candidate_id
            except Exception:
                continue
        return None

    def _claim_monitoring_tool_id(self) -> Optional[int]:
        monitoring = sys.monitoring
        for candidate_id in self._monitoring_candidate_ids():
            try:
                monitoring.use_tool_id(candidate_id, "peeka-exact")
                return candidate_id
            except ValueError:
                continue
        return None

    def _release_monitoring_tool_id(self, tool_id: int) -> None:
        monitoring = getattr(sys, "monitoring", None)
        if monitoring is None:
            return
        try:
            monitoring.set_events(tool_id, 0)
        except Exception:
            pass
        try:
            monitoring.register_callback(
                tool_id, monitoring.events.PY_START, None
            )
        except Exception:
            pass
        try:
            monitoring.free_tool_id(tool_id)
        except Exception:
            pass

    def _has_other_threads(self) -> bool:
        return len(sys._current_frames()) > 1 or threading.active_count() > 1

    def _is_gevent_patched(self) -> bool:
        gevent = sys.modules.get("gevent")
        if gevent is None:
            return False

        monkey = getattr(gevent, "monkey", None)
        if monkey is True:
            return True
        if monkey is None:
            return bool(getattr(gevent, "patched", False))

        is_module_patched = getattr(monkey, "is_module_patched", None)
        if callable(is_module_patched):
            for module_name in ("threading", "socket", "time", "select"):
                try:
                    if is_module_patched(module_name):
                        return True
                except Exception:
                    continue

        return bool(
            getattr(monkey, "saved", None)
            or getattr(monkey, "patched", False)
            or getattr(gevent, "patched", False)
        )
