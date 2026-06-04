# pyright: reportDeprecated=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportAny=false
"""Result consumer domain objects.

Implements the ``ResultConsumer`` object contract from
``.sisyphus/plans/session-optimize.md`` §ResultConsumer.

Consumer status state machine:
    active: consumer can accept new records and be drained.
    draining: consumer is actively serving a drain request.
    closed: consumer was explicitly closed and cannot accept new records.
    failed: consumer encountered a terminal internal error.
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
from typing import List
from typing import Literal
from typing import Optional

from peeka.core.jobs import prune_result_summary


RESULT_CONSUMER_SCHEMA_VERSION = "1"
RESULT_CONSUMER_RECORD_SCHEMA_VERSION = "1"
MAX_RESULT_CONSUMERS = 256
MAX_CONSUMER_BUFFER_SIZE = 10000

ConsumerSource = Literal["cli", "tui", "mcp", "api", "internal"]
ConsumerScopeType = Literal["job", "probe", "target"]
ConsumerStatus = Literal["active", "draining", "closed", "failed"]
BackpressurePolicy = Literal["drop_oldest", "drop_newest", "fail"]
RecordType = Literal["result", "observation", "error", "summary"]


@dataclass
class ConsumerRecord:
    """Represents one buffered output record for a result consumer."""

    sequence: int
    emitted_at: float
    source_type: Literal["job", "probe"]
    source_id: str
    record_type: RecordType
    payload: Dict[str, Any] = field(default_factory=dict)
    schema_version: str = RESULT_CONSUMER_RECORD_SCHEMA_VERSION


@dataclass
class ResultConsumer:
    """Represents one consumer subscribed to job/probe outputs."""

    consumer_id: str
    target_id: str
    client_session_id: Optional[str]
    source: ConsumerSource
    scope_type: ConsumerScopeType
    scope_id: str
    status: ConsumerStatus
    created_at: float
    updated_at: float
    last_drain_at: Optional[float]
    max_buffer_size: int
    buffer_size: int
    dropped_count: int
    backpressure_policy: BackpressurePolicy
    last_error: Optional[Dict[str, str]] = None
    schema_version: str = RESULT_CONSUMER_SCHEMA_VERSION

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the consumer into a JSON-safe dictionary."""
        result = asdict(self)
        result["next_valid_actions"] = next_valid_actions(self.status)
        result["schema_version"] = self.schema_version
        return result


def to_dict(consumer: ResultConsumer) -> Dict[str, Any]:
    """Serialize a consumer into a JSON-safe dictionary."""
    return consumer.to_dict()


def next_valid_actions(status: ConsumerStatus) -> List[str]:
    """Return the next valid actions for a consumer status."""
    if status == "active":
        return ["drain", "close", "inspect"]
    if status == "draining":
        return ["drain", "close", "inspect"]
    if status == "closed":
        return ["inspect", "cleanup"]
    if status == "failed":
        return ["inspect", "cleanup"]
    return []


