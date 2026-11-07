"""
Process Attacher - Based on PEP 768
Attach to running Python processes and inject agent code
"""

import importlib.util
import logging
import os
import re
import shutil
import socket as sock_mod
import subprocess
import sys
import time
import uuid
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from peeka.core.attach_workflow.capability import AttachCapabilityMixin
from peeka.core.attach_workflow.injectors import AttachInjectionMixin
from peeka.core.attach_workflow.progress import AttachProgressMixin
from peeka.core.attach_workflow.readiness import AttachReadinessMixin
from peeka.core.attach_workflow.session import AttachSessionMixin

logger = logging.getLogger(__name__)

# Compatibility surface for tests and integrations that monkeypatch
# ``peeka.core.attach.Path`` or ``peeka.core.attach.warnings``.
_COMPAT_PATCH_SURFACE = (Path, warnings)

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

# Max progress events to bound memory growth in long-running attach operations
_MAX_PROGRESS_EVENTS = 256

_INJECTOR_BUILD_HINT = (
    "Install a wheel that includes peeka.core._inject, or build the extension "
    "in the active Python environment. Source checkout command: "
    "python setup.py build_ext --inplace. Editable install command: "
    "python -m pip install -e ."
)


@dataclass
class AttachProgressEvent:
    """Structured progress event emitted by ProcessAttacher."""

    phase: str
    status: str
    message: str
    level: str = "info"
    elapsed_ms: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase,
            "status": self.status,
            "message": self.message,
            "level": self.level,
            "elapsed_ms": self.elapsed_ms,
            "details": dict(self.details),
            "timestamp": self.timestamp,
        }


class _AttachProgressLogHandler(logging.Handler):
    """Mirror attach logger records into ProcessAttacher progress events."""

    def __init__(self, attacher: "ProcessAttacher") -> None:
        super().__init__(level=logging.DEBUG)
        self.attacher = attacher

    def emit(self, record: logging.LogRecord) -> None:
        self.attacher._emit_progress(
            "attach_log",
            "logged",
            record.getMessage(),
            level=record.levelname.lower(),
            details={"logger": record.name},
        )


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


_DEBUGGER_SCRIPT_ERROR_PATTERNS = [
    r"no such file or directory",
    r"warning:.*_attach\.(gdb|lldb)",
    r"error:.*_attach\.(gdb|lldb)",
    r"undefined command",
    r"error in sourced command file",
    r"command file not found",
    r"cannot open.*for reading",
    r"command source.*failed",
    r"no commands in script",
]

_BENIGN_WARNING_PATTERNS = [
    r"ptrace",
    r"libthread_db",
    r"reading symbols",
    r"no debugging symbols",
    r"inferior",
    r"\[thread",
]


def _looks_like_debugger_script_error(output: str, debugger: str = "gdb") -> bool:
    """Return True if the output indicates a debugger script/source failure.

    Only escalates errors directly related to loading the debugger script,
    NOT benign warnings about symbols, ptrace, or threads.

    Args:
        output: Combined stdout+stderr from the debugger subprocess.
        debugger: "gdb" or "lldb" (reserved for future specialisation).
    """
    import re

    lowered = output.lower()
    debugger = debugger.lower()

    has_script_error = any(
        re.search(pattern, lowered) for pattern in _DEBUGGER_SCRIPT_ERROR_PATTERNS
    )
    if not has_script_error:
        return False

    # Path-anchor: require the output to also reference the actual attach
    # script (_attach.gdb or _attach.lldb).  Broad patterns such as
    # "no such file or directory" appear in many unrelated subprocess outputs;
    # the script name anchors detection to real _attach.* failures only.
    script_anchor = f"_attach.{debugger}"
    return script_anchor in lowered


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


# Timeout for the target-side C extension loadability probe (seconds).
_INJECTOR_PROBE_TIMEOUT = 5.0

# Only run the target executable as a probe when it is clearly a Python
# interpreter; embedded hosts (uwsgi, blender, ...) must not be executed.
_PYTHON_EXE_RE = re.compile(r"^python\d*(\.\d+)*[a-z]*$")

