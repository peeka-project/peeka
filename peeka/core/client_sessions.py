# pyright: reportDeprecated=false, reportExplicitAny=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnannotatedClassAttribute=false, reportAny=false
"""Client session domain objects.

Implements the ``ClientSession`` object contract from
``.sisyphus/plans/session-optimize.md`` §ClientSession.

Client input state machine:
    idle: client is connected but has no pending input exchange.
    waiting_input: client is waiting for user or tool input.
    sending: client is sending a command or payload.
    streaming: client is actively receiving streaming output.
"""

import threading
import time
import uuid
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from typing import Any
from typing import Dict
from typing import List
from typing import Literal
from typing import Optional


CLIENT_SCHEMA_VERSION = "1"

ClientSource = Literal["cli", "tui", "mcp", "api", "internal"]
InputStatus = Literal["idle", "waiting_input", "sending", "streaming"]


@dataclass
class ClientSession:
    """Represents one client interaction context for a target.

    Attributes:
        client_session_id: Public client session identifier.
        target_id: Public target identifier that owns this client.
        source: Origin of the client request.
        user_id: Optional user identity associated with the client.
        input_status: Current client input lifecycle state.
        foreground_job_id: Optional foreground job currently owned by the client.
        created_at: Client creation timestamp in epoch seconds.
        last_access_at: Last client access timestamp in epoch seconds.
        result_consumers: Result consumer identifiers associated with this client.
        auth: Optional authentication metadata reserved for future use.
    """

    client_session_id: str
    target_id: str
    source: ClientSource
    user_id: Optional[str]
    input_status: InputStatus
    foreground_job_id: Optional[str]
    created_at: float
    last_access_at: float
    result_consumers: List[str] = field(default_factory=list)
    auth: Optional[Dict[str, Any]] = None


class ClientRegistry:
    """Thread-safe in-memory registry for client sessions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._clients: Dict[str, ClientSession] = {}

    def create(
        self,
        target_id: str,
        source: ClientSource,
        user_id: Optional[str] = None,
    ) -> ClientSession:
        """Create and register a client session.

        Args:
            target_id: Public target identifier for this client.
            source: Origin of the client request.
            user_id: Optional user identity for the client.

        Returns:
            Newly created client session.
        """
        now = time.time()
        client = ClientSession(
            client_session_id="client_" + uuid.uuid4().hex[:8],
            target_id=target_id,
            source=source,
            user_id=user_id,
            input_status="idle",
            foreground_job_id=None,
            created_at=now,
            last_access_at=now,
            result_consumers=[],
            auth=None,
        )
        with self._lock:
            self._clients[client.client_session_id] = client
        return client

    def get(self, client_session_id: str) -> Optional[ClientSession]:
        """Return a client session by identifier and refresh access time.

        Args:
            client_session_id: Public client session identifier.

        Returns:
            Client session if present, otherwise None.
        """
        with self._lock:
            client = self._clients.get(client_session_id)
            if client is None:
                return None
            client.last_access_at = time.time()
            return client

    def list(self, target_id: Optional[str] = None) -> List[ClientSession]:
        """Return a snapshot of registered client sessions.

        Args:
            target_id: Optional target filter.

        Returns:
            List of client sessions matching the filter.
        """
        with self._lock:
            clients = list(self._clients.values())
            if target_id is None:
                return list(clients)
            return [client for client in clients if client.target_id == target_id]

    def set_foreground_job(self, client_session_id: str, job_id: str) -> bool:
        """Set the current foreground job for a client session.

        Args:
            client_session_id: Public client session identifier.
            job_id: Public job identifier to assign as foreground.

        Returns:
            True if the client exists and was updated, otherwise False.
        """
        with self._lock:
            client = self._clients.get(client_session_id)
            if client is None:
                return False
            client.foreground_job_id = job_id
            client.last_access_at = time.time()
            return True

    def clear_foreground_job(
        self, client_session_id: str, expected_job_id: Optional[str] = None
    ) -> bool:
        """Clear the current foreground job for a client session.

        Args:
            client_session_id: Public client session identifier.
            expected_job_id: Optional guard that must match the current
                foreground job identifier before clearing.

        Returns:
            True if the client exists and was cleared, otherwise False.
        """
        with self._lock:
            client = self._clients.get(client_session_id)
            if client is None:
                return False
            if (
                expected_job_id is not None
                and client.foreground_job_id != expected_job_id
            ):
                return False
            client.foreground_job_id = None
            client.last_access_at = time.time()
            return True

    def close(self, client_session_id: str) -> bool:
        """Close a client session if it exists.

        Args:
            client_session_id: Public client session identifier.

        Returns:
            True if the client existed and was removed, otherwise False.
        """
        with self._lock:
            if client_session_id not in self._clients:
                return False
            del self._clients[client_session_id]
            return True

    def cleanup_idle(
        self, now: Optional[float] = None, idle_threshold_seconds: float = 900.0
    ) -> List[str]:
        """Close idle client sessions that have no foreground job.

        Args:
            now: Current epoch timestamp in seconds. Defaults to time.time().
            idle_threshold_seconds: Maximum idle age before cleanup.

        Returns:
            List of closed client session identifiers.
        """
        if now is None:
            now = time.time()
        closed_ids = []
        with self._lock:
            for client_session_id, client in list(self._clients.items()):
                if client.foreground_job_id is not None:
                    continue
                if (now - client.last_access_at) <= idle_threshold_seconds:
                    continue
                closed_ids.append(client_session_id)
                del self._clients[client_session_id]
        return closed_ids


def to_dict(client: ClientSession) -> Dict[str, Any]:
    """Serialize a client session into a JSON-safe dictionary."""
    result = {"schema_version": CLIENT_SCHEMA_VERSION}
    result.update(asdict(client))
    return result
