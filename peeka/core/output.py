"""
Output Formatter - Standardized JSONL output for all commands

All Peeka commands output JSONL (one JSON object per line) with a 'type' field
to enable easy parsing by upstream applications.
"""

import json
import logging
import os
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
    def status(message: str, file=None, **kwargs) -> None:
        output = {"type": "status", "level": "info", "message": message}
        output.update(kwargs)
        print(json.dumps(output), flush=True, file=file or sys.stdout)

    @staticmethod
    def success(
        command: str, data: Optional[Dict[str, Any]] = None, file=None, **kwargs
    ) -> None:
        output = {"type": "success", "command": command}
        if data:
            output["data"] = data
        output.update(kwargs)
        print(json.dumps(output), flush=True, file=file or sys.stdout)

    @staticmethod
    def error(
        command: str, error: str, suggestion: Optional[str] = None, file=None, **kwargs
    ) -> None:
        output = {"type": "error", "command": command, "error": error}
        if suggestion:
            output["suggestion"] = suggestion
        output.update(kwargs)
        print(json.dumps(output), flush=True, file=file or sys.stdout)

    @staticmethod
    def event(
        event: str, data: Optional[Dict[str, Any]] = None, file=None, **kwargs
    ) -> None:
        output = {"type": "event", "event": event}
        if data:
            output["data"] = data
        output.update(kwargs)
        print(json.dumps(output), flush=True, file=file or sys.stdout)

    @staticmethod
    def observation(data: Dict[str, Any], file=None, **kwargs) -> None:
        output = {"type": "observation", "data": data}
        output.update(kwargs)
        print(json.dumps(output), flush=True, file=file or sys.stdout)

    @staticmethod
    def result(command: str, data: Dict[str, Any], file=None, **kwargs) -> None:
        output = {"type": "result", "command": command, "data": data}
        output.update(kwargs)
        print(json.dumps(output), flush=True, file=file or sys.stdout)


def configure_logging(
    add_stream_handler: bool = True,
    custom_handler: Optional[logging.Handler] = None,
) -> None:
    """Configure logging for peeka process from environment variable.

    Reads PEEKA_LOG_LEVEL environment variable to set root logger level.
    Defaults to WARNING if not set.
    Logs go to stderr to avoid mixing with JSONL output on stdout.

    Args:
        add_stream_handler: Whether to add a stream handler (stderr).
        custom_handler: Optional custom handler to add.
    """
    log_level_name = os.environ.get("PEEKA_LOG_LEVEL", "WARNING").upper()
    log_level = getattr(logging, log_level_name, logging.WARNING)

    # Check if we need to configure
    if logging.root.level == logging.NOTSET or add_stream_handler or custom_handler:
        # Only call basicConfig if no handlers exist and we want to add a stream handler
        if not logging.root.handlers and add_stream_handler:
            logging.basicConfig(
                level=log_level,
                format="%(asctime)s %(name)s %(levelname)s: %(message)s",
                stream=sys.stderr,
            )
        else:
            # Otherwise, just set the level
            logging.root.setLevel(log_level)

    # Always set the level even if basicConfig has already been called
    logging.root.setLevel(log_level)

    # Add custom handler if provided
    if custom_handler:
        # Set the same format as the stream handler
        formatter = logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
        custom_handler.setFormatter(formatter)
        custom_handler.setLevel(log_level)
        logging.root.addHandler(custom_handler)
