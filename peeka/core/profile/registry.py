# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnnecessaryIsInstance=false, reportUnreachable=false, reportUnusedCallResult=false, reportUnnecessaryComparison=false
"""Thread-safe in-memory registry for profile sessions."""

import time
import uuid
from copy import deepcopy
from threading import Lock
from typing import Dict
from typing import List
from typing import Optional

from peeka.core.profile.models import ProfileConfig
from peeka.core.profile.models import ProfileSession
from peeka.core.profile.models import ProfileSummary
from peeka.core.profile.models import SampleRecord


class ProfileRegistry:
    """Manage profile session lifecycles in memory with bounded retention."""

    def __init__(self, max_sessions: int = 50) -> None:
        if max_sessions < 0:
            raise ValueError("max_sessions must be greater than or equal to 0")
        self._lock: Lock = Lock()
        self._max_sessions: int = max_sessions
        self._sessions: Dict[str, ProfileSession] = {}

    def start(self, config: ProfileConfig) -> str:
        """Start a new profile session and return its identifier."""
        now = time.time()
        profile_id = self._new_profile_id()
        session = ProfileSession(
            profile_id=profile_id,
            backend=config.backend,
            config=deepcopy(config),
            status="running",
            started_at=now,
            ended_at=None,
        )

        with self._lock:
            while profile_id in self._sessions:
                profile_id = self._new_profile_id()
                session.profile_id = profile_id
            self._sessions[profile_id] = session
        return profile_id

    def stop(
        self,
        profile_id: str,
        overflow: bool = False,
        dropped_events: int = 0,
    ) -> ProfileSession:
        """Stop a running profile session and return a snapshot of it."""
        with self._lock:
            session = self._sessions.get(profile_id)
            if session is None:
                raise KeyError(profile_id)

            if session.status != "stopped":
                session.status = "stopped"
                session.ended_at = time.time()
            elif session.ended_at is None:
                session.ended_at = time.time()
            preserved_overflow = overflow
            preserved_dropped_events = dropped_events
            if session.summary is not None:
                preserved_overflow = overflow or session.summary.overflow
                if dropped_events == 0 and session.summary.dropped_events:
                    preserved_dropped_events = session.summary.dropped_events
            session.summary = self._build_summary(
                session,
                overflow=preserved_overflow,
                dropped_events=preserved_dropped_events,
            )

            _ = self._evict_if_needed()
            return deepcopy(session)

    def snapshot(self, profile_id: str) -> ProfileSession:
        """Return a deep copy of the current session state."""
        with self._lock:
            session = self._sessions.get(profile_id)
            if session is None:
                raise KeyError(profile_id)
            return deepcopy(session)

    def list_sessions(self) -> List[ProfileSession]:
        """Return snapshots of all tracked sessions."""
        with self._lock:
            return [deepcopy(session) for session in self._sessions.values()]

    def cleanup(
        self,
        older_than_secs: Optional[float] = None,
        max_sessions: Optional[int] = None,
    ) -> int:
        """Remove stopped sessions that exceed the age or retention bounds."""
        now = time.time()
        removed = 0
        effective_max = self._max_sessions if max_sessions is None else max_sessions

        with self._lock:
            if older_than_secs is not None:
                for profile_id, session in list(self._sessions.items()):
                    if session.status != "stopped" or session.ended_at is None:
                        continue
                    if (now - session.ended_at) <= older_than_secs:
                        continue
                    del self._sessions[profile_id]
                    removed += 1

            if effective_max >= 0:
                removed += self._evict_if_needed(effective_max)

        return removed

    def add_sample(self, profile_id: str, sample: SampleRecord) -> int:
        """Append a sample to a running session while respecting sample limits.

        The registry takes ownership of ``sample``; callers must not mutate it
        afterwards. This avoids a deep copy on the hot sampling path.

        Args:
            profile_id: Target session identifier.
            sample: Freshly built sample record.

        Returns:
            The session's sample count after the call, or ``-1`` when the
            session is missing or no longer running.
        """
        with self._lock:
            session = self._sessions.get(profile_id)
            if session is None or session.status != "running":
                return -1
            max_samples = session.config.max_samples or 100000
            if len(session.samples) < max_samples:
                session.samples.append(sample)
            return len(session.samples)

    def get_session(self, profile_id: str) -> Optional[ProfileSession]:
        """Return a copy of the session if it exists."""
        with self._lock:
            session = self._sessions.get(profile_id)
            if session is None:
                return None
            return deepcopy(session)

    def remove_session(self, profile_id: str) -> bool:
        """Remove one profile session by identifier if it exists."""
        with self._lock:
            if profile_id not in self._sessions:
                return False
            del self._sessions[profile_id]
            return True

    def _evict_if_needed(self, max_sessions: Optional[int] = None) -> int:
        """Evict the oldest stopped sessions when the retention limit is exceeded."""
        limit = self._max_sessions if max_sessions is None else max_sessions
        if limit < 0:
            return 0

        stopped_sessions = [
            session
            for session in self._sessions.values()
            if session.status == "stopped"
        ]
        if len(stopped_sessions) <= limit:
            return 0

        removed = 0
        stopped_sessions.sort(
            key=lambda session: (
                float("inf") if session.ended_at is None else session.ended_at,
                session.started_at,
                session.profile_id,
            )
        )
        for session in stopped_sessions[: len(stopped_sessions) - limit]:
            if session.profile_id in self._sessions:
                del self._sessions[session.profile_id]
                removed += 1
        return removed

    def _new_profile_id(self) -> str:
        return "prof_" + uuid.uuid4().hex[:12]

    def _build_summary(
        self,
        session: ProfileSession,
        overflow: bool = False,
        dropped_events: int = 0,
    ) -> ProfileSummary:
        ended_at = session.ended_at if session.ended_at is not None else time.time()
        return ProfileSummary(
            sample_count=len(session.samples),
            duration_ms=max((ended_at - session.started_at) * 1000.0, 0.0),
            start_time=session.started_at,
            top_functions=[],
            overflow=overflow,
            dropped_events=dropped_events,
        )
