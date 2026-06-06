# pyright: reportDeprecated=false, reportExplicitAny=false, reportUnusedParameter=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportAny=false, reportUnnecessaryCast=false
"""Target discovery domain objects.

Implements the ``TargetAgent`` object contract from
``.sisyphus/plans/session-optimize.md`` §TargetAgent.

Target state machine:
    alive: hello probe succeeds for a live PID.
    stale: marker files or socket remain, but the PID is gone or probe fails.
    unknown: there is not enough information to classify safely.
    attaching: attach is in progress.
    failed: the latest attach attempt failed.
    detached: the target was explicitly detached.
"""

import json
import os
import socket
import time
from dataclasses import asdict
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Any
from typing import Dict
from typing import List
from typing import Literal
from typing import Optional
from typing import cast


TARGET_SCHEMA_VERSION = "1"
SOCKET_DIR = Path("/tmp")
_HELLO_TIMEOUT_SECONDS = 0.2
_HELLO_RETRY_COUNT = 3

TargetState = Literal[
    "alive",
    "stale",
    "unknown",
    "attaching",
    "failed",
    "detached",
]
AgentMode = Literal["injected", "preinstalled"]
InjectionMode = Literal[
    "gdb_dlopen",
    "lldb_dlopen",
    "pep768",
    "preinstalled",
]


