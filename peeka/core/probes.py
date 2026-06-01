# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportPrivateUsage=false
"""Probe run domain objects.

Implements the ``ProbeRun`` and ``ObservationEvent`` object contracts from
``.sisyphus/plans/session-optimize.md`` §ProbeRun and §ObservationEvent.

Probe status state machine:
    created: probe exists but streaming has not started yet.
    active: probe is actively producing observation events.
    paused: probe is temporarily suspended.
    stopped: probe finished normally and will not emit more events.
    failed: probe terminated with an error and will not emit more events.
"""

import threading
import time
import uuid
from collections import deque
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Deque
from typing import Dict
from typing import FrozenSet
from typing import List
from typing import Literal
from typing import Optional


PROBE_SCHEMA_VERSION = "1"
_RECENT_EVENT_LIMIT = 100

ProbeStatus = Literal["created", "active", "paused", "stopped", "failed"]

TERMINAL_STATUSES = frozenset({"stopped", "failed"})

_LEGAL_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    "created": frozenset({"active"}),
    "active": frozenset({"paused", "stopped", "failed"}),
    "paused": frozenset({"active", "stopped", "failed"}),
    "stopped": frozenset(),
    "failed": frozenset(),
}

_NEXT_VALID_ACTIONS: Dict[str, List[str]] = {
    "created": ["inspect"],
    "active": ["pause", "stop", "inspect"],
    "paused": ["resume", "stop", "inspect"],
    "stopped": ["inspect"],
    "failed": ["inspect", "cleanup"],
}


