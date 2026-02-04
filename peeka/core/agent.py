"""
Agent Code - Runs inside target process
This code is injected into the target process and handles command execution
"""

import json
import socket
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

from peeka.commands.base import BaseCommand
from peeka.core.injector import DecoratorInjector
from peeka.core.observer import ObservationManager


class PeekaAgent:
    """Agent running inside target process"""

    def __init__(self, session_id: str, attached_pid: Optional[int] = None):
        self.session_id = session_id
        self.attached_pid = attached_pid
        self.running = True
        self.sock_path = f"/tmp/peeka_{session_id}.sock"
        self.server: Optional[socket.socket] = None
        self.command_handlers: Dict[str, Any] = {}
        self._client_connections: list = []
        self._connections_lock = threading.Lock()

        self.observer = ObservationManager()
        self.injector = DecoratorInjector(self)

        self._register_handlers()

    def _register_handlers(self) -> None:
        from peeka.commands.complete import CompleteCommand
        from peeka.commands.watch import WatchCommand
        from peeka.commands.stack import StackCommand
        from peeka.commands.logger import LoggerCommand
        from peeka.commands.memory import MemoryCommand
        from peeka.commands.reset import ResetCommand
        from peeka.commands.search import SearchClassCommand, SearchMethodCommand
        from peeka.commands.monitor import MonitorCommand
        from peeka.commands.vmtool import VMToolCommand
        from peeka.commands.detach import DetachCommand

        self.command_handlers["complete"] = CompleteCommand(self)  # type: ignore[abstract]
        self.command_handlers["watch"] = WatchCommand(self)  # type: ignore[abstract]
        self.command_handlers["stack"] = StackCommand(self)  # type: ignore[abstract]
        self.command_handlers["logger"] = LoggerCommand(self)  # type: ignore[abstract]
        self.command_handlers["sc"] = SearchClassCommand(self)  # type: ignore[abstract]
        self.command_handlers["sm"] = SearchMethodCommand(self)  # type: ignore[abstract]
        self.command_handlers["monitor"] = MonitorCommand(self)  # type: ignore[abstract]
        self.command_handlers["memory"] = MemoryCommand(self)  # type: ignore[abstract]
        self.command_handlers["reset"] = ResetCommand(self)  # type: ignore[abstract]
        self.command_handlers["vmtool"] = VMToolCommand(self)  # type: ignore[abstract]
        self.command_handlers["detach"] = DetachCommand(self)  # type: ignore[abstract]

    def start(self) -> None:
        try:
            self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

            if Path(self.sock_path).exists():
                Path(self.sock_path).unlink()

            self.server.bind(self.sock_path)
            self.server.listen(5)

            Path(f"/tmp/peeka_{self.session_id}.ready").touch()

            thread = threading.Thread(target=self._accept_loop, daemon=True)
            print("[peeka Agent] Started and listening for connections")
            thread.start()
            print("[peeka Agent] Ready for commands")

        except Exception as e:
            print(f"[peeka Agent] Start failed: {e}", file=sys.stderr)
            traceback.print_exc()

    def _accept_loop(self) -> None:
        while self.running:
            try:
                if self.server is None:
                    break
                conn, _ = self.server.accept()
                threading.Thread(
                    target=self._handle_client, args=(conn,), daemon=True
                ).start()
            except Exception as e:
                if self.running:
                    print(f"[peeka Agent] Accept error: {e}", file=sys.stderr)

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
                conn.sendall(len(response).to_bytes(4, "big"))
                conn.sendall(response)

        except Exception as e:
            print(f"[peeka Agent] Client error: {e}", file=sys.stderr)
        finally:
            with self._connections_lock:
                if conn in self._client_connections:
                    self._client_connections.remove(conn)
            conn.close()

    def _execute_command(self, command: dict) -> dict:
        cmd_type = command.get("type", "")

        handler: BaseCommand = self.command_handlers.get(cmd_type)
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

    def stop(self) -> None:
        self.running = False
        self.injector.uninject_all()
        if self.server:
            self.server.close()


def _init_agent(session_id: str, attached_pid: Optional[int] = None) -> None:
    try:
        agent = PeekaAgent(session_id, attached_pid)
        agent.start()

        if not hasattr(sys, "_peeka_agents"):
            sys._peeka_agents = {}  # type: ignore[attr-defined]
        sys._peeka_agents[session_id] = agent  # type: ignore[attr-defined]

    except Exception as e:
        print(f"[peeka Agent] Initialization failed: {e}", file=sys.stderr)
        traceback.print_exc()


# Auto-initialize when injected via sys.remote_exec() or GDB
# {{SESSION_ID}} and {{ATTACHED_PID}} are replaced by ProcessAttacher before injection
# This runs both when imported (PEP 768) and when exec'd (GDB fallback)
_session_id = "{{SESSION_ID}}"
_attached_pid_str = "{{ATTACHED_PID}}"
_attached_pid = int(_attached_pid_str) if _attached_pid_str.isdigit() else None
if not _session_id.startswith("{{"):
    _init_agent(_session_id, _attached_pid)
