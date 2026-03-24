"""
Process Attacher - Based on PEP 768
Attach to running Python processes and inject agent code
"""

import logging
import os
import shutil
import socket as sock_mod
import subprocess
import sys
import tempfile
import time
import uuid
import warnings
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)
# Python 3.9+ uses importlib.resources.files(), Python 3.8 uses read_text()
try:
    from importlib.resources import files as resource_files
except ImportError:
    # Python 3.8 compatibility
    resource_files = None
    from importlib import resources as legacy_resources


def _read_agent_code() -> str:
    """
    Read agent.py content in a Python 3.8+ compatible way.

    Returns:
        str: Content of agent.py
    """
    if resource_files is not None:
        # Python 3.9+ - use new Traversable API
        return (
            resource_files("peeka.core")
            .joinpath("agent.py")
            .read_text(encoding="utf-8")
        )
    else:
        # Python 3.8 - use legacy API
        return legacy_resources.read_text("peeka.core", "agent.py", encoding="utf-8")


class ProcessAttacher:
    """
    Process attacher using PEP 768 interface

    For Python 3.14+, uses sys.remote_exec()
    For older versions, uses fallback mechanism (GDB + ptrace)
    """

    # Timeout for waiting for agent readiness (seconds).
    # GDB fallback needs more time: agent imports 13+ command modules
    # and may contend for the import lock.
    READY_TIMEOUT_PEP768 = 10
    READY_TIMEOUT_GDB = 30
    MAX_ATTEMPTS = 2

    def __init__(self, pid: int):
        self.pid = pid
        self.agent_script = None
        self.session_id = str(uuid.uuid4())
        self._existing_session = None
        self._notify_server: Optional[sock_mod.socket] = None
    def _check_existing_attachment(self) -> Optional[tuple]:
        """
        Check if there's already an active Peeka agent attached to any process.
        Returns (session_id, pid) tuple if found, None otherwise.

        Validates by both process existence AND socket connectivity to avoid
        stale files left after process restarts.
        """
        socket_dir = Path("/tmp")
        for sock_file in socket_dir.glob("peeka_*.sock"):
            if sock_file.is_socket():
                session_id = sock_file.stem.replace("peeka_", "")
                pid_file = socket_dir / f"peeka_{session_id}.pid"
                ready_file = socket_dir / f"peeka_{session_id}.ready"

                if pid_file.exists():
                    try:
                        attached_pid = int(pid_file.read_text().strip())
                        try:
                            os.kill(attached_pid, 0)
                        except (ProcessLookupError, PermissionError):
                            self._cleanup_stale_files(sock_file, pid_file, ready_file)
                            continue

                        if self._is_socket_alive(str(sock_file)):
                            return (session_id, attached_pid)
                        else:
                            self._cleanup_stale_files(sock_file, pid_file, ready_file)
                    except (ValueError, OSError):
                        continue
                else:
                    self._cleanup_stale_files(sock_file, pid_file, ready_file)
        return None

    @staticmethod
    def _is_socket_alive(socket_path: str) -> bool:
        """Try connecting to the socket to verify the agent is actually responsive."""
        try:
            s = sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM)
            s.settimeout(1.0)
            s.connect(socket_path)
            s.close()
            return True
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            return False
    @staticmethod
    def _cleanup_stale_files(*paths: Path) -> None:
        for p in paths:
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass

    def _save_attachment_state(self) -> None:
        """Save the attached PID to a marker file for validation."""
        pid_file = Path(f"/tmp/peeka_{self.session_id}.pid")
        pid_file.write_text(str(self.pid))

    def attach(self) -> bool:
        """
        Attach to target process

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            existing = self._check_existing_attachment()

            if existing:
                existing_session, existing_pid = existing
                if existing_pid == self.pid:
                    logger.info("Already attached to process %d", self.pid)
                    logger.info("Socket path: /tmp/peeka_%s.sock", existing_session)
                    self._existing_session = existing_session
                    return True
                else:
                    raise RuntimeError(
                        f"Already attached to process {existing_pid}. "
                        f"Please detach first: peeka detach"
                    )

            logger.info("Attaching to process %d...", self.pid)

            if hasattr(sys, "remote_exec"):
                result = self._attach_pep768()
            else:
                logger.warning("PEP 768 not available (Python 3.14+ required)")
                logger.info("Using fallback mechanism for demonstration")
                result = self._attach_fallback()

            if result:
                self._save_attachment_state()

            return result

        except Exception as e:
            logger.error("Attach failed: %s", e)
            import traceback

            traceback.print_exc()
            return False

    def _attach_pep768(self) -> bool:
        """Attach using PEP 768 sys.remote_exec()"""
        agent_code = _read_agent_code()

        # Create agent script
        self.agent_script = self._create_agent_script(agent_code)
        if not os.path.exists(self.agent_script):
            raise FileNotFoundError(f"Agent script not found: {self.agent_script}")
        else:
            logger.debug("Agent script created at %s", self.agent_script)

        # Inject to target process
        sys.remote_exec(self.pid, self.agent_script)

        # Wait for agent ready with retry — agent bootstrap imports 13+
        # command modules and may take longer than a single timeout on
        # loaded systems or first injection into a cold process.
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                if self._wait_for_agent_ready(timeout=self.READY_TIMEOUT_PEP768):
                    logger.info("Successfully attached to process %d", self.pid)
                    return True
            except TimeoutError:
                if attempt < self.MAX_ATTEMPTS - 1:
                    logger.info(
                        "Agent not ready yet, retrying... (attempt %d/%d)",
                        attempt + 1, self.MAX_ATTEMPTS,
                    )
                else:
                    raise

        return False
    def _attach_fallback(self) -> bool:
        """
        Fallback mechanism for older Python versions using GDB + ptrace.

        The GDB injection runs a minimal bootstrap that spawns a daemon
        thread and returns immediately, releasing the GIL back to the
        target process.  The heavy agent initialisation (13+ command
        module imports, socket bind/listen) happens on the background
        thread so that the target process is never blocked for long.

        A TCP reverse-connect is used to detect readiness: the attacher
        opens a localhost TCP server, passes the port to the agent, and
        the agent connects back once it is fully initialised.  This is
        much more reliable than polling for a file on disk.

        Requirements:
        - GDB 7.3+
        - CAP_SYS_PTRACE or same UID
        - ptrace_scope <= 1
        - Python debugging symbols
        """
        logger.info("Using GDB injection for PID %d (Python <3.14)", self.pid)

        self._check_gdb_available()
        self._check_ptrace_permissions()

        agent_code = _read_agent_code()

        # Open a TCP server for the agent to connect back to.
        notify_port = self._create_notify_server()

        agent_script = self._create_agent_script(
            agent_code, notify_port=notify_port
        )

        try:
            self._inject_via_gdb(agent_script)

            # Wait with retry, matching PEP 768 path behaviour.
            for attempt in range(self.MAX_ATTEMPTS):
                try:
                    if self._wait_for_agent_ready(
                        timeout=self.READY_TIMEOUT_GDB
                    ):
                        logger.info("Successfully attached to process %d", self.pid)
                        return True
                except TimeoutError:
                    if attempt < self.MAX_ATTEMPTS - 1:
                        logger.info(
                            "Agent not ready yet, retrying... (attempt %d/%d)",
                            attempt + 1, self.MAX_ATTEMPTS,
                        )
                    else:
                        raise

            return False

        except Exception as e:
            logger.error("GDB injection failed: %s", e)
            raise
        finally:
            if os.path.exists(agent_script):
                os.remove(agent_script)
            self._close_notify_server()

    # ------------------------------------------------------------------ #
    #  Notify server (TCP reverse-connect for readiness detection)       #
    # ------------------------------------------------------------------ #

    def _create_notify_server(self) -> int:
        """Open a localhost TCP server and return the port number.

        The injected agent will connect back to this port once it is
        ready, which is far more reliable than polling for a file.
        """
        self._notify_server = sock_mod.socket(
            sock_mod.AF_INET, sock_mod.SOCK_STREAM
        )
        self._notify_server.setsockopt(
            sock_mod.SOL_SOCKET, sock_mod.SO_REUSEADDR, 1
        )
        self._notify_server.bind(("127.0.0.1", 0))
        self._notify_server.listen(1)
        port = self._notify_server.getsockname()[1]
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
        self, agent_code: str, notify_port: Optional[int] = None
    ) -> str:
        agent_path = Path(tempfile.gettempdir()) / f"peeka_agent_{self.session_id}.py"

        agent_code_injected = agent_code.replace("{{SESSION_ID}}", self.session_id)
        agent_code_injected = agent_code_injected.replace(
            "{{ATTACHED_PID}}", str(self.pid)
        )
        agent_code_injected = agent_code_injected.replace(
            "{{NOTIFY_PORT}}", str(notify_port) if notify_port else "0"
        )

        peeka_root = str(Path(__file__).parent.parent.parent.resolve())
        path_bootstrap = f"import sys; sys.path.insert(0, {peeka_root!r}) if {peeka_root!r} not in sys.path else None\n"

        with open(agent_path, "w") as f:
            logger.debug("Creating agent script at %s", agent_path)
            f.write(path_bootstrap + agent_code_injected)

        return str(agent_path)

    def _wait_for_agent_ready(self, timeout: int = 10) -> bool:
        """Wait for agent initialization and socket readiness.

        Uses TCP reverse-connect when a notify server is available
        (GDB fallback path).  Falls back to polling for the .ready
        file and then verifying socket connectivity (PEP 768 path
        and degraded fallback).
        """
        socket_path = f"/tmp/peeka_{self.session_id}.sock"

        # --- Fast path: TCP reverse-connect -------------------------
        server = getattr(self, "_notify_server", None)
        if server:
            server.settimeout(timeout)
            try:
                conn, _ = server.accept()
                # Agent sends a short "READY" payload.
                data = conn.recv(16)
                conn.close()
                if data == b"READY":
                    # Double-check the Unix socket is connectable.
                    if self._is_socket_alive(socket_path):
                        return True
                    # Socket not yet reachable — fall through to polling.
            except (sock_mod.timeout, OSError):
                pass  # fall through to file-based polling

        # --- Slow path: .ready file polling -------------------------
        ready_file = Path(f"/tmp/peeka_{self.session_id}.ready")

        start_time = time.time()
        # Phase 1: Wait for .ready file
        while time.time() - start_time < timeout:
            if ready_file.exists():
                break
            time.sleep(0.1)
        else:
            raise TimeoutError("Agent initialization timeout (ready file)")

        # Phase 2: Verify socket is actually connectable
        while time.time() - start_time < timeout:
            if self._is_socket_alive(socket_path):
                return True
            time.sleep(0.05)

        raise TimeoutError("Agent initialization timeout (socket not connectable)")
    def get_socket_path(self) -> str:
        """Get Unix domain socket path for communication"""
        if self._existing_session:
            return f"/tmp/peeka_{self._existing_session}.sock"
        return f"/tmp/peeka_{self.session_id}.sock"

    def _check_gdb_available(self):
        """Check if GDB is available on the system"""
        if not shutil.which("gdb"):
            raise RuntimeError(
                "GDB not found. Install with:\n"
                "  Debian/Ubuntu: sudo apt-get install gdb python3-dbg\n"
                "  RHEL/Fedora: sudo yum install gdb python3-debuginfo\n"
                "  Arch: sudo pacman -S gdb"
            )

    def _check_ptrace_permissions(self):
        """Check if ptrace is available and warn user if restricted"""
        ptrace_scope_file = "/proc/sys/kernel/yama/ptrace_scope"

        if os.path.exists(ptrace_scope_file):
            try:
                with open(ptrace_scope_file) as f:
                    scope = int(f.read().strip())

                if scope >= 2:
                    raise PermissionError(
                        f"ptrace_scope is {scope} (admin-only or disabled).\n"
                        "To enable: echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope"
                    )
                elif scope == 1:
                    warnings.warn(
                        f"ptrace_scope is {scope} (restricted mode). "
                        "Injection may fail if target is not a child process.\n"
                        "To enable: echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope",
                        RuntimeWarning,
                    )
            except (IOError, ValueError) as e:
                warnings.warn(f"Could not read ptrace_scope: {e}", RuntimeWarning)

        # Check if target process exists and we have permissions
        try:
            os.kill(self.pid, 0)  # Signal 0 checks process existence
        except ProcessLookupError:
            raise ProcessLookupError(f"Process {self.pid} does not exist")
        except PermissionError:
            raise PermissionError(
                f"No permission to access process {self.pid}. "
                "Requires same UID or CAP_SYS_PTRACE capability."
            )

    def _inject_via_gdb(self, agent_script: str):
        """
        Inject agent bootstrap via GDB.

        Instead of executing the full agent script synchronously inside
        PyRun_SimpleString (which holds the GIL for the entire duration
        and can deadlock if the target holds the import lock), we run a
        tiny bootstrap snippet that:
        1. Reads the agent script into memory
        2. Spawns a daemon thread to exec() it
        3. Returns immediately, releasing the GIL

        The real agent initialisation then happens on the daemon thread
        without blocking the target process.

        Calls Python C API functions via GDB:
        - PyGILState_Ensure(): Acquire GIL
        - PyRun_SimpleString(): Execute bootstrap snippet
        - PyGILState_Release(): Release GIL
        """
        escaped_script = agent_script.replace("\\", "\\\\").replace('"', '\\"')

        # For Python <= 3.8, there's a bug where threads created during
        # injection don't get scheduled after GDB detaches.
        # So instead we just execute directly here while we still hold the GIL.
        # This takes a bit longer but is guaranteed to work.
        bootstrap = (
            f"_c = open(\\\"{escaped_script}\\\").read(); "
            "exec(_c);"
        )

        # Use appropriate casts for each function's return type to avoid
        # "Invalid cast" errors.
        # PyGILState_Ensure returns PyGILState_STATE (int-like enum)
        # PyRun_SimpleString returns int
        # PyGILState_Release returns void
        gdb_commands = [
            ("call (int) PyGILState_Ensure()", "Acquire GIL"),
            (
                f'call (int) PyRun_SimpleString("{bootstrap}")',
                "Execute agent bootstrap",
            ),
            ("call (void) PyGILState_Release($1)", "Release GIL"),
        ]

        cmd = ["gdb", "-p", str(self.pid), "-batch", "-q"]
        for gdb_cmd, description in gdb_commands:
            cmd.extend(["-eval-command", gdb_cmd])

        logger.info("Injecting agent via GDB...")

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                text=True,
            )

            stderr = result.stderr.lower()
            if "permission denied" in stderr or "operation not permitted" in stderr:
                raise PermissionError(
                    "GDB attach failed: Permission denied.\n"
                    "Check ptrace_scope and process ownership."
                )
            elif "no symbol" in stderr and "pygil" in stderr:
                raise RuntimeError(
                    "Python debugging symbols not found.\n"
                    "Install python3-dbg (Debian/Ubuntu) or python3-debuginfo (RHEL/Fedora)"
                )
            elif result.returncode != 0:
                raise RuntimeError(
                    f"GDB injection failed (exit code {result.returncode}):\n"
                    f"stderr: {result.stderr}\n"
                    f"stdout: {result.stdout}"
                )

            logger.info("GDB injection completed")

        except subprocess.TimeoutExpired:
            raise TimeoutError(
                "GDB injection timed out after 30 seconds. "
                "Process may be deadlocked or unresponsive."
            )
        except FileNotFoundError:
            raise RuntimeError("GDB executable not found in PATH")
    def cleanup(self):
        """Cleanup agent script only; socket and ready file persist for agent"""
        if self.agent_script and os.path.exists(self.agent_script):
            os.remove(self.agent_script)
        self._close_notify_server()
