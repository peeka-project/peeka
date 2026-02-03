"""
Output Formatter - Standardized JSONL output for all commands

All Peeka commands output JSONL (one JSON object per line) with a 'type' field
to enable easy parsing by upstream applications.
"""

import json
import sys
from typing import Any, Dict, Optional


class OutputFormatter:
    """
    Standardized output formatter for consistent JSONL output.

    Output Types:
    - status: Progress/informational messages (non-critical)
    - success: Command completed successfully
    - error: Command failed with error details
    - event: Control events (started, stopped, etc.)
    - observation: Real-time observation data from watched functions
    - result: Query results from non-streaming commands
    """

    @staticmethod
    def status(message: str, **kwargs) -> None:
        """Output a status/info message."""
        output = {"type": "status", "level": "info", "message": message}
        output.update(kwargs)
        print(json.dumps(output), flush=True)

    @staticmethod
    def success(command: str, data: Optional[Dict[str, Any]] = None, **kwargs) -> None:
        """Output a success response."""
        output = {"type": "success", "command": command}
        if data:
            output["data"] = data
        output.update(kwargs)
        print(json.dumps(output), flush=True)

    @staticmethod
    def error(
        command: str, error: str, suggestion: Optional[str] = None, **kwargs
    ) -> None:
        """Output an error response."""
        output = {"type": "error", "command": command, "error": error}
        if suggestion:
            output["suggestion"] = suggestion
        output.update(kwargs)
        print(json.dumps(output), flush=True)

    @staticmethod
    def event(event: str, data: Optional[Dict[str, Any]] = None, **kwargs) -> None:
        """Output a control event."""
        output = {"type": "event", "event": event}
        if data:
            output["data"] = data
        output.update(kwargs)
        print(json.dumps(output), flush=True)

    @staticmethod
    def observation(data: Dict[str, Any], **kwargs) -> None:
        """Output an observation from watched function."""
        output = {"type": "observation", "data": data}
        output.update(kwargs)
        print(json.dumps(output), flush=True)

    @staticmethod
    def result(command: str, data: Dict[str, Any], **kwargs) -> None:
        """Output a query result."""
        output = {"type": "result", "command": command, "data": data}
        output.update(kwargs)
        print(json.dumps(output), flush=True)
