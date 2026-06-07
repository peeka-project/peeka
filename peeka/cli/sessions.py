"""CLI helpers for discovering attached Peeka sessions."""

import os
from pathlib import Path
from typing import Optional, Tuple


def _find_active_session() -> Optional[str]:
    """
    Find the active Peeka session socket.
    Returns socket path if an agent is attached, None otherwise.
    """
    socket_dir = Path("/tmp")
    for sock_file in socket_dir.glob("peeka_*.sock"):
        if sock_file.is_socket():
            session_id = sock_file.stem.replace("peeka_", "")
            pid_file = socket_dir / f"peeka_{session_id}.pid"

            if pid_file.exists():
                try:
                    attached_pid = int(pid_file.read_text().strip())
                    try:
                        os.kill(attached_pid, 0)
                        return str(sock_file)
                    except (ProcessLookupError, PermissionError):
                        pid_file.unlink(missing_ok=True)
                        sock_file.unlink(missing_ok=True)
                except (ValueError, OSError):
                    continue
    return None


def _check_agent_attached() -> Tuple[str, int]:
    """
    Check if agent is attached to any process.
    Returns (socket_path, pid) tuple.
    Raises ValueError with clear message if not attached.
    """
    socket_path = _find_active_session()
    if socket_path is None:
        raise ValueError(
            "Not attached to any process.\nPlease run: peeka-cli attach <pid>"
        )

    session_id = Path(socket_path).stem.replace("peeka_", "")
    pid_file = Path(f"/tmp/peeka_{session_id}.pid")
    attached_pid = int(pid_file.read_text().strip())

    return (socket_path, attached_pid)
