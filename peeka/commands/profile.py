# pyright: reportArgumentType=false
"""Profile Command - direct management of profile sessions in ProfileRegistry."""

import io
import json
import logging
import sys
import threading
import time
from typing import Any, ClassVar, Dict, List, Optional, TYPE_CHECKING

from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand
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
    _exact_lock: ClassVar[threading.Lock] = threading.Lock()
    _exact_profile_id: ClassVar[Optional[str]] = None
    _active_exact_sampler: ClassVar[Optional[ExactProfileSampler]] = None
    _active_exact_stop_timer: ClassVar[Optional[threading.Timer]] = None
    _sampling_lock: ClassVar[threading.Lock] = threading.Lock()
    _active_sampling_thread: ClassVar[Optional[threading.Thread]] = None
    _active_sampling_stop_event: ClassVar[Optional[threading.Event]] = None
    _active_sampling_profile_id: ClassVar[Optional[str]] = None

    def __init__(self, agent: Optional["PeekaAgent"] = None):
        super().__init__(agent)
        self._exact_sampler: Optional[ExactProfileSampler] = None
        self._exact_stop_timer: Optional[threading.Timer] = None
        self._sampling_thread: Optional[threading.Thread] = None
        self._sampling_stop_event: Optional[threading.Event] = None
        self._sampling_profile_id: Optional[str] = None

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
            with ProfileCommand._sampling_lock:
                active_sampling_id = self._get_active_sampling_profile_id()
            if active_sampling_id is not None:
                return {
                    "status": "error",
                    "error": (
                        "exact and sampling profiles are mutually exclusive; "
                        f"sampling profile already running: {active_sampling_id}"
                    ),
                    "profile_id": active_sampling_id,
                }
            return self._start_exact(params, config)

        if config.backend == "sampling":
            with ProfileCommand._exact_lock:
                active_exact_id = self._active_exact_profile_id()
            if active_exact_id is not None:
                return {
                    "status": "error",
                    "error": (
                        "exact and sampling profiles are mutually exclusive; "
                        f"exact profile already running: {active_exact_id}"
                    ),
                    "profile_id": active_exact_id,
                }
            with ProfileCommand._sampling_lock:
                active_sampling_id = self._get_active_sampling_profile_id()
                if active_sampling_id is not None:
                    return {
                        "status": "error",
                        "error": "Sampling profile already running",
                        "profile_id": active_sampling_id,
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
        with ProfileCommand._exact_lock:
            active_exact_id = self._active_exact_profile_id()
            if active_exact_id is not None:
                return {
                    "status": "error",
                    "error": f"exact profile already running: {active_exact_id}",
                    "profile_id": active_exact_id,
                }

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

        with ProfileCommand._exact_lock:
            active_exact_id = self._active_exact_profile_id()
            if active_exact_id is not None:
                _PROFILE_REGISTRY.stop(profile_id)
                return {
                    "status": "error",
                    "error": f"exact profile already running: {active_exact_id}",
                    "profile_id": active_exact_id,
                }
            ProfileCommand._exact_profile_id = profile_id
            ProfileCommand._active_exact_sampler = sampler
            self._exact_sampler = sampler

        try:
            sampler.start()
        except Exception:
            with ProfileCommand._exact_lock:
                self._exact_sampler = None
                if ProfileCommand._exact_profile_id == profile_id:
                    ProfileCommand._exact_profile_id = None
                    ProfileCommand._active_exact_sampler = None
            _PROFILE_REGISTRY.stop(profile_id)
            raise

        with ProfileCommand._exact_lock:
            if ProfileCommand._exact_profile_id != profile_id:
                return {"status": "success", "profile_id": profile_id}
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
        return {"status": "success", "profile_id": profile_id}

    def _stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        profile_id = params.get("profile_id")
        if not profile_id:
            return {"status": "error", "error": "Missing profile_id"}
        try:
            with ProfileCommand._exact_lock:
                is_exact_owner = profile_id == ProfileCommand._exact_profile_id
                sampler = ProfileCommand._active_exact_sampler if is_exact_owner else None
                if sampler is not None:
                    ProfileCommand._exact_profile_id = None
                    ProfileCommand._active_exact_sampler = None
                    self._clear_local_exact_sampler_if_matches(sampler)
                timer = self._cancel_exact_timer_if_matches(profile_id)
            if sampler is not None:
                sampler.stop()
            if timer is not None:
                timer.cancel()
            self._stop_sampling_profile(profile_id)
            session = _PROFILE_REGISTRY.stop(profile_id)
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
        with ProfileCommand._exact_lock:
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
        with ProfileCommand._exact_lock:
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

    def _timer_matches_profile(self, profile_id: str) -> bool:
        if self._exact_stop_timer is None:
            return False
        return getattr(self._exact_stop_timer, "_peeka_profile_id", None) == profile_id

    def _get_active_sampling_profile_id(self) -> Optional[str]:
        profile_id = ProfileCommand._active_sampling_profile_id
        thread = ProfileCommand._active_sampling_thread
        if profile_id is None or thread is None:
            return None
        if thread.is_alive():
            return profile_id
        ProfileCommand._active_sampling_thread = None
        ProfileCommand._active_sampling_stop_event = None
        ProfileCommand._active_sampling_profile_id = None
        return None

    def _start_sampling(self, profile_id: str, config: ProfileConfig) -> None:
        stop_event = threading.Event()
        self._sampling_stop_event = stop_event
        self._sampling_profile_id = profile_id
        deadline = None
        if config.duration_ms is not None:
            deadline = time.time() + config.duration_ms / 1000.0
        interval = max(float(config.interval_ms) / 1000.0, 0.001)
        thread = threading.Thread(
            target=self._sampling_loop,
            args=(profile_id, interval, stop_event, deadline),
            name=f"peeka-profile-{profile_id}",
            daemon=True,
        )
        self._sampling_thread = thread
        ProfileCommand._active_sampling_thread = thread
        ProfileCommand._active_sampling_stop_event = stop_event
        ProfileCommand._active_sampling_profile_id = profile_id
        thread.start()

    def _stop_sampling(self) -> None:
        profile_id = self._sampling_profile_id
        if self._sampling_stop_event is not None:
            self._sampling_stop_event.set()
        if self._sampling_thread is not None:
            self._sampling_thread.join(timeout=2.0)
        if profile_id is not None:
            try:
                _PROFILE_REGISTRY.stop(profile_id)
            except KeyError:
                logger.debug("sampling profile %s already removed", profile_id)
        self._sampling_thread = None
        self._sampling_stop_event = None
        self._sampling_profile_id = None
        if ProfileCommand._active_sampling_profile_id == profile_id:
            ProfileCommand._active_sampling_thread = None
            ProfileCommand._active_sampling_stop_event = None
            ProfileCommand._active_sampling_profile_id = None

    def _stop_sampling_profile(self, profile_id: str) -> None:
        with ProfileCommand._sampling_lock:
            if profile_id != ProfileCommand._active_sampling_profile_id:
                return
            thread = ProfileCommand._active_sampling_thread
            stop_event = ProfileCommand._active_sampling_stop_event
            ProfileCommand._active_sampling_thread = None
            ProfileCommand._active_sampling_stop_event = None
            ProfileCommand._active_sampling_profile_id = None
            if self._sampling_profile_id == profile_id:
                self._sampling_thread = None
                self._sampling_stop_event = None
                self._sampling_profile_id = None

        if stop_event is not None:
            stop_event.set()
        if thread is not None:
            thread.join(timeout=2.0)
        try:
            _PROFILE_REGISTRY.stop(profile_id)
        except KeyError:
            logger.debug("sampling profile %s already removed", profile_id)

    def _sampling_loop(
        self,
        profile_id: str,
        interval: float,
        stop_event: threading.Event,
        deadline: Optional[float],
    ) -> None:
        expired = False
        try:
            while not stop_event.is_set():
                if deadline is not None and time.time() >= deadline:
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
                with ProfileCommand._sampling_lock:
                    if (
                        ProfileCommand._active_sampling_profile_id == profile_id
                        and ProfileCommand._active_sampling_stop_event is stop_event
                    ):
                        ProfileCommand._active_sampling_thread = None
                        ProfileCommand._active_sampling_stop_event = None
                        ProfileCommand._active_sampling_profile_id = None
                    if (
                        self._sampling_profile_id == profile_id
                        and self._sampling_stop_event is stop_event
                    ):
                        self._sampling_thread = None
                        self._sampling_stop_event = None
                        self._sampling_profile_id = None

    def _collect_sampling_snapshot(self, profile_id: str) -> None:
        current_thread_id = threading.get_ident()
        thread_names = {thread.ident: thread.name for thread in threading.enumerate()}
        for thread_id, frame in sys._current_frames().items():
            if thread_id == current_thread_id:
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
                timestamp=time.time(),
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

        with ProfileCommand._exact_lock:
            exact_profile_id = ProfileCommand._exact_profile_id
            exact_sampler = ProfileCommand._active_exact_sampler
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

        active_sampling_id = ProfileCommand._active_sampling_profile_id
        if active_sampling_id is not None:
            try:
                self._stop_sampling_profile(active_sampling_id)
                stopped.append(active_sampling_id)
            except Exception as exc:
                logger.error(
                    "[peeka Profile] sampling cleanup failed (%s)",
                    reason,
                    exc_info=True,
                )
                errors.append({"profile_id": "sampling", "error": str(exc)})

        if self._sampling_thread is not None:
            try:
                profile_id = self._sampling_profile_id
                self._stop_sampling_profile(profile_id)
                if profile_id is not None:
                    stopped.append(profile_id)
            except Exception as exc:
                logger.error(
                    "[peeka Profile] sampling cleanup failed (%s)",
                    reason,
                    exc_info=True,
                )
                errors.append({"profile_id": "sampling", "error": str(exc)})

        for session in sessions:
            session_id = session["profile_id"]
            if session["status"] != "running":
                continue
            if session_id in stopped:
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
