"""
Agent client utilities for talking to the in-process Peeka agent over
Unix domain sockets using the length-prefixed JSON protocol defined in
``peeka.core.agent``.
"""

from contextlib import contextmanager
import json
import logging
import os
import socket
import threading
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple

logger = logging.getLogger(__name__)

_DEFAULT_CLIENT_INSTANCE_ID = f"cli-{uuid.uuid4().hex[:6]}"
_OBS_PREFIX = b"OBS:"
_LOG_PREFIX = b"LOG:"
_CONTROL_PREFIXES = (_OBS_PREFIX, _LOG_PREFIX)


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


def _uncertain_rpc_error(reason: str) -> Dict[str, Any]:
    """Build an error response for an RPC whose request was already sent."""
    detail = (
        f"{reason}; request was already sent, mutation outcome is uncertain, "
        "and command was not retried"
    )
    return {
        "status": "error",
        "error_code": "TRANSPORT_ERROR",
        "error": detail,
        "message": detail,
        "outcome_uncertain": True,
        "retried": False,
        "hint": (
            "The command may already have taken effect on the agent; "
            "inspect state before retrying manually."
        ),
    }


def _close_socket_quietly(sock: Optional[socket.socket]) -> None:
    """Best-effort shutdown and close for a client socket or mock."""
    if sock is None:
        return
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except Exception:
        pass
    try:
        sock.close()
    except Exception:
        pass


