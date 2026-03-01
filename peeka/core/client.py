"""
Agent client utilities for talking to the in-process Peeka agent over
Unix domain sockets using the length-prefixed JSON protocol defined in
``peeka.core.agent``.
"""

import json
import socket
import threading
from pathlib import Path
from typing import Any, Dict, Generator, Optional


class AgentClient:
    """Lightweight client for communicating with the Peeka agent."""

    def __init__(self, socket_path: str, timeout: float = 5.0):
        self.socket_path = socket_path
        self.timeout = timeout

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

                payload = json.dumps(command).encode("utf-8")
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
    PREFIX_LEN = 4

    def __init__(self, socket_path: str, timeout: Optional[float] = None):
        self.socket_path = socket_path
        self.timeout = timeout
        self._sock: Optional[socket.socket] = None
        self._buffer = b""
        self._stop_event = threading.Event()
        self._send_lock = threading.Lock()

    def connect(self) -> Dict[str, Any]:
        """Connect to the agent socket."""
        if not Path(self.socket_path).exists():
            return {
                "status": "error",
                "error": f"Agent socket not found: {self.socket_path}",
            }

        try:
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout if self.timeout else 1.0)
            self._sock.connect(self.socket_path)
            return {"status": "success"}
        except Exception as e:
            self._sock = None
            return {"status": "error", "error": str(e)}

    def disconnect(self) -> None:
        """Close the connection and signal streaming loops to stop."""
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
            return {"status": "error", "error": "Not connected"}

        with self._send_lock:
            try:
                payload = json.dumps(command).encode("utf-8")
                self._sock.sendall(len(payload).to_bytes(4, "big"))
                self._sock.sendall(payload)

                # Drain any OBS frames that arrived before the response
                self._drain_obs_frames()

                length_bytes = self._recv_exact(4)
                if not length_bytes:
                    return {"status": "error", "error": "No response received"}

                # After _recv_exact we may have read more data into _buffer.
                # If the 4 bytes we got look like the OBS prefix, drain and retry.
                while length_bytes == self.OBS_PREFIX:
                    # We just consumed "OBS:" — read & discard the OBS payload
                    obs_len_bytes = self._recv_exact(4)
                    if not obs_len_bytes:
                        return {"status": "error", "error": "Truncated OBS frame"}
                    obs_len = int.from_bytes(obs_len_bytes, "big")
                    obs_data = self._recv_exact(obs_len)
                    if not obs_data:
                        return {"status": "error", "error": "Truncated OBS payload"}
                    # Try reading the next 4 bytes (hopefully the real response)
                    self._drain_obs_frames()
                    length_bytes = self._recv_exact(4)
                    if not length_bytes:
                        return {"status": "error", "error": "No response received"}

                length = int.from_bytes(length_bytes, "big")
                data = self._recv_exact(length)
                if not data:
                    return {"status": "error", "error": "Incomplete response"}

                return json.loads(data.decode("utf-8"))

            except Exception as e:
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
                    break

                self._buffer += chunk

                while True:
                    obs = self._extract_observation()
                    if obs is None:
                        break
                    yield obs

            except socket.timeout:
                continue
            except OSError:
                break
            except Exception:
                break

    def _extract_observation(self) -> Optional[Dict[str, Any]]:
        """Extract one observation from buffer if complete."""
        if not self._buffer.startswith(self.OBS_PREFIX):
            idx = self._buffer.find(self.OBS_PREFIX)
            if idx == -1:
                return None
            self._buffer = self._buffer[idx:]

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
            return json.loads(data.decode("utf-8"))
        except json.JSONDecodeError:
            return None

    def _drain_obs_frames(self) -> None:
        """Remove complete OBS frames sitting at the front of ``_buffer``.

        This is called inside ``send_command`` to skip over any observation
        broadcasts that arrived before the command response.  Only already-
        buffered data is considered — we never block waiting for more.
        """
        while self._buffer.startswith(self.OBS_PREFIX):
            header_size = self.PREFIX_LEN + 4  # "OBS:" + 4-byte length
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