@dataclass
class ProbeRun:
    """Represents one probe execution lifecycle.

    Attributes:
        id: Public probe identifier.
        target_id: Public target identifier that owns this probe.
        client_session_id: Client session that initiated the probe.
        job_id: Related command job identifier.
        type: Probe kind such as watch, trace, or monitor.
        pattern: Optional user-supplied match pattern.
        config: Probe configuration snapshot.
        status: Current probe lifecycle state.
        created_at: Probe creation timestamp in epoch seconds.
        started_at: Optional activation timestamp.
        stopped_at: Optional terminal timestamp.
        last_event_at: Optional timestamp of the most recent observation event.
        event_count: Total number of observation events recorded.
        last_error: Optional error shaped like {"code": str, "message": str}.
        summary: Optional probe summary payload.
        schema_version: Wire schema version for serialized records.
    """

    id: str
    target_id: str
    client_session_id: str
    job_id: str
    type: str
    pattern: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    status: ProbeStatus = "created"
    created_at: float = 0.0
    started_at: Optional[float] = None
    stopped_at: Optional[float] = None
    last_event_at: Optional[float] = None
    event_count: int = 0
    last_error: Optional[Dict[str, str]] = None
    summary: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = PROBE_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the probe run into a JSON-safe dictionary."""
        result = asdict(self)
        result["next_valid_actions"] = next_valid_actions(self.status)
        result["schema_version"] = self.schema_version
        return result


@dataclass
class ObservationEvent:
    """Represents one emitted observation event for a probe run.

    Attributes:
        event_id: Public observation event identifier.
        probe_id: Public probe identifier that produced this event.
        target_id: Public target identifier that owns this event.
        sequence: Zero-based sequence number scoped to the probe.
        timestamp: Event creation timestamp in epoch seconds.
        payload: JSON-safe event payload.
    """

    event_id: str
    probe_id: str
    target_id: str
    sequence: int
    timestamp: float
    payload: Dict[str, Any] = field(default_factory=dict)


class ProbeRegistry:
    """Thread-safe in-memory registry for probe runs and recent events."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._probes: Dict[str, ProbeRun] = {}
        self._recent_events: Dict[str, Deque[ObservationEvent]] = {}
        self._event_sequences: Dict[str, int] = {}

    def create(
        self,
        target_id: str,
        client_session_id: str,
        job_id: str,
        type: str,
        pattern: Optional[str],
        config: Optional[Dict[str, Any]],
    ) -> ProbeRun:
        """Create and register a probe run.

        Args:
            target_id: Public target identifier for this probe.
            client_session_id: Client session initiating the probe.
            job_id: Related command job identifier.
            type: Probe kind such as watch, trace, or monitor.
            pattern: Optional user-supplied match pattern.
            config: Optional configuration snapshot.

        Returns:
            Newly created probe run.
        """
        now = time.time()
        probe = ProbeRun(
            id="prb_" + uuid.uuid4().hex[:8],
            target_id=target_id,
            client_session_id=client_session_id,
            job_id=job_id,
            type=type,
            pattern=pattern,
            config=dict(config or {}),
            status="created",
            created_at=now,
            started_at=None,
            stopped_at=None,
            last_event_at=None,
            event_count=0,
            last_error=None,
            summary={},
            schema_version=PROBE_SCHEMA_VERSION,
        )
        with self._lock:
            self._probes[probe.id] = probe
            self._recent_events[probe.id] = deque(maxlen=_RECENT_EVENT_LIMIT)
            self._event_sequences[probe.id] = 0
        return probe

    def get(self, probe_id: str) -> Optional[ProbeRun]:
        """Return a probe run by identifier."""
        with self._lock:
            return self._probes.get(probe_id)

    def list(
        self,
        target_id: Optional[str] = None,
        status: Optional[ProbeStatus] = None,
        type: Optional[str] = None,
    ) -> List[ProbeRun]:
        """Return a snapshot of registered probes matching optional filters."""
        with self._lock:
            probes = list(self._probes.values())
            if target_id is not None:
                probes = [probe for probe in probes if probe.target_id == target_id]
            if status is not None:
                probes = [probe for probe in probes if probe.status == status]
            if type is not None:
                probes = [probe for probe in probes if probe.type == type]
            return list(probes)

    def set_status(self, probe_id: str, new_status: ProbeStatus, **fields: Any) -> bool:
        """Transition a probe to a new status if the move is legal.

        Args:
            probe_id: Public probe identifier.
            new_status: Desired new lifecycle state.
            **fields: Optional field overrides applied on successful transition.

        Returns:
            True if the transition was applied, otherwise False.
        """
        with self._lock:
            probe = self._probes.get(probe_id)
            if probe is None:
                return False
            if new_status not in _LEGAL_TRANSITIONS.get(probe.status, frozenset()):
                return False

            now = time.time()
            probe.status = new_status

            if new_status == "active" and probe.started_at is None:
                probe.started_at = now
            if new_status in TERMINAL_STATUSES:
                probe.stopped_at = now

            self._apply_mutation_fields(probe, fields, now)
            return True

    def update_summary(
        self,
        probe_id: str,
        *,
        event_count_delta: int = 1,
        last_event_at: Optional[float] = None,
    ) -> bool:
        """Update event counters and summary metadata for a probe run."""
        with self._lock:
            probe = self._probes.get(probe_id)
            if probe is None:
                return False
            timestamp = time.time() if last_event_at is None else last_event_at
            self._update_summary_locked(
                probe,
                event_count_delta=event_count_delta,
                last_event_at=timestamp,
            )
            return True

    def record_event(
        self, probe_id: str, payload: Dict[str, Any]
    ) -> Optional[ObservationEvent]:
        """Record one observation event for a probe run."""
        with self._lock:
            probe = self._probes.get(probe_id)
            if probe is None:
                return None

            sequence = self._event_sequences.get(probe_id, 0)
            timestamp = time.time()
            event = ObservationEvent(
                event_id=self._build_event_id(probe_id, sequence),
                probe_id=probe_id,
                target_id=probe.target_id,
                sequence=sequence,
                timestamp=timestamp,
                payload=dict(payload),
            )
            self._event_sequences[probe_id] = sequence + 1
            self._recent_events[probe_id].append(event)
            self._update_summary_locked(
                probe,
                event_count_delta=1,
                last_event_at=timestamp,
            )
            return event

    def get_recent_events(self, probe_id: str, limit: int = 100) -> List[ObservationEvent]:
        """Return the most recent observation events for a probe run."""
        if limit <= 0:
            return []
        with self._lock:
            events = self._recent_events.get(probe_id)
            if events is None:
                return []
            return list(events)[-limit:]

    def cleanup(
        self, older_than_seconds: float = 600, status_filter: Optional[ProbeStatus] = None
    ) -> int:
        """Remove terminal probes older than the retention window.

        Args:
            older_than_seconds: Maximum retained age in seconds for terminal probes.
            status_filter: Optional terminal status filter to restrict cleanup.

        Returns:
            Number of removed probes.
        """
        now = time.time()
        removed_count = 0
        with self._lock:
            for probe_id, probe in list(self._probes.items()):
                if probe.status not in TERMINAL_STATUSES:
                    continue
                if status_filter is not None and probe.status != status_filter:
                    continue
                terminal_at = probe.stopped_at if probe.stopped_at is not None else probe.created_at
                if (now - terminal_at) <= older_than_seconds:
                    continue
                self._remove_locked(probe_id)
                removed_count += 1
        return removed_count

    def remove(self, probe_id: str) -> bool:
        """Remove a probe from the registry."""
        with self._lock:
            if probe_id not in self._probes:
                return False
            self._remove_locked(probe_id)
            return True

    def _apply_mutation_fields(
        self, probe: ProbeRun, fields: Dict[str, Any], default_timestamp: float
    ) -> None:
        if "started_at" in fields:
            probe.started_at = fields["started_at"]
        if "stopped_at" in fields:
            probe.stopped_at = fields["stopped_at"]
        if "last_event_at" in fields:
            probe.last_event_at = fields["last_event_at"]
        if "event_count" in fields:
            probe.event_count = int(fields["event_count"])
        if "last_error" in fields and fields["last_error"] is not None:
            last_error = fields["last_error"]
            probe.last_error = {
                "code": str(last_error.get("code", "")),
                "message": str(last_error.get("message", "")),
            }
        if "summary" in fields and fields["summary"] is not None:
            probe.summary = dict(fields["summary"])
        self._sync_summary_fields(probe, default_timestamp)

    def _update_summary_locked(
        self,
        probe: ProbeRun,
        *,
        event_count_delta: int,
        last_event_at: float,
    ) -> None:
        probe.event_count += event_count_delta
        probe.last_event_at = last_event_at
        self._sync_summary_fields(probe, last_event_at)

    def _sync_summary_fields(self, probe: ProbeRun, default_timestamp: float) -> None:
        summary = dict(probe.summary)
        summary["event_count"] = probe.event_count
        summary["last_event_at"] = (
            default_timestamp if probe.last_event_at is None else probe.last_event_at
        )
        summary["status"] = probe.status
        probe.summary = summary

    def _remove_locked(self, probe_id: str) -> None:
        del self._probes[probe_id]
        _ = self._recent_events.pop(probe_id, None)
        _ = self._event_sequences.pop(probe_id, None)

    def _build_event_id(self, probe_id: str, sequence: int) -> str:
        return "evt_{}_{}".format(probe_id[-6:], sequence)


