"""
Agent client utilities for talking to the in-process Peeka agent over
Unix domain sockets using the length-prefixed JSON protocol defined in
``peeka.core.agent``.
"""
import json
import socket
from pathlib import Path
from typing import Any, Dict


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

        except Exception as exc:  # Broad catch to surface connection/protocol errors
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
