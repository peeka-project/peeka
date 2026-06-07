"""Reusable request/reply CLI command runner."""

from typing import Any, Callable, Dict, Optional

from peeka.cli.connection import _connect_streaming_agent
from peeka.core.output import OutputFormatter


def run_command(
    args: Any,
    command_name: str,
    build_command: Callable[[Any], Dict[str, Any]],
    render_success: Callable[[Any, Dict[str, Any]], None],
    *,
    render_error: Optional[
        Callable[[Any, Dict[str, Any], str, Optional[str]], None]
    ] = None,
    error_message: str = "Command failed",
    error_exit_codes: Optional[Dict[str, int]] = None,
) -> int:
    """Run a request/reply CLI command against the attached agent.

    Encapsulates the connect / send / disconnect / error pattern used by
    Variant A handlers (clients, jobs, probes, dx).

    Args:
        args: Parsed argparse namespace.
        command_name: Command name used in error output.
        build_command: Callable(args) -> Dict — builds the command dict to send.
        render_success: Callable(args, response) -> None — renders success output.
    error_message: Fallback error message when the response provides none.
    render_error: Optional callback to render failure output.
    error_exit_codes: Optional mapping of error_code string to exit integer.

    Returns:
        0 on success, 1 or a mapped exit code on failure.
    """
    target_id = getattr(args, "target", None)
    client = _connect_streaming_agent(
        command_name,
        target_id,
        require_unambiguous_default=hasattr(args, "target"),
    )
    if client is None:
        return 1

    try:
        command = build_command(args)
        response = client.send_command(command)
    finally:
        client.disconnect()

    if response.get("status") == "success":
        render_success(args, response)
        return 0

    error_code = response.get("error_code")
    message = response.get("message", error_message)
    if render_error is not None:
        render_error(args, response, message, error_code)
    else:
        OutputFormatter.error(command_name, error=message, error_code=error_code)
    if error_exit_codes and error_code:
        return error_exit_codes.get(error_code, 1)
    return 1
