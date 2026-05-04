"""Helpers for wiring TUI client activity into the dashboard activity log."""

from typing import Callable, Optional


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