class AgentClient:
    """Lightweight client for communicating with the Peeka agent."""

    def __init__(
        self,
        socket_path: str,
        timeout: float = 5.0,
        client_info: Optional[Dict[str, Any]] = None,
        rpc_timeout: float = 30.0,
    ):
        self.socket_path = socket_path
        self.timeout = timeout
        self.rpc_timeout = rpc_timeout
        self._client_info = _build_client_info(client_info, "request")

    @staticmethod
    @contextmanager
    def _temporary_timeout(
        sock: socket.socket, timeout: float
    ) -> Generator[None, None, None]:
        """Temporarily override a socket timeout for one RPC round-trip."""
        previous_timeout = sock.gettimeout()
        sock.settimeout(timeout)
        try:
            yield
        finally:
            sock.settimeout(previous_timeout)

    def _attach_client_info(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Attach client metadata without mutating the caller's command."""
        payload = dict(command)
        payload["_client"] = dict(self._client_info)
        return payload

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send a JSON command and return the agent response.

        Agent-side activity and observations are broadcast to every open
        connection, including the one waiting for the immediate response.
        Skip those control frames until the length-prefixed JSON response
        arrives.
        """
        if not Path(self.socket_path).exists():
            return {
                "status": "error",
                "error": f"Agent socket not found: {self.socket_path}",
                "hint": "Ensure the target process is running and attach succeeded.",
            }

        send_attempted = False
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect(self.socket_path)

                payload = json.dumps(self._attach_client_info(command)).encode("utf-8")
                send_attempted = True
                sock.sendall(len(payload).to_bytes(4, "big"))
                sock.sendall(payload)

                with self._temporary_timeout(sock, self.rpc_timeout):
                    length_bytes = self._recv_response_header(sock)
                    if not length_bytes:
                        raise TimeoutError("No response length received")

                    length = int.from_bytes(length_bytes, "big")
                    data = self._recv_exact(sock, length)
                    if not data:
                        raise TimeoutError("No response payload received")

                result = json.loads(data.decode("utf-8"))
                if not isinstance(result, dict):
                    raise ValueError(
                        f"Expected JSON object response, got {type(result).__name__}"
                    )
                return result

        except Exception as exc:
            logger.debug("Command failed on %s: %s", self.socket_path, exc)
            if send_attempted:
                return _uncertain_rpc_error(str(exc))
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

    @classmethod
    def _recv_response_header(cls, sock: socket.socket) -> bytes:
        """Read the next JSON response length, skipping broadcast frames."""
        length_bytes = cls._recv_exact(sock, 4)
        while length_bytes in _CONTROL_PREFIXES:
            frame_len_bytes = cls._recv_exact(sock, 4)
            if not frame_len_bytes:
                return b""
            frame_len = int.from_bytes(frame_len_bytes, "big")
            if frame_len and not cls._recv_exact(sock, frame_len):
                return b""
            length_bytes = cls._recv_exact(sock, 4)
        return length_bytes


class StreamingAgentClient:
    """
    Client for streaming observations from the Peeka agent.

    Maintains a persistent connection and yields observations as they arrive.
    The agent sends observations with "OBS:" prefix followed by length-prefixed JSON.
    """

    OBS_PREFIX = _OBS_PREFIX
    LOG_PREFIX = _LOG_PREFIX
    PREFIX_LEN = 4

    def __init__(
        self,
        socket_path: str,
        timeout: Optional[float] = None,
        activity_reporter: Optional[Callable[[str, str], None]] = None,
        client_info: Optional[Dict[str, Any]] = None,
        rpc_timeout: float = 30.0,
    ):
        self.socket_path = socket_path
        self.timeout = timeout
        self.rpc_timeout = rpc_timeout
        self._sock: Optional[socket.socket] = None
        self._buffer = b""
        self._stop_event = threading.Event()
        self._send_lock = threading.Lock()
        # Serialises socket reads and ``_buffer`` mutations performed by
        # ``stream_observations`` so concurrent readers never interleave
        # partial frames. Never held while yielding to the caller.
        # Signal handlers may disconnect on the same thread during recv().
        self._stream_read_lock = threading.RLock()
        # Protects tiny non-blocking state transitions (``_sock``,
        # ``_connection_generation``, ``_stop_event``); never held across I/O
        # or activity callbacks. Lock order: _send_lock -> _stream_read_lock -> _state_lock.
        self._state_lock = threading.RLock()
        self._connection_generation = 0
        self._last_recv_error: Optional[str] = None
        self._active_rpc: Optional[Tuple[socket.socket, int]] = None
        self._activity_reporter = activity_reporter
        self._client_info = _build_client_info(client_info, "cli")
        self._identify_on_connect = client_info is not None

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

    @contextmanager
    def _temporary_rpc_timeout(
        self, sock: Optional[socket.socket] = None
    ) -> Generator[None, None, None]:
        """Temporarily widen socket timeout while awaiting an RPC response."""
        target_sock = sock if sock is not None else self._sock
        if target_sock is None:
            yield
            return

        previous_timeout = target_sock.gettimeout()
        target_sock.settimeout(self.rpc_timeout)
        try:
            yield
        finally:
            try:
                if self._sock is target_sock:
                    target_sock.settimeout(previous_timeout)
            except OSError:
                pass

    def _invalidate_connection_with_generation(
        self,
        expected_sock: Optional[socket.socket] = None,
        expected_generation: Optional[int] = None,
    ) -> Tuple[bool, int]:
        """Close active socket if it matches and return ``(had_socket, new_generation)``."""
        with self._state_lock:
            if expected_sock is not None and self._sock is not expected_sock:
                return False, self._connection_generation
            if (
                expected_generation is not None
                and self._connection_generation != expected_generation
            ):
                return False, self._connection_generation
            sock = self._sock
            had_socket = sock is not None
            self._sock = None
            self._connection_generation += 1
            invalidated_gen = self._connection_generation
            self._stop_event.set()

        _close_socket_quietly(sock)
        with self._stream_read_lock:
            with self._state_lock:
                if self._connection_generation == invalidated_gen:
                    self._buffer = b""
        return had_socket, invalidated_gen

    def _invalidate_connection(
        self,
        expected_sock: Optional[socket.socket] = None,
        expected_generation: Optional[int] = None,
    ) -> bool:
        """Close the active socket and advance connection generation if it matches."""
        had_socket, _ = self._invalidate_connection_with_generation(
            expected_sock=expected_sock,
            expected_generation=expected_generation,
        )
        return had_socket

    def _identify_connection(
        self,
        expected_sock: Optional[socket.socket] = None,
        expected_gen: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Send a lightweight identity frame for stream-only connections."""
        if expected_sock is None or expected_gen is None:
            return self.send_command({"type": "client", "action": "hello"})

        command: Dict[str, Any] = {"type": "client", "action": "hello"}
        summary = self._summarize_command(command)
        pending_activity: Optional[Tuple[str, str]] = None

        with self._send_lock:
            with self._state_lock:
                if (
                    self._sock is not expected_sock
                    or self._connection_generation != expected_gen
                ):
                    return {
                        "status": "error",
                        "error": "Disconnected during connect",
                    }
            result, pending_activity = self._send_command_locked(
                expected_sock, expected_gen, command, summary
            )

        if pending_activity is not None:
            self._report_activity(pending_activity[0], pending_activity[1])
        return result

    def connect(self) -> Dict[str, Any]:
        """Connect to the agent socket."""
        if not Path(self.socket_path).exists():
            self._invalidate_connection()
            result = {
                "status": "error",
                "error": f"Agent socket not found: {self.socket_path}",
            }
            self._report_activity("ERROR", f"connect failed: {result['error']}")
            return result

        _, attempt_gen = self._invalidate_connection_with_generation()
        sock: Optional[socket.socket] = None
        published_gen: Optional[int] = None
        try:
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(self.timeout if self.timeout else 1.0)
            sock.connect(self.socket_path)
            with self._stream_read_lock:
                with self._state_lock:
                    if self._connection_generation != attempt_gen:
                        stale = True
                    else:
                        self._sock = sock
                        self._connection_generation += 1
                        published_gen = self._connection_generation
                        self._stop_event.clear()
                        self._buffer = b""
                        stale = False

            if stale:
                _close_socket_quietly(sock)
                error = "Disconnected during connect"
                self._report_activity("ERROR", f"connect failed: {error}")
                return {"status": "error", "error": error}

            if self._identify_on_connect:
                assert published_gen is not None
                hello_result = self._identify_connection(sock, published_gen)
                if hello_result.get("status") != "success":
                    self._invalidate_connection(
                        expected_sock=sock, expected_generation=published_gen
                    )
                    _close_socket_quietly(sock)
                    error = hello_result.get("error", "client identification failed")
                    self._report_activity("ERROR", f"connect failed: {error}")
                    return {"status": "error", "error": error}
                with self._state_lock:
                    still_owns = (
                        self._sock is sock
                        and self._connection_generation == published_gen
                    )
                if not still_owns:
                    _close_socket_quietly(sock)
                    error = "Disconnected during connect"
                    self._report_activity("ERROR", f"connect failed: {error}")
                    return {"status": "error", "error": error}

            self._report_activity("INFO", "connected")
            return {"status": "success"}
        except Exception as e:
            logger.debug("Connection to %s failed: %s", self.socket_path, e)
            _close_socket_quietly(sock)
            if published_gen is not None:
                self._invalidate_connection(
                    expected_sock=sock, expected_generation=published_gen
                )
            else:
                self._invalidate_connection(expected_generation=attempt_gen)
            self._report_activity("ERROR", f"connect failed: {e}")
            return {"status": "error", "error": str(e)}

    def disconnect(self) -> None:
        """Close the connection and signal streaming loops to stop."""
        if self._invalidate_connection():
            self._report_activity("INFO", "disconnected")

    def _fail_post_send_rpc(
        self,
        sock: socket.socket,
        conn_gen: int,
        summary: str,
        reason: str,
    ) -> Tuple[Dict[str, Any], Tuple[str, str]]:
        """Invalidate a desynchronized connection and build an uncertain-outcome error."""
        self._invalidate_connection(expected_sock=sock, expected_generation=conn_gen)
        result = _uncertain_rpc_error(reason)
        return result, ("ERROR", f"{summary} failed: {result['error']}")

    def _no_response_reason(self) -> str:
        """Describe why a response header read yielded no bytes."""
        if self._last_recv_error == "timeout":
            return "No response received (timed out)"
        if self._last_recv_error == "eof":
            return "No response received (connection closed by peer)"
        return "No response received"

    def _send_command_locked(
        self,
        sock: socket.socket,
        conn_gen: int,
        command: Dict[str, Any],
        summary: str,
    ) -> Tuple[Dict[str, Any], Optional[Tuple[str, str]]]:
        """Execute one serialized RPC while holding ``_send_lock``."""
        try:
            payload = json.dumps(self._attach_client_info(command)).encode("utf-8")
        except Exception as e:
            logger.debug("send_command serialization error: %s", e)
            return {"status": "error", "error": str(e)}, ("ERROR", f"{summary} failed: {e}")

        try:
            self._active_rpc = (sock, conn_gen)
            sock.sendall(len(payload).to_bytes(4, "big"))
            sock.sendall(payload)

            with self._temporary_rpc_timeout(sock):
                # Drain any OBS frames that arrived before the response
                self._drain_obs_frames()

                length_bytes = self._recv_exact(4)
                if not length_bytes:
                    return self._fail_post_send_rpc(
                        sock, conn_gen, summary, self._no_response_reason()
                    )

                # After _recv_exact we may have read more data into _buffer.
                # If the 4 bytes we got look like the OBS or LOG prefix, drain and retry.
                while length_bytes == self.OBS_PREFIX or length_bytes == self.LOG_PREFIX:
                    obs_len_bytes = self._recv_exact(4)
                    if not obs_len_bytes:
                        return self._fail_post_send_rpc(
                            sock, conn_gen, summary, "Truncated frame"
                        )
                    obs_len = int.from_bytes(obs_len_bytes, "big")
                    if obs_len > 0:
                        obs_data = self._recv_exact(obs_len)
                        if not obs_data:
                            return self._fail_post_send_rpc(
                                sock, conn_gen, summary, "Truncated payload"
                            )
                    self._drain_obs_frames()
                    length_bytes = self._recv_exact(4)
                    if not length_bytes:
                        return self._fail_post_send_rpc(
                            sock, conn_gen, summary, self._no_response_reason()
                        )

                length = int.from_bytes(length_bytes, "big")
                data = self._recv_exact(length)
                if not data:
                    return self._fail_post_send_rpc(
                        sock, conn_gen, summary, "Incomplete response"
                    )

            try:
                result = json.loads(data.decode("utf-8"))
                if not isinstance(result, dict):
                    raise ValueError(
                        f"Expected JSON object response, got {type(result).__name__}"
                    )
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as e:
                return self._fail_post_send_rpc(
                    sock, conn_gen, summary, f"Invalid response payload ({e})"
                )

            if result.get("status") == "error":
                return result, (
                    "ERROR",
                    f"{summary} failed: {result.get('error', 'unknown error')}",
                )
            return result, None

        except Exception as e:
            logger.debug("send_command error: %s", e)
            return self._fail_post_send_rpc(sock, conn_gen, summary, str(e))
        finally:
            self._active_rpc = None

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Send a command and receive the immediate response.

        Because the agent broadcasts OBS: frames to ALL connections
        (including this one), observation data may arrive in the socket
        buffer before the command response.  We drain any such frames
        before reading the 4-byte response length so that we don't
        mis-interpret ``OBS:`` (0x4f42533a) as a payload size.

        A lock serialises concurrent callers (e.g. Textual worker threads
        issuing commands and completions simultaneously) so that only one
        send/receive cycle uses the socket at a time.  If an RPC fails after
        sending (timeout, truncation, parse error, or socket error), the
        connection is invalidated rather than reused or retried so subsequent
        calls never consume a delayed/stale reply.
        """
        summary = self._summarize_command(command)
        pending_activity: Optional[Tuple[str, str]] = None

        with self._send_lock:
            with self._state_lock:
                sock = self._sock
                conn_gen = self._connection_generation

            if sock is None:
                pending_activity = ("ERROR", f"{summary} failed: not connected")
                result = {"status": "error", "error": "Not connected"}
            else:
                result, pending_activity = self._send_command_locked(
                    sock, conn_gen, command, summary
                )

        if pending_activity is not None:
            self._report_activity(pending_activity[0], pending_activity[1])
        return result

    def _drain_buffered_observations(self) -> List[Dict[str, Any]]:
        """Extract all complete observation frames currently in ``_buffer``."""
        frames: List[Dict[str, Any]] = []
        while True:
            obs = self._extract_observation()
            if obs is None:
                break
            frames.append(obs)
        return frames

    def stream_observations(self) -> Generator[Dict[str, Any], None, None]:
        """
        Yield observations as they arrive from the agent.

        This generator blocks waiting for observations. Use with a timeout
        or run in a separate thread. Exits when connection closes, reconnects
        to a new generation, or encounters an error.
        """
        with self._state_lock:
            if not self._sock:
                return
            reader_gen = self._connection_generation

        while True:
            # Read and parse under the lock, but yield and report activity
            # outside of it so a slow consumer or callback never blocks other
            # users of the socket/buffer.
            pending: List[Dict[str, Any]] = []
            should_break = False
            pending_activity: Optional[Tuple[str, str]] = None
            try:
                with self._stream_read_lock:
                    with self._state_lock:
                        if (
                            self._stop_event.is_set()
                            or self._connection_generation != reader_gen
                            or self._sock is None
                        ):
                            should_break = True
                        sock = self._sock

                    if not should_break:
                        # Parse any trailing complete frames already buffered
                        # (e.g. read ahead by send_command) before blocking/EOF on recv.
                        pending = self._drain_buffered_observations()

                    if not should_break and not pending:
                        assert sock is not None
                        chunk = sock.recv(4096)
                        if not chunk:
                            with self._state_lock:
                                same_gen = (
                                    not self._stop_event.is_set()
                                    and self._connection_generation == reader_gen
                                )
                            if same_gen:
                                pending_activity = (
                                    "WARNING",
                                    "observation stream closed by peer",
                                )
                            should_break = True
                        else:
                            with self._state_lock:
                                if (
                                    self._stop_event.is_set()
                                    or self._connection_generation != reader_gen
                                ):
                                    should_break = True
                                else:
                                    self._buffer += chunk
                            if not should_break:
                                pending = self._drain_buffered_observations()
            except socket.timeout:
                continue
            except OSError as e:
                with self._state_lock:
                    same_gen = (
                        not self._stop_event.is_set()
                        and self._connection_generation == reader_gen
                    )
                if same_gen:
                    pending_activity = ("WARNING", f"observation stream error: {e}")
                should_break = True
            except Exception:
                with self._state_lock:
                    same_gen = (
                        not self._stop_event.is_set()
                        and self._connection_generation == reader_gen
                    )
                if same_gen:
                    pending_activity = (
                        "WARNING",
                        "observation stream crashed unexpectedly",
                    )
                logger.debug("Unexpected error in stream_observations", exc_info=True)
                should_break = True

            if pending_activity is not None:
                self._report_activity(pending_activity[0], pending_activity[1])

            for obs in pending:
                with self._state_lock:
                    if (
                        self._stop_event.is_set()
                        or self._connection_generation != reader_gen
                    ):
                        should_break = True
                        break
                yield obs

            if should_break:
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
        active_rpc = self._active_rpc
        with self._state_lock:
            if active_rpc is not None:
                pinned_sock, pinned_gen = active_rpc
                if (
                    self._connection_generation != pinned_gen
                    or self._sock is not pinned_sock
                ):
                    return
            while self._buffer.startswith(self.OBS_PREFIX) or self._buffer.startswith(
                self.LOG_PREFIX
            ):
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

    def _consume_buffer(self, size: int) -> bytes:
        """Pop ``size`` bytes from the front of ``_buffer``."""
        result = self._buffer[:size]
        self._buffer = self._buffer[size:]
        return result

    def _recv_exact(self, size: int) -> bytes:
        """Receive exactly ``size`` bytes, using buffer first."""
        self._last_recv_error = None
        active_rpc = self._active_rpc

        while True:
            if active_rpc is not None:
                pinned_sock, pinned_gen = active_rpc
                with self._state_lock:
                    if (
                        self._connection_generation != pinned_gen
                        or self._sock is not pinned_sock
                    ):
                        self._last_recv_error = "disconnected"
                        return b""
                    if len(self._buffer) >= size:
                        return self._consume_buffer(size)
                sock: Optional[socket.socket] = pinned_sock
            else:
                if len(self._buffer) >= size:
                    return self._consume_buffer(size)
                sock = self._sock
                if sock is None:
                    self._last_recv_error = "disconnected"
                    return b""

            try:
                chunk = sock.recv(4096)
                if not chunk:
                    self._last_recv_error = "eof"
                    return b""
                if active_rpc is not None:
                    _, pinned_gen = active_rpc
                    with self._state_lock:
                        if self._connection_generation != pinned_gen:
                            self._last_recv_error = "disconnected"
                            return b""
                        self._buffer += chunk
                else:
                    self._buffer += chunk
            except socket.timeout:
                self._last_recv_error = "timeout"
                return b""

    def __enter__(self) -> "StreamingAgentClient":
        self.connect()
        return self

    def __exit__(self, *args: Any) -> None:
        self.disconnect()
