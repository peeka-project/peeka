# pyright: reportImportCycles=false
"""
Agent Code - Runs inside target process
This code is injected into the target process and handles command execution
"""

from collections import deque

import atexit
import json
import logging
import signal
import socket
import sys
import threading
import time as _time
import traceback
from pathlib import Path
from typing import Any, Deque, Dict, List, Optional, Tuple, cast

from peeka.core import probes as probes_module
from peeka.core.agent_control.clients import AgentClientControlMixin
from peeka.core.agent_control.consumers import AgentConsumerControlMixin
from peeka.core.agent_control.dispatch import AgentCommandDispatchMixin
from peeka.core.agent_control.dx import AgentDXControlMixin
from peeka.core.agent_control.jobs import AgentJobControlMixin
from peeka.core.agent_control.lifecycle import shutdown_agent_resources
from peeka.core.agent_control.probes import AgentProbeControlMixin
from peeka.core.agent_control.target import AgentTargetControlMixin
from peeka.core.injector import DecoratorInjector
from peeka.core.jobs import job_registry
from peeka.core.observer import ObservationManager
from peeka.core.probes import ProbeContext
from peeka.core.probes import ProbeRegistry
from peeka.core.runtime import primitives as _rpl

# Lazy import to avoid circular dependency issues
_client_registry = None
_consumer_registry = None
_dx_case_registry = None


def _get_client_registry():
    """Lazily initialize and return the global client registry singleton."""
    global _client_registry
    if _client_registry is None:
        from peeka.core.client_sessions import ClientRegistry
        _client_registry = ClientRegistry()
    return _client_registry


def _get_consumer_registry():
    """Lazily initialize and return the global result consumer registry singleton."""
    global _consumer_registry
    if _consumer_registry is None:
        from peeka.core.result_consumers import ResultConsumerRegistry
        _consumer_registry = ResultConsumerRegistry()
    return _consumer_registry


def _get_dx_case_registry():
    """Lazily initialize and return the global DX case registry singleton."""
    global _dx_case_registry
    if _dx_case_registry is None:
        from peeka.core.dx_cases import DXCaseRegistry

        _dx_case_registry = DXCaseRegistry()
    return _dx_case_registry


def _get_requesting_client_session_id(command: Dict[str, Any]) -> Optional[str]:
    """Return the explicit client session id associated with a command."""
    client_session_id = command.get("client_session_id")
    if client_session_id in (None, ""):
        return None
    return str(client_session_id)


def _consumer_owner_matches(consumer: Any, requesting_client_session_id: Optional[str]) -> bool:
    """Return True if the requesting client is allowed to access the consumer."""
    owner = consumer.client_session_id
    if owner in (None, ""):
        return requesting_client_session_id is None
    return owner == requesting_client_session_id


def _dx_owner_matches(dx_case: Any, requesting_client_session_id: Optional[str]) -> bool:
    """Return True if the requesting client is allowed to access the DX case."""
    owner = dx_case.client_session_id
    if owner in (None, ""):
        return requesting_client_session_id is None
    return owner == requesting_client_session_id


def _client_success(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a standard success envelope for client namespace handlers."""
    return {"status": "success", "data": data}


def _client_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for client namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
    }


def _job_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for job namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "error": f"{error_code}: {message}",
    }


def _consumer_success(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a standard success envelope for consumer namespace handlers."""
    return {"status": "success", "data": data}


def _consumer_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for consumer namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "error": f"{error_code}: {message}",
    }


