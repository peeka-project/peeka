"""Helpers for wiring TUI client identity and activity into diagnostics."""

import os
import re

from typing import Any, Callable, Dict, List, Optional, Tuple

from peeka.core.attach import AttachProgressEvent

_PTRACE_SCOPE_PATTERN = re.compile(r"ptrace_scope is (?P<scope>\d+)")


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
        if level in ("DEBUG", "INFO"):
            return None
        if event.message.startswith("PEP 768 not available"):
            return None
        ptrace_warning = _format_ptrace_scope_warning(event.message)
        if ptrace_warning:
            return level, ptrace_warning
        elapsed = _format_attach_elapsed(event)
        message = " ".join(event.message.split())
        return level, f"attach.log {event.level.lower()}: {message}{elapsed}"

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


def format_attach_summary(
    events: List[AttachProgressEvent],
) -> Optional[Tuple[str, str, Dict[str, Any]]]:
    """Summarize a completed attach attempt for client activity logs."""
    if not events:
        return None

    terminal = events[-1]
    if terminal.phase != "attached" or terminal.status not in ("done", "failed"):
        return None

    timed_events = [
        event
        for event in events
        if event.phase not in ("attach_log", "attached")
        and event.elapsed_ms is not None
    ]
    slowest = max(timed_events, key=lambda event: event.elapsed_ms or 0, default=None)
    total_elapsed = terminal.elapsed_ms
    method = _extract_attach_method(events)

    details: Dict[str, Any] = {
        "timed_phase_count": len(timed_events),
    }
    parts = []
    if total_elapsed is not None:
        details["total_elapsed_ms"] = total_elapsed
        parts.append(f"total={int(total_elapsed)}ms")
    if slowest is not None and slowest.elapsed_ms is not None:
        details["slowest_phase"] = slowest.phase
        details["slowest_elapsed_ms"] = slowest.elapsed_ms
        parts.append(f"slowest={slowest.phase} {int(slowest.elapsed_ms)}ms")
    parts.append(f"timed_phases={len(timed_events)}")
    if method:
        details["method"] = method
        parts.append(f"method={method}")

    summary = ", ".join(parts) if parts else "no timing data"
    metadata = {
        "phase": "summary",
        "status": terminal.status,
        "elapsed_ms": total_elapsed,
        "details": details,
    }
    return terminal.level.upper(), f"attach.summary {terminal.status}: {summary}", metadata


def _extract_attach_method(events: List[AttachProgressEvent]) -> Optional[str]:
    """Return the most specific attach method observed in progress metadata."""
    for event in reversed(events):
        method = event.details.get("method")
        if method:
            return str(method)
    return None


def _format_ptrace_scope_warning(message: str) -> Optional[str]:
    """Return a compact Dashboard warning for ptrace scope diagnostics."""
    match = _PTRACE_SCOPE_PATTERN.search(message)
    if not match:
        return None

    return (
        f"attach.prepare_injection warning: ptrace_scope={match.group('scope')}; "
        "GDB attach may fail for non-child targets"
    )


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
