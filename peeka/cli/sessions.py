"""CLI helpers for discovering attached Peeka sessions."""

import os
from pathlib import Path
from typing import List, Optional, Tuple


class TargetResolutionError(ValueError):
    """Raised when a target-scoped or default CLI command cannot resolve its target."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _find_active_sessions() -> List[Tuple[str, int]]:
    """Find all alive Peeka session `(socket_path, pid)` pairs.

    Dead sessions (`ProcessLookupError`) have their socket/pid files cleaned up.
    Sessions owned by another user (`PermissionError` on ``os.kill(pid, 0)``)
    are treated as alive and preserved untouched.
    """
    socket_dir = Path("/tmp")
    active_sessions: List[Tuple[str, int]] = []
    for sock_file in sorted(socket_dir.glob("peeka_*.sock")):
        if not sock_file.is_socket():
            continue
        session_id = sock_file.stem.replace("peeka_", "", 1)
        pid_file = socket_dir / f"peeka_{session_id}.pid"
        if not pid_file.exists():
            continue
        try:
            attached_pid = int(pid_file.read_text().strip())
        except (ValueError, OSError):
            continue
        try:
            os.kill(attached_pid, 0)
        except ProcessLookupError:
            pid_file.unlink(missing_ok=True)
            sock_file.unlink(missing_ok=True)
            continue
        except PermissionError:
            # Process belongs to another user and is still alive; preserve session files.
            pass
        active_sessions.append((str(sock_file), attached_pid))
    return active_sessions


def _find_active_session() -> Optional[str]:
    """
    Find the active Peeka session socket.
    Returns socket path if a single agent is attached, None if none.
    Raises TargetResolutionError("TARGET_AMBIGUOUS", ...) if multiple alive sessions exist.
    """
    active_sessions = _find_active_sessions()
    if not active_sessions:
        return None
    if len(active_sessions) > 1:
        details = ", ".join(
            f"target_{Path(sock).stem.replace('peeka_', '', 1)[:8]} (pid={pid})"
            for sock, pid in active_sessions
        )
        raise TargetResolutionError(
            "TARGET_AMBIGUOUS",
            f"Multiple active Peeka sessions found ({details}); pass --target or detach extra sessions",
        )
    return active_sessions[0][0]


def _check_agent_attached() -> Tuple[str, int]:
    """
    Check if agent is attached to a process.
    Returns (socket_path, pid) tuple.
    Raises ValueError if not attached, or TargetResolutionError if ambiguous.
    """
    socket_path = _find_active_session()
    if socket_path is None:
        raise ValueError(
            "Not attached to any process.\nPlease run: peeka-cli attach <pid>"
        )

    session_id = Path(socket_path).stem.replace("peeka_", "", 1)
    pid_file = Path(f"/tmp/peeka_{session_id}.pid")
    attached_pid = int(pid_file.read_text().strip())

    return (socket_path, attached_pid)