def _dx_success(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a standard success envelope for dx namespace handlers."""
    return {"status": "success", "data": data}


def _dx_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for dx namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "error": f"{error_code}: {message}",
    }


def _probe_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for probe namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "error": f"{error_code}: {message}",
    }


def _response_message(response: Dict[str, Any], fallback: str) -> str:
    """Return the most specific human-readable message in a response."""
    message = response.get("message") or response.get("error")
    if message:
        return str(message)
    return fallback


class _ObservationQueue(deque):  # pyright: ignore[reportMissingTypeArgument]
    """Bounded FIFO queue for observations destined to one stream client."""

    @property
    def maxsize(self) -> Optional[int]:
        """Return the configured capacity using queue.Queue-compatible naming."""
        return self.maxlen

    def put_nowait(self, item: Any) -> None:
        """Append an item without blocking, dropping the oldest item when full."""
        self.append(item)

    def get_nowait(self) -> Any:
        """Pop the oldest item without blocking."""
        return self.popleft()

    def empty(self) -> bool:
        """Return True when the queue has no pending observations."""
        return len(self) == 0


def _write_session_log(
    session_id: str, level: str, message: str, details: Optional[str] = None
) -> None:
    """Persist agent diagnostics without touching the target process stdio."""
    try:
        log_path = Path(f"/tmp/peeka_{session_id}.log")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{_time.time():.3f} {level} {message}\n")
            if details:
                log_file.write(details.rstrip() + "\n")
    except OSError:
        pass


class PeekaAgent(
    AgentTargetControlMixin,
    AgentProbeControlMixin,
    AgentClientControlMixin,
    AgentJobControlMixin,
    AgentConsumerControlMixin,
    AgentDXControlMixin,
    AgentCommandDispatchMixin,
):
    """Agent running inside target process"""

    _get_client_registry = staticmethod(_get_client_registry)
    _get_consumer_registry = staticmethod(_get_consumer_registry)
    _get_dx_case_registry = staticmethod(_get_dx_case_registry)
    _job_registry = staticmethod(lambda: job_registry)
    _get_requesting_client_session_id = staticmethod(_get_requesting_client_session_id)
    _consumer_owner_matches = staticmethod(_consumer_owner_matches)
    _dx_owner_matches = staticmethod(_dx_owner_matches)
    _client_success = staticmethod(_client_success)
    _client_error = staticmethod(_client_error)
    _job_error = staticmethod(_job_error)
    _consumer_success = staticmethod(_consumer_success)
    _consumer_error = staticmethod(_consumer_error)
    _dx_success = staticmethod(_dx_success)
    _dx_error = staticmethod(_dx_error)
    _probe_error = staticmethod(_probe_error)
    _response_message = staticmethod(_response_message)

    _OBS_STREAM_COMMANDS = {
        "watch": {"", "start"},
        "trace": {"", "start"},
        "stack": {"", "start"},
        "monitor": {"", "start"},
        "top": {"", "start"},
    }

    _QUIET_COMMAND_ACTIONS = {
        ("complete", ""),
        ("logger", "get"),
        ("logger", "list"),
        ("memory", "gc"),
        ("memory", "overview"),
        ("memory", "top"),
        ("monitor", "status"),
        ("reset", "list"),
        ("sc", ""),
        ("sm", ""),
        ("stack", "status"),
        ("target", "hello"),
        ("target", "status"),
        ("thread", "detail"),
        ("thread", "list"),
        ("top", "snapshot"),
        ("trace", "status"),
        ("vmtool", "count"),
        ("vmtool", "get"),
        ("vmtool", "instances"),
        ("watch", "status"),
    }

    # Lazy command registry: (module_path, class_name) tuples.
    # Commands are imported and instantiated on first dispatch,
    # dramatically reducing startup time under GDB injection.
    _COMMAND_REGISTRY: Dict[str, Tuple[str, str]] = {
        "complete": ("peeka.commands.complete", "CompleteCommand"),
        "watch": ("peeka.commands.watch", "WatchCommand"),
        "trace": ("peeka.commands.trace", "TraceCommand"),
        "stack": ("peeka.commands.stack", "StackCommand"),
        "logger": ("peeka.commands.logger", "LoggerCommand"),
        "sc": ("peeka.commands.search", "SearchClassCommand"),
        "sm": ("peeka.commands.search", "SearchMethodCommand"),
        "monitor": ("peeka.commands.monitor", "MonitorCommand"),
        "memory": ("peeka.commands.memory", "MemoryCommand"),
        "reset": ("peeka.commands.reset", "ResetCommand"),
        "vmtool": ("peeka.commands.vmtool", "VMToolCommand"),
        "detach": ("peeka.commands.detach", "DetachCommand"),
        "thread": ("peeka.commands.thread", "ThreadCommand"),
        "top": ("peeka.commands.top", "TopCommand"),
        "patch-status": ("peeka.commands.patch_status", "PatchStatusCommand"),
    }

    def __init__(
        self,
        session_id: str,
        attached_pid: Optional[int] = None,
        notify_port: int = 0,
        suppress_startup_messages: bool = False,
        agent_mode: Optional[str] = None,
        injection_mode: Optional[str] = None,
    ):
        self.session_id = session_id
        self.attached_pid = attached_pid
        self.running = True
        self.suppress_startup_messages = suppress_startup_messages
        self.sock_path = f"/tmp/peeka_{session_id}.sock"
        self.server: Optional[socket.socket] = None
        self.command_handlers: Dict[str, Any] = {}
        self._client_connections: List[socket.socket] = []
        self._client_connection_kinds: Dict[socket.socket, str] = {}
        self._client_write_locks: Dict[socket.socket, Any] = {}
        self._connections_lock = _rpl.allocate_lock()  # DOMAIN: native_thread
        self._observation_queues: Dict[Any, Deque[Any]] = {}
        self._observation_queue_stats: Dict[Any, Dict[str, int]] = {}
        self._observation_queue_flushers: Dict[Any, Any] = {}
        self._observation_queue_lock = _rpl.allocate_lock()
        self._observation_sequence = 0
        self._observation_flush_event = _rpl.create_event()
        self._flush_thread_running = False
        self._flush_thread_id: Optional[int] = None
        self._mutation_lock: threading.RLock = threading.RLock()  # DOMAIN: mixed (command orchestration)

        self._client_counter = 0
        self.observer = ObservationManager()
        self.injector = DecoratorInjector(self)  # pyright: ignore[reportArgumentType]
        self.watch_orphan_grace_seconds = 3600.0
        self.probe_registry: ProbeRegistry = probes_module.probe_registry
        self._probe_contexts: Dict[str, ProbeContext] = {}
        self._probe_context_types: Dict[str, str] = {}
        self._probe_context_lock = _rpl.allocate_lock()  # DOMAIN: mixed (probe lifecycle)

        self._notify_port = notify_port
        
        # Target identification fields (transitional: default from runtime)
        self.agent_mode = agent_mode or "injected"
        if injection_mode:
            self.injection_mode = injection_mode
        else:
            # Default from Python version: PEP 768 for 3.14+ else GDB fallback
            self.injection_mode = "pep768" if sys.version_info >= (3, 14) else "gdb_dlopen"
        
        # Error ring buffer for target.status (last 5 errors)
        self._recent_errors: List[Dict[str, Any]] = []
        self._error_ring_lock = _rpl.allocate_lock()  # DOMAIN: native_thread
        self._stopped: bool = False
        self._stop_lock = threading.Lock()
        self._prev_sigterm_handler: Any = None
        atexit.register(self.stop)
        if threading.current_thread() is threading.main_thread():
            try:
                self._prev_sigterm_handler = signal.signal(signal.SIGTERM, self._handle_sigterm)
            except (ValueError, OSError):
                self._prev_sigterm_handler = None
        self._last_seen_at = _time.time()

    def _handle_sigterm(self, signum: int, frame: Any) -> None:
        self.stop()
        prev = self._prev_sigterm_handler
        if callable(prev) and prev not in (signal.SIG_DFL, signal.SIG_IGN):
            prev(signum, frame)

    # ------------------------------------------------------------------ #
    #  Lazy command handler loading                                      #
    # ------------------------------------------------------------------ #

    def _get_handler(self, cmd_type: str) -> Optional[Any]:
        """Return the handler for *cmd_type*, importing lazily if needed."""
        handler = self.command_handlers.get(cmd_type)
        if handler is not None:
            return handler

        spec = self._COMMAND_REGISTRY.get(cmd_type)
        if spec is None:
            return None

        module_path, class_name = spec
        try:
            import importlib

            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            handler = cls(self)  # type: ignore[abstract]
            self.command_handlers[cmd_type] = handler
            return handler
        except Exception:
            self._emit_log(
                "ERROR",
                f"[peeka Agent] Failed to load handler for {cmd_type}",
                traceback.format_exc(),
            )
            return None

    def _emit_log(
        self, level: str, message: str, details: Optional[str] = None
    ) -> None:
        """Send diagnostics through side channels only."""
        self._send_log(level, message)
        _write_session_log(self.session_id, level, message, details)

    def _add_recent_error(self, error_entry: Dict[str, Any]) -> None:
        """Add an error entry to the ring buffer (max 5)."""
        with self._error_ring_lock:
            self._recent_errors.append(error_entry)
            if len(self._recent_errors) > 5:
                self._recent_errors.pop(0)

    def is_client_session_live(self, client_session_id: Optional[str]) -> bool:
        """Return True when a client session is still registered as live."""
        if client_session_id in (None, ""):
            return False
        try:
            return self._get_client_registry().get(str(client_session_id)) is not None
        except Exception:
            return True  # Fail-open: registry lookup error must not trigger orphan cleanup.

    def cleanup_orphan_watches(self, now: Optional[float] = None) -> int:
        """Sweep abandoned watch probes after owner-loss grace expires."""
        return self.injector.cleanup_orphan_watches(now=now)
    







    def _register_handlers(self) -> None:
        """Eagerly import and register ALL command handlers.

        Used by `start()` after the socket is ready so that commands
        are available immediately.  Runs on the agent thread so it
        does not block GIL during GDB injection.
        """
        for cmd_type in list(self._COMMAND_REGISTRY):
            self._get_handler(cmd_type)

    @staticmethod
    def _normalize_action(command: Dict[str, Any]) -> str:
        """Return a normalized action name for logging decisions."""
        action = command.get("action")
        if action is None:
            return ""
        return str(action).lower()

    def _should_log_command(self, command: Dict[str, Any]) -> bool:
        """Return True when a command is worth surfacing in agent activity logs."""
        cmd_type = str(command.get("type", "unknown"))
        action = self._normalize_action(command)
        return (cmd_type, action) not in self._QUIET_COMMAND_ACTIONS

    @staticmethod
    def _sanitize_client_field(value: Any, default: str) -> str:
        """Normalize client identity fields before placing them in logs."""
        text = str(value if value not in (None, "") else default)
        sanitized = []
        for char in text[:48]:
            if char.isalnum() or char in ("-", "_", "."):
                sanitized.append(char)
            else:
                sanitized.append("_")
        return "".join(sanitized) or default

    def _extract_client_info(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Extract sanitized client metadata from a command payload."""
        raw_info = command.get("_client")
        if not isinstance(raw_info, dict):
            return {}

        info: Dict[str, Any] = {
            "id": self._sanitize_client_field(raw_info.get("id"), "anonymous"),
            "source": self._sanitize_client_field(raw_info.get("source"), "unknown"),
            "kind": self._sanitize_client_field(raw_info.get("kind"), "client"),
        }
        pid = raw_info.get("pid")
        if isinstance(pid, int) or (isinstance(pid, str) and pid.isdigit()):
            info["pid"] = str(pid)
        return info

    @staticmethod
    def _strip_client_info(command: Dict[str, Any]) -> Dict[str, Any]:
        """Remove transport metadata before command dispatch."""
        if "_client" not in command:
            return command
        stripped = dict(command)
        stripped.pop("_client", None)
        return stripped

    def _is_client_hello(self, command: Dict[str, Any]) -> bool:
        """Return True for client identity frames handled by the transport layer."""
        cmd_type = str(command.get("type", ""))
        action = self._normalize_action(command)
        return cmd_type == "client" and action == "hello"

    @staticmethod
    def _client_info_requests_stream(client_info: Dict[str, Any]) -> bool:
        """Return True when client metadata identifies a stream-only connection."""
        source = str(client_info.get("source", ""))
        kind = str(client_info.get("kind", ""))
        return kind == "stream" or source.endswith("-stream")

    @staticmethod
    def _format_client_label(client_id: int, client_info: Dict[str, Any]) -> str:
        """Return a readable stable client label for activity logs."""
        instance_id = client_info.get("id")
        source = client_info.get("source")
        if instance_id and source:
            return f"client {instance_id}/{source} conn#{client_id}"
        return f"conn#{client_id}"

    def _summarize_command(self, command: Dict[str, Any]) -> str:
        """Build a concise command summary for agent-side diagnostics."""
        cmd_type = str(command.get("type", "unknown"))
        action = self._normalize_action(command) or "execute"
        details = []

        for key in ("pattern", "watch_id", "top_id", "logger", "level", "target"):
            value = command.get(key)
            if value not in (None, ""):
                details.append(f"{key}={value}")

        if "interval" in command:
            details.append(f"interval={command.get('interval')}")
        if "times" in command:
            details.append(f"times={command.get('times')}")

        summary = f"{cmd_type}/{action}"
        if details:
            summary += " " + " ".join(details[:4])
        return summary

    @staticmethod
    def _summarize_result(result: Dict[str, Any]) -> str:
        """Build a concise result summary for command completion logs."""
        details = []
        for key in ("watch_id", "top_id", "message", "observation_count"):
            value = result.get(key)
            if value not in (None, "", []):
                details.append(f"{key}={value}")

        if not details:
            return "success"
        return "success " + " ".join(details[:3])

    def start(self) -> bool:
        try:
            self.server = _rpl.create_socket("AF_UNIX", "SOCK_STREAM")

            if Path(self.sock_path).exists():
                Path(self.sock_path).unlink()

            assert self.server is not None
            self.server.bind(self.sock_path)
            self.server.listen(5)
            # Set a timeout so accept() doesn't block forever,
            # allowing the accept loop to check self.running periodically.
            self.server.settimeout(1.0)

            # Start the accept loop with a native low-level thread. Do not use
            # target-process threading primitives here: frameworks such as
            # gevent may monkey-patch threading.Event/Thread and make blocking
            # waits illegal in the injection callback.
            _rpl.start_thread(self._accept_loop)

            # Signal readiness via TCP reverse-connect (preferred) and
            # .ready file (fallback / backward compatibility).
            self._notify_ready()
            Path(f"/tmp/peeka_{self.session_id}.ready").touch()
            msg_start = "[peeka Agent] Started and listening for connections"
            msg_ready = "[peeka Agent] Ready for commands"
            self._emit_log("INFO", msg_start)
            self._emit_log("INFO", msg_ready)

            # Eagerly load all command handlers now that the socket is
            # ready.  This runs on the agent thread (not GIL-blocking).
            self._register_handlers()
            self._start_flush_thread()
            return True

        except Exception as e:
            self.running = False
            self._signal_observation_queue_drain()
            if self.server:
                try:
                    self.server.close()
                except OSError:
                    pass
            self._cleanup_session_files()
            msg = f"[peeka Agent] Start failed: {e}"
            self._emit_log("ERROR", msg, traceback.format_exc())
            return False

    def _accept_loop(self) -> None:
        while self.running:
            try:
                if self.server is None:
                    break
                conn, _ = _rpl.native_accept(self.server)
                self._client_counter += 1
                _rpl.start_thread(self._handle_client, (conn, self._client_counter))
            except socket.timeout:
                # Periodic wakeup to re-check self.running
                continue
            except OSError:
                # Server socket closed (stop() called) — exit cleanly
                break
            except Exception as e:
                if self.running:
                    msg = f"[peeka Agent] Accept error: {e}"
                    self._emit_log("ERROR", msg, traceback.format_exc())

    def _register_client_connection(
        self, conn: socket.socket, kind: str = "control"
    ) -> int:
        """Track a live client connection and initialize its write lock."""
        with self._connections_lock:
            self._client_connections.append(conn)
            self._client_connection_kinds[conn] = kind
            self._client_write_locks[conn] = _rpl.allocate_lock()
            connection_count = len(self._client_connections)
        if kind == "stream":
            self._get_or_create_connection_queue(conn)
            self._start_flush_thread()
        return connection_count

    @staticmethod
    def _new_observation_queue_stats() -> Dict[str, int]:
        """Return a fresh stats dictionary for one observation queue."""
        return {
            "enqueued": 0,
            "delivered": 0,
            "dropped": 0,
            "dropped_count": 0,
            "encode_dropped_count": 0,
            "oversize_dropped_count": 0,
            "drain_dropped": 0,
            "drain_dropped_count": 0,
            "slow_evicted_count": 0,
            "evicted_count": 0,
        }

    def _get_or_create_connection_queue(self, conn: socket.socket) -> Deque[Any]:
        """Return the bounded observation queue for a stream connection.

        Args:
            conn: Client connection that receives observation frames.

        Returns:
            The per-connection FIFO observation queue.
        """
        with self._observation_queue_lock:
            queue = self._observation_queues.get(conn)
            if queue is None:
                queue = _ObservationQueue(maxlen=1024)
                self._observation_queues[conn] = queue
                self._observation_queue_stats[conn] = self._new_observation_queue_stats()
                if self._flush_thread_id is not None:
                    self._observation_queue_flushers[conn] = self._flush_thread_id
            return queue

    def _enqueue_observation(self, conn: socket.socket, item: Any) -> None:
        """Enqueue an observation for a stream connection and track overflow."""
        with self._observation_queue_lock:
            queue = self._observation_queues.get(conn)
            if queue is None:
                queue = _ObservationQueue(maxlen=1024)
                self._observation_queues[conn] = queue
                self._observation_queue_stats[conn] = self._new_observation_queue_stats()
                if self._flush_thread_id is not None:
                    self._observation_queue_flushers[conn] = self._flush_thread_id

            stats = self._observation_queue_stats[conn]
            if queue.maxlen is not None and len(queue) == queue.maxlen:
                stats["dropped"] += 1
                stats["dropped_count"] += 1

            queue.append(item)
            stats["enqueued"] += 1

    def _set_client_connection_kind(self, conn: socket.socket, kind: str) -> None:
        """Update the broadcast kind for a live client connection."""
        with self._connections_lock:
            if conn in self._client_connections:
                self._client_connection_kinds[conn] = kind
        if kind == "stream":
            self._get_or_create_connection_queue(conn)
            self._start_flush_thread()

    def _unregister_client_connection(self, conn: socket.socket) -> int:
        """Forget a client connection, write lock, and observation queue."""
        with self._connections_lock:
            if conn in self._client_connections:
                self._client_connections.remove(conn)
            self._client_connection_kinds.pop(conn, None)
            self._client_write_locks.pop(conn, None)
            connection_count = len(self._client_connections)
        with self._observation_queue_lock:
            self._observation_queues.pop(conn, None)
            self._observation_queue_stats.pop(conn, None)
            self._observation_queue_flushers.pop(conn, None)
        return connection_count

    def _start_flush_thread(self) -> None:
        """Start the observation queue flush worker on a native thread."""
        if self._flush_thread_id is not None:
            return
        self._flush_thread_running = True
        thread_id = _rpl.start_thread(
            self._flush_loop,
            name="peeka-observation-flusher",
        )
        self._flush_thread_id = thread_id
        with self._observation_queue_lock:
            for conn in self._observation_queues:
                self._observation_queue_flushers[conn] = thread_id

    def _flush_loop(self) -> None:
        """Flush queued observations to stream sockets until the agent stops."""
        while self._flush_thread_running:
            try:
                self._observation_flush_event.wait(timeout=0.05)
                self._observation_flush_event.clear()
                self._flush_all_connections()
            except Exception:
                self._emit_log(
                    "ERROR",
                    "[peeka Agent] Observation flush loop error",
                    traceback.format_exc(),
                )

    def _flush_all_connections(self) -> None:
        """Drain pending observation batches for all stream connections."""
        dead_connections = []
        with self._observation_queue_lock:
            conn_list = list(self._observation_queues.keys())

        for conn in conn_list:
            if not self._flush_connection(conn):
                dead_connections.append(conn)

        for conn in dead_connections:
            self._unregister_client_connection(conn)

    def _encode_observation_frame(self, observation: Any) -> Optional[bytes]:
        """Encode one queued observation as an OBS frame."""
        if isinstance(observation, bytes):
            if observation.startswith(b"OBS:"):
                return observation
            return None
        try:
            payload = json.dumps(observation).encode("utf-8")
        except (TypeError, ValueError):
            return None
        return b"OBS:" + len(payload).to_bytes(4, "big") + payload

    def _flush_connection(self, conn: socket.socket) -> bool:
        """Flush a bounded batch for one connection; return False if dead."""
        max_batch_count = 64
        max_batch_bytes = 256 * 1024
        frames = bytearray()
        encoded_count = 0
        dropped_count = 0
        encode_dropped_count = 0
        oversize_dropped_count = 0
        processed_count = 0

        while processed_count < max_batch_count:
            with self._observation_queue_lock:
                queue = self._observation_queues.get(conn)
                if queue is None:
                    break
                if not queue:
                    break
                observation = queue.popleft()

            frame = self._encode_observation_frame(observation)
            if frame is None:
                dropped_count += 1
                encode_dropped_count += 1
                processed_count += 1
                continue

            if len(frame) > max_batch_bytes:
                dropped_count += 1
                oversize_dropped_count += 1
                processed_count += 1
                continue

            if len(frames) + len(frame) > max_batch_bytes:
                with self._observation_queue_lock:
                    queue = self._observation_queues.get(conn)
                    if queue is not None:
                        queue.appendleft(observation)
                break

            frames.extend(frame)
            encoded_count += 1
            processed_count += 1

        if dropped_count:
            with self._observation_queue_lock:
                stats = self._observation_queue_stats.get(conn)
                if stats is not None:
                    stats["dropped"] += dropped_count
                    stats["dropped_count"] += dropped_count
                    stats["encode_dropped_count"] = (
                        stats.get("encode_dropped_count", 0) + encode_dropped_count
                    )
                    stats["oversize_dropped_count"] = (
                        stats.get("oversize_dropped_count", 0) + oversize_dropped_count
                    )

        if not frames:
            return True

        if not self._send_observation_frames_with_timeout(conn, bytes(frames)):
            self._record_slow_client_eviction(conn)
            return False

        with self._observation_queue_lock:
            stats = self._observation_queue_stats.get(conn)
            if stats is not None:
                stats["delivered"] += encoded_count
        return True

    def _record_slow_client_eviction(self, conn: socket.socket) -> None:
        """Increment slow-client eviction counters for a stream connection."""
        with self._observation_queue_lock:
            stats = self._observation_queue_stats.get(conn)
            if stats is not None:
                stats["slow_evicted_count"] = stats.get("slow_evicted_count", 0) + 1
                stats["evicted_count"] = stats.get("evicted_count", 0) + 1

    def _send_observation_frames_with_timeout(
        self, conn: socket.socket, frames: bytes, timeout: float = 0.1
    ) -> bool:
        """Send observation frames with a bounded per-connection timeout."""
        try:
            conn.settimeout(timeout)
        except Exception:
            pass

        done = _rpl.allocate_lock()
        done.acquire()
        result = {"success": False}

        def send_frames() -> None:
            try:
                result["success"] = self._send_frame_to_connection(conn, frames)
            finally:
                try:
                    done.release()
                except Exception:
                    pass

        try:
            _rpl.start_thread(send_frames, name="peeka-observation-send")
            if not done.acquire(blocking=True, timeout=timeout):
                return False
            return bool(result["success"])
        finally:
            try:
                conn.settimeout(None)
            except Exception:
                pass

    def _signal_observation_queue_drain(self) -> None:
        """Signal the flush worker to stop and wake any pending wait."""
        self._flush_thread_running = False
        try:
            self._observation_flush_event.set()
        except Exception:
            pass

    def _snapshot_client_connections(
        self, kind: Optional[str] = None
    ) -> List[socket.socket]:
        """Return a snapshot of currently tracked client sockets."""
        with self._connections_lock:
            if kind is not None:
                return [
                    conn
                    for conn in self._client_connections
                    if self._client_connection_kinds.get(conn, "control") == kind
                ]
            return list(self._client_connections)

    @classmethod
    def _command_opens_observation_stream(cls, command: Dict[str, Any]) -> bool:
        """Return True when a command should receive future OBS broadcasts."""
        cmd_type = str(command.get("type", ""))
        action = str(command.get("action", ""))
        allowed_actions = cls._OBS_STREAM_COMMANDS.get(cmd_type)
        if allowed_actions is None:
            return False
        return action in allowed_actions

    def _send_frame_to_connection(self, conn: socket.socket, frame: bytes) -> bool:
        """Send one framed message to a tracked connection.

        Returns:
            True when the frame is written successfully, else False.
        """
        with self._connections_lock:
            write_lock = self._client_write_locks.get(conn)
        if write_lock is None:
            return False

        try:
            with write_lock:
                conn.sendall(frame)
            return True
        except Exception:
            return False

    def _handle_client(self, conn: socket.socket, client_id: int) -> None:
        connection_total = self._register_client_connection(conn)

        client_info: Dict[str, Any] = {}
        identified = False
        client_label = self._format_client_label(client_id, client_info)

        try:
            while True:
                length_bytes = conn.recv(4)
                if not length_bytes:
                    break

                length = int.from_bytes(length_bytes, "big")
                data = b""
                while len(data) < length:
                    chunk = conn.recv(min(length - len(data), 4096))
                    if not chunk:
                        break
                    data += chunk

                if len(data) < length:
                    break

                raw_command = json.loads(data.decode("utf-8"))
                extracted_info = self._extract_client_info(raw_command)
                if extracted_info:
                    client_info = extracted_info
                    client_label = self._format_client_label(client_id, client_info)
                    if self._client_info_requests_stream(client_info):
                        self._set_client_connection_kind(conn, "stream")
                    if not identified:
                        pid = client_info.get("pid")
                        pid_suffix = f" pid={pid}" if pid else ""
                        kind = client_info.get("kind", "client")
                        self._emit_log(
                            "INFO",
                            (
                                f"[peeka Agent] {client_label} connected "
                                f"({connection_total} total) kind={kind}{pid_suffix}"
                            ),
                        )
                        identified = True

                command = self._strip_client_info(raw_command)
                if self._is_client_hello(command):
                    result = {"status": "success", "client": client_label}
                else:
                    should_log = self._should_log_command(command)
                    command_summary = self._summarize_command(command)
                    if should_log:
                        self._emit_log(
                            "INFO",
                            f"[peeka Agent] {client_label} -> {command_summary}",
                        )
                    result = self._execute_command(command)

                    if (
                        result.get("status") == "success"
                        and self._command_opens_observation_stream(command)
                    ):
                        self._set_client_connection_kind(conn, "stream")

                    if result.get("status") == "error":
                        self._emit_log(
                            "ERROR",
                            f"[peeka Agent] {client_label} {command_summary} failed: "
                            f"{result.get('error', 'unknown error')}",
                            result.get("traceback"),
                        )
                    elif should_log:
                        self._emit_log(
                            "INFO",
                            f"[peeka Agent] {client_label} {command_summary} "
                            f"{self._summarize_result(result)}",
                        )

                response = json.dumps(result).encode("utf-8")
                response_frame = len(response).to_bytes(4, "big") + response
                if not self._send_frame_to_connection(conn, response_frame):
                    break

        except Exception as e:
            msg = f"[peeka Agent] Client error: {e}"
            self._emit_log("ERROR", msg, traceback.format_exc())
        finally:
            connection_total = self._unregister_client_connection(conn)
            conn.close()
            self._emit_log(
                "INFO",
                f"[peeka Agent] {client_label} disconnected ({connection_total} total)",
            )


    def _send_observation(self, observation: Dict[str, Any]) -> None:
        """Called by injector when a watched function is invoked."""
        observation["type"] = "observation"
        with self._observation_queue_lock:
            self._observation_sequence += 1
            seq = self._observation_sequence
        observation["seq"] = seq
        self.observer.add_observation(observation)

        # Enqueue raw observation dict (no JSON encoding here).
        # JSON encoding and frame building happen in the flush thread.
        for conn in self._snapshot_client_connections(kind="stream"):
            self._enqueue_observation(conn, observation)

        if self._observation_flush_event is not None:
            try:
                self._observation_flush_event.set()
            except Exception:
                pass

    def _send_log(self, level: str, message: str) -> None:
        """Send a log message from Agent to all connected host clients."""
        log_msg = {
            "type": "log",
            "level": level,
            "message": message,
            "timestamp": _time.time(),
        }
        obs_json = json.dumps(log_msg).encode("utf-8")
        frame = b"LOG:" + len(obs_json).to_bytes(4, "big") + obs_json

        dead_connections = []
        for conn in self._snapshot_client_connections():
            if not self._send_frame_to_connection(conn, frame):
                dead_connections.append(conn)

        for conn in dead_connections:
            self._unregister_client_connection(conn)

    def _notify_ready(self) -> None:
        """Notify the attacher that the agent is ready via TCP."""
        if self._notify_port <= 0:
            return
        try:
            s = _rpl.create_socket("AF_INET", "SOCK_STREAM")
            s.settimeout(5.0)
            s.connect(("127.0.0.1", self._notify_port))
            s.sendall(b"READY")
            s.close()
        except Exception:
            # Non-fatal: attacher will fall back to .ready file polling.
            pass

    def stop(self) -> None:
        if self._stopped:
            return
        with self._stop_lock:
            if self._stopped:
                return
            self._stopped = True

        logger = logging.getLogger(__name__)
        # probe types discovered dynamically from agent state — do not hardcode
        shutdown_agent_resources(
            self, logger, self.list_tracked_probe_types()
        )

        self.running = False
        self._signal_observation_queue_drain()

        drain_deadline = _time.monotonic() + 0.3
        while _time.monotonic() < drain_deadline:
            with self._observation_queue_lock:
                total_queued = sum(len(queue) for queue in self._observation_queues.values())
            if total_queued == 0:
                break
            _time.sleep(0.01)

        with self._observation_queue_lock:
            for conn, queue in list(self._observation_queues.items()):
                remaining = len(queue)
                if remaining <= 0:
                    continue
                stats = self._observation_queue_stats.get(conn)
                if stats is not None:
                    stats["drain_dropped"] = stats.get("drain_dropped", 0) + remaining
                    stats["drain_dropped_count"] = stats.get("drain_dropped_count", 0) + remaining
                queue.clear()
        if self.server:
            try:
                self.server.close()
            except OSError:
                pass

        self._cleanup_session_files()

        # Remove self from the global agent registry
        agents = cast(Optional[Dict[str, "PeekaAgent"]], getattr(sys, "_peeka_agents", None))
        if agents is not None:
            keys_to_remove = [k for k, v in agents.items() if v is self]
            for k in keys_to_remove:
                del agents[k]

        try:
            atexit.unregister(self.stop)
        except Exception:
            # Non-fatal: atexit.unregister should not raise; silently skip on any error.
            pass
        if (
            self._prev_sigterm_handler is not None
            and threading.current_thread() is threading.main_thread()
        ):
            try:
                signal.signal(signal.SIGTERM, self._prev_sigterm_handler)
            except (ValueError, OSError):
                pass

    def _cleanup_session_files(self) -> None:
        """Remove .sock, .ready, and .pid files for this session.

        Called on stop/detach so that stale files don't trick
        _check_existing_attachment() into reporting a live agent.
        """
        for suffix in (".sock", ".ready", ".pid"):
            p = Path(f"/tmp/peeka_{self.session_id}{suffix}")
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def _init_agent(
    session_id: str,
    attached_pid: Optional[int] = None,
    notify_port: int = 0,
    suppress_startup_messages: bool = False,
) -> None:
    try:
        # Stop ALL existing agents from previous sessions to prevent thread leaks.
        # Each sys.remote_exec() call creates a new agent; without this cleanup,
        # old accept-loop and client-handler threads accumulate indefinitely.
        agents = cast(Optional[Dict[str, PeekaAgent]], getattr(sys, "_peeka_agents", None))
        if agents is not None:
            old_agents = list(agents.values())
            for old_agent in old_agents:
                try:
                    old_agent.stop()
                    msg = (
                        f"[peeka Agent] Stopped previous agent: {old_agent.session_id}"
                    )
                    old_agent._emit_log("INFO", msg)
                except Exception:
                    pass
            agents.clear()

        agent = PeekaAgent(
            session_id,
            attached_pid,
            notify_port=notify_port,
            suppress_startup_messages=suppress_startup_messages,
        )
        if agent.start():
            agents = cast(Optional[Dict[str, PeekaAgent]], getattr(sys, "_peeka_agents", None))
            if agents is None:
                agents = {}
                setattr(sys, "_peeka_agents", agents)
            agents[session_id] = agent
        else:
            msg = "[peeka Agent] Start failed; session not registered"
            _write_session_log(session_id, "ERROR", msg)

    except Exception as e:
        msg = f"[peeka Agent] Initialization failed: {e}"
        _write_session_log(session_id, "ERROR", msg, traceback.format_exc())


# Auto-initialize when injected via sys.remote_exec() or GDB
# {{SESSION_ID}}, {{ATTACHED_PID}}, and {{NOTIFY_PORT}} are replaced by
# ProcessAttacher before injection.
# This runs both when imported (PEP 768) and when exec'd (GDB fallback)
_session_id = "{{SESSION_ID}}"
_attached_pid_str = "{{ATTACHED_PID}}"
_notify_port_str = "{{NOTIFY_PORT}}"
_suppress_startup = "{{SUPPRESS_STARTUP_MESSAGES}}"
_attached_pid = int(_attached_pid_str) if _attached_pid_str.isdigit() else None
_notify_port = int(_notify_port_str) if _notify_port_str.isdigit() else 0
_suppress_startup_messages = _suppress_startup == "True"
if not _session_id.startswith("{{"):
    _init_agent(
        _session_id,
        _attached_pid,
        notify_port=_notify_port,
        suppress_startup_messages=_suppress_startup_messages,
    )


# ================================================================ #
# PEP 562 Module-level Deprecation Shim                            #
# ================================================================ #
# Backward-compatible access to relocated _NATIVE_* aliases.
# This shim coexists with the eager-capture block (lines 6-77)
# until T8 removes the eager block.


def __getattr__(name: str) -> Any:
    """PEP 562 module-level deprecation shim for relocated _NATIVE_* helpers."""
    _deprecated_aliases = {
        "_NATIVE_SOCKET": "_NATIVE_SOCKET",
        "_NATIVE_START_NEW_THREAD": "_NATIVE_START_NEW_THREAD",
        "_NATIVE_ALLOCATE_LOCK": "_NATIVE_ALLOCATE_LOCK",
        "_NATIVE_RLOCK": "_NATIVE_RLOCK",
        "_NATIVE_EVENT": "_NATIVE_EVENT",
        "_NATIVE_TIME": "_NATIVE_TIME",
        "_NATIVE_PERF_COUNTER": "_NATIVE_PERF_COUNTER",
        "_NATIVE_GET_IDENT": "_NATIVE_GET_IDENT",
        "_start_native_thread": "start_thread",
        "_native_accept": "native_accept",
        "_get_original_runtime_attr": "_get_original_runtime_attr",
    }

    if name in _deprecated_aliases:
        import warnings

        from peeka.core.runtime import primitives as _rpl

        warnings.warn(
            f"peeka.core.agent.{name} is deprecated; import from peeka.core.runtime.primitives instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(_rpl, _deprecated_aliases[name])
    raise AttributeError(f"module 'peeka.core.agent' has no attribute {name!r}")
