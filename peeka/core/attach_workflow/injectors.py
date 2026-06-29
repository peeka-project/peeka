"""PEP 768, GDB, and LLDB attach implementations."""

import os
import platform
from pathlib import Path
import shutil
import signal
import subprocess
from typing import Optional

from peeka.core.resources import require_core_resource
from peeka.core.runtime import primitives as _rpl


def _attach_module():
    from peeka.core import attach as attach_module

    return attach_module


def _preflight_debugger_injection(
    *,
    debugger: str,
    debugger_script: Path,
    injector_path: str,
) -> None:
    """Fail fast before launching the debugger subprocess.

    Raises RuntimeError with an actionable message if any resource is missing
    or the debugger executable is unavailable.
    """
    from pathlib import Path as _Path

    if not shutil.which(debugger):
        raise RuntimeError(
            f"Debugger not found in PATH: {debugger!r}. "
            "Install GDB (Linux) or LLDB (macOS) before attaching."
        )
    if not isinstance(debugger_script, _Path):
        debugger_script = _Path(debugger_script)
    if not debugger_script.exists():
        raise RuntimeError(
            f"Attach debugger script not found: {debugger_script}. "
            "This is a packaging issue — the script should ship with peeka."
        )
    if not injector_path or not _Path(injector_path).exists():
        raise RuntimeError(
            f"C extension injector not found: {injector_path!r}. "
            "Rebuild the peeka C extension for your platform."
        )


