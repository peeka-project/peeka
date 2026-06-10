"""Helpers for rendering runtime status responses in TUI views."""

from typing import Any, Dict, Optional


def extract_patch_status_payload(response: Dict[str, Any]) -> Dict[str, Any]:
    """Return the nested patch-status payload when the command envelope is present."""
    payload = response.get("data")
    if isinstance(payload, dict):
        return payload
    return response


def summarize_patch_status(response: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize patch-status responses for compact TUI rendering."""
    payload = extract_patch_status_payload(response)
    gevent_state = payload.get("gevent_state") or _gevent_state_from_payload(payload)
    backend = payload.get("backend") or "unknown"
    downgraded = bool(payload.get("downgraded", False))
    degraded_reason = payload.get("degraded_reason")

    return {
        "gevent_state": gevent_state or "none",
        "backend": backend,
        "downgraded": downgraded,
        "degraded_reason": degraded_reason,
    }


def has_runtime_signal(summary: Dict[str, Any]) -> bool:
    """Return True when a compact runtime banner has useful information."""
    return (
        summary.get("gevent_state") not in (None, "", "none")
        or summary.get("backend") not in (None, "", "unknown")
        or bool(summary.get("downgraded"))
    )


def _gevent_state_from_payload(payload: Dict[str, Any]) -> Optional[str]:
    """Derive a display state from the patch-status monkey_patch section."""
    monkey_patch = payload.get("monkey_patch")
    if not isinstance(monkey_patch, dict):
        return None

    gevent = monkey_patch.get("gevent")
    if isinstance(gevent, str):
        if gevent == "not_imported":
            return "none"
        return gevent

    if not isinstance(gevent, dict):
        return None

    status = gevent.get("status")
    if status == "active":
        return "patched"
    if status == "imported_not_active":
        return "imported"
    if isinstance(status, str):
        return status
    return None
