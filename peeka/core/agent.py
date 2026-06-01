# pyright: reportImportCycles=false
"""
Agent Code - Runs inside target process
This code is injected into the target process and handles command execution
"""

import json
import socket
import sys
import time as _time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from peeka.core.injector import DecoratorInjector
from peeka.core.jobs import JobCategory
from peeka.core.jobs import job_registry
from peeka.core.observer import ObservationManager
from peeka.core.runtime import primitives as _rpl

# Lazy import to avoid circular dependency issues
_client_registry = None


def _get_client_registry():
    """Lazily initialize and return the global client registry singleton."""
    global _client_registry
    if _client_registry is None:
        from peeka.core.client_sessions import ClientRegistry
        _client_registry = ClientRegistry()
    return _client_registry


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


class PeekaAgent:
    """Agent running inside target process"""

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
        self._connections_lock = _rpl.allocate_lock()

        self._client_counter = 0
        self.observer = ObservationManager()
        self.injector = DecoratorInjector(self)

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
        self._error_ring_lock = _rpl.allocate_lock()
        self._last_seen_at = _time.time()

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
    
    def _handle_target_hello(self) -> Dict[str, Any]:
        """Handle target.hello command - returns basic target information."""
        try:
            import peeka
            from peeka.core.targets import TARGET_SCHEMA_VERSION
            
            target_id = f"target_{self.session_id[:8]}"
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            
            return {
                "status": "success",
                "schema_version": TARGET_SCHEMA_VERSION,
                "target_id": target_id,
                "pid": self.attached_pid or 0,
                "python_version": python_version,
                "peeka_version": peeka.__version__,
                "capabilities": {},
                "runtime": {},
                "state": "alive",
                "agent_mode": self.agent_mode,
                "injection_mode": self.injection_mode,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }
    
    def _handle_target_status(self) -> Dict[str, Any]:
        """Handle target.status command - returns hello payload + last_seen_at + recent_errors."""
        try:
            self._last_seen_at = _time.time()
            
            hello_payload = self._handle_target_hello()
            if hello_payload.get("status") != "success":
                return hello_payload
            
            with self._error_ring_lock:
                recent_errors = list(self._recent_errors)
            
            hello_payload["last_seen_at"] = self._last_seen_at
            hello_payload["recent_errors"] = recent_errors
            
            return hello_payload
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

    def _target_id_for_jobs(self) -> str:
        """Return the stable target identifier used by job records."""
        return f"target_{self.session_id[:8]}"

    def _handle_client_create(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.create command - create and register a client session."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict
            
            target_id = command.get("target_id", "")
            source = command.get("source", "")
            user_id = command.get("user_id")
            
            if not target_id:
                return _client_error(
                    "UNSUPPORTED_CAPABILITY",
                    "target_id is required and cannot be empty",
                )
            
            valid_sources = {"cli", "tui", "mcp", "api", "internal"}
            if source not in valid_sources:
                return _client_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"source must be one of {valid_sources}, got {source!r}",
                )
            
            registry = _get_client_registry()
            client = registry.create(target_id=target_id, source=source, user_id=user_id)
            
            return _client_success(client_to_dict(client))
        except Exception as e:
            result = _client_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_client_list(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.list command - list client sessions optionally filtered by target_id."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict
            
            target_id = command.get("target_id")
            
            registry = _get_client_registry()
            clients = registry.list(target_id=target_id)
            
            return _client_success({"clients": [client_to_dict(c) for c in clients]})
        except Exception as e:
            result = _client_error("TRANSPORT_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_client_status(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.status command - get client session details by ID."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict
            
            client_session_id = command.get("client_session_id", "")
            if not client_session_id:
                return _client_error("CLIENT_NOT_FOUND", "client_session_id is required")
            
            registry = _get_client_registry()
            client = registry.get(client_session_id)
            
            if client is None:
                return _client_error(
                    "CLIENT_NOT_FOUND",
                    f"Client session {client_session_id!r} not found",
                )
            
            return _client_success(client_to_dict(client))
        except Exception as e:
            result = _client_error("TRANSPORT_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_client_close(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.close command - close a client session by ID."""
        try:
            client_session_id = command.get("client_session_id", "")
            if not client_session_id:
                return _client_error("CLIENT_NOT_FOUND", "client_session_id is required")
            
            registry = _get_client_registry()
            removed = registry.close(client_session_id)
            
            if not removed:
                return _client_error(
                    "CLIENT_NOT_FOUND",
                    f"Client session {client_session_id!r} not found",
                )
            
            return _client_success({"closed": True, "client_session_id": client_session_id})
        except Exception as e:
            result = _client_error("TRANSPORT_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

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
            return True

        except Exception as e:
            self.running = False
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

    def _handle_client(self, conn: socket.socket, client_id: int) -> None:
        with self._connections_lock:
            self._client_connections.append(conn)
            connection_total = len(self._client_connections)

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
                with self._connections_lock:
                    conn.sendall(response_frame)

        except Exception as e:
            msg = f"[peeka Agent] Client error: {e}"
            self._emit_log("ERROR", msg, traceback.format_exc())
        finally:
            with self._connections_lock:
                if conn in self._client_connections:
                    self._client_connections.remove(conn)
                connection_total = len(self._client_connections)
            conn.close()
            self._emit_log(
                "INFO",
                f"[peeka Agent] {client_label} disconnected ({connection_total} total)",
            )

    def _execute_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        cmd_type = command.get("type", "")

        # Handle legacy {"command":"ping"} as alias to target.hello
        if "command" in command and command.get("command") == "ping":
            return self._handle_target_hello()

        # Handle new target namespace
        if cmd_type == "target":
            action = command.get("action", "")
            if action == "hello":
                return self._handle_target_hello()
            elif action == "status":
                return self._handle_target_status()
            else:
                return {"status": "error", "error": f"Unknown target action: {action}"}

        if cmd_type == "client":
            action = command.get("action", "")
            registry = _get_client_registry()
            registry.cleanup_idle(idle_threshold_seconds=900)
            if action == "create":
                return self._handle_client_create(command)
            elif action == "list":
                return self._handle_client_list(command)
            elif action == "status":
                return self._handle_client_status(command)
            elif action == "close":
                return self._handle_client_close(command)
            else:
                return _client_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown client action: {action}",
                )

        handler = self._get_handler(cmd_type)
        if handler:
            job_registry.cleanup(retention_seconds=600)

            client_session_id = str(command.get("client_session_id", ""))
            action = str(command.get("action", ""))
            foreground = not bool(command.get("background", False))
            params = {
                key: value
                for key, value in command.items()
                if key not in {"type", "action", "client_session_id", "background"}
            }
            category = getattr(type(handler), "category", "snapshot")
            if category not in {"snapshot", "probe", "mutation"}:
                category = "snapshot"
            job_category = cast(JobCategory, category)

            job = job_registry.create(
                target_id=self._target_id_for_jobs(),
                client_session_id=client_session_id,
                command_type=str(cmd_type),
                action=action,
                params=params,
                category=job_category,
                foreground=foreground,
            )
            job_registry.set_status(job.id, "running")

            try:
                result = handler.execute(command)

                result_summary = result.get("data") if "data" in result else result
                if category == "probe" and result.get("status") == "success":
                    job_registry.set_status(
                        job.id,
                        "streaming",
                        result_summary=result_summary,
                    )
                else:
                    job_registry.set_status(
                        job.id,
                        "completed",
                        result_summary=result_summary,
                    )

                result["job_id"] = job.id
                return result
            except Exception as e:
                error_entry = {
                    "timestamp": _time.time(),
                    "code": "COMMAND_EXECUTION_ERROR",
                    "message": str(e),
                }
                self._add_recent_error(error_entry)
                job_registry.set_status(
                    job.id,
                    "failed",
                    last_error={
                        "code": "COMMAND_EXECUTION_ERROR",
                        "message": str(e),
                    },
                )
                result = {
                    "status": "error",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
                result["job_id"] = job.id
                return result
        else:
            return {"status": "error", "error": f"Unknown command type: {cmd_type}"}

    def _send_observation(self, observation: Dict[str, Any]) -> None:
        """Called by injector when a watched function is invoked."""
        observation["type"] = "observation"
        self.observer.add_observation(observation)

        obs_json = json.dumps(observation).encode("utf-8")
        message = b"OBS:" + len(obs_json).to_bytes(4, "big") + obs_json

        with self._connections_lock:
            dead_connections = []
            for conn in self._client_connections:
                try:
                    conn.sendall(message)
                except Exception:
                    dead_connections.append(conn)

            for conn in dead_connections:
                self._client_connections.remove(conn)

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

        with self._connections_lock:
            dead_connections = []
            for conn in self._client_connections:
                try:
                    conn.sendall(frame)
                except Exception:
                    dead_connections.append(conn)

            for conn in dead_connections:
                self._client_connections.remove(conn)

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
        self.running = False
        self.injector.uninject_all()

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
