# pyright: reportArgumentType=false
"""Profile Command - direct management of profile sessions in ProfileRegistry."""

import io
import json
import logging
import sys
import threading
from typing import Any, ClassVar, Dict, List, Optional, TYPE_CHECKING

from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand
from peeka.core.runtime import primitives as _rpl
from peeka.core.profile.exact import ExactProfileSampler
from peeka.core.profile.models import ProfileConfig, ProfileSession, SampleRecord, StackRecord
from peeka.core.profile.processors import BuildTimelineProcessor
from peeka.core.profile.processors import BuildTopListProcessor
from peeka.core.profile.processors import ProcessedProfile
from peeka.core.profile.registry import PROFILE_REGISTRY as _PROFILE_REGISTRY
from peeka.core.profile.renderers import (
    JsonRenderer,
    PerfettoRenderer,
    SpeedscopeRenderer,
    TextRenderer,
)

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent

logger = logging.getLogger(__name__)

_RENDERER_MAP = {
    "json": JsonRenderer,
    "text": TextRenderer,
    "speedscope": SpeedscopeRenderer,
    "perfetto": PerfettoRenderer,
}


class _NativeThreadHandle:
    def __init__(self, target: Any, args: tuple, name: str):
        self._done_event = _rpl.create_event()
        self.ident = _rpl.start_thread(self._run, args=(target, args), name=name)

    def _run(self, target: Any, args: tuple) -> None:
        try:
            target(*args)
        finally:
            self._done_event.set()

    def is_alive(self) -> bool:
        return not self._done_event.is_set()

    def join(self, timeout: Optional[float] = None) -> None:
        self._done_event.wait(timeout=timeout)


