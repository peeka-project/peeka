"""
Process Attacher - Based on PEP 768
Attach to running Python processes and inject agent code
"""

import importlib.util
import json
import logging
import os
import platform
import re
import shutil
import signal
import socket as sock_mod
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import warnings
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)
# Python 3.9+ uses importlib.resources.files(), Python 3.8 uses read_text()
legacy_resources = None
try:
    from importlib.resources import files as resource_files
except ImportError:
    # Python 3.8 compatibility
    resource_files = None
    from importlib import resources as legacy_resources

# RTLD constants for dynamic linking
_RTLD_DEFAULT = -2
_RTLD_NOW = 2


class GDBSymbolResolutionError(RuntimeError):
    """Raised when GDB cannot resolve the Python C API symbols we need."""


def _looks_like_gdb_symbol_resolution_error(output: str) -> bool:
    """Return True when GDB failed before it could resolve Python symbols."""
    lowered = output.lower()
    symbol_error_markers = (
        "no symbol table is loaded",
        "no symbol",
        "unknown return type",
        "no function contains program counter",
    )
    return any(marker in lowered for marker in symbol_error_markers)


def _format_gdb_symbol_error(method: str, stderr: str, stdout: str) -> str:
    """Build an actionable error for GDB symbol-resolution failures."""
    return (
        f"{method} failed because GDB could not resolve Python runtime symbols.\n"
        "The target process is attachable, but this injection path requires "
        "symbols such as PyMem_Malloc, Py_AddPendingCall, PyCallable_Check, "
        "and allocator entry points to be visible to GDB.\n"
        "Fix: install matching Python debug symbols or use a Python build that "
        "exports the Python C API symbols for the target interpreter.\n"
        f"stderr:\n{stderr}\n"
        f"stdout:\n{stdout}"
    )


def _find_injector_path() -> Optional[str]:
    """
    Locate the injector extension module (_inject.*.so or _inject.*.dylib).

    Uses importlib.util.find_spec to locate the peeka.core._inject module
    and returns its origin path if found.

    Returns:
        Optional[str]: Path to the injector extension module, or None if not found.
    """
    try:
        spec = importlib.util.find_spec("peeka.core._inject")
        if spec is not None and spec.origin is not None:
            return spec.origin
    except (ImportError, AttributeError, ValueError):
        pass
    return None


def _check_lldb_available() -> None:
    """
    Check if LLDB is available on the system.

    Raises:
        RuntimeError: If LLDB is not found with platform-specific install instructions.
    """
    if not shutil.which("lldb"):
        raise RuntimeError(
            "LLDB not found. Install Xcode Command Line Tools: xcode-select --install (macOS only)"
        )