_INJECTOR_PROBE_CODE = "import ctypes, sys; ctypes.CDLL(sys.argv[1])"


def _summarize_dlopen_error(output: str) -> str:
    """Condense a dlopen/ctypes failure into a short, log-friendly reason."""
    match = re.search(r"version [`'\"]?(GLIBC_[0-9.]+)[`'\"]? not found", output)
    if match:
        return f"{match.group(1)} not found"
    if "cannot open shared object file" in output:
        return "shared object not visible in target filesystem"
    lines = [line.strip() for line in output.strip().splitlines() if line.strip()]
    if not lines:
        return "unknown error"
    reason = lines[-1]
    return reason if len(reason) <= 200 else reason[:197] + "..."


def _probe_injector_in_target(
    pid: int,
    injector_path: str,
    timeout: float = _INJECTOR_PROBE_TIMEOUT,
) -> Tuple[Optional[bool], str]:
    """Check whether the target's environment can dlopen the C injector.

    ``_has_injector()`` only proves the extension loads in the *peeka* process.
    The GDB path dlopen()s it inside the target, whose glibc may be older (for
    example a Python 3.8 Debian container on a GLIBC 2.34+ host). This runs
    ``ctypes.CDLL(injector_path)`` with the target's own interpreter, inside
    the target's mount namespace when it differs from ours (via ``nsenter``),
    so the same dynamic loader and libc that GDB's dlopen would see are used.

    Returns:
        ``(True, "")`` when the extension loads, ``(False, reason)`` when it
        definitely does not, and ``(None, reason)`` when the probe itself could
        not run (no permission, not a python executable, timeout, ...). Callers
        must keep the original behaviour on ``None``.
    """
    if not sys.platform.startswith("linux"):
        return None, "probe only supported on Linux"

    try:
        exe_in_target = os.readlink(f"/proc/{pid}/exe")
    except OSError as exc:
        return None, f"cannot read /proc/{pid}/exe: {exc}"
    exe_in_target = exe_in_target.replace(" (deleted)", "")
    if not _PYTHON_EXE_RE.match(os.path.basename(exe_in_target)):
        return None, f"target executable is not a python interpreter: {exe_in_target}"

    try:
        same_mount_ns = os.readlink(f"/proc/{pid}/ns/mnt") == os.readlink(
            "/proc/self/ns/mnt"
        )
    except OSError:
        same_mount_ns = True

    if same_mount_ns:
        cmd = [exe_in_target]
    else:
        # The interpreter, its dynamic loader and libc live under the target's
        # root; check the binary is there before entering the namespace.
        rooted_exe = f"/proc/{pid}/root{exe_in_target}"
        if not os.access(rooted_exe, os.X_OK):
            return None, f"target interpreter not executable: {rooted_exe}"
        nsenter = shutil.which("nsenter")
        if not nsenter:
            return None, "nsenter not available for cross-namespace probe"
        cmd = [nsenter, f"--target={pid}", "--mount", "--", exe_in_target]
    cmd += ["-I", "-S", "-c", _INJECTOR_PROBE_CODE, injector_path]

    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, f"probe timed out after {timeout:g}s"
    except OSError as exc:
        return None, f"probe could not run: {exc}"

    if result.returncode == 0:
        return True, ""

    output = f"{result.stderr}\n{result.stdout}"
    lowered = output.lower()
    if not same_mount_ns and (
        "operation not permitted" in lowered or "permission denied" in lowered
    ) and "ctypes" not in lowered:
        return None, "no permission to enter target mount namespace"
    if "OSError" in output or "cannot open shared object" in output:
        return False, _summarize_dlopen_error(output)
    return None, f"probe failed (exit {result.returncode}): {_summarize_dlopen_error(output)}"


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


