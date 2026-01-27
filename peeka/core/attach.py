"""
Process Attacher - Based on PEP 768
Attach to running Python processes and inject agent code
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
import warnings
from importlib import resources
from pathlib import Path


class ProcessAttacher:
    """
    Process attacher using PEP 768 interface

    For Python 3.14+, uses sys.remote_exec()
    For older versions, uses fallback mechanism
    """

    def __init__(self, pid: int):
        self.pid = pid
        self.agent_script = None
        self.session_id = str(uuid.uuid4())

    def attach(self) -> bool:
        """
        Attach to target process

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            print(f"[Peeka] Attaching to process {self.pid}...")

            # Check if PEP 768 is supported
            if hasattr(sys, "remote_exec"):
                return self._attach_pep768()
            else:
                print("[Peeka] Warning: PEP 768 not available (Python 3.14+ required)")
                print("[Peeka] Using fallback mechanism for demonstration")
                return self._attach_fallback()

        except Exception as e:
            print(f"[Peeka] Attach failed: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _attach_pep768(self) -> bool:
        """Attach using PEP 768 sys.remote_exec()"""
        # from peeka.core.agent import AGENT_CODE
        agent_code = (
            resources.files("peeka.core")
            .joinpath("agent.py")
            .read_text(encoding="utf-8")
        )

        # Create agent script
        self.agent_script = self._create_agent_script(agent_code)
        if not os.path.exists(self.agent_script):
            raise FileNotFoundError(f"Agent script not found: {self.agent_script}")
        else:
            print(f"[Peeka] Agent script created at {self.agent_script}")

        # Inject to target process
        sys.remote_exec(self.pid, self.agent_script)

        # Wait for agent ready
        if self._wait_for_agent_ready():
            print(f"[Peeka] Successfully attached to process {self.pid}")
            return True

        return False

    def _attach_fallback(self) -> bool:
        """
        Fallback mechanism for older Python versions using GDB + ptrace.

        This uses the pyrasite approach:
        1. Use GDB to attach to target process (via ptrace)
        2. Call PyGILState_Ensure to acquire GIL
        3. Call PyRun_SimpleString to execute agent bootstrap code
        4. Call PyGILState_Release to release GIL
        5. GDB detaches, process continues

        Requirements:
        - GDB 7.3+
        - CAP_SYS_PTRACE or same UID
        - ptrace_scope <= 1
        - Python debugging symbols
        """
        print(f"[Peeka] Using GDB injection for PID {self.pid} (Python <3.14)")

        self._check_gdb_available()
        self._check_ptrace_permissions()

        agent_code = (
            resources.files("peeka.core")
            .joinpath("agent.py")
            .read_text(encoding="utf-8")
        )

        agent_script = self._create_agent_script(agent_code)

        try:
            self._inject_via_gdb(agent_script)

            if self._wait_for_agent_ready():
                print(f"[Peeka] Successfully attached to process {self.pid}")
                return True
            else:
                raise RuntimeError("Agent failed to initialize")

        except Exception as e:
            print(f"[Peeka] GDB injection failed: {e}")
            raise
        finally:
            if os.path.exists(agent_script):
                os.remove(agent_script)

    def _create_agent_script(self, agent_code: str) -> str:
        agent_path = Path(tempfile.gettempdir()) / f"peeka_agent_{self.session_id}.py"

        agent_code_injected = agent_code.replace("{{SESSION_ID}}", self.session_id)

        peeka_root = str(Path(__file__).parent.parent.parent.resolve())
        path_bootstrap = f"import sys; sys.path.insert(0, {peeka_root!r}) if {peeka_root!r} not in sys.path else None\n"

        with open(agent_path, "w") as f:
            print(f"[Peeka] Creating agent script at {agent_path}")
            f.write(path_bootstrap + agent_code_injected)

        return str(agent_path)

    def _wait_for_agent_ready(self, timeout: int = 5) -> bool:
        """Wait for agent initialization"""
        ready_file = Path(f"/tmp/peeka_{self.session_id}.ready")

        start_time = time.time()
        while time.time() - start_time < timeout:
            if ready_file.exists():
                return True
            time.sleep(0.1)

        raise TimeoutError("Agent initialization timeout")

    def get_socket_path(self) -> str:
        """Get Unix domain socket path for communication"""
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
        Inject agent script using GDB.

        Executes Python code in target process by calling Python C API functions:
        - PyGILState_Ensure(): Acquire GIL
        - PyRun_SimpleString(): Execute Python code
        - PyGILState_Release(): Release GIL
        """
        escaped_script = agent_script.replace("\\", "\\\\").replace('"', '\\"')

        gdb_commands = [
            "PyGILState_Ensure()",
            f'PyRun_SimpleString("exec(open(\\"{escaped_script}\\").read())")',
            "PyGILState_Release($1)",
        ]

        cmd = ["gdb", "-p", str(self.pid), "-batch", "-q"]
        for gdb_cmd in gdb_commands:
            cmd.extend(["-eval-command", f"call (void*) {gdb_cmd}"])

        print(f"[Peeka] Injecting agent via GDB...")

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

            print(f"[Peeka] GDB injection completed")

        except subprocess.TimeoutExpired:
            raise TimeoutError(
                "GDB injection timed out after 30 seconds. "
                "Process may be deadlocked or unresponsive."
            )
        except FileNotFoundError:
            raise RuntimeError("GDB executable not found in PATH")

    def cleanup(self):
        """Cleanup temporary files"""
        if self.agent_script and os.path.exists(self.agent_script):
            os.remove(self.agent_script)

        ready_file = Path(f"/tmp/peeka_{self.session_id}.ready")
        if ready_file.exists():
            ready_file.unlink()

        sock_path = Path(self.get_socket_path())
        if sock_path.exists():
            sock_path.unlink()