def _has_injector() -> bool:
    """
    Check if the injector extension module is available and loadable.

    Uses actual import instead of find_spec to detect GLIBC or ABI
    mismatches that would prevent the C extension from loading.

    Returns:
        bool: True if the injector extension can be loaded, False otherwise.
    """
    try:
        import peeka.core._inject  # noqa: F401

        return True
    except (ImportError, OSError):
        return False


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
        assert legacy_resources is not None
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

    def __init__(
        self,
        pid: int,
        suppress_startup_messages: bool = False,
        session_id: Optional[str] = None,
    ):
        self.pid = pid
        self.suppress_startup_messages = suppress_startup_messages
        self.agent_script = None
        self.session_id = session_id or str(uuid.uuid4())
        self._existing_session = None
        self._notify_server: Optional[sock_mod.socket] = None

    def _check_existing_attachment(self) -> Optional[Tuple[str, int]]:
        """
        Check if there's already an active Peeka agent attached to any process.
        Returns (session_id, pid) tuple if found, None otherwise.

        Validates by both process existence AND agent responsiveness to avoid
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

                        if self._is_agent_responsive(str(sock_file)):
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
        """Try connecting to the socket to verify the path is reachable."""
        try:
            with sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(socket_path)
            return True
        except (ConnectionRefusedError, FileNotFoundError, OSError):
            return False

    @staticmethod
    def _recv_exact(s: sock_mod.socket, size: int) -> bytes:
        chunks = []
        remaining = size
        while remaining > 0:
            try:
                chunk = s.recv(remaining)
            except sock_mod.timeout:
                return b""
            if not chunk:
                return b""
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    @classmethod
    def _recv_response_header(cls, s: sock_mod.socket) -> bytes:
        length_bytes = cls._recv_exact(s, 4)
        while length_bytes in (b"OBS:", b"LOG:"):
            frame_len_bytes = cls._recv_exact(s, 4)
            if not frame_len_bytes:
                return b""
            frame_len = int.from_bytes(frame_len_bytes, "big")
            if frame_len and not cls._recv_exact(s, frame_len):
                return b""
            length_bytes = cls._recv_exact(s, 4)
        return length_bytes

    @classmethod
    def _is_agent_responsive(cls, socket_path: str) -> bool:
        """Verify the agent can complete one command/response round trip."""
        try:
            with sock_mod.socket(sock_mod.AF_UNIX, sock_mod.SOCK_STREAM) as s:
                s.settimeout(1.0)
                s.connect(socket_path)

                payload = json.dumps(
                    {"type": "client", "action": "hello"}
                ).encode("utf-8")
                s.sendall(len(payload).to_bytes(4, "big"))
                s.sendall(payload)

                length_bytes = cls._recv_response_header(s)
                if not length_bytes:
                    return False
                length = int.from_bytes(length_bytes, "big")
                data = cls._recv_exact(s, length)
                if not data:
                    return False
                response = json.loads(data.decode("utf-8"))
                return response.get("status") == "success"
        except (
            ConnectionRefusedError,
            FileNotFoundError,
            OSError,
            ValueError,
            json.JSONDecodeError,
        ):
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

            self._check_python_version_match()

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
        self.agent_script = self._create_agent_script(
            agent_code, suppress_startup_messages=self.suppress_startup_messages
        )
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
                        attempt + 1,
                        self.MAX_ATTEMPTS,
                    )
                else:
                    raise

        return False

    def _attach_fallback(self) -> bool:
        """Attach on pre-PEP-768 Python versions via debugger + dlopen."""
        system_name = platform.system()

        if system_name == "Darwin":
            if not _has_injector():
                raise RuntimeError(
                    "C extension required for macOS attach. "
                    "Build with: uv run python setup.py build_ext --inplace"
                )
            return self._inject_via_lldb()

        if system_name == "Linux":
            if not _has_injector():
                raise RuntimeError(
                    "C extension required for Linux attach. "
                    "Install a wheel with the peeka.core._inject extension or build with: "
                    "uv run python setup.py build_ext --inplace"
                )
            return self._inject_via_gdb()

        raise NotImplementedError(f"Unsupported platform: {system_name}")

    def _inject_via_gdb(self) -> bool:
        """
        Inject via GDB using dlopen + C extension.
        """
        logger.info("Using GDB dlopen injection for PID %d", self.pid)

        self._check_gdb_available()
        self._check_ptrace_permissions()

        agent_code = _read_agent_code()
        notify_port = self._create_notify_server()

        agent_script_path = self._create_agent_script(
            agent_code,
            notify_port=notify_port,
            suppress_startup_messages=self.suppress_startup_messages,
        )
        with open(agent_script_path, encoding="utf-8") as f:
            agent_script_content = f.read()

        injector_path = _find_injector_path()
        if not injector_path:
            raise RuntimeError("C extension not found")

        gdb_script = os.path.join(os.path.dirname(__file__), "_attach.gdb")

        cmd = ["gdb", "-p", str(self.pid), "-batch", "-q"]
        cmd.extend(["-eval-command", f"set $peeka_port = {notify_port}"])
        cmd.extend(["-eval-command", f'set $peeka_injector = "{injector_path}"'])
        cmd.extend(["-eval-command", f"set $peeka_rtld_now = {_RTLD_NOW}"])
        cmd.extend(["-x", gdb_script])

        server_thread = threading.Thread(
            target=self._serve_agent_code,
            args=(agent_script_content, 30),
            daemon=True,
        )
        server_thread.start()

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                text=True,
            )

            stderr = result.stderr.lower()
            combined_output = f"{result.stderr}\n{result.stdout}"
            if "permission denied" in stderr or "operation not permitted" in stderr:
                raise PermissionError("GDB attach failed: permission denied")
            if _looks_like_gdb_symbol_resolution_error(combined_output):
                raise GDBSymbolResolutionError(
                    _format_gdb_symbol_error(
                        "GDB dlopen injection", result.stderr, result.stdout
                    )
                )
            if result.returncode != 0:
                raise RuntimeError(
                    f"GDB dlopen injection failed (exit code {result.returncode}):\n"
                    f"stderr: {result.stderr}\n"
                    f"stdout: {result.stdout}"
                )

            for attempt in range(self.MAX_ATTEMPTS):
                try:
                    if self._wait_for_agent_ready(timeout=self.READY_TIMEOUT_GDB):
                        logger.info("Successfully attached via GDB dlopen")
                        return True
                except TimeoutError:
                    if attempt < self.MAX_ATTEMPTS - 1:
                        logger.info(
                            "Agent not ready yet, retrying... (attempt %d/%d)",
                            attempt + 1,
                            self.MAX_ATTEMPTS,
                        )
                    else:
                        raise

            return False
        except subprocess.TimeoutExpired:
            raise TimeoutError("GDB dlopen injection timed out after 30 seconds")
        except FileNotFoundError:
            raise RuntimeError("GDB executable not found in PATH")
        finally:
            if os.path.exists(agent_script_path):
                os.remove(agent_script_path)
            self._close_notify_server()

    def _inject_via_lldb(self) -> bool:
        """
        Inject via LLDB using dlopen + C extension (macOS only).
        """
        logger.info("Using LLDB dlopen injection for PID %d", self.pid)

        _check_lldb_available()
        self._check_ptrace_permissions()

        agent_code = _read_agent_code()
        notify_port = self._create_notify_server()

        agent_script_path = self._create_agent_script(
            agent_code,
            notify_port=notify_port,
            suppress_startup_messages=self.suppress_startup_messages,
        )
        with open(agent_script_path, encoding="utf-8") as f:
            agent_script_content = f.read()

        injector_path = _find_injector_path()
        if not injector_path:
            raise RuntimeError("C extension not found")

        lldb_script = os.path.join(os.path.dirname(__file__), "_attach.lldb")

        cmd = ["lldb", "-p", str(self.pid), "--batch", "--no-lldbinit"]
        cmd.extend(["--one-line", f"script rtld_default = {_RTLD_DEFAULT}"])
        cmd.extend(["--one-line", f"script rtld_now = {_RTLD_NOW}"])
        cmd.extend(["--one-line", f"script libpath = '{injector_path}'"])
        cmd.extend(["--one-line", f"script port = {notify_port}"])
        cmd.extend(["--source", lldb_script])

        server_thread = threading.Thread(
            target=self._serve_agent_code,
            args=(agent_script_content, 30),
            daemon=True,
        )
        server_thread.start()

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                text=True,
            )

            try:
                os.kill(self.pid, signal.SIGCONT)
            except ProcessLookupError:
                pass

            stderr = result.stderr.lower()
            if "permission denied" in stderr or "operation not permitted" in stderr:
                raise PermissionError("LLDB attach failed: permission denied")
            if result.returncode != 0:
                raise RuntimeError(
                    f"LLDB dlopen injection failed (exit code {result.returncode}):\n"
                    f"stderr: {result.stderr}\n"
                    f"stdout: {result.stdout}"
                )

            for attempt in range(self.MAX_ATTEMPTS):
                try:
                    if self._wait_for_agent_ready(timeout=self.READY_TIMEOUT_GDB):
                        logger.info("Successfully attached via LLDB dlopen")
                        return True
                except TimeoutError:
                    if attempt < self.MAX_ATTEMPTS - 1:
                        logger.info(
                            "Agent not ready yet, retrying... (attempt %d/%d)",
                            attempt + 1,
                            self.MAX_ATTEMPTS,
                        )
                    else:
                        raise

            return False
        except subprocess.TimeoutExpired:
            raise TimeoutError("LLDB dlopen injection timed out after 30 seconds")
        except FileNotFoundError:
            raise RuntimeError("LLDB executable not found in PATH")
        finally:
            if os.path.exists(agent_script_path):
                os.remove(agent_script_path)
            self._close_notify_server()

    def _serve_agent_code(self, agent_code: str, timeout: int = 30):
        """
        Serve agent code to injector via TCP side-channel.
        """
        try:
            server = getattr(self, "_notify_server", None)
            if server is None:
                logger.warning("Notify server not available for side-channel")
                return

            server.settimeout(timeout)
            conn, _ = server.accept()
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
                        logger.warning(
                            "Injector reported agent bootstrap error: %s",
                            error.decode("utf-8", errors="replace"),
                        )
                except sock_mod.timeout:
                    pass
            finally:
                conn.close()
        except sock_mod.timeout:
            logger.warning("Timeout waiting for injector to connect")
        except Exception as e:
            logger.error("Failed to serve agent code: %s", e)

    # ------------------------------------------------------------------ #
    #  Notify server (TCP reverse-connect for readiness detection)       #
    # ------------------------------------------------------------------ #

    def _create_notify_server(self) -> int:
        """Open a localhost TCP server and return the port number.

        The injected agent will connect back to this port once it is
        ready, which is far more reliable than polling for a file.
        """
        self._notify_server = sock_mod.socket(sock_mod.AF_INET, sock_mod.SOCK_STREAM)
        self._notify_server.setsockopt(sock_mod.SOL_SOCKET, sock_mod.SO_REUSEADDR, 1)
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
        self,
        agent_code: str,
        notify_port: Optional[int] = None,
        suppress_startup_messages: bool = False,
    ) -> str:
        agent_path = Path(tempfile.gettempdir()) / f"peeka_agent_{self.session_id}.py"

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
                    # Double-check the Unix socket can complete a command
                    # round trip; connect-only probes miss broken client loops.
                    if self._is_agent_responsive(socket_path):
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

        # Phase 2: Verify the socket can serve a lightweight hello command.
        while time.time() - start_time < timeout:
            if self._is_agent_responsive(socket_path):
                return True
            time.sleep(0.05)

        raise TimeoutError("Agent initialization timeout (agent not responsive)")

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

    def _get_target_python_version(self) -> Optional[Tuple[int, int]]:
        """
        Get the Python major.minor version of the target process.

        On Linux, reads /proc/<pid>/exe to find the Python binary.
        On macOS, uses lsof to find the executable path.
        Then runs the binary with a minimal version-print snippet.

        Returns:
            Optional[Tuple[int, int]]: (major, minor) version tuple, or None
            if the version cannot be determined.
        """
        system_name = platform.system()
        exe_path = None

        if system_name == "Linux":
            try:
                exe_path = os.readlink(f"/proc/{self.pid}/exe")
            except (OSError, PermissionError):
                logger.debug(
                    "Cannot read /proc/%d/exe, skipping version check", self.pid
                )
                return None
        elif system_name == "Darwin":
            try:
                result = subprocess.run(
                    ["lsof", "-p", str(self.pid), "-Fn"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in result.stdout.splitlines():
                    # lsof -Fn: 'n' prefix = file name
                    if line.startswith("n") and "python" in line.lower():
                        exe_path = line[1:]
                        break
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                logger.debug(
                    "Cannot determine executable for PID %d on macOS", self.pid
                )
                return None
        else:
            return None

        if not exe_path:
            return None

        try:
            result = subprocess.run(
                [
                    exe_path,
                    "-c",
                    "import sys; print(sys.version_info[0], sys.version_info[1])",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) == 2:
                    return (int(parts[0]), int(parts[1]))
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
            pass

        # Fallback: extract version from binary name (e.g., /usr/bin/python3.12)
        match = re.search(r"python(\d+)\.(\d+)", exe_path)
        if match:
            return (int(match.group(1)), int(match.group(2)))

        return None

    def _check_python_version_match(self) -> None:
        """
        Verify the target process Python version matches peeka's version.

        Raises:
            RuntimeError: If versions don't match (major.minor mismatch).
        """
        target_version = self._get_target_python_version()
        if target_version is None:
            logger.debug("Could not determine target Python version, skipping check")
            return

        peeka_version = (sys.version_info.major, sys.version_info.minor)

        if target_version != peeka_version:
            target_str = f"{target_version[0]}.{target_version[1]}"
            peeka_str = f"{peeka_version[0]}.{peeka_version[1]}"
            raise RuntimeError(
                f"Python version mismatch: target process (PID {self.pid}) is "
                f"Python {target_str}, but peeka is running on Python {peeka_str}.\n"
                f"The agent code injected into the target process must match "
                f"the target's Python version.\n"
                f"Fix: run peeka with Python {target_str}, e.g.:\n"
                f"  python{target_str} -m peeka.cli.main attach {self.pid}"
            )

    def cleanup(self):
        """Cleanup agent script only; socket and ready file persist for agent"""
        if self.agent_script and os.path.exists(self.agent_script):
            os.remove(self.agent_script)
        self._close_notify_server()