class ProbeContext:
    """Context manager for probe-category commands streaming loop.
    
    Handles probe lifecycle: creates probe on entry, transitions to active,
    records events, marks failures, and ensures proper cleanup on exit.
    
    Example usage:
        with ProbeContext(registry, target_id="tgt_1", client_session_id="cli_1",
                          job_id="job_1234", type="watch", pattern="pkg.fn") as ctx:
            for event_data in stream_observations():
                ctx.record_event(event_data)
                if ctx.should_stop():
                    break
    """

    def __init__(
        self,
        registry: ProbeRegistry,
        *,
        target_id: str,
        client_session_id: Optional[str],
        job_id: Optional[str],
        type: str,
        pattern: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize probe context.
        
        Args:
            registry: ProbeRegistry instance to manage probe lifecycle.
            target_id: Public target identifier.
            client_session_id: Client session initiating the probe.
            job_id: Related command job identifier.
            type: Probe kind such as watch, trace, or monitor.
            pattern: Optional user-supplied match pattern.
            config: Optional probe configuration snapshot.
        """
        self._registry = registry
        self._target_id = target_id
        self._client_session_id = client_session_id or ""
        self._job_id = job_id or ""
        self._type = type
        self._pattern = pattern
        self._config = config
        self._probe: Optional[ProbeRun] = None

    def __enter__(self) -> "ProbeContext":
        """Create probe and transition to active status."""
        self._probe = self._registry.create(
            target_id=self._target_id,
            client_session_id=self._client_session_id,
            job_id=self._job_id,
            type=self._type,
            pattern=self._pattern,
            config=self._config,
        )
        self._registry.set_status(self._probe.id, "active")
        return self

    def __exit__(
        self,
        exc_type: Any,
        exc_val: Any,
        exc_tb: Any,
    ) -> None:
        """Handle probe cleanup on context exit.
        
        On exception: marks probe as failed with error details.
        On clean exit: transitions probe to stopped if still active.
        
        Returns None to propagate exceptions (does not suppress).
        """
        if self._probe is None:
            return None

        if exc_type is not None:
            # Exception path: mark failed with error details
            error_message = str(exc_val) if exc_val is not None else "Unknown error"
            self.mark_failed(
                error_code="COMMAND_EXECUTION_ERROR",
                message=error_message,
            )
            return None  # Do not suppress exception

        # Clean exit: transition to stopped if not already terminal
        # Idempotent: if already failed/stopped, set_status returns False but that's OK
        if self._probe.status not in {"stopped", "failed"}:
            self._registry.set_status(self._probe.id, "stopped")
        return None

    def record_event(self, payload: Dict[str, Any]) -> Optional[ObservationEvent]:
        """Record one observation event for this probe.
        
        Thread-safe: registry uses internal locking.
        
        Args:
            payload: JSON-safe event payload.
            
        Returns:
            ObservationEvent with auto-filled event_id, probe_id, target_id, timestamp.
        """
        if self._probe is None:
            return None
        return self._registry.record_event(self._probe.id, payload)

    def mark_failed(self, error_code: str, message: str) -> None:
        """Mark probe as failed with error details.
        
        Args:
            error_code: Error category code.
            message: Human-readable error message.
        """
        if self._probe is None:
            return
        self._registry.set_status(
            self._probe.id,
            "failed",
            last_error={"code": error_code, "message": message},
        )

    def should_stop(self) -> bool:
        """Check if probe has been externally stopped.
        
        Enables cooperative stop: streaming loops can poll this method
        and exit gracefully when probe.status transitions to stopped.
        
        Returns:
            True if probe status is stopped or failed, otherwise False.
        """
        if self._probe is None:
            return False
        # Refresh from registry to see external status changes
        current = self._registry.get(self._probe.id)
        if current is None:
            return True  # Probe was removed, treat as stopped
        return current.status in {"stopped", "failed"}

    @property
    def probe_id(self) -> Optional[str]:
        """Return the created probe identifier."""
        return self._probe.id if self._probe is not None else None

    @property
    def probe(self) -> Optional[ProbeRun]:
        """Return the created ProbeRun dataclass."""
        return self._probe


def next_valid_actions(status: ProbeStatus) -> List[str]:
    """Return the next valid actions for a probe status."""
    return list(_NEXT_VALID_ACTIONS.get(status, []))


probe_registry = ProbeRegistry()
