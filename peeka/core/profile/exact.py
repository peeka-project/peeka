"""Capability-gated exact profile backend."""

import sys
import threading
import time
from types import FrameType
from typing import Any, Callable, Dict, Optional

from peeka.core.profile.models import SampleRecord, StackRecord
from peeka.core.profile.registry import ProfileRegistry


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
        self._active = False
        self._overflow = False
        self._dropped_events = 0
        self._backend_name: Optional[str] = None
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

        if hasattr(threading, "setprofile_all_threads"):
            return {
                "available": True,
                "reason": None,
                "backend_name": "setprofile_all_threads",
            }

        return {
            "available": False,
            "reason": "exact profiling requires threading.setprofile_all_threads",
            "backend_name": "setprofile",
        }

    def start(self) -> None:
        """Install the exact profile hook."""
        capability = self.check_capability()
        if not capability["available"]:
            raise RuntimeError(str(capability["reason"]))
        self._backend_name = capability["backend_name"]
        self._active = True
        threading.setprofile(self._on_event)
        threading.setprofile_all_threads(self._on_event)

    def stop(self) -> None:
        """Remove the exact profile hook."""
        if self._active:
            threading.setprofile(None)
            threading.setprofile_all_threads(None)
        self._active = False

    def _on_event(self, frame: FrameType, event: str, arg: Any) -> None:  # noqa: ARG002
        """Record one call-event sample and stop after the configured bound."""
        if event != "call":
            return
        if getattr(self._callback_state, "active", False):
            return
        if self._is_internal_profile_frame(frame):
            return
        if self._overflow:
            self._dropped_events += 1
            return

        self._callback_state.active = True
        try:
            session = self.registry.get_session(self.profile_id)
            if session is None or session.status != "running":
                return
            if len(session.samples) >= self.max_events:
                self._overflow = True
                self._dropped_events += 1
                self._stop_for_overflow()
                return

            self.registry.add_sample(self.profile_id, self._build_sample(frame))

            session = self.registry.get_session(self.profile_id)
            if session is not None and len(session.samples) >= self.max_events:
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
            timestamp=time.time(),
            thread_id=threading.get_ident(),
            thread_name=thread.name,
            stack=stack,
            lane="exact",
        )

    def _is_internal_profile_frame(self, frame: FrameType) -> bool:
        current: Optional[FrameType] = frame
        while current is not None:
            module = current.f_globals.get("__name__")
            if isinstance(module, str) and module.startswith("peeka.core.profile"):
                return True
            current = current.f_back
        return False

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
