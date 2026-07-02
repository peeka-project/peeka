"""Injected agent script, side channel, and readiness helpers."""

import os
import socket as sock_mod
import tempfile
import time
from typing import Optional, cast

from peeka.core.runtime import primitives as _rpl


def _attach_module():
    from peeka.core import attach as attach_module

    return attach_module


def _cleanup_peeka_modules() -> None:
    """Remove all cached peeka.* modules from sys.modules.

    Evicts the bare 'peeka' key and every key starting with 'peeka.'
    so that the next import loads fresh code from disk. Iterates over
    a snapshot of keys to avoid mutation-during-iteration errors.
    """
    import sys

    for _mod_name in list(sys.modules.keys()):
        if _mod_name == "peeka" or _mod_name.startswith("peeka."):
            sys.modules.pop(_mod_name, None)


class AttachReadinessMixin:

    def _serve_agent_code(self, agent_code: str, timeout: int = 30):
        """
        Serve agent code to injector via TCP side-channel.
        """
        try:
            server = getattr(self, "_notify_server", None)
            if server is None:
                _attach_module().logger.warning("Notify server not available for side-channel")
                return

            server.settimeout(timeout)
            conn, _ = _rpl.native_accept(server)
            try:
                code_bytes = agent_code.encode("utf-8")
                # The native injector reads until EOF and passes the bytes
                # directly to Py_CompileString().  Do not prepend the
                # length-prefixed protocol used by the agent command socket.
                conn.sendall(code_bytes)
                conn.shutdown(sock_mod.SHUT_WR)

                # If the injector fails to compile or execute the script it
                # sends a short error string back on the same side channel.
                # Successful injection sends no payload and simply closes.
                try:
                    error = conn.recv(4096)
                    if error:
                        _attach_module().logger.warning(
                            "Injector reported agent bootstrap error: %s",
                            error.decode("utf-8", errors="replace"),
                        )
                except sock_mod.timeout:
                    pass
            finally:
                conn.close()
        except sock_mod.timeout:
            _attach_module().logger.warning("Timeout waiting for injector to connect")
        except Exception as e:
            _attach_module().logger.error("Failed to serve agent code: %s", e)

    # ------------------------------------------------------------------ #
    #  Notify server (TCP reverse-connect for readiness detection)       #
    # ------------------------------------------------------------------ #

    def _create_notify_server(self) -> int:
        """Open a localhost TCP server and return the port number.

        The injected agent will connect back to this port once it is
        ready, which is far more reliable than polling for a file.
        """
        server = cast(sock_mod.socket, _rpl.create_socket("AF_INET", "SOCK_STREAM"))
        self._notify_server = server
        server.setsockopt(sock_mod.SOL_SOCKET, sock_mod.SO_REUSEADDR, 1)
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        return port

    def _close_notify_server(self) -> None:
        server = getattr(self, "_notify_server", None)
        if server:
            try:
                server.close()
            except OSError:
                pass
            self._notify_server = None

    # ------------------------------------------------------------------ #
    #  Agent script creation                                            #
    # ------------------------------------------------------------------ #

    def _create_agent_script(
        self,
        agent_code: str,
        notify_port: Optional[int] = None,
        suppress_startup_messages: bool = False,
    ) -> str:
        agent_path = _attach_module().Path(tempfile.gettempdir()) / f"peeka_agent_{self.session_id}.py"

        agent_code_injected = agent_code.replace("{{SESSION_ID}}", self.session_id)
        agent_code_injected = agent_code_injected.replace(
            "{{ATTACHED_PID}}", str(self.pid)
        )
        agent_code_injected = agent_code_injected.replace(
            "{{NOTIFY_PORT}}", str(notify_port) if notify_port else "0"
        )
        agent_code_injected = agent_code_injected.replace(
            "{{SUPPRESS_STARTUP_MESSAGES}}",
            "True" if suppress_startup_messages else "False",
        )

        peeka_root = str(_attach_module().Path(__file__).parent.parent.parent.resolve())
        path_bootstrap = f"import sys; sys.path.insert(0, {peeka_root!r}) if {peeka_root!r} not in sys.path else None\n"
        module_cleanup = (
            "for _peeka_mod in list(sys.modules.keys()):\n"
            "    if _peeka_mod == 'peeka' or _peeka_mod.startswith('peeka.'):\n"
            "        sys.modules.pop(_peeka_mod, None)\n"
        )

        with open(agent_path, "w") as f:
            _attach_module().logger.debug("Creating agent script at %s", agent_path)
            f.write(path_bootstrap + module_cleanup + agent_code_injected)

        return str(agent_path)

    def _wait_for_agent_ready(self, timeout: int = 10) -> bool:
        """Wait for agent initialization and socket readiness.

        Uses TCP reverse-connect when a notify server is available
        (GDB fallback path).  Falls back to polling for the .ready
        file and then verifying socket connectivity (PEP 768 path
        and degraded fallback).
        """
        socket_path = f"/tmp/peeka_{self.session_id}.sock"
        wait_start = time.monotonic()
        wait_ready_done_emitted = False
        self._emit_progress(
            "wait_agent_ready",
            "running",
            "Waiting for injected agent readiness",
            details={"timeout": timeout, "socket_path": socket_path},
        )

        # --- Fast path: TCP reverse-connect -------------------------
        server = getattr(self, "_notify_server", None)
        if server:
            server.settimeout(timeout)
            try:
                conn, _ = _rpl.native_accept(server)
                # Agent sends a short "READY" payload.
                data = conn.recv(16)
                conn.close()
                if data == b"READY":
                    # Double-check the Unix socket can complete a command
                    # round trip; connect-only probes miss broken client loops.
                    self._emit_progress(
                        "wait_agent_ready",
                        "done",
                        "Agent readiness signal received",
                        elapsed_ms=(time.monotonic() - wait_start) * 1000,
                    )
                    wait_ready_done_emitted = True
                    hello_start = time.monotonic()
                    self._emit_progress(
                        "hello_probe",
                        "running",
                        "Probing agent command socket",
                        details={"socket_path": socket_path},
                    )
                    if self._is_agent_responsive(socket_path):
                        self._emit_progress(
                            "hello_probe",
                            "done",
                            "Agent command socket responded",
                            elapsed_ms=(time.monotonic() - hello_start) * 1000,
                            details={"socket_path": socket_path},
                        )
                        return True
                    self._emit_progress(
                        "hello_probe",
                        "running",
                        "Agent readiness signal received but command socket did not respond yet",
                        level="warning",
                        elapsed_ms=(time.monotonic() - hello_start) * 1000,
                        details={"socket_path": socket_path},
                    )
                    # Socket not yet reachable — fall through to polling.
            except (sock_mod.timeout, OSError):
                pass  # fall through to file-based polling

        # --- Slow path: .ready file polling -------------------------
        ready_file = _attach_module().Path(f"/tmp/peeka_{self.session_id}.ready")

        start_time = time.time()
        # Phase 1: Wait for .ready file
        while time.time() - start_time < timeout:
            if ready_file.exists():
                if not wait_ready_done_emitted:
                    self._emit_progress(
                        "wait_agent_ready",
                        "done",
                        "Agent ready file detected",
                        elapsed_ms=(time.monotonic() - wait_start) * 1000,
                        details={"ready_file": str(ready_file)},
                    )
                    wait_ready_done_emitted = True
                break
            time.sleep(0.1)
        else:
            if not wait_ready_done_emitted:
                self._emit_progress(
                    "wait_agent_ready",
                    "failed",
                    "Agent initialization timeout (ready file)",
                    level="error",
                    elapsed_ms=(time.monotonic() - wait_start) * 1000,
                    details={"ready_file": str(ready_file), "timeout": timeout},
                )
            raise TimeoutError("Agent initialization timeout (ready file)")

        # Phase 2: Verify the socket can serve a lightweight hello command.
        hello_start = time.monotonic()
        self._emit_progress(
            "hello_probe",
            "running",
            "Probing agent command socket",
            details={"socket_path": socket_path},
        )
        while time.time() - start_time < timeout:
            if self._is_agent_responsive(socket_path):
                self._emit_progress(
                    "hello_probe",
                    "done",
                    "Agent command socket responded",
                    elapsed_ms=(time.monotonic() - hello_start) * 1000,
                    details={"socket_path": socket_path},
                )
                return True
            time.sleep(0.05)

        self._emit_progress(
            "hello_probe",
            "failed",
            "Agent initialization timeout (agent not responsive)",
            level="error",
            elapsed_ms=(time.monotonic() - hello_start) * 1000,
            details={"socket_path": socket_path, "timeout": timeout},
        )
        raise TimeoutError("Agent initialization timeout (agent not responsive)")

    def get_socket_path(self) -> str:
        """Get Unix domain socket path for communication"""
        if self._existing_session:
            return f"/tmp/peeka_{self._existing_session}.sock"
        return f"/tmp/peeka_{self.session_id}.sock"

    def cleanup(self):
        """Cleanup agent script only; socket and ready file persist for agent"""
        if self.agent_script and os.path.exists(self.agent_script):
            os.remove(self.agent_script)
        self._close_notify_server()
