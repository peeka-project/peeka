"""Shared CLI context and target-aware agent connection helpers."""

import argparse
import os
from pathlib import Path
from typing import Optional, Tuple

from peeka.core.client import StreamingAgentClient
from peeka.core.output import OutputFormatter
from peeka.core.targets import get_target


def _find_pid_by_name(name: str) -> int:
    if not name:
        raise ValueError("Process name is required when pid is not provided")
    proc_root = Path("/proc")
    for entry in proc_root.iterdir():
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        cmdline_path = entry / "cmdline"
        comm_path = entry / "comm"
        try:
            if cmdline_path.exists():
                cmdline = cmdline_path.read_text(errors="ignore").replace("\x00", " ")
                if name in cmdline:
                    return int(entry.name)
            if comm_path.exists():
                comm = comm_path.read_text(errors="ignore").strip()
                if comm == name:
                    return int(entry.name)
        except Exception:
            continue
    raise ValueError(f"Process with name '{name}' not found")


def _resolve_pid(args) -> int:
    if args.pid:
        return args.pid
    if getattr(args, "name", None):
        return _find_pid_by_name(args.name)
    raise ValueError("Either --pid or --name must be provided")


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


class TargetResolutionError(ValueError):
    """Raised when a target-scoped CLI command cannot resolve its target."""

    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def _check_agent_for_target(target_id: Optional[str]) -> Tuple[str, int]:
    """Return the socket and PID for a specific target or the default agent."""
    if not target_id:
        return _check_agent_attached()

    target = get_target(target_id)
    if target is not None:
        if target.state != "alive":
            raise TargetResolutionError(
                "TARGET_STALE",
                f"Target {target_id!r} is not alive (state={target.state})",
            )
        return target.socket_path, target.pid

    socket_path, pid = _check_agent_attached()
    if _socket_path_to_target_id(socket_path) == target_id:
        return socket_path, pid

    raise TargetResolutionError("TARGET_NOT_FOUND", f"Target not found: {target_id}")


def _connect_streaming_agent(
    command_name: str,
    target_id: Optional[str] = None,
) -> Optional[StreamingAgentClient]:
    """Connect to the default or target-specific agent for a CLI command."""
    try:
        socket_path, _ = _check_agent_for_target(target_id)
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


def _parse_duration(duration_str: str) -> int:
    """Parse duration string into seconds.

    Supports:
        - Bare integers (interpreted as seconds)
        - Ns (N seconds)
        - Nm (N minutes)
        - Nh (N hours)

    Args:
        duration_str: Duration string to parse.

    Returns:
        Duration in seconds.

    Raises:
        argparse.ArgumentTypeError: If duration_str is invalid.
    """
    if not duration_str:
        raise argparse.ArgumentTypeError("Duration cannot be empty")

    duration_str = duration_str.strip()

    # Try bare integer
    try:
        seconds = int(duration_str)
        if seconds < 0:
            raise argparse.ArgumentTypeError("Duration must be non-negative")
        return seconds
    except ValueError:
        pass

    # Try unit-suffixed form
    if len(duration_str) < 2:
        raise argparse.ArgumentTypeError(f"Invalid duration format: {duration_str}")

    value_str = duration_str[:-1]
    unit = duration_str[-1].lower()

    try:
        value = int(value_str)
        if value < 0:
            raise argparse.ArgumentTypeError("Duration must be non-negative")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid duration value: {value_str}")

    if unit == "s":
        return value
    elif unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    else:
        raise argparse.ArgumentTypeError(
            f"Invalid duration unit: {unit} (use s, m, or h)"
        )
