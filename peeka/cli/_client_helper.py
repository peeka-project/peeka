"""
Ephemeral client lifecycle helper for CLI handlers.

Provides automatic client session creation and cleanup for legacy CLI commands
that don't explicitly manage client lifecycle via `--client` flag.
"""

import sys
from contextlib import contextmanager
from typing import Iterator, Optional

from peeka.core.client import AgentClient


@contextmanager
def ephemeral_client(
    target_id: str, agent_client: Optional[AgentClient] = None
) -> Iterator[str]:
    """Create an ephemeral client session for the duration of a CLI command.

    Args:
        target_id: Public target identifier for the client session.
        agent_client: Optional pre-connected agent client. If provided, uses it;
            otherwise creates a new connection (not yet implemented here).

    Yields:
        client_session_id: Public identifier for the ephemeral client session.

    Example:
        with ephemeral_client(target_id) as cid:
            # Use cid for downstream job/probe context
            pass
        # Client is automatically closed on exit
    """
    client_session_id = None
    try:
        if agent_client is None:
            raise NotImplementedError(
                "ephemeral_client requires a pre-connected AgentClient instance"
            )

        # Create ephemeral client via agent
        create_response = agent_client.send_command(
            {
                "type": "client",
                "action": "create",
                "target_id": target_id,
                "source": "cli",
            }
        )

        if not create_response.get("ok", False):
            error_code = create_response.get("error_code", "UNKNOWN")
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
                agent_client.send_command(
                    {
                        "type": "client",
                        "action": "close",
                        "client_session_id": client_session_id,
                    }
                )
            except Exception as e:
                # Swallow transport errors; log to stderr at debug level
                # (OutputFormatter not available in this helper; raw stderr only)
                print(
                    f"[peeka debug] Failed to close ephemeral client {client_session_id}: {e}",
                    file=sys.stderr,
                )
