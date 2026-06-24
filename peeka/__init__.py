"""PeekA - Python Dynamic Debugger."""

import os
import sys
import tempfile

__version__ = "0.1.18"

# Cached for testability: tests can monkeypatch peeka._geteuid without
# mutating the global os module.
_geteuid = os.geteuid

_SUDO_PYCACHE_ENV = "PEEKA_SUDO_PYCACHE_PREFIX"
_DISABLE_SUDO_PYCACHE_REDIRECT_ENV = "PEEKA_DISABLE_SUDO_PYCACHE_REDIRECT"


def _running_under_sudo(geteuid=_geteuid) -> bool:
    """Return True when Peeka is running as root through sudo."""
    return callable(geteuid) and geteuid() == 0 and "SUDO_UID" in os.environ


def _sudo_pycache_prefix() -> str:
    """Return the pycache prefix used for sudo-launched Peeka imports."""
    return os.environ.get(
        _SUDO_PYCACHE_ENV,
        os.path.join(tempfile.gettempdir(), "peeka-pycache-root"),
    )


def _configure_sudo_bytecode_policy(geteuid=_geteuid) -> None:
    """Redirect sudo bytecode caches away from user-owned virtualenvs."""
    if not _running_under_sudo(geteuid):
        return
    if os.environ.get(_DISABLE_SUDO_PYCACHE_REDIRECT_ENV) == "1":
        return
    if getattr(sys, "pycache_prefix", None) is None:
        sys.pycache_prefix = _sudo_pycache_prefix()


_configure_sudo_bytecode_policy()
