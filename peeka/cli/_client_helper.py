"""
Ephemeral client lifecycle helper for CLI handlers.

Provides automatic client session creation and cleanup for legacy CLI commands
that don't explicitly manage client lifecycle via `--client` flag.
"""

import sys
from contextlib import contextmanager
from typing import Any
from typing import Iterator, Optional

from peeka.core.client import StreamingAgentClient
from peeka.core.targets import get_target


@contextmanager
def ephemeral_client(
    target_id: str,
    source: str = "cli",
    user: Optional[str] = None,
    agent_client: Optional[Any] = None,
) -> Iterator[str]:
    """Create an ephemeral client session for the duration of a CLI command.

    Args:
        target_id: Public target identifier for the client session.
        source: Client source used for client.create.
        user: Optional user identifier passed through to client.create.
        agent_client: Optional pre-connected agent client. If omitted, a short-lived
            StreamingAgentClient is created from the target_id.

    Yields:
        client_session_id: Public identifier for the ephemeral client session.

    Example:
        with ephemeral_client(target_id) as cid:
            # Use cid for downstream job/probe context
            pass
        # Client is automatically closed on exit
    """
    client_session_id = None
    owned_client = None
    try:
        if agent_client is None:
            target = get_target(target_id)
            if target is None:
                raise RuntimeError("[TRANSPORT_ERROR] Target {0!r} not found".format(target_id))
            owned_client = StreamingAgentClient(target.socket_path)
            connect_result = owned_client.connect()
            if connect_result.get("status") != "success":
                message = connect_result.get("error", "Failed to connect to agent")
                raise RuntimeError("[TRANSPORT_ERROR] {0}".format(message))
            agent_client = owned_client

        # Create ephemeral client via agent
        create_response = agent_client.send_command(
            {
                "type": "client",
                "action": "create",
                "target_id": target_id,
                "source": source,
                "user_id": user,
            }
        )

        if create_response.get("status") != "success":
            error_code = create_response.get("error_code", "TRANSPORT_ERROR")
            message = create_response.get("message", "Failed to create client session")
            raise RuntimeError(f"[{error_code}] {message}")

        client_data = create_response.get("data", {})
        client_session_id = client_data.get("client_session_id")
        if not client_session_id:
            raise RuntimeError("No client_session_id in create response")

        yield client_session_id

    finally:
        # Best-effort cleanup: close the ephemeral client
        if client_session_id is not None and agent_client is not None:
            try:
                close_response = agent_client.send_command(
                    {
                        "type": "client",
                        "action": "close",
                        "client_session_id": client_session_id,
                    }
                )
                if close_response.get("status") != "success":
                    raise RuntimeError(
                        "[{0}] {1}".format(
                            close_response.get("error_code", "TRANSPORT_ERROR"),
                            close_response.get("message", "Failed to close client session"),
                        )
                    )
            except Exception as e:
                # Swallow transport errors; log to stderr at debug level
                # (OutputFormatter not available in this helper; raw stderr only)
                print(
                    f"[peeka debug] Failed to close ephemeral client {client_session_id}: {e}",
                    file=sys.stderr,
                )
        if owned_client is not None:
            owned_client.disconnect()
