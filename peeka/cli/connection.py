"""Target-aware CLI agent connection helpers."""

from pathlib import Path
from typing import Optional, Tuple

import peeka.cli.sessions as cli_sessions
from peeka.core.client import StreamingAgentClient
from peeka.core.output import OutputFormatter
from peeka.core.targets import discover_targets
from peeka.core.targets import get_target


class TargetResolutionError(ValueError):
    """Raised when a target-scoped CLI command cannot resolve its target."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _check_agent_for_target(
    target_id: Optional[str],
    *,
    require_unambiguous_default: bool = False,
) -> Tuple[str, int]:
    """Return the socket and PID for a specific target or the default agent."""
    if not target_id:
        if require_unambiguous_default:
            return _check_unambiguous_default_agent()
        return cli_sessions._check_agent_attached()

    target = get_target(target_id)
    if target is not None:
        if target.state != "alive":
            raise TargetResolutionError(
                "TARGET_STALE",
                f"Target {target_id!r} is not alive (state={target.state})",
            )
        return target.socket_path, target.pid

    socket_path, pid = cli_sessions._check_agent_attached()
    if _socket_path_to_target_id(socket_path) == target_id:
        return socket_path, pid

    raise TargetResolutionError("TARGET_NOT_FOUND", f"Target not found: {target_id}")


def _check_unambiguous_default_agent() -> Tuple[str, int]:
    """Return the only alive target, or reject ambiguous target selection."""
    alive_targets = [
        target for target in discover_targets() if target.state == "alive"
    ]
    if len(alive_targets) == 1:
        target = alive_targets[0]
        return target.socket_path, target.pid

    if len(alive_targets) > 1:
        target_ids = ", ".join(target.target_id for target in alive_targets)
        raise TargetResolutionError(
            "TARGET_AMBIGUOUS",
            f"Multiple alive targets found ({target_ids}); pass --target",
        )

    return cli_sessions._check_agent_attached()


def _connect_streaming_agent(
    command_name: str,
    target_id: Optional[str] = None,
    *,
    require_unambiguous_default: bool = False,
) -> Optional[StreamingAgentClient]:
    """Connect to the default or target-specific agent for a CLI command."""
    try:
        socket_path, _ = _check_agent_for_target(
            target_id,
            require_unambiguous_default=require_unambiguous_default,
        )
    except ValueError as exc:
        OutputFormatter.error(
            command_name,
            error=str(exc),
            error_code=getattr(exc, "error_code", "AGENT_UNREACHABLE"),
        )
        return None

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()
    if connect_result.get("status") == "success":
        return streaming_client

    OutputFormatter.error(
        command_name,
        error=connect_result.get("error", "Connection failed"),
        error_code="TRANSPORT_ERROR",
    )
    return None


def _socket_path_to_target_id(socket_path: str) -> str:
    """Derive target_id from socket path."""
    session_id = Path(socket_path).stem.replace("peeka_", "")
    return f"target_{session_id[:8]}"
