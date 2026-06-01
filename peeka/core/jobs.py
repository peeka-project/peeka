# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportPrivateUsage=false
"""Command job domain objects.

Implements the ``CommandJob`` object contract from
``.sisyphus/plans/session-optimize.md`` §CommandJob.

Job status state machine:
    created: job exists but execution has not started yet.
    running: command execution is active.
    streaming: command execution is actively producing long-lived output.
    completed: command finished successfully.
    failed: command finished with an error.
    cancelled: command was cancelled before normal completion.
    interrupted: command was interrupted by an external request.
    timed_out: command exceeded its allowed runtime.
"""

import json
import threading
import time
import uuid
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import FrozenSet
from typing import List
from typing import Literal
from typing import Optional
from typing import Tuple


JOB_SCHEMA_VERSION = "1"

JobStatus = Literal[
    "created",
    "running",
    "streaming",
    "completed",
    "failed",
    "cancelled",
    "interrupted",
    "timed_out",
]
JobCategory = Literal["snapshot", "probe", "mutation"]

TERMINAL_STATUSES = frozenset(
    {"completed", "failed", "cancelled", "interrupted", "timed_out"}
)

_LEGAL_TRANSITIONS: Dict[str, FrozenSet[str]] = {
    "created": frozenset({"running"}),
    "running": frozenset(
        {
            "streaming",
            "completed",
            "failed",
            "cancelled",
            "interrupted",
            "timed_out",
        }
    ),
    "streaming": frozenset(
        {"completed", "failed", "cancelled", "interrupted", "timed_out"}
    ),
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "interrupted": frozenset(),
    "timed_out": frozenset(),
}

_TRUNCATED_SENTINEL = "...[truncated]"


@dataclass
class CommandJob:
    """Represents one command execution lifecycle.

    Attributes:
        id: Public job identifier.
        target_id: Public target identifier that owns this job.
        client_session_id: Client session that initiated the job.
        command_type: Command namespace or command name.
        action: Requested command action.
        params: Input parameter snapshot for the command.
        category: Command concurrency category.
        status: Current job lifecycle state.
        foreground: Whether the job occupies foreground execution for its client.
        created_at: Job creation timestamp in epoch seconds.
        started_at: Optional execution start timestamp.
        updated_at: Last lifecycle mutation timestamp.
        completed_at: Optional terminal timestamp.
        result_summary: Bounded summary of command output.
        last_error: Optional error shaped like {"code": str, "message": str}.
    """

    id: str
    target_id: str
    client_session_id: str
    command_type: str
    action: str
    params: Dict[str, Any] = field(default_factory=dict)
    category: JobCategory = "snapshot"
    status: JobStatus = "created"
    foreground: bool = True
    created_at: float = 0.0
    started_at: Optional[float] = None
    updated_at: float = 0.0
    completed_at: Optional[float] = None
    result_summary: Dict[str, Any] = field(default_factory=dict)
    last_error: Optional[Dict[str, str]] = None


