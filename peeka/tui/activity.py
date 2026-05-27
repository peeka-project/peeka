"""Helpers for wiring TUI client identity and activity into diagnostics."""

import os

from typing import Any, Callable, Dict, Optional, Tuple

from peeka.core.attach import AttachProgressEvent


def format_attach_activity(
    event: AttachProgressEvent,
) -> Optional[Tuple[str, str]]:
    """Format one attach progress event for client activity logs.

    Args:
        event: Structured attach progress event from ``ProcessAttacher``.

    Returns:
        ``(level, message)`` for activity buffers, or ``None`` when the event
        should stay out of high-level activity logs.
    """
    phase = event.phase
    status = event.status
    level = event.level.upper()

    if phase == "attach_log":
        if level == "DEBUG":
            return None
        elapsed = _format_attach_elapsed(event)
        return level, f"attach.log {event.level.lower()}: {event.message}{elapsed}"

    elapsed = _format_attach_elapsed(event)
    return level, f"attach.{phase} {status}: {event.message}{elapsed}"


def attach_activity_metadata(event: AttachProgressEvent) -> Dict[str, Any]:
    """Return structured metadata for an attach progress activity entry."""
    return {
        "phase": event.phase,
        "status": event.status,
        "elapsed_ms": event.elapsed_ms,
        "details": dict(event.details),
    }


def _format_attach_elapsed(event: AttachProgressEvent) -> str:
    """Return a compact elapsed-time suffix for attach activity entries."""
    if event.elapsed_ms is None:
        return ""

    label = " total" if event.phase == "attached" else ""
    return f" ({int(event.elapsed_ms)}ms{label})"


def make_activity_reporter(
    app: object, source: str
) -> Optional[Callable[[str, str], None]]:
    """Return a reporter closure bound to a specific TUI activity source."""
    recorder = getattr(app, "record_client_activity", None)
    if not callable(recorder):
        return None

    def reporter(level: str, message: str) -> None:
        recorder(level, message, source=source)

    return reporter


def make_client_info(app: object, source: str) -> Dict[str, Any]:
    """Return stable identity metadata for a TUI socket connection."""
    instance_id = getattr(app, "client_instance_id", None)
    if not instance_id:
        instance_id = f"tui-{os.getpid()}"
    return {
        "id": instance_id,
        "kind": "tui",
        "source": source,
        "pid": os.getpid(),
    }