class AttachInjectionMixin:

    def _attach_pep768(self) -> bool:
        """Attach using PEP 768 _attach_module().sys.remote_exec()"""
        with self._progress_phase(
            "prepare_injection",
            "Preparing PEP 768 agent script",
            "PEP 768 agent script prepared",
            details={"method": "pep768"},
        ):
            agent_code = _attach_module()._read_agent_code()

            # Create agent script
            self.agent_script = self._create_agent_script(
                agent_code, suppress_startup_messages=self.suppress_startup_messages
            )
            if not os.path.exists(self.agent_script):
                raise FileNotFoundError(f"Agent script not found: {self.agent_script}")
            else:
                _attach_module().logger.debug("Agent script created at %s", self.agent_script)

        with self._progress_phase(
            "run_injector",
            "Running PEP 768 remote_exec injection",
            "PEP 768 remote_exec injection completed",
            details={"method": "pep768"},
        ):
            _attach_module().sys.remote_exec(self.pid, self.agent_script)

        # Wait for agent ready with retry — agent bootstrap imports 13+
        # command modules and may take longer than a single timeout on
        # loaded systems or first injection into a cold process.
        for attempt in range(self.MAX_ATTEMPTS):
            try:
                if self._wait_for_agent_ready(timeout=self.READY_TIMEOUT_PEP768):
                    _attach_module().logger.info("Successfully attached to process %d", self.pid)
                    return True
            except TimeoutError:
                if attempt < self.MAX_ATTEMPTS - 1:
                    _attach_module().logger.info(
                        "Agent not ready yet, retrying... (attempt %d/%d)",
                        attempt + 1,
                        self.MAX_ATTEMPTS,
                    )
                else:
                    raise

        self._last_attach_error = "Agent did not become ready after waiting"
        return False

    def _attach_fallback(self) -> bool:
        """Attach on pre-PEP-768 Python versions via debugger + dlopen."""
        system_name = platform.system()

        if system_name == "Darwin":
            if not _attach_module()._has_injector():
                raise RuntimeError(
                    "C extension required for macOS attach. "
                    f"{_attach_module()._INJECTOR_BUILD_HINT}"
                )
            return self._inject_via_lldb()

        if system_name == "Linux":
            if not _attach_module()._has_injector():
                raise RuntimeError(
                    "C extension required for Linux attach. "
                    f"{_attach_module()._INJECTOR_BUILD_HINT}"
                )
            return self._inject_via_gdb()

        raise NotImplementedError(f"Unsupported platform: {system_name}")

    def _inject_via_gdb(self) -> bool:
        """
        Inject via GDB using dlopen + C extension.
        """
        _attach_module().logger.info("Using GDB dlopen injection for PID %d", self.pid)

        agent_script_path: Optional[str] = None
        with self._progress_phase(
            "prepare_injection",
            "Preparing GDB dlopen injection",
            "GDB dlopen injection prepared",
            details={"method": "gdb_dlopen"},
        ):
            self._check_gdb_available()
            self._check_ptrace_permissions()

            agent_code = _attach_module()._read_agent_code()
            notify_port = self._create_notify_server()

            agent_script_path = self._create_agent_script(
                agent_code,
                notify_port=notify_port,
                suppress_startup_messages=self.suppress_startup_messages,
            )
            with open(agent_script_path, encoding="utf-8") as f:
                agent_script_content = f.read()

            injector_path = _attach_module()._find_injector_path()
            if not injector_path:
                raise RuntimeError("C extension not found")

            gdb_script_path = require_core_resource("_attach.gdb")
            _preflight_debugger_injection(
                debugger="gdb",
                debugger_script=gdb_script_path,
                injector_path=injector_path or "",
            )
            gdb_script = str(gdb_script_path)

            cmd = ["gdb", "-p", str(self.pid), "-batch", "-q"]
            cmd.extend(["-eval-command", f"set $peeka_port = {notify_port}"])
            cmd.extend(["-eval-command", f'set $peeka_injector = "{injector_path}"'])
            cmd.extend(["-eval-command", f"set $peeka_rtld_now = {_attach_module()._RTLD_NOW}"])
            cmd.extend(["-x", gdb_script])

            server_thread_id = _rpl.start_thread(
                target=self._serve_agent_code,
                args=(agent_script_content, 30),
                daemon=True,
                name="peeka-attach-server",
            )
            _attach_module().logger.debug("Started attach server thread id=%s", server_thread_id)

        try:
            with self._progress_phase(
                "run_injector",
                "Running GDB dlopen injector",
                "GDB dlopen injector completed",
                details={"method": "gdb_dlopen", "timeout": 30},
            ):
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
            if _attach_module()._looks_like_debugger_script_error(combined_output, "gdb"):
                raise RuntimeError(
                    "GDB injection failed: debugger script error detected "
                    f"(exit code {result.returncode}).\n"
                    f"stderr: {result.stderr}\nstdout: {result.stdout}"
                )
            if _attach_module()._looks_like_gdb_symbol_resolution_error(combined_output):
                raise _attach_module().GDBSymbolResolutionError(
                    _attach_module()._format_gdb_symbol_error(
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
                        _attach_module().logger.info("Successfully attached via GDB dlopen")
                        return True
                except TimeoutError:
                    if attempt < self.MAX_ATTEMPTS - 1:
                        _attach_module().logger.info(
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
            if agent_script_path and os.path.exists(agent_script_path):
                os.remove(agent_script_path)
            self._close_notify_server()

    def _inject_via_lldb(self) -> bool:
        """
        Inject via LLDB using dlopen + C extension (macOS only).
        """
        _attach_module().logger.info("Using LLDB dlopen injection for PID %d", self.pid)

        agent_script_path: Optional[str] = None
        with self._progress_phase(
            "prepare_injection",
            "Preparing LLDB dlopen injection",
            "LLDB dlopen injection prepared",
            details={"method": "lldb_dlopen"},
        ):
            _attach_module()._check_lldb_available()
            self._check_ptrace_permissions()

            agent_code = _attach_module()._read_agent_code()
            notify_port = self._create_notify_server()

            agent_script_path = self._create_agent_script(
                agent_code,
                notify_port=notify_port,
                suppress_startup_messages=self.suppress_startup_messages,
            )
            with open(agent_script_path, encoding="utf-8") as f:
                agent_script_content = f.read()

            injector_path = _attach_module()._find_injector_path()
            if not injector_path:
                raise RuntimeError("C extension not found")

            lldb_script_path = require_core_resource("_attach.lldb")
            _preflight_debugger_injection(
                debugger="lldb",
                debugger_script=lldb_script_path,
                injector_path=injector_path or "",
            )
            lldb_script = str(lldb_script_path)

            cmd = ["lldb", "-p", str(self.pid), "--batch", "--no-lldbinit"]
            cmd.extend(["--one-line", f"script rtld_default = {_attach_module()._RTLD_DEFAULT}"])
            cmd.extend(["--one-line", f"script rtld_now = {_attach_module()._RTLD_NOW}"])
            cmd.extend(["--one-line", f"script libpath = '{injector_path}'"])
            cmd.extend(["--one-line", f"script port = {notify_port}"])
            cmd.extend(["--source", lldb_script])

            server_thread_id = _rpl.start_thread(
                target=self._serve_agent_code,
                args=(agent_script_content, 30),
                daemon=True,
                name="peeka-attach-server",
            )
            _attach_module().logger.debug("Started attach server thread id=%s", server_thread_id)

        try:
            with self._progress_phase(
                "run_injector",
                "Running LLDB dlopen injector",
                "LLDB dlopen injector completed",
                details={"method": "lldb_dlopen", "timeout": 30},
            ):
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
            combined_output = f"{result.stderr}\n{result.stdout}"
            if _attach_module()._looks_like_debugger_script_error(combined_output, "lldb"):
                raise RuntimeError(
                    "LLDB injection failed: debugger script error detected "
                    f"(exit code {result.returncode}).\n"
                    f"stderr: {result.stderr}\nstdout: {result.stdout}"
                )
            if result.returncode != 0:
                raise RuntimeError(
                    f"LLDB dlopen injection failed (exit code {result.returncode}):\n"
                    f"stderr: {result.stderr}\n"
                    f"stdout: {result.stdout}"
                )

            for attempt in range(self.MAX_ATTEMPTS):
                try:
                    if self._wait_for_agent_ready(timeout=self.READY_TIMEOUT_GDB):
                        _attach_module().logger.info("Successfully attached via LLDB dlopen")
                        return True
                except TimeoutError:
                    if attempt < self.MAX_ATTEMPTS - 1:
                        _attach_module().logger.info(
                            "Agent not ready yet, retrying... (attempt %d/%d)",
                            attempt + 1,
                            self.MAX_ATTEMPTS,
                        )
                    else:
                        raise

            self._last_attach_error = "Agent did not become ready after waiting"
            return False
        except subprocess.TimeoutExpired:
            raise TimeoutError("LLDB dlopen injection timed out after 30 seconds")
        except FileNotFoundError:
            raise RuntimeError("LLDB executable not found in PATH")
        finally:
            if agent_script_path and os.path.exists(agent_script_path):
                os.remove(agent_script_path)
            self._close_notify_server()