class JobRegistry:
    """Thread-safe in-memory registry for command jobs."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._jobs: Dict[str, CommandJob] = {}

    def create(
        self,
        target_id: str,
        client_session_id: str,
        command_type: str,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        category: JobCategory = "snapshot",
        foreground: bool = True,
    ) -> CommandJob:
        """Create and register a command job.

        Args:
            target_id: Public target identifier for this job.
            client_session_id: Client session initiating the job.
            command_type: Command namespace or name.
            action: Requested action for the command.
            params: Optional parameter snapshot.
            category: Concurrency category for the command.
            foreground: Whether the job should be considered foreground.

        Returns:
            Newly created command job.
        """
        now = time.time()
        job = CommandJob(
            id="job_" + uuid.uuid4().hex[:12],
            target_id=target_id,
            client_session_id=client_session_id,
            command_type=command_type,
            action=action,
            params=dict(params or {}),
            category=category,
            status="created",
            foreground=foreground,
            created_at=now,
            started_at=None,
            updated_at=now,
            completed_at=None,
            result_summary={},
            last_error=None,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[CommandJob]:
        """Return a command job by identifier."""
        with self._lock:
            return self._jobs.get(job_id)

    def list(
        self,
        target: Optional[str] = None,
        client: Optional[str] = None,
        status: Optional[JobStatus] = None,
    ) -> List[CommandJob]:
        """Return a snapshot of registered jobs matching optional filters."""
        with self._lock:
            jobs = list(self._jobs.values())
            if target is not None:
                jobs = [job for job in jobs if job.target_id == target]
            if client is not None:
                jobs = [job for job in jobs if job.client_session_id == client]
            if status is not None:
                jobs = [job for job in jobs if job.status == status]
            return list(jobs)

    def set_status(
        self,
        job_id: str,
        new_status: JobStatus,
        result_summary: Optional[Dict[str, Any]] = None,
        last_error: Optional[Dict[str, str]] = None,
    ) -> bool:
        """Transition a job to a new status if the move is legal.

        Args:
            job_id: Public job identifier.
            new_status: Desired new lifecycle state.
            result_summary: Optional bounded output summary.
            last_error: Optional terminal error payload.

        Returns:
            True if the transition was applied, otherwise False.
        """
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if new_status not in _LEGAL_TRANSITIONS.get(job.status, frozenset()):
                return False

            now = time.time()
            job.status = new_status
            job.updated_at = now

            if new_status == "running" and job.started_at is None:
                job.started_at = now
            if new_status in TERMINAL_STATUSES:
                job.completed_at = now

            if result_summary is not None:
                pruned_summary, truncated = prune_result_summary(result_summary)
                if truncated and "_truncated" not in pruned_summary:
                    pruned_summary["_truncated"] = True
                job.result_summary = pruned_summary
            if last_error is not None:
                job.last_error = {
                    "code": str(last_error.get("code", "")),
                    "message": str(last_error.get("message", "")),
                }

            return True

    def remove(self, job_id: str) -> bool:
        """Remove a job from the registry.

        Args:
            job_id: Public job identifier.

        Returns:
            True if the job was removed, False if not found.
        """
        with self._lock:
            if job_id not in self._jobs:
                return False
            del self._jobs[job_id]
            return True

    def cleanup(
        self, now: Optional[float] = None, retention_seconds: float = 600.0
    ) -> List[str]:
        """Remove terminal jobs older than the retention window.

        Args:
            now: Current epoch timestamp in seconds. Defaults to time.time().
            retention_seconds: Maximum age for retained terminal jobs.

        Returns:
            List of removed job identifiers.
        """
        if now is None:
            now = time.time()

        removed_ids: List[str] = []
        with self._lock:
            for job_id, job in list(self._jobs.items()):
                if job.status not in TERMINAL_STATUSES:
                    continue
                terminal_at = job.completed_at if job.completed_at is not None else job.updated_at
                if (now - terminal_at) <= retention_seconds:
                    continue
                removed_ids.append(job_id)
                del self._jobs[job_id]
        return removed_ids


def to_dict(job: CommandJob) -> Dict[str, Any]:
    """Serialize a command job into a JSON-safe dictionary."""
    result = {"schema_version": JOB_SCHEMA_VERSION}
    result.update(asdict(job))
    return result


def prune_result_summary(
    data: Dict[str, Any], max_size: int = 65536, max_keys: int = 20
) -> Tuple[Dict[str, Any], bool]:
    """Prune a result summary to bounded key and serialized size limits."""
    truncated = False
    pruned: Dict[str, Any] = {}

    for index, (key, value) in enumerate(data.items()):
        if index >= max_keys:
            truncated = True
            break
        pruned[key] = value

    while _json_size(pruned) > max_size:
        next_pruned = _shrink_top_level(pruned)
        if next_pruned == pruned:
            break
        pruned = next_pruned
        truncated = True

    if _json_size(pruned) > max_size:
        pruned = _force_fit(pruned, max_size)
        truncated = True

    return pruned, truncated


def _json_size(value: Dict[str, Any]) -> int:
    return len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))


def _shrink_top_level(data: Dict[str, Any]) -> Dict[str, Any]:
    if not data:
        return {}

    serialized_sizes = {
        key: len(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))
        for key, value in data.items()
    }
    largest_key = max(serialized_sizes, key=lambda key: serialized_sizes[key])
    shrunk = dict(data)
    shrunk[largest_key] = _shrink_value(shrunk[largest_key])
    return shrunk


def _shrink_value(value: Any) -> Any:
    if isinstance(value, str):
        if len(value) <= len(_TRUNCATED_SENTINEL):
            return _TRUNCATED_SENTINEL
        keep = max(8, len(value) // 2)
        return value[:keep] + _TRUNCATED_SENTINEL

    if isinstance(value, list):
        if not value:
            return value
        if len(value) > 3:
            return [_shrink_value(item) for item in value[:3]] + [_TRUNCATED_SENTINEL]
        shrunk_items = [_shrink_value(item) for item in value]
        if shrunk_items == value:
            return [_TRUNCATED_SENTINEL]
        return shrunk_items

    if isinstance(value, dict):
        if not value:
            return value
        items = list(value.items())
        if len(items) > 3:
            result = {key: _shrink_value(item) for key, item in items[:3]}
            result["truncated"] = True
            return result
        result = {key: _shrink_value(item) for key, item in items}
        if result == value:
            return {"truncated": True}
        return result

    rendered = str(value)
    if len(rendered) <= len(_TRUNCATED_SENTINEL):
        return rendered
    keep = max(8, len(rendered) // 2)
    return rendered[:keep] + _TRUNCATED_SENTINEL


def _force_fit(data: Dict[str, Any], max_size: int) -> Dict[str, Any]:
    if not data:
        return {}

    key = next(iter(data))
    value = data[key]

    if isinstance(value, str):
        result = {key: value}
        while _json_size(result) > max_size and result[key] != _TRUNCATED_SENTINEL:
            current_value = result[key]
            if len(current_value) <= len(_TRUNCATED_SENTINEL) + 8:
                result[key] = _TRUNCATED_SENTINEL
            else:
                result[key] = current_value[: max(8, len(current_value) // 2)] + _TRUNCATED_SENTINEL
        return result

    return {key: _TRUNCATED_SENTINEL}


job_registry = JobRegistry()
