"""Small response helpers shared by CLI handler families."""

from typing import Any, Dict


def response_error_message(response: Dict[str, Any], fallback: str) -> str:
    """Return the most specific error string available in an agent response."""
    return response.get("error") or response.get("message") or fallback


# Backward-compatible private alias for old tests/imports.
def _response_error_message(response: Dict[str, Any], fallback: str) -> str:
    return response_error_message(response, fallback)
