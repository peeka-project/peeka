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
        self._overflow = False
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

        if self._monitoring_supported():
            if self._find_free_monitoring_tool_id() is not None:
                return {
                    "available": True,
                    "reason": None,
                    "backend_name": "sys_monitoring",
                }
            if self._has_other_threads() or not hasattr(
                threading, "setprofile_all_threads"
            ):
                return {
                    "available": False,
                    "reason": (
                        "cannot protect existing thread profilers without an "
                        "available sys.monitoring tool id"
                    ),
                    "backend_name": None,
                }
            return {
                "available": True,
                "reason": None,
                "backend_name": "setprofile",
            }

        if hasattr(threading, "setprofile_all_threads"):
            if self._has_other_threads():
                return {
                    "available": False,
                    "reason": (
                        "cannot protect existing thread profilers with "
                        "setprofile_all_threads"
                    ),
                    "backend_name": None,
                }
            return {
                "available": True,
                "reason": None,
                "backend_name": "setprofile",
            }

        return {
            "available": False,
            "reason": "exact profiling requires threading.setprofile_all_threads",
            "backend_name": "setprofile",
        }

    def start(self) -> None:
        """Install the exact profile hook."""
        with self._lock:
            if self._cancelled:
                return

        capability = self.check_capability()
        if not capability["available"]:
            raise RuntimeError(str(capability["reason"]))

        backend_name = capability["backend_name"]
        if backend_name == "sys_monitoring":
            self._start_monitoring()
            return

        with self._lock:
            if self._cancelled:
                return
            if sys.getprofile() is not None or self._threading_profile() is not None:
                raise RuntimeError("another profiler is already installed")
            if self._has_other_threads():
                raise RuntimeError(
                    "cannot protect existing thread profilers on concurrent threads"
                )
            self._backend_name = "setprofile"
            self._active = True
            sys.setprofile(self._on_event)

    def _start_monitoring(self) -> None:
        monitoring = sys.monitoring
        tool_id = self._claim_monitoring_tool_id()
        if tool_id is None:
            raise RuntimeError(
                "cannot protect existing thread profilers without an available "
                "sys.monitoring tool id"
            )

        events = monitoring.events
        try:
            with self._lock:
                if self._cancelled:
                    self._release_monitoring_tool_id(tool_id)
                    return
                self._backend_name = "sys_monitoring"
                self._monitoring_tool_id = tool_id
                self._active = True

            monitoring.register_callback(
                tool_id, events.PY_START, self._on_monitoring_start
            )
            monitoring.set_events(tool_id, events.PY_START)
            with self._lock:
                cancelled = self._cancelled
            if cancelled:
                self.stop()
        except Exception:
            with self._lock:
                if self._monitoring_tool_id == tool_id:
                    self._monitoring_tool_id = None
                self._active = False
            self._release_monitoring_tool_id(tool_id)
            raise

    def stop(self) -> None:
        """Remove the exact profile hook."""
        with self._lock:
            self._cancelled = True
            was_active = self._active
            self._active = False
            tool_id = self._monitoring_tool_id
            self._monitoring_tool_id = None
            backend_name = self._backend_name

        if tool_id is not None:
            self._release_monitoring_tool_id(tool_id)
        elif was_active and backend_name == "setprofile":
            if sys.getprofile() == self._on_event:
                sys.setprofile(None)
        elif was_active and backend_name == "setprofile_all_threads":
            threading.setprofile(None)
            threading.setprofile_all_threads(None)

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
        if self._overflow:
            self._dropped_events += 1
            return
        if self._cancelled:
            return

        self._callback_state.active = True
        try:
            count = self.registry.add_sample(self.profile_id, self._build_sample(frame))
            if count < 0:
                return
            if count >= self.max_events:
                self._overflow = True
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
        try:
            _ = self.registry.stop(
                self.profile_id,
                overflow=True,
                dropped_events=self._dropped_events,
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
