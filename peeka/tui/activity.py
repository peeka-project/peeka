"""Helpers for wiring TUI client identity and activity into diagnostics."""

import os

from typing import Any, Callable, Dict, Optional


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