@dataclass
class TargetAgent:
    """Represents one Peeka-managed target process.

    Attributes:
        target_id: Public target identifier.
        legacy_session_id: Legacy session identifier used by /tmp/peeka_* files.
        pid: Target process PID.
        socket_path: Unix socket path for the target agent.
        state: Current target lifecycle state.
        agent_mode: Whether the agent is injected or preinstalled.
        injection_mode: Attach mechanism used for the target agent.
        python_version: Target interpreter version string.
        peeka_version: Peeka version reported by the target.
        capabilities: Free-form capability map for target features.
        runtime: Free-form runtime metadata map.
        created_at: Target creation timestamp in epoch seconds.
        last_seen_at: Last successful observation timestamp in epoch seconds.
        recent_errors: Recent error records shaped like
            {"timestamp": float, "code": str, "message": str}.
        next_valid_actions: Allowed next actions for the target.
    """

    target_id: str
    legacy_session_id: str
    pid: int
    socket_path: str
    state: TargetState
    agent_mode: AgentMode
    injection_mode: InjectionMode
    python_version: str
    peeka_version: str
    capabilities: Dict[str, Any] = field(default_factory=dict)
    runtime: Dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    last_seen_at: float = 0.0
    recent_errors: List[Dict[str, Any]] = field(default_factory=list)
    next_valid_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the target into a JSON-safe dictionary."""
        result = {"schema_version": TARGET_SCHEMA_VERSION}
        result.update(asdict(self))
        return result


def discover_targets() -> List[TargetAgent]:
    """Discover Peeka target agents on the current host."""
    targets = []

    for socket_path in SOCKET_DIR.glob("peeka_*.sock"):
        if not socket_path.exists():
            continue

        session_id = _parse_session_id(socket_path)
        if session_id is None:
            continue

        now = time.time()
        pid_path = SOCKET_DIR / f"peeka_{session_id}.pid"
        ready_path = SOCKET_DIR / f"peeka_{session_id}.ready"
        pid = _read_pid(pid_path)
        _ = _read_ready_metadata(ready_path)

        hello_response = None
        state = cast(TargetState, "unknown")

        if pid is not None:
            if _is_pid_alive(pid):
                hello_response = _probe_target_hello(str(socket_path))
                if hello_response is not None:
                    state = cast(TargetState, "alive")
                else:
                    state = cast(TargetState, "stale")
            else:
                state = cast(TargetState, "stale")

        targets.append(
            _build_target(
                session_id=session_id,
                socket_path=socket_path,
                pid=pid or 0,
                state=state,
                created_at=_get_created_at(socket_path, now),
                last_seen_at=now,
                hello_response=hello_response,
            )
        )

    return sorted(targets, key=lambda target: (target.created_at, target.target_id))


def get_target(target_id: str) -> Optional[TargetAgent]:
    """Return a target by public identifier if it exists."""
    for target in discover_targets():
        if target.target_id == target_id:
            return target
    return None


def cleanup_stale_targets(dry_run: bool = False, target_id: Optional[str] = None) -> Dict[str, Any]:
    """Plan or perform stale target cleanup.
    
    Args:
        dry_run: If True, report what would be removed without unlinking files.
        target_id: If provided, clean only this specific target. Otherwise clean all stale targets.
    
    Returns:
        Dictionary with "removed", "skipped", and "errors" lists.
    """
    result: Dict[str, Any] = {"removed": [], "skipped": [], "errors": []}

    if target_id:
        # Single-target cleanup
        target = get_target(target_id)
        if target is None:
            result["errors"].append(
                {"target_id": target_id, "message": "TARGET_NOT_FOUND"}
            )
            return result
        
        if target.state != "stale":
            result["skipped"].append(
                {"target_id": target.target_id, "reason": f"not_stale (state={target.state})"}
            )
            return result
        
        if target.pid > 0 and _is_pid_alive(target.pid):
            result["skipped"].append(
                {"target_id": target.target_id, "reason": "race_alive"}
            )
            return result
        
        if dry_run:
            result["removed"].append(target.target_id)
            return result
        
        try:
            for path in _target_related_paths(target.legacy_session_id):
                path.unlink(missing_ok=True)
            result["removed"].append(target.target_id)
        except OSError as exc:
            result["errors"].append(
                {"target_id": target.target_id, "message": str(exc)}
            )
        return result

    # Bulk cleanup: all stale targets
    for target in discover_targets():
        if target.state != "stale":
            continue

        if target.pid > 0 and _is_pid_alive(target.pid):
            result["skipped"].append(
                {"target_id": target.target_id, "reason": "race_alive"}
            )
            continue

        if dry_run:
            result["removed"].append(target.target_id)
            continue

        try:
            for path in _target_related_paths(target.legacy_session_id):
                path.unlink(missing_ok=True)
            result["removed"].append(target.target_id)
        except OSError as exc:
            result["errors"].append(
                {"target_id": target.target_id, "message": str(exc)}
            )

    return result


def detach_target(target_id: str, force: bool = False) -> Dict[str, Any]:
    """Detach a target from Peeka management."""
    target = get_target(target_id)
    if target is None:
        return {"ok": False, "error_code": "TARGET_NOT_FOUND"}

    if target.state == "unknown":
        return {"ok": False, "error_code": "TARGET_NOT_FOUND"}

    if target.state == "alive" and not force:
        return {
            "ok": False,
            "error_code": "UNSUPPORTED_CAPABILITY",
            "message": "force required for alive detach",
        }

    if target.state == "alive":
        detach_response = _send_detach_command(target.socket_path)
        if detach_response is None or detach_response.get("status") != "success":
            return {
                "ok": False,
                "error_code": "AGENT_UNREACHABLE",
                "message": _detach_error_message(detach_response),
            }

    if target.state == "stale" and target.pid > 0 and _is_pid_alive(target.pid):
        detach_response = _send_detach_command(target.socket_path)
        if detach_response is None or detach_response.get("status") != "success":
            return {
                "ok": False,
                "error_code": "AGENT_UNREACHABLE",
                "message": _detach_error_message(detach_response),
            }

    if target.state in ("alive", "stale"):
        errors: List[Dict[str, str]] = []
        for path in _target_related_paths(target.legacy_session_id):
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                errors.append({"path": str(path), "message": str(exc)})

        result: Dict[str, Any] = {"ok": True, "target_id": target.target_id}
        if errors:
            result["errors"] = errors
        return result

    return {"ok": False, "error_code": "TARGET_NOT_FOUND"}


def _parse_session_id(socket_path: Path) -> Optional[str]:
    stem = socket_path.stem
    if not stem.startswith("peeka_"):
        return None

    session_id = stem.replace("peeka_", "", 1)
    if not session_id:
        return None
    return session_id


def _read_pid(pid_path: Path) -> Optional[int]:
    if not pid_path.exists():
        return None

    try:
        return int(pid_path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _read_ready_metadata(ready_path: Path) -> Dict[str, Any]:
    if not ready_path.exists():
        return {}

    try:
        raw = ready_path.read_text(encoding="utf-8").strip()
    except OSError:
        return {}

    if not raw:
        return {}

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}

    if isinstance(payload, dict):
        return payload
    return {}


def _get_created_at(socket_path: Path, fallback: float) -> float:
    try:
        return os.path.getctime(socket_path)
    except OSError:
        return fallback


def _is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _probe_target_hello(socket_path: str) -> Optional[Dict[str, Any]]:
    for _ in range(_HELLO_RETRY_COUNT):
        response = _send_target_command(
            socket_path,
            {"type": "target", "action": "hello"},
        )
        if response and response.get("status") == "success":
            return response
    return None


def _send_detach_command(socket_path: str) -> Optional[Dict[str, Any]]:
    return _send_target_command(socket_path, {"type": "detach"})


def _detach_error_message(response: Optional[Dict[str, Any]]) -> str:
    if response is None:
        return "Agent detach RPC failed"
    message = response.get("message") or response.get("error")
    if message:
        return str(message)
    return "Agent detach RPC failed"


def _send_target_command(
    socket_path: str, command: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(_HELLO_TIMEOUT_SECONDS)
            sock.connect(socket_path)

            payload = json.dumps(command).encode("utf-8")
            sock.sendall(len(payload).to_bytes(4, "big"))
            sock.sendall(payload)

            length_bytes = _recv_response_header(sock)
            if not length_bytes:
                return None

            length = int.from_bytes(length_bytes, "big")
            data = _recv_exact(sock, length)
            if not data:
                return None

            response = json.loads(data.decode("utf-8"))
            if isinstance(response, dict):
                return response
    except (
        ConnectionRefusedError,
        FileNotFoundError,
        OSError,
        ValueError,
        json.JSONDecodeError,
    ):
        return None

    return None


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining > 0:
        try:
            chunk = sock.recv(remaining)
        except socket.timeout:
            return b""
        if not chunk:
            return b""
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_response_header(sock: socket.socket) -> bytes:
    length_bytes = _recv_exact(sock, 4)
    while length_bytes in (b"OBS:", b"LOG:"):
        frame_length_bytes = _recv_exact(sock, 4)
        if not frame_length_bytes:
            return b""
        frame_length = int.from_bytes(frame_length_bytes, "big")
        if frame_length and not _recv_exact(sock, frame_length):
            return b""
        length_bytes = _recv_exact(sock, 4)
    return length_bytes


def _build_target(
    session_id: str,
    socket_path: Path,
    pid: int,
    state: TargetState,
    created_at: float,
    last_seen_at: float,
    hello_response: Optional[Dict[str, Any]],
) -> TargetAgent:
    agent_mode = cast(AgentMode, "injected")
    injection_mode = cast(InjectionMode, "preinstalled")
    python_version = ""
    peeka_version = ""
    capabilities = {}
    runtime = {}

    if hello_response:
        agent_mode_value = str(hello_response.get("agent_mode") or "injected")
        injection_mode_value = str(
            hello_response.get("injection_mode") or "preinstalled"
        )
        if agent_mode_value in ("injected", "preinstalled"):
            agent_mode = cast(AgentMode, agent_mode_value)
        if injection_mode_value in (
            "gdb_dlopen",
            "lldb_dlopen",
            "pep768",
            "preinstalled",
        ):
            injection_mode = cast(InjectionMode, injection_mode_value)
        python_version = str(hello_response.get("python_version") or "")
        peeka_version = str(hello_response.get("peeka_version") or "")
        capabilities = dict(hello_response.get("capabilities") or {})
        runtime = dict(hello_response.get("runtime") or {})

    next_valid_actions = []
    if state == "alive":
        next_valid_actions = ["detach"]
    elif state == "stale":
        next_valid_actions = ["cleanup", "detach"]

    return TargetAgent(
        target_id=f"target_{session_id[:8]}",
        legacy_session_id=session_id,
        pid=pid,
        socket_path=str(socket_path),
        state=state,
        agent_mode=agent_mode,
        injection_mode=injection_mode,
        python_version=python_version,
        peeka_version=peeka_version,
        capabilities=capabilities,
        runtime=runtime,
        created_at=created_at,
        last_seen_at=last_seen_at,
        recent_errors=[],
        next_valid_actions=next_valid_actions,
    )


def _target_related_paths(session_id: str) -> List[Path]:
    return [
        SOCKET_DIR / f"peeka_{session_id}.sock",
        SOCKET_DIR / f"peeka_{session_id}.pid",
        SOCKET_DIR / f"peeka_{session_id}.ready",
        SOCKET_DIR / f"peeka_{session_id}.log",
    ]
