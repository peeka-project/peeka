"""Zero-side-effect gevent runtime state detection.

This module is imported inside target Python processes. It must never import
gevent, greenlet, or eventlet as part of detection; doing so would change the
runtime state that diagnostic commands are supposed to report.
"""

import sys
from enum import Enum


class GeventState(str, Enum):
    """Stable gevent runtime states used by data-plane policy."""

    NONE = "none"
    IMPORTED = "imported"
    PATCHED = "patched"
    ACTIVE_HUB = "active_hub"


def has_greenlet() -> bool:
    """Return True when greenlet is already loaded in the target process."""
    return "greenlet" in sys.modules


def _is_module_patched(monkey_module, module_name: str) -> bool:
    """Best-effort wrapper around gevent.monkey.is_module_patched()."""
    is_module_patched = getattr(monkey_module, "is_module_patched", None)
    if not callable(is_module_patched):
        return False
    try:
        return bool(is_module_patched(module_name))
    except Exception:
        return False


def _has_active_hub() -> bool:
    """Return True when an already-loaded gevent hub appears initialized."""
    hub_module = sys.modules.get("gevent.hub")
    if hub_module is None:
        return False

    for attr_name in ("_get_hub", "get_hub_if_exists"):
        get_hub = getattr(hub_module, attr_name, None)
        if not callable(get_hub):
            continue
        try:
            return get_hub() is not None
        except Exception:
            return False

    return False


def probe() -> GeventState:
    """Detect gevent state without importing or mutating runtime modules.

    Returns:
        GeventState: The best-effort gevent runtime state.
    """
    monkey_module = sys.modules.get("gevent.monkey")
    if monkey_module is None:
        return GeventState.NONE

    socket_patched = _is_module_patched(monkey_module, "socket")
    threading_patched = _is_module_patched(monkey_module, "threading")
    if not (socket_patched or threading_patched):
        return GeventState.IMPORTED

    if _has_active_hub():
        return GeventState.ACTIVE_HUB

    return GeventState.PATCHED
