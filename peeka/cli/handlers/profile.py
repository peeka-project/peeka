"""Profile CLI handlers."""

import argparse
from pathlib import Path
from typing import Any, Callable, Dict

from peeka.cli.command_runner import run_command
from peeka.core.output import OutputFormatter


def handle_profile(args: argparse.Namespace) -> int:
    """Dispatch a profile subcommand.

    Args:
        args: Parsed argparse namespace.

    Returns:
        Process exit code.
    """
    subcommand = getattr(args, "profile_subcommand", None)
    if not subcommand:
        OutputFormatter.error("profile", error="Missing profile subcommand")
        return 1

    handlers = {
        "start": _handle_start,
        "stop": _handle_stop,
        "snapshot": _handle_snapshot,
        "list": _handle_list,
        "cleanup": _handle_cleanup,
        "export": _handle_export,
    }
    handler = handlers.get(str(subcommand))
    if handler is None:
        OutputFormatter.error("profile", error=f"Unknown profile subcommand: {subcommand}")
        return 1
    return handler(args)


def _result_payload(response: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict(response)
    payload.pop("status", None)
    return payload


def _emit_profile_response(command: str, response: Dict[str, Any]) -> int:
    if response.get("status") == "success":
        OutputFormatter.result(command, data=_result_payload(response))
        return 0
    OutputFormatter.error(command, error=response.get("error", "Profile command failed"))
    return 1


def _render_profile_success(args: argparse.Namespace, response: Dict[str, Any]) -> None:
    command = f"profile.{args.profile_subcommand}"
    content = response.get("content")
    if getattr(args, "output", None) and content is not None:
        Path(args.output).write_text(str(content), encoding="utf-8")
        response = dict(response)
        response["output"] = args.output
    OutputFormatter.result(command, data=_result_payload(response))


def _render_profile_error(
    args: argparse.Namespace,
    response: Dict[str, Any],
    message: str,
    error_code: Any,
) -> None:
    command = f"profile.{args.profile_subcommand}"
    error = response.get("error", message)
    OutputFormatter.error(command, error=error, error_code=error_code)


def _run_profile_command(
    args: argparse.Namespace,
    command_name: str,
    build_payload: Callable[[argparse.Namespace], Dict[str, Any]],
) -> int:
    return run_command(
        args,
        command_name,
        build_command=lambda a: {"type": "profile", **build_payload(a)},
        render_success=_render_profile_success,
        render_error=_render_profile_error,
        error_message="Profile command failed",
    )


def _handle_start(args: argparse.Namespace) -> int:
    return _run_profile_command(
        args,
        "profile.start",
        lambda a: {
            "action": "start",
            "backend": a.backend,
            "interval_ms": max(1, int(round(a.interval * 1000.0))),
            "duration_ms": None if a.duration is None else max(1, int(round(a.duration * 1000.0))),
            "max_samples": a.max_samples,
        },
    )


def _handle_stop(args: argparse.Namespace) -> int:
    return _run_profile_command(
        args,
        "profile.stop",
        lambda a: {"action": "stop", "profile_id": a.profile_id},
    )


def _handle_snapshot(args: argparse.Namespace) -> int:
    return _run_profile_command(
        args,
        "profile.snapshot",
        lambda a: {"action": "snapshot", "profile_id": a.profile_id, "format": a.format},
    )


def _handle_list(args: argparse.Namespace) -> int:
    return _run_profile_command(
        args,
        "profile.list",
        lambda a: {"action": "list"},
    )


def _handle_cleanup(args: argparse.Namespace) -> int:
    return _run_profile_command(
        args,
        "profile.cleanup",
        lambda a: {
            "action": "cleanup",
            "older_than_secs": a.older_than,
            "max_sessions": a.max_sessions,
        },
    )


def _handle_export(args: argparse.Namespace) -> int:
    return _run_profile_command(
        args,
        "profile.export",
        lambda a: {
            "action": "export",
            "profile_id": a.profile_id,
            "format": a.format,
        },
    )
