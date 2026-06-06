"""
Process Attacher - Based on PEP 768
Attach to running Python processes and inject agent code
"""

import importlib.util
import logging
import shutil
import socket as sock_mod
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
