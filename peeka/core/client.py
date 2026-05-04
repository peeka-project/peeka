"""
Agent client utilities for talking to the in-process Peeka agent over
Unix domain sockets using the length-prefixed JSON protocol defined in
``peeka.core.agent``.
"""

import json
import logging
import os
import socket
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Generator, Optional

logger = logging.getLogger(__name__)

_DEFAULT_CLIENT_INSTANCE_ID = f"cli-{uuid.uuid4().hex[:6]}"


def _build_client_info(
    client_info: Optional[Dict[str, Any]], default_source: str
) -> Dict[str, Any]:
    """Build stable client metadata sent with each command."""
    info = {
        "id": _DEFAULT_CLIENT_INSTANCE_ID,
        "kind": "cli",
        "source": default_source,
        "pid": os.getpid(),
    }
    if client_info:
        info.update(client_info)
    return info


class AgentClient:
    """Lightweight client for communicating with the Peeka agent."""

    def __init__(
        self,
        socket_path: str,
        timeout: float = 5.0,
        client_info: Optional[Dict[str, Any]] = None,
    ):
        self.socket_path = socket_path
        self.timeout = timeout
        self._client_info = _build_client_info(client_info, "request")

    def _attach_client_info(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Attach client metadata without mutating the caller's command."""
        payload = dict(command)
        payload["_client"] = dict(self._client_info)
        return payload

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON command and return the agent response."""
        if not Path(self.socket_path).exists():
            return {
                "status": "error",
                "error": f"Agent socket not found: {self.socket_path}",
                "hint": "Ensure the target process is running and attach succeeded.",
            }

        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(self.socket_path)

                payload = json.dumps(self._attach_client_info(command)).encode("utf-8")
                sock.sendall(len(payload).to_bytes(4, "big"))
                sock.sendall(payload)

                length_bytes = self._recv_exact(sock, 4)
                if not length_bytes:
                    raise TimeoutError("No response length received")

                length = int.from_bytes(length_bytes, "big")
                data = self._recv_exact(sock, length)
                if not data:
                    raise TimeoutError("No response payload received")

                return json.loads(data.decode("utf-8"))

        except Exception as exc:
            logger.debug("Command failed on %s: %s", self.socket_path, exc)
            return {
                "status": "error",
                "error": str(exc),
                "hint": "Check that the agent is running and reachable.",
            }

    @staticmethod
    def _recv_exact(sock: socket.socket, size: int) -> bytes:
        """Receive exactly ``size`` bytes or return b"" on failure/timeout."""
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


class StreamingAgentClient:
    """
    Client for streaming observations from the Peeka agent.

    Maintains a persistent connection and yields observations as they arrive.
    The agent sends observations with "OBS:" prefix followed by length-prefixed JSON.
    """

    OBS_PREFIX = b"OBS:"
    LOG_PREFIX = b"LOG:"
    PREFIX_LEN = 4

    def __init__(
        self,
        socket_path: str,
        timeout: Optional[float] = None,
        activity_reporter: Optional[Callable[[str, str], None]] = None,
        client_info: Optional[Dict[str, Any]] = None,
    ):
        self.socket_path = socket_path
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._buffer = b""
        self._stop_event = threading.Event()
        self._send_lock = threading.Lock()
        self._activity_reporter = activity_reporter
        self._client_info = _build_client_info(client_info, "cli")

    @staticmethod
    def _summarize_command(command: Dict[str, Any]) -> str:
        """Build a concise command summary for client-side diagnostics."""
        cmd_type = str(command.get("type", "unknown"))
        action_value = command.get("action")
        action = str(action_value).lower() if action_value is not None else "execute"
        details = []

        for key in ("pattern", "watch_id", "top_id", "logger", "target"):
            value = command.get(key)
            if value not in (None, ""):
                details.append(f"{key}={value}")

        summary = f"{cmd_type}/{action}"
        if details:
            summary += " " + " ".join(details[:3])
        return summary

    def _report_activity(self, level: str, message: str) -> None:
        """Emit a client-side activity entry when a reporter is configured."""
        if not self._activity_reporter:
            return
        try:
            self._activity_reporter(level, message)
        except Exception:
            logger.debug("activity reporter failed", exc_info=True)

    def _attach_client_info(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Attach client metadata without exposing it to command callers."""
        payload = dict(command)
        payload["_client"] = dict(self._client_info)
        return payload

    def connect(self) -> Dict[str, Any]:
        """Connect to the agent socket."""
        if not Path(self.socket_path).exists():
            result = {
                "status": "error",
                "error": f"Agent socket not found: {self.socket_path}",
            }
            self._report_activity("ERROR", f"connect failed: {result['error']}")
            return result

        try:
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout if self.timeout else 1.0)
            self._sock.connect(self.socket_path)
            self._stop_event.clear()
            self._report_activity("INFO", "connected")
            return {"status": "success"}
        except Exception as e:
            logger.debug("Connection to %s failed: %s", self.socket_path, e)
            self._sock = None
            self._report_activity("ERROR", f"connect failed: {e}")
            return {"status": "error", "error": str(e)}

    def disconnect(self) -> None:
        """Close the connection and signal streaming loops to stop."""
        had_socket = self._sock is not None
        self._stop_event.set()
        if self._sock:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._buffer = b""
        if had_socket:
            self._report_activity("INFO", "disconnected")

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send a command and receive the immediate response.

        Because the agent broadcasts OBS: frames to ALL connections
        (including this one), observation data may arrive in the socket
        buffer before the command response.  We drain any such frames
        before reading the 4-byte response length so that we don't
        mis-interpret ``OBS:`` (0x4f42533a) as a payload size.

        A lock serialises concurrent callers (e.g. Textual worker threads
        issuing commands and completions simultaneously) so that only one
        send/receive cycle uses the socket at a time.
        """
        if not self._sock:
            summary = self._summarize_command(command)
            self._report_activity("ERROR", f"{summary} failed: not connected")
            return {"status": "error", "error": "Not connected"}

        with self._send_lock:
            try:
                summary = self._summarize_command(command)
                payload = json.dumps(self._attach_client_info(command)).encode("utf-8")
                self._sock.sendall(len(payload).to_bytes(4, "big"))
                self._sock.sendall(payload)

                # Drain any OBS frames that arrived before the response
                self._drain_obs_frames()

                length_bytes = self._recv_exact(4)
                if not length_bytes:
                    self._report_activity("ERROR", f"{summary} failed: no response received")
                    return {"status": "error", "error": "No response received"}

                # After _recv_exact we may have read more data into _buffer.
                # If the 4 bytes we got look like the OBS or LOG prefix, drain and retry.
                while length_bytes == self.OBS_PREFIX or length_bytes == self.LOG_PREFIX:
                    # We just consumed the prefix — read & discard the payload
                    obs_len_bytes = self._recv_exact(4)
                    if not obs_len_bytes:
                        self._report_activity("ERROR", f"{summary} failed: truncated frame")
                        return {"status": "error", "error": "Truncated frame"}
                    obs_len = int.from_bytes(obs_len_bytes, "big")
                    obs_data = self._recv_exact(obs_len)
                    if not obs_data:
                        self._report_activity(
                            "ERROR", f"{summary} failed: truncated payload"
                        )
                        return {"status": "error", "error": "Truncated payload"}
                    # Try reading the next 4 bytes (hopefully the real response)
                    self._drain_obs_frames()
                    length_bytes = self._recv_exact(4)
                    if not length_bytes:
                        self._report_activity(
                            "ERROR", f"{summary} failed: no response received"
                        )
                        return {"status": "error", "error": "No response received"}

                length = int.from_bytes(length_bytes, "big")
                data = self._recv_exact(length)
                if not data:
                    result = {"status": "error", "error": "Incomplete response"}
                    self._report_activity("ERROR", f"{summary} failed: incomplete response")
                    return result

                result = json.loads(data.decode("utf-8"))
                if result.get("status") == "error":
                    self._report_activity(
                        "ERROR",
                        f"{summary} failed: {result.get('error', 'unknown error')}",
                    )
                return result

            except Exception as e:
                logger.debug("send_command error: %s", e)
                self._report_activity("ERROR", f"{summary} failed: {e}")
                return {"status": "error", "error": str(e)}
    def stream_observations(self) -> Generator[Dict[str, Any], None, None]:
        """
        Yield observations as they arrive from the agent.

        This generator blocks waiting for observations. Use with a timeout
        or run in a separate thread. Exits when connection closes or on error.
        """
        if not self._sock:
            return

        while not self._stop_event.is_set():
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    if not self._stop_event.is_set():
                        self._report_activity("WARNING", "observation stream closed by peer")
                    break

                self._buffer += chunk

                while True:
                    obs = self._extract_observation()
                    if obs is None:
                        break
                    yield obs

            except socket.timeout:
                continue
            except OSError as e:
                if not self._stop_event.is_set():
                    self._report_activity("WARNING", f"observation stream error: {e}")
                break
            except Exception:
                if not self._stop_event.is_set():
                    self._report_activity("WARNING", "observation stream crashed unexpectedly")
                logger.debug("Unexpected error in stream_observations", exc_info=True)
                break

    def _extract_observation(self) -> Optional[Dict[str, Any]]:
        """Extract one observation from buffer if complete."""
        # Check for observation prefix first
        if self._buffer.startswith(self.OBS_PREFIX):
            prefix = self.OBS_PREFIX
        elif self._buffer.startswith(self.LOG_PREFIX):
            prefix = self.LOG_PREFIX
        else:
            # Look for either prefix in the buffer
            idx_obs = self._buffer.find(self.OBS_PREFIX)
            idx_log = self._buffer.find(self.LOG_PREFIX)
            if idx_obs == -1 and idx_log == -1:
                return None
            # Take the earliest occurrence
            if idx_obs == -1:
                self._buffer = self._buffer[idx_log:]
                prefix = self.LOG_PREFIX
            elif idx_log == -1:
                self._buffer = self._buffer[idx_obs:]
                prefix = self.OBS_PREFIX
            elif idx_obs < idx_log:
                self._buffer = self._buffer[idx_obs:]
                prefix = self.OBS_PREFIX
            else:
                self._buffer = self._buffer[idx_log:]
                prefix = self.LOG_PREFIX

        header_size = self.PREFIX_LEN + 4
        if len(self._buffer) < header_size:
            return None

        length = int.from_bytes(self._buffer[self.PREFIX_LEN : header_size], "big")
        total_size = header_size + length

        if len(self._buffer) < total_size:
            return None

        data = self._buffer[header_size:total_size]
        self._buffer = self._buffer[total_size:]

        try:
            if prefix is self.LOG_PREFIX:
                # LOG messages already contain the type, level, and message in the JSON payload
                return json.loads(data.decode("utf-8"))
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def _drain_obs_frames(self) -> None:
        """Remove complete OBS or LOG frames sitting at the front of ``_buffer``.

        This is called inside ``send_command`` to skip over any observation
        broadcasts that arrived before the command response.  Only already-
        buffered data is considered — we never block waiting for more.
        """
        while self._buffer.startswith(self.OBS_PREFIX) or self._buffer.startswith(self.LOG_PREFIX):
            header_size = self.PREFIX_LEN + 4  # Prefix + 4-byte length
            if len(self._buffer) < header_size:
                break  # incomplete header — leave it for the next recv
            obs_len = int.from_bytes(
                self._buffer[self.PREFIX_LEN:header_size], "big"
            )
            total_size = header_size + obs_len
            if len(self._buffer) < total_size:
                break  # incomplete payload — leave it
            self._buffer = self._buffer[total_size:]

    def _recv_exact(self, size: int) -> bytes:
        """Receive exactly ``size`` bytes, using buffer first."""
        while len(self._buffer) < size:
            if not self._sock:
                return b""
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    return b""
                self._buffer += chunk
            except socket.timeout:
                return b""

        result = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return result

    def __enter__(self) -> "StreamingAgentClient":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()
