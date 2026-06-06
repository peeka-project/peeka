"""Attach session discovery and agent socket probes."""

import json
import os
import socket as sock_mod
from pathlib import Path
from typing import Optional, Tuple


def _attach_module():
    from peeka.core import attach as attach_module

    return attach_module


class AttachSessionMixin:

    def _check_existing_attachment(self) -> Optional[Tuple[str, int]]:
        """
        Check if there's already an active Peeka agent attached to any process.
        Returns (session_id, pid) tuple if found, None otherwise.

        Validates by both process existence AND agent responsiveness to avoid
        stale files left after process restarts.
        """
        self._emit_progress(
            "check_existing_session",
            "running",
            "Scanning for reusable Peeka sessions",
        )
        socket_dir = _attach_module().Path("/tmp")
        scanned = 0
        stale = 0
        for sock_file in socket_dir.glob("peeka_*.sock"):
            if sock_file.is_socket():
                scanned += 1
                session_id = sock_file.stem.replace("peeka_", "")
                pid_file = socket_dir / f"peeka_{session_id}.pid"
                ready_file = socket_dir / f"peeka_{session_id}.ready"

                if pid_file.exists():
                    try:
                        attached_pid = int(pid_file.read_text().strip())
                        try:
                            os.kill(attached_pid, 0)
                        except (ProcessLookupError, PermissionError):
                            stale += 1
                            self._cleanup_stale_files(sock_file, pid_file, ready_file)
                            continue

                        if self._is_agent_responsive(str(sock_file)):
                            self._emit_progress(
                                "check_existing_session",
                                "done",
                                f"Found reusable Peeka session for PID {attached_pid}",
                                details={
                                    "scanned": scanned,
                                    "stale_cleaned": stale,
                                    "session_id": session_id,
                                    "pid": attached_pid,
                                },
                            )
                            return (session_id, attached_pid)
                        else:
                            stale += 1
                            self._cleanup_stale_files(sock_file, pid_file, ready_file)
                    except (ValueError, OSError):
                        continue
                else:
                    stale += 1
                    self._cleanup_stale_files(sock_file, pid_file, ready_file)
        self._emit_progress(
            "check_existing_session",
            "done",
            "No reusable Peeka session found",
            details={"scanned": scanned, "stale_cleaned": stale},
        )
        return None

    @staticmethod
    def _is_socket_alive(socket_path: str) -> bool:
        """Try connecting to the socket to verify the path is reachable."""
        try:
            with sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(socket_path)
            return True
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            return False

    @staticmethod
    def _recv_exact(s: sock_mod.socket, size: int) -> bytes:
        chunks = []
        remaining = size
        while remaining > 0:
            try:
                chunk = s.recv(remaining)
            except sock_mod.timeout:
                return b""
            if not chunk:
                return b""
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    @classmethod
    def _recv_response_header(cls, s: sock_mod.socket) -> bytes:
        length_bytes = cls._recv_exact(s, 4)
        while length_bytes in (b"OBS:", b"LOG:"):
            frame_len_bytes = cls._recv_exact(s, 4)
            if not frame_len_bytes:
                return b""
            frame_len = int.from_bytes(frame_len_bytes, "big")
            if frame_len and not cls._recv_exact(s, frame_len):
                return b""
            length_bytes = cls._recv_exact(s, 4)
        return length_bytes

    @classmethod
    def _is_agent_responsive(cls, socket_path: str) -> bool:
        """Verify the agent can complete one command/response round trip."""
        try:
            with sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(socket_path)

                payload = json.dumps(
                    {"type": "client", "action": "hello"}
                ).encode("utf-8")
                s.sendall(len(payload).to_bytes(4, "big"))
                s.sendall(payload)

                length_bytes = cls._recv_response_header(s)
                if not length_bytes:
                    return False
                length = int.from_bytes(length_bytes, "big")
                data = cls._recv_exact(s, length)
                if not data:
                    return False
                response = json.loads(data.decode("utf-8"))
                return response.get("status") == "success"
        except (
            ConnectionRefusedError,
            FileNotFoundError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ):
            return False

    @staticmethod
    def _cleanup_stale_files(*paths: Path) -> None:
        for p in paths:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

    def _save_attachment_state(self) -> None:
        """Save the attached PID to a marker file for validation."""
        pid_file = _attach_module().Path(f"/tmp/peeka_{self.session_id}.pid")
        pid_file.write_text(str(self.pid))
