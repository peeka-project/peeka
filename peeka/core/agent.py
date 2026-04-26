"""
Agent Code - Runs inside target process
This code is injected into the target process and handles command execution
"""

import time as _time
import json
import socket
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from peeka.core.injector import DecoratorInjector
from peeka.core.observer import ObservationManager


class PeekaAgent:
    """Agent running inside target process"""

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
    }

    def __init__(
        self,
        session_id: str,
        attached_pid: Optional[int] = None,
        notify_port: int = 0,
        suppress_startup_messages: bool = False,
    ):
        self.session_id = session_id
        self.attached_pid = attached_pid
        self.running = True
        self.suppress_startup_messages = suppress_startup_messages
        self.sock_path = f"/tmp/peeka_{session_id}.sock"
        self.server: Optional[socket.socket] = None
        self.command_handlers: Dict[str, Any] = {}
        self._client_connections: list = []
        self._connections_lock = threading.Lock()

        self._client_counter = 0
        self.observer = ObservationManager()
        self.injector = DecoratorInjector(self)

        self._notify_port = notify_port

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
            traceback.print_exc()
            return None

    def _register_handlers(self) -> None:
        """Eagerly import and register ALL command handlers.

        Used by `start()` after the socket is ready so that commands
        are available immediately.  Runs on the agent thread so it
        does not block GIL during GDB injection.
        """
        for cmd_type in list(self._COMMAND_REGISTRY):
            self._get_handler(cmd_type)

    def start(self) -> None:
        try:
            self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

            if Path(self.sock_path).exists():
                Path(self.sock_path).unlink()

            self.server.bind(self.sock_path)
            self.server.listen(5)
            # Set a timeout so accept() doesn't block forever,
            # allowing the accept loop to check self.running periodically.
            self.server.settimeout(1.0)

            # Use an event to ensure the accept loop is actually running
            # before signaling readiness, avoiding a race where clients
            # connect before accept() is called.
            accept_ready = threading.Event()
            thread = threading.Thread(
                target=self._accept_loop,
                args=(accept_ready,),
                name="peeka-agent-accept",
                daemon=True,
            )
            thread.start()
            accept_ready.wait(timeout=10)

            # Signal readiness via TCP reverse-connect (preferred) and
            # .ready file (fallback / backward compatibility).
            self._notify_ready()
            Path(f"/tmp/peeka_{self.session_id}.ready").touch()
            msg_start = "[peeka Agent] Started and listening for connections"
            msg_ready = "[peeka Agent] Ready for commands"
            if not self.suppress_startup_messages:
                print(msg_start)
                print(msg_ready)
            self._send_log("INFO", msg_start)
            self._send_log("INFO", msg_ready)

            # Eagerly load all command handlers now that the socket is
            # ready.  This runs on the agent thread (not GIL-blocking).
            self._register_handlers()

        except Exception as e:
            msg = f"[peeka Agent] Start failed: {e}"
            print(msg, file=sys.stderr)
            self._send_log("ERROR", msg)
            traceback.print_exc()

    def _accept_loop(self, ready_event: threading.Event) -> None:
        ready_event.set()
        while self.running:
            try:
                if self.server is None:
                    break
                conn, _ = self.server.accept()
                self._client_counter += 1
                threading.Thread(
                    target=self._handle_client,
                    args=(conn,),
                    name=f"peeka-agent-client-{self._client_counter}",
                    daemon=True,
                ).start()
            except socket.timeout:
                # Periodic wakeup to re-check self.running
                continue
            except OSError:
                # Server socket closed (stop() called) — exit cleanly
                break
            except Exception as e:
                if self.running:
                    msg = f"[peeka Agent] Accept error: {e}"
                    print(msg, file=sys.stderr)
                    self._send_log("ERROR", msg)

    def _handle_client(self, conn: socket.socket) -> None:
        with self._connections_lock:
            self._client_connections.append(conn)

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

                command = json.loads(data.decode("utf-8"))
                result = self._execute_command(command)

                response = json.dumps(result).encode("utf-8")
                response_frame = len(response).to_bytes(4, "big") + response
                with self._connections_lock:
                    conn.sendall(response_frame)

        except Exception as e:
            msg = f"[peeka Agent] Client error: {e}"
            print(msg, file=sys.stderr)
            self._send_log("ERROR", msg)
        finally:
            with self._connections_lock:
                if conn in self._client_connections:
                    self._client_connections.remove(conn)
            conn.close()

    def _execute_command(self, command: dict) -> dict:
        cmd_type = command.get("type", "")

        handler = self._get_handler(cmd_type)
        if handler:
            try:
                return handler.execute(command)
            except Exception as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
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
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
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
        if hasattr(sys, "_peeka_agents"):
            agents = sys._peeka_agents  # type: ignore[attr-defined]
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
        if hasattr(sys, "_peeka_agents"):
            old_agents = list(sys._peeka_agents.values())  # type: ignore[attr-defined]
            for old_agent in old_agents:
                try:
                    old_agent.stop()
                    msg = (
                        f"[peeka Agent] Stopped previous agent: {old_agent.session_id}"
                    )
                    print(msg)
                    old_agent._send_log("INFO", msg)
                except Exception:
                    pass
            sys._peeka_agents.clear()  # type: ignore[attr-defined]

        agent = PeekaAgent(
            session_id,
            attached_pid,
            notify_port=notify_port,
            suppress_startup_messages=suppress_startup_messages,
        )
        agent.start()

        if not hasattr(sys, "_peeka_agents"):
            sys._peeka_agents = {}  # type: ignore[attr-defined]
        sys._peeka_agents[session_id] = agent  # type: ignore[attr-defined]

    except Exception as e:
        msg = f"[peeka Agent] Initialization failed: {e}"
        print(msg, file=sys.stderr)
        traceback.print_exc()
        # Note: _send_log can't be called here because agent isn't fully initialized yet


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
