"""
Agent client utilities for talking to the in-process Peeka agent over
Unix domain sockets using the length-prefixed JSON protocol defined in
``peeka.core.agent``.
"""

import json
import socket
import time
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

    def connect(self) -> Dict[str, Any]:
        """Connect to the agent socket."""
        if not Path(self.socket_path).exists():
            return {
                "status": "error",
                "error": f"Agent socket not found: {self.socket_path}",
            }

        try:
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            if self.timeout:
                self._sock.settimeout(self.timeout)
            self._sock.connect(self.socket_path)
            return {"status": "success"}
        except Exception as e:
            self._sock = None
            return {"status": "error", "error": str(e)}

    def disconnect(self) -> None:
        """Close the connection."""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        self._buffer = b""

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send a command and receive the immediate response."""
        if not self._sock:
            return {"status": "error", "error": "Not connected"}

        try:
            payload = json.dumps(command).encode("utf-8")
            self._sock.sendall(len(payload).to_bytes(4, "big"))
            self._sock.sendall(payload)

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

        while True:
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
                time.sleep(0.1)  # Add 100ms delay to reduce CPU usage
                continue
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