class ProcessAttacher(
    AttachProgressMixin,
    AttachSessionMixin,
    AttachInjectionMixin,
    AttachReadinessMixin,
    AttachCapabilityMixin,
):
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
        progress_callback: Optional[Callable[[AttachProgressEvent], None]] = None,
    ):
        self.pid = pid
        self.suppress_startup_messages = suppress_startup_messages
        self.agent_script = None
        self.session_id = session_id or str(uuid.uuid4())
        self._existing_session = None
        self._notify_server: Optional[sock_mod.socket] = None
        self.progress_callback = progress_callback
        self.progress_events: List[AttachProgressEvent] = []
        self._progress_callback_error_active = False
        self._last_attach_error: Optional[str] = None


    def attach(self) -> bool:
        """Attach to target process while mirroring diagnostics if requested."""
        with self._capture_attach_diagnostics():
            return self._attach_internal()

    def get_last_error(self) -> Optional[str]:
        """Get the last attach error message, if any.

        Returns:
            Optional[str]: Error message from the most recent attach failure, or None
        """
        return self._last_attach_error

    def _attach_internal(self) -> bool:
        """
        Attach to target process

        Returns:
            bool: True if successful, False otherwise
        """
        attach_start = time.monotonic()
        try:
            self._emit_progress(
                "target_selected",
                "done",
                f"Selected target process {self.pid}",
                details={"pid": self.pid},
            )

            existing = self._check_existing_attachment()

            if existing:
                existing_session, existing_pid = existing
                if existing_pid == self.pid:
                    logger.info("Already attached to process %d", self.pid)
                    logger.info("Socket path: /tmp/peeka_%s.sock", existing_session)
                    self._existing_session = existing_session
                    self._emit_progress(
                        "attached",
                        "done",
                        f"Reused existing attachment for PID {self.pid}",
                        elapsed_ms=(time.monotonic() - attach_start) * 1000,
                        details={"session_id": existing_session, "pid": self.pid},
                    )
                    return True
                else:
                    raise RuntimeError(
                        f"Already attached to process {existing_pid}. "
                        f"Please detach first: peeka detach"
                    )

            logger.info("Attaching to process %d...", self.pid)

            target_version: Optional[Tuple[int, int]] = None
            capability_start = time.monotonic()
            self._emit_progress(
                "detect_python_capability",
                "running",
                "Detecting target Python version and attach capability",
            )
            try:
                target_version = self._get_target_python_version()
                if target_version is None:
                    logger.debug(
                        "Could not determine target Python version, skipping check"
                    )
                else:
                    self._check_python_version_match(target_version)
            except Exception as exc:
                self._emit_progress(
                    "detect_python_capability",
                    "failed",
                    f"Python capability check failed: {exc}",
                    level="error",
                    elapsed_ms=(time.monotonic() - capability_start) * 1000,
                )
                raise

            capability_elapsed_ms = (time.monotonic() - capability_start) * 1000

            if hasattr(sys, "remote_exec"):
                self._emit_progress(
                    "detect_python_capability",
                    "done",
                    "PEP 768 available; using remote_exec",
                    elapsed_ms=capability_elapsed_ms,
                    details={
                        "target_python": self._format_python_version(target_version),
                        "pep768_available": True,
                    },
                )
                result = self._attach_pep768()
            else:
                logger.warning("PEP 768 not available (Python 3.14+ required)")
                self._emit_progress(
                    "detect_python_capability",
                    "done",
                    "PEP 768 unavailable; using debugger fallback",
                    level="warning",
                    elapsed_ms=capability_elapsed_ms,
                    details={
                        "target_python": self._format_python_version(target_version),
                        "pep768_available": False,
                        "fallback": "debugger",
                    },
                )
                logger.info("Using fallback mechanism for demonstration")
                result = self._attach_fallback()

            if result:
                self._save_attachment_state()
                self._emit_progress(
                    "attached",
                    "done",
                    f"Successfully attached to process {self.pid}",
                    elapsed_ms=(time.monotonic() - attach_start) * 1000,
                    details={
                        "pid": self.pid,
                        "session_id": self.session_id,
                        "socket_path": self.get_socket_path(),
                    },
                )

            return result

        except Exception as e:
            self._last_attach_error = str(e)
            self._emit_progress(
                "attached",
                "failed",
                f"Attach failed: {e}",
                level="error",
                elapsed_ms=(time.monotonic() - attach_start) * 1000,
                details={"pid": self.pid},
            )
            logger.error("Attach failed: %s", e)
            import traceback

            traceback.print_exc()
            return False