class ResultConsumerRegistry:
    """Thread-safe in-memory registry for result consumers and records."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._consumers: Dict[str, ResultConsumer] = {}
        self._records: Dict[str, Deque[ConsumerRecord]] = {}
        self._next_sequences: Dict[str, int] = {}

    def create(
        self,
        target_id: str,
        source: ConsumerSource,
        scope_type: ConsumerScopeType,
        scope_id: str,
        client_session_id: Optional[str] = None,
        max_buffer_size: int = 1000,
        backpressure_policy: BackpressurePolicy = "drop_oldest",
    ) -> ResultConsumer:
        """Create and register a result consumer."""
        if max_buffer_size <= 0:
            raise ValueError("max_buffer_size must be greater than zero")
        if max_buffer_size > MAX_CONSUMER_BUFFER_SIZE:
            raise ValueError(
                f"max_buffer_size must be <= {MAX_CONSUMER_BUFFER_SIZE}"
            )

        now = time.time()
        consumer = ResultConsumer(
            consumer_id="consumer_" + uuid.uuid4().hex[:8],
            target_id=target_id,
            client_session_id=client_session_id,
            source=source,
            scope_type=scope_type,
            scope_id=scope_id,
            status="active",
            created_at=now,
            updated_at=now,
            last_drain_at=None,
            max_buffer_size=max_buffer_size,
            buffer_size=0,
            dropped_count=0,
            backpressure_policy=backpressure_policy,
            last_error=None,
            schema_version=RESULT_CONSUMER_SCHEMA_VERSION,
        )
        with self._lock:
            if len(self._consumers) >= MAX_RESULT_CONSUMERS:
                raise ValueError(
                    f"consumer limit exceeded ({MAX_RESULT_CONSUMERS})"
                )
            self._consumers[consumer.consumer_id] = consumer
            self._records[consumer.consumer_id] = deque(maxlen=max_buffer_size)
            self._next_sequences[consumer.consumer_id] = 0
        return consumer

    def get(self, consumer_id: str) -> Optional[ResultConsumer]:
        """Return a consumer by identifier."""
        with self._lock:
            return self._consumers.get(consumer_id)

    def list(
        self,
        target_id: Optional[str] = None,
        client_session_id: Optional[str] = None,
        scope_type: Optional[ConsumerScopeType] = None,
        scope_id: Optional[str] = None,
        status: Optional[ConsumerStatus] = None,
    ) -> List[ResultConsumer]:
        """Return consumers matching the provided filters."""
        with self._lock:
            consumers = list(self._consumers.values())
            if target_id is not None:
                consumers = [item for item in consumers if item.target_id == target_id]
            if client_session_id is not None:
                consumers = [
                    item
                    for item in consumers
                    if item.client_session_id == client_session_id
                ]
            if scope_type is not None:
                consumers = [item for item in consumers if item.scope_type == scope_type]
            if scope_id is not None:
                consumers = [item for item in consumers if item.scope_id == scope_id]
            if status is not None:
                consumers = [item for item in consumers if item.status == status]
            return list(consumers)

    def append_record(
        self,
        consumer_id: str,
        source_type: Literal["job", "probe"],
        source_id: str,
        record_type: RecordType,
        payload: Dict[str, Any],
    ) -> bool:
        """Append one record to a consumer according to its backpressure policy."""
        normalized_payload = _normalize_record_payload(payload)
        with self._lock:
            consumer = self._consumers.get(consumer_id)
            if consumer is None:
                return False
            if consumer.status in ("closed", "failed"):
                return False

            queue = self._records[consumer_id]
            sequence = self._next_sequences[consumer_id]
            now = time.time()

            if len(queue) >= consumer.max_buffer_size:
                if consumer.backpressure_policy == "drop_newest":
                    consumer.dropped_count += 1
                    consumer.updated_at = now
                    consumer.buffer_size = len(queue)
                    return True
                if consumer.backpressure_policy == "fail":
                    consumer.status = "failed"
                    consumer.updated_at = now
                    consumer.last_error = {
                        "code": "CONSUMER_BACKPRESSURE",
                        "message": "Consumer buffer reached maximum capacity",
                    }
                    consumer.buffer_size = len(queue)
                    return False

                if queue:
                    queue.popleft()
                consumer.dropped_count += 1

            queue.append(
                ConsumerRecord(
                    sequence=sequence,
                    emitted_at=now,
                    source_type=source_type,
                    source_id=source_id,
                    record_type=record_type,
                    payload=normalized_payload,
                    schema_version=RESULT_CONSUMER_RECORD_SCHEMA_VERSION,
                )
            )
            self._next_sequences[consumer_id] = sequence + 1
            consumer.updated_at = now
            consumer.buffer_size = len(queue)
            return True

    def append_for_scope(
        self,
        target_id: str,
        source_type: Literal["job", "probe"],
        source_id: str,
        record_type: RecordType,
        payload: Dict[str, Any],
    ) -> int:
        """Append one record to all consumers interested in this scope.

        Matches:
        - direct scope subscriptions (`scope_type == source_type` and same scope_id)
        - target-wide subscriptions (`scope_type == "target"` and scope_id == target_id)
        """
        with self._lock:
            matching_ids = [
                consumer.consumer_id
                for consumer in self._consumers.values()
                if (
                    consumer.scope_type == source_type and consumer.scope_id == source_id
                )
                or (
                    consumer.scope_type == "target" and consumer.scope_id == target_id
                )
            ]

        appended = 0
        for consumer_id in matching_ids:
            if self.append_record(
                consumer_id,
                source_type=source_type,
                source_id=source_id,
                record_type=record_type,
                payload=payload,
            ):
                appended += 1
        return appended

    def drain(
        self,
        consumer_id: str,
        limit: int = 100,
        after_sequence: Optional[int] = None,
        timeout_ms: int = 0,
    ) -> Optional[Dict[str, Any]]:
        """Drain records for a consumer without removing retained history."""
        if limit <= 0:
            raise ValueError("limit must be greater than zero")

        timeout_deadline = time.time() + (max(timeout_ms, 0) / 1000.0)
        timed_out = False

        while True:
            with self._lock:
                consumer = self._consumers.get(consumer_id)
                if consumer is None:
                    return None

                queue = self._records[consumer_id]
                consumer.status = "draining" if consumer.status == "active" else consumer.status
                eligible = list(queue)
                if after_sequence is not None:
                    eligible = [record for record in eligible if record.sequence > after_sequence]

                if eligible or timeout_ms <= 0 or time.time() >= timeout_deadline:
                    selected = eligible[:limit]
                    has_more = len(eligible) > len(selected)
                    now = time.time()
                    consumer.last_drain_at = now
                    consumer.updated_at = now
                    if consumer.status == "draining":
                        consumer.status = "active"
                    consumer.buffer_size = len(queue)
                    timed_out = not bool(eligible) and timeout_ms > 0 and time.time() >= timeout_deadline

                    next_sequence = (
                        selected[-1].sequence
                        if selected
                        else after_sequence
                        if after_sequence is not None
                        else 0
                    )

                    return {
                        "consumer_id": consumer_id,
                        "records": [asdict(record) for record in selected],
                        "next_sequence": next_sequence,
                        "has_more": has_more,
                        "timed_out": timed_out,
                    }

                if consumer.status == "draining":
                    consumer.status = "active"

            time.sleep(0.01)

    def close(self, consumer_id: str) -> bool:
        """Mark a consumer as closed."""
        with self._lock:
            consumer = self._consumers.get(consumer_id)
            if consumer is None:
                return False
            if consumer.status == "closed":
                return True
            consumer.status = "closed"
            consumer.updated_at = time.time()
            return True

    def remove(self, consumer_id: str) -> Optional[ResultConsumer]:
        """Remove a consumer from the registry and return it if present."""
        with self._lock:
            consumer = self._consumers.pop(consumer_id, None)
            if consumer is None:
                return None
            self._records.pop(consumer_id, None)
            self._next_sequences.pop(consumer_id, None)
            return consumer

    def cleanup(self, closed_only: bool = True) -> List[str]:
        """Remove closed/failed consumers from the registry."""
        removed_ids: List[str] = []
        with self._lock:
            for consumer_id, consumer in list(self._consumers.items()):
                if closed_only and consumer.status not in ("closed", "failed"):
                    continue
                removed_ids.append(consumer_id)
                del self._consumers[consumer_id]
                del self._records[consumer_id]
                del self._next_sequences[consumer_id]
        return removed_ids


result_consumer_registry = ResultConsumerRegistry()


def _normalize_record_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Bound payload size before storing records in consumer buffers."""
    normalized = dict(payload)
    pruned, truncated = prune_result_summary(normalized)
    if truncated and "_truncated" not in pruned:
        pruned["_truncated"] = True
    return pruned