class ProfileCommand(ResourceOwningCommand):
    """Manage profile sessions in the shared ProfileRegistry.

    Actions:
    - start: Create a new profiling session and return its profile_id.
    - stop: Stop a running session and return its summary.
    - snapshot: Return a point-in-time JSON snapshot of a session.
    - list: List all tracked sessions with metadata.
    - cleanup: Remove old stopped sessions from the registry.
    - export: Render a session to a chosen output format (json/text/speedscope/perfetto).
    """

    is_resource_owner: bool = True
    cleanup_scope: CleanupScope = CleanupScope.DETACH_ONLY
    category: ClassVar[str] = "snapshot"
    allows_concurrent: ClassVar[bool] = False
    _state_lock: ClassVar[Any] = _rpl.allocate_lock()
    _exact_lock: ClassVar[Any] = _rpl.allocate_lock()
    _exact_profile_id: ClassVar[Optional[str]] = None
    _active_exact_sampler: ClassVar[Optional[ExactProfileSampler]] = None
    _active_exact_stop_timer: ClassVar[Optional[threading.Timer]] = None
    _exact_starting_token: ClassVar[Optional[object]] = None
    _exact_inflight_profile_id: ClassVar[Optional[str]] = None
    _exact_inflight_sampler: ClassVar[Optional[ExactProfileSampler]] = None
    _exact_inflight_cancelled: ClassVar[bool] = False
    _exact_inflight_done: ClassVar[Optional[Any]] = None
    _exact_start_token_tls: ClassVar[threading.local] = threading.local()
    _sampling_lock: ClassVar[Any] = _rpl.allocate_lock()
    _active_sampling_thread: ClassVar[Optional[_NativeThreadHandle]] = None
    _active_sampling_stop_event: ClassVar[Optional[Any]] = None
    _active_sampling_profile_id: ClassVar[Optional[str]] = None
    _active_sampling_stopping: ClassVar[bool] = False

    def __init__(self, agent: Optional["PeekaAgent"] = None):
        super().__init__(agent)
        self._exact_sampler: Optional[ExactProfileSampler] = None
        self._exact_stop_timer: Optional[threading.Timer] = None
        self._sampling_thread: Optional[_NativeThreadHandle] = None
        self._sampling_stop_event: Optional[Any] = None
        self._sampling_profile_id: Optional[str] = None
        self._sampling_stopping: bool = False

    def _is_agent_stopped(self) -> bool:
        return self.agent is not None and bool(getattr(self.agent, "_stopped", False))

    def _reap_dead_sampling_locked(self) -> None:
        thread = ProfileCommand._active_sampling_thread
        if thread is not None and not thread.is_alive():
            ProfileCommand._active_sampling_thread = None
            ProfileCommand._active_sampling_stop_event = None
            ProfileCommand._active_sampling_profile_id = None
            ProfileCommand._active_sampling_stopping = False

        local_thread = self._sampling_thread
        if local_thread is not None and not local_thread.is_alive():
            self._sampling_thread = None
            self._sampling_stop_event = None
            self._sampling_profile_id = None
            self._sampling_stopping = False

    def _sampling_conflict_locked(self) -> Optional[Dict[str, Any]]:
        self._reap_dead_sampling_locked()
        thread = ProfileCommand._active_sampling_thread
        if thread is not None and thread.is_alive():
            return {
                "profile_id": ProfileCommand._active_sampling_profile_id,
                "stopping": ProfileCommand._active_sampling_stopping,
            }
        if self._sampling_thread is not None and self._sampling_thread.is_alive():
            return {
                "profile_id": self._sampling_profile_id,
                "stopping": self._sampling_stopping,
            }
        return None

    def _exact_conflict_locked(self) -> Optional[Dict[str, Any]]:
        inflight_done = ProfileCommand._exact_inflight_done
        if inflight_done is not None and not inflight_done.is_set():
            return {
                "profile_id": ProfileCommand._exact_inflight_profile_id,
                "state": "stopping" if ProfileCommand._exact_inflight_cancelled else "starting",
            }
        if ProfileCommand._exact_starting_token is not None:
            return {"profile_id": None, "state": "starting"}
        active_exact_id = self._active_exact_profile_id()
        if active_exact_id is not None:
            return {"profile_id": active_exact_id, "state": "running"}
        return None

    def _release_exact_start_token(self, token: object) -> None:
        with ProfileCommand._state_lock:
            if ProfileCommand._exact_starting_token is token:
                ProfileCommand._exact_starting_token = None

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = params.get("action", "list")

            if action == "start":
                return self._start(params)
            elif action == "stop":
                return self._stop(params)
            elif action == "snapshot":
                return self._snapshot(params)
            elif action == "list":
                return self._list(params)
            elif action == "cleanup":
                return self._cleanup(params)
            elif action == "export":
                return self._export(params)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}
        except Exception as exc:
            return {"status": "error", "error": str(exc)}

    def _start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        max_samples = params.get("max_samples")
        config = ProfileConfig(
            backend=params.get("backend", "sampling"),
            interval_ms=params.get("interval_ms", 10),
            duration_ms=params.get("duration_ms"),
            max_samples=100000 if max_samples is None else max_samples,
        )
        if config.backend == "exact":
            if not params.get("experimental"):
                return {
                    "status": "error",
                    "error": (
                        "exact backend is experimental and disabled by default; "
                        "pass experimental=true (CLI: --experimental) to enable it"
                    ),
                }
            token = object()
            with ProfileCommand._state_lock:
                if self._is_agent_stopped():
                    return {"status": "error", "error": "agent is stopped"}
                sampling_conflict = self._sampling_conflict_locked()
                if sampling_conflict is not None:
                    pid = sampling_conflict["profile_id"]
                    state = "still stopping" if sampling_conflict["stopping"] else "already running"
                    resp: Dict[str, Any] = {
                        "status": "error",
                        "error": (
                            "exact and sampling profiles are mutually exclusive; "
                            f"sampling profile {state}: {pid}"
                        ),
                    }
                    if pid is not None:
                        resp["profile_id"] = pid
                    return resp
                exact_conflict = self._exact_conflict_locked()
                if exact_conflict is not None:
                    pid = exact_conflict["profile_id"]
                    state = exact_conflict["state"]
                    err = (
                        f"exact profile already running: {pid}"
                        if state == "running"
                        else f"exact profile already running ({state})"
                    )
                    resp = {"status": "error", "error": err}
                    if pid is not None:
                        resp["profile_id"] = pid
                    return resp
                ProfileCommand._exact_starting_token = token

            ProfileCommand._exact_start_token_tls.token = token
            try:
                return self._start_exact(params, config)
            finally:
                if getattr(ProfileCommand._exact_start_token_tls, "token", None) is token:
                    ProfileCommand._exact_start_token_tls.token = None
                self._release_exact_start_token(token)

        if config.backend == "sampling":
            with ProfileCommand._state_lock:
                if self._is_agent_stopped():
                    return {"status": "error", "error": "agent is stopped"}
                exact_conflict = self._exact_conflict_locked()
                if exact_conflict is not None:
                    pid = exact_conflict["profile_id"]
                    state = exact_conflict["state"]
                    suffix = f": {pid}" if pid is not None else ""
                    resp = {
                        "status": "error",
                        "error": (
                            "exact and sampling profiles are mutually exclusive; "
                            f"exact profile {state}{suffix}"
                        ),
                    }
                    if pid is not None:
                        resp["profile_id"] = pid
                    return resp
                sampling_conflict = self._sampling_conflict_locked()
                if sampling_conflict is not None:
                    pid = sampling_conflict["profile_id"]
                    if sampling_conflict["stopping"]:
                        return {
                            "status": "error",
                            "error": "Sampling profile is still stopping; thread still alive",
                            "profile_id": pid,
                        }
                    return {
                        "status": "error",
                        "error": "Sampling profile already running",
                        "profile_id": pid,
                    }

                profile_id = _PROFILE_REGISTRY.start(config)
                self._start_sampling(profile_id, config)
                return {"status": "success", "profile_id": profile_id}

        profile_id = _PROFILE_REGISTRY.start(config)
        return {"status": "success", "profile_id": profile_id}

    def _start_exact(
        self,
        params: Dict[str, Any],
        config: ProfileConfig,
    ) -> Dict[str, Any]:
        tls_token = getattr(ProfileCommand._exact_start_token_tls, "token", None)
        owns_token = False
        reserved_token: Optional[object] = None

        with ProfileCommand._state_lock:
            if self._is_agent_stopped():
                return {"status": "error", "error": "agent is stopped"}
            if (
                tls_token is not None
                and ProfileCommand._exact_starting_token is tls_token
            ):
                reserved_token = tls_token
            else:
                sampling_conflict = self._sampling_conflict_locked()
                if sampling_conflict is not None:
                    pid = sampling_conflict["profile_id"]
                    return {
                        "status": "error",
                        "error": (
                            "exact and sampling profiles are mutually exclusive; "
                            f"sampling profile active: {pid}"
                        ),
                        "profile_id": pid,
                    }
                exact_conflict = self._exact_conflict_locked()
                if exact_conflict is not None:
                    pid = exact_conflict["profile_id"]
                    state = exact_conflict["state"]
                    resp: Dict[str, Any] = {
                        "status": "error",
                        "error": (
                            f"exact profile already running: {pid}"
                            if state == "running"
                            else f"exact profile already running ({state})"
                        ),
                    }
                    if pid is not None:
                        resp["profile_id"] = pid
                    return resp
                reserved_token = object()
                ProfileCommand._exact_starting_token = reserved_token
                owns_token = True

        try:
            profile_id = _PROFILE_REGISTRY.start(config)
            effective_max_events = min(
                int(params.get("max_events", 10000)),
                int(config.max_samples or 100000),
            )
            sampler = ExactProfileSampler(
                profile_id,
                _PROFILE_REGISTRY,
                max_events=effective_max_events,
                on_stop=lambda stopped_id: self._clear_exact_state(stopped_id, sampler),
            )
            capability = sampler.check_capability()
            if not capability["available"]:
                _PROFILE_REGISTRY.remove_session(profile_id)
                return {
                    "status": "error",
                    "error": capability["reason"],
                    "capability": capability,
                }

            inflight_done = _rpl.create_event()
            with ProfileCommand._state_lock:
                if self._is_agent_stopped():
                    _PROFILE_REGISTRY.remove_session(profile_id)
                    return {"status": "error", "error": "agent is stopped"}
                sampling_conflict = self._sampling_conflict_locked()
                if sampling_conflict is not None:
                    _PROFILE_REGISTRY.remove_session(profile_id)
                    pid = sampling_conflict["profile_id"]
                    return {
                        "status": "error",
                        "error": (
                            "exact and sampling profiles are mutually exclusive; "
                            f"sampling profile active: {pid}"
                        ),
                        "profile_id": pid,
                    }
                active_exact_id = self._active_exact_profile_id()
                if active_exact_id is not None:
                    _PROFILE_REGISTRY.remove_session(profile_id)
                    return {
                        "status": "error",
                        "error": f"exact profile already running: {active_exact_id}",
                        "profile_id": active_exact_id,
                    }
                if ProfileCommand._exact_starting_token is reserved_token:
                    ProfileCommand._exact_starting_token = None
                ProfileCommand._exact_profile_id = profile_id
                ProfileCommand._active_exact_sampler = sampler
                self._exact_sampler = sampler
                ProfileCommand._exact_inflight_profile_id = profile_id
                ProfileCommand._exact_inflight_sampler = sampler
                ProfileCommand._exact_inflight_cancelled = False
                ProfileCommand._exact_inflight_done = inflight_done

            try:
                sampler.start()
            except Exception:
                with ProfileCommand._state_lock:
                    self._clear_local_exact_sampler_if_matches(sampler)
                    if ProfileCommand._exact_profile_id == profile_id:
                        ProfileCommand._exact_profile_id = None
                        ProfileCommand._active_exact_sampler = None
                    if ProfileCommand._exact_inflight_profile_id == profile_id:
                        ProfileCommand._exact_inflight_profile_id = None
                        ProfileCommand._exact_inflight_sampler = None
                        ProfileCommand._exact_inflight_cancelled = False
                        ProfileCommand._exact_inflight_done = None
                try:
                    _PROFILE_REGISTRY.stop(profile_id)
                except KeyError:
                    pass
                inflight_done.set()
                raise

            cancelled_while_starting = False
            with ProfileCommand._state_lock:
                cancelled_while_starting = (
                    ProfileCommand._exact_inflight_cancelled
                    or ProfileCommand._exact_profile_id != profile_id
                    or ProfileCommand._active_exact_sampler is not sampler
                    or self._is_agent_stopped()
                )
                if cancelled_while_starting:
                    self._clear_local_exact_sampler_if_matches(sampler)
                    if ProfileCommand._exact_profile_id == profile_id:
                        ProfileCommand._exact_profile_id = None
                        ProfileCommand._active_exact_sampler = None
                    if ProfileCommand._exact_inflight_profile_id == profile_id:
                        ProfileCommand._exact_inflight_profile_id = None
                        ProfileCommand._exact_inflight_sampler = None
                        ProfileCommand._exact_inflight_cancelled = False
                        ProfileCommand._exact_inflight_done = None
                else:
                    if ProfileCommand._exact_inflight_profile_id == profile_id:
                        ProfileCommand._exact_inflight_profile_id = None
                        ProfileCommand._exact_inflight_sampler = None
                        ProfileCommand._exact_inflight_cancelled = False
                        ProfileCommand._exact_inflight_done = None
                    inflight_done.set()
                    if config.duration_ms is not None:
                        self._exact_stop_timer = threading.Timer(
                            config.duration_ms / 1000.0,
                            self._expire_exact_profile,
                            args=(profile_id, sampler),
                        )
                        setattr(self._exact_stop_timer, "_peeka_profile_id", profile_id)
                        self._exact_stop_timer.daemon = True
                        ProfileCommand._active_exact_stop_timer = self._exact_stop_timer
                        self._exact_stop_timer.start()

            if cancelled_while_starting:
                try:
                    sampler.stop()
                finally:
                    try:
                        _PROFILE_REGISTRY.stop(profile_id)
                    except KeyError:
                        pass
                    inflight_done.set()
                return {
                    "status": "error",
                    "error": "exact profile was stopped while starting",
                    "profile_id": profile_id,
                }

            return {"status": "success", "profile_id": profile_id}
        finally:
            if owns_token and reserved_token is not None:
                self._release_exact_start_token(reserved_token)

    def _stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        profile_id = params.get("profile_id")
        if not profile_id:
            return {"status": "error", "error": "Missing profile_id"}
        try:
            with ProfileCommand._state_lock:
                self._reap_dead_sampling_locked()
                is_exact_owner = profile_id == ProfileCommand._exact_profile_id
                is_exact_inflight = profile_id == ProfileCommand._exact_inflight_profile_id
                if is_exact_inflight:
                    ProfileCommand._exact_inflight_cancelled = True
                sampler = (
                    ProfileCommand._active_exact_sampler
                    if is_exact_owner
                    else (
                        ProfileCommand._exact_inflight_sampler
                        if is_exact_inflight
                        else None
                    )
                )
                if sampler is not None:
                    ProfileCommand._exact_profile_id = None
                    ProfileCommand._active_exact_sampler = None
                    self._clear_local_exact_sampler_if_matches(sampler)
                timer = self._cancel_exact_timer_if_matches(profile_id)
            if sampler is not None:
                sampler.stop()
            if timer is not None:
                timer.cancel()
            sampling_error = self._stop_sampling_profile(profile_id)
            session = _PROFILE_REGISTRY.stop(profile_id)
            if sampling_error is not None:
                return {
                    "status": "error",
                    "error": sampling_error,
                    "profile_id": profile_id,
                }
            return {
                "status": "success",
                "profile_id": profile_id,
                "summary": session.summary.to_dict() if session.summary else {},
            }
        except KeyError:
            return {"status": "error", "error": "profile not found"}

    def _expire_exact_profile(
        self,
        profile_id: str,
        sampler: ExactProfileSampler,
    ) -> None:
        with ProfileCommand._state_lock:
            if ProfileCommand._exact_profile_id != profile_id:
                return
            if self._exact_sampler is not sampler:
                return
            try:
                sampler.stop()
                try:
                    _PROFILE_REGISTRY.stop(profile_id)
                except KeyError:
                    logger.debug("exact profile %s already removed", profile_id)
            finally:
                self._exact_sampler = None
                ProfileCommand._exact_profile_id = None
                ProfileCommand._active_exact_sampler = None
                ProfileCommand._active_exact_stop_timer = None
                self._exact_stop_timer = None

    def _active_exact_profile_id(self) -> Optional[str]:
        profile_id = ProfileCommand._exact_profile_id
        if profile_id is None:
            return None
        session = _PROFILE_REGISTRY.get_session_info(profile_id)
        if session is not None and session["status"] == "running":
            return profile_id
        ProfileCommand._exact_profile_id = None
        ProfileCommand._active_exact_sampler = None
        ProfileCommand._active_exact_stop_timer = None
        return None

    def _clear_exact_state(
        self,
        profile_id: str,
        sampler: ExactProfileSampler,
    ) -> None:
        with ProfileCommand._state_lock:
            if ProfileCommand._exact_profile_id != profile_id:
                return
            if self._exact_sampler is not sampler:
                return
            self._exact_sampler = None
            ProfileCommand._exact_profile_id = None
            ProfileCommand._active_exact_sampler = None
            timer = self._cancel_exact_timer_if_matches(profile_id)
        if timer is not None:
            timer.cancel()

    def _cancel_exact_timer_if_matches(self, profile_id: str) -> Optional[threading.Timer]:
        timer = ProfileCommand._active_exact_stop_timer or self._exact_stop_timer
        if timer is None:
            return None
        if getattr(timer, "_peeka_profile_id", None) != profile_id:
            return None
        if self._exact_stop_timer is timer:
            self._exact_stop_timer = None
        if ProfileCommand._active_exact_stop_timer is timer:
            ProfileCommand._active_exact_stop_timer = None
        return timer

    def _clear_local_exact_sampler_if_matches(self, sampler: ExactProfileSampler) -> None:
        if self._exact_sampler is sampler:
            self._exact_sampler = None

    def _get_active_sampling_profile_id(self) -> Optional[str]:
        self._reap_dead_sampling_locked()
        profile_id = ProfileCommand._active_sampling_profile_id
        thread = ProfileCommand._active_sampling_thread
        if profile_id is None or thread is None:
            return None
        if thread.is_alive():
            return profile_id
        return None

    def _start_sampling(self, profile_id: str, config: ProfileConfig) -> None:
        stop_event = _rpl.create_event()
        self._sampling_stop_event = stop_event
        self._sampling_profile_id = profile_id
        self._sampling_stopping = False
        deadline = None
        if config.duration_ms is not None:
            deadline = _rpl.time_now() + config.duration_ms / 1000.0
        interval = max(float(config.interval_ms) / 1000.0, 0.001)
        thread = _NativeThreadHandle(
            target=self._sampling_loop,
            args=(profile_id, interval, stop_event, deadline),
            name=f"peeka-profile-{profile_id}",
        )
        self._sampling_thread = thread
        ProfileCommand._active_sampling_thread = thread
        ProfileCommand._active_sampling_stop_event = stop_event
        ProfileCommand._active_sampling_profile_id = profile_id
        ProfileCommand._active_sampling_stopping = False

    def _stop_sampling_profile(self, profile_id: str) -> Optional[str]:
        with ProfileCommand._state_lock:
            self._reap_dead_sampling_locked()
            if profile_id == ProfileCommand._active_sampling_profile_id:
                thread = ProfileCommand._active_sampling_thread
                stop_event = ProfileCommand._active_sampling_stop_event
                ProfileCommand._active_sampling_stopping = True
                if self._sampling_profile_id == profile_id:
                    self._sampling_stopping = True
                is_class_active = True
            elif profile_id == self._sampling_profile_id:
                # Stale per-instance handle that is no longer the active one.
                thread = self._sampling_thread
                stop_event = self._sampling_stop_event
                self._sampling_stopping = True
                is_class_active = False
            else:
                return None

        if stop_event is not None:
            stop_event.set()
        if thread is not None:
            thread.join(timeout=2.0)

        still_alive = thread is not None and thread.is_alive()
        with ProfileCommand._state_lock:
            if not still_alive:
                if (
                    is_class_active
                    and ProfileCommand._active_sampling_profile_id == profile_id
                    and ProfileCommand._active_sampling_thread is thread
                ):
                    ProfileCommand._active_sampling_thread = None
                    ProfileCommand._active_sampling_stop_event = None
                    ProfileCommand._active_sampling_profile_id = None
                    ProfileCommand._active_sampling_stopping = False
                if (
                    self._sampling_profile_id == profile_id
                    and self._sampling_thread is thread
                ):
                    self._sampling_thread = None
                    self._sampling_stop_event = None
                    self._sampling_profile_id = None
                    self._sampling_stopping = False

        try:
            _PROFILE_REGISTRY.stop(profile_id)
        except KeyError:
            logger.debug("sampling profile %s already removed", profile_id)

        if still_alive:
            return "sampling thread still alive after join timeout"
        return None

    def _sampling_loop(
        self,
        profile_id: str,
        interval: float,
        stop_event: Any,
        deadline: Optional[float],
    ) -> None:
        expired = False
        try:
            while not stop_event.is_set():
                if deadline is not None and _rpl.time_now() >= deadline:
                    expired = True
                    break
                try:
                    self._collect_sampling_snapshot(profile_id)
                except Exception:
                    logger.debug("sampling profile snapshot failed", exc_info=True)
                if stop_event.wait(timeout=interval):
                    break
        finally:
            if expired:
                try:
                    _PROFILE_REGISTRY.stop(profile_id)
                except KeyError:
                    logger.debug("sampling profile %s already removed", profile_id)
            with ProfileCommand._state_lock:
                if (
                    ProfileCommand._active_sampling_profile_id == profile_id
                    and ProfileCommand._active_sampling_stop_event is stop_event
                    and (expired or ProfileCommand._active_sampling_stopping)
                ):
                    ProfileCommand._active_sampling_thread = None
                    ProfileCommand._active_sampling_stop_event = None
                    ProfileCommand._active_sampling_profile_id = None
                    ProfileCommand._active_sampling_stopping = False
                if (
                    self._sampling_profile_id == profile_id
                    and self._sampling_stop_event is stop_event
                    and (expired or self._sampling_stopping)
                ):
                    self._sampling_thread = None
                    self._sampling_stop_event = None
                    self._sampling_profile_id = None
                    self._sampling_stopping = False

    def _collect_sampling_snapshot(self, profile_id: str) -> None:
        current_thread_id = _rpl.get_ident()
        sampling_thread = self._sampling_thread
        sampling_ident = sampling_thread.ident if sampling_thread is not None else None
        thread_names = {
            getattr(thread, "ident", None): getattr(thread, "name", "")
            for thread in threading.enumerate()
        }
        timestamp = _rpl.time_now()
        for thread_id, frame in sys._current_frames().items():
            if thread_id == current_thread_id or (
                sampling_ident is not None and thread_id == sampling_ident
            ):
                continue
            stack: List[StackRecord] = []
            current_frame = frame
            while current_frame is not None:
                stack.append(
                    StackRecord(
                        filename=current_frame.f_code.co_filename,
                        lineno=current_frame.f_lineno,
                        name=current_frame.f_code.co_name,
                    )
                )
                current_frame = current_frame.f_back
            stack.reverse()
            if not stack:
                continue
            sample = SampleRecord(
                timestamp=timestamp,
                thread_id=thread_id,
                thread_name=thread_names.get(thread_id, ""),
                stack=stack,
            )
            _PROFILE_REGISTRY.add_sample(profile_id, sample)

    def _snapshot(self, params: Dict[str, Any]) -> Dict[str, Any]:
        profile_id = params.get("profile_id")
        if not profile_id:
            return {"status": "error", "error": "Missing profile_id"}
        format_name = params.get("format", "json")
        renderer_cls = _RENDERER_MAP.get(format_name)
        if renderer_cls is None:
            return {"status": "error", "error": f"Unknown format: {format_name}"}
        try:
            session = _PROFILE_REGISTRY.snapshot(profile_id)
        except KeyError:
            return {"status": "error", "error": "profile not found"}

        processed = self._process_for_export(session, format_name)
        buf = io.StringIO()
        renderer_cls().render(processed, buf)
        content = buf.getvalue()
        if format_name == "json":
            result = json.loads(content)
            return {"status": "success", "profile_id": profile_id, "snapshot": result}
        return {
            "status": "success",
            "profile_id": profile_id,
            "format": format_name,
            "content": content,
        }

    def _list(self, params: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG002
        sessions = _PROFILE_REGISTRY.list_session_infos()
        return {
            "status": "success",
            "sessions": [
                {
                    "profile_id": s["profile_id"],
                    "backend": s["backend"],
                    "status": s["status"],
                    "started_at": s["started_at"],
                    "sample_count": s["sample_count"],
                }
                for s in sessions
            ],
        }

    def _cleanup(self, params: Dict[str, Any]) -> Dict[str, Any]:
        count = _PROFILE_REGISTRY.cleanup(
            older_than_secs=params.get("older_than_secs"),
            max_sessions=params.get("max_sessions"),
        )
        return {"status": "success", "removed": count}

    def _export(self, params: Dict[str, Any]) -> Dict[str, Any]:
        profile_id = params.get("profile_id")
        if not profile_id:
            return {"status": "error", "error": "Missing profile_id"}

        format_name = params.get("format", "json")
        renderer_cls = _RENDERER_MAP.get(format_name)
        if renderer_cls is None:
            return {"status": "error", "error": f"Unknown format: {format_name}"}

        try:
            session = _PROFILE_REGISTRY.snapshot(profile_id)
        except KeyError:
            return {"status": "error", "error": "profile not found"}

        processed = self._process_for_export(session, format_name)
        buf = io.StringIO()
        if format_name == "json":
            JsonRenderer(include_samples=bool(params.get("include_samples"))).render(
                processed,
                buf,
            )
        else:
            renderer_cls().render(processed, buf)
        return {
            "status": "success",
            "content": buf.getvalue(),
            "format": format_name,
        }

    def _process_for_export(
        self,
        session: ProfileSession,
        format_name: str,
    ) -> ProcessedProfile:
        if format_name in ("json", "text"):
            return BuildTopListProcessor().process(session)
        if format_name == "perfetto":
            return BuildTimelineProcessor().process(session)
        return ProcessedProfile(
            profile_id=session.profile_id,
            backend=session.backend,
            session=session,
        )

    def stop_active_resources(
        self, pattern: Optional[str], reason: str
    ) -> Dict[str, Any]:
        sessions = _PROFILE_REGISTRY.list_session_infos()
        stopped: List[str] = []
        errors: List[Dict[str, Any]] = []

        with ProfileCommand._state_lock:
            self._reap_dead_sampling_locked()
            exact_profile_id = ProfileCommand._exact_profile_id
            exact_sampler = ProfileCommand._active_exact_sampler
            inflight_id = ProfileCommand._exact_inflight_profile_id
            inflight_sampler = ProfileCommand._exact_inflight_sampler
            if inflight_id is not None:
                ProfileCommand._exact_inflight_cancelled = True
                if exact_sampler is None:
                    exact_sampler = inflight_sampler
                    exact_profile_id = inflight_id
            if exact_profile_id is not None and exact_sampler is not None:
                ProfileCommand._exact_profile_id = None
                ProfileCommand._active_exact_sampler = None
                self._clear_local_exact_sampler_if_matches(exact_sampler)
                exact_timer = self._cancel_exact_timer_if_matches(exact_profile_id)
            else:
                exact_timer = None

        if exact_sampler is not None:
            try:
                exact_sampler.stop()
                if exact_profile_id is not None:
                    stopped.append(exact_profile_id)
            except Exception as exc:
                logger.error(
                    "[peeka Profile] exact sampler cleanup failed (%s)",
                    reason,
                    exc_info=True,
                )
                errors.append({"profile_id": "exact", "error": str(exc)})
        if exact_timer is not None:
            exact_timer.cancel()

        with ProfileCommand._state_lock:
            self._reap_dead_sampling_locked()
            active_sampling_id = ProfileCommand._active_sampling_profile_id
        if active_sampling_id is not None:
            try:
                sampling_error = self._stop_sampling_profile(active_sampling_id)
                if sampling_error is not None:
                    errors.append(
                        {"profile_id": active_sampling_id, "error": sampling_error}
                    )
                else:
                    stopped.append(active_sampling_id)
            except Exception as exc:
                logger.error(
                    "[peeka Profile] sampling cleanup failed (%s)",
                    reason,
                    exc_info=True,
                )
                errors.append({"profile_id": "sampling", "error": str(exc)})

        with ProfileCommand._state_lock:
            self._reap_dead_sampling_locked()
            local_sampling_id = self._sampling_profile_id
            has_local_sampling = (
                self._sampling_thread is not None and local_sampling_id is not None
            )
        if has_local_sampling and local_sampling_id is not None:
            try:
                sampling_error = self._stop_sampling_profile(local_sampling_id)
                if sampling_error is not None:
                    if not any(
                        e.get("profile_id") == local_sampling_id for e in errors
                    ):
                        errors.append(
                            {"profile_id": local_sampling_id, "error": sampling_error}
                        )
                elif local_sampling_id not in stopped:
                    stopped.append(local_sampling_id)
            except Exception as exc:
                logger.error(
                    "[peeka Profile] sampling cleanup failed (%s)",
                    reason,
                    exc_info=True,
                )
                errors.append({"profile_id": "sampling", "error": str(exc)})

        errored_ids = {e.get("profile_id") for e in errors}
        for session in sessions:
            session_id = session["profile_id"]
            if session["status"] != "running":
                continue
            if session_id in stopped or session_id in errored_ids:
                continue
            try:
                _PROFILE_REGISTRY.stop(session_id)
                stopped.append(session_id)
            except Exception as exc:
                logger.error(
                    "[peeka Profile] stop_active_resources failed for %s (%s)",
                    session_id,
                    reason,
                    exc_info=True,
                )
                errors.append({"profile_id": session_id, "error": str(exc)})

        return {"stopped": stopped, "errors": errors}

    def list_active_resources(self) -> Dict[str, Any]:
        sessions = _PROFILE_REGISTRY.list_session_infos()
        active = [
            {
                "profile_id": s["profile_id"],
                "backend": s["backend"],
                "started_at": s["started_at"],
            }
            for s in sessions
            if s["status"] == "running"
        ]
        return {"active": active}
