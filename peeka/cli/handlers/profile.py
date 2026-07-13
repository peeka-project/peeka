"""Profile CLI handlers."""

import argparse
from pathlib import Path
from typing import Any, Dict, Protocol

from peeka.core.output import OutputFormatter


class _ProfileClient(Protocol):
    def execute(self, namespace: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        ...

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        ...


def handle_profile(args: argparse.Namespace, client: _ProfileClient) -> int:
    """Dispatch a profile subcommand.

    Args:
        args: Parsed argparse namespace.
        client: Agent client compatible with ``execute`` or ``send_command``.

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
    return handler(args, client)


def _send_profile_command(client: _ProfileClient, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Send a profile command using the available client API."""
    execute = getattr(client, "execute", None)
    if callable(execute):
        response = execute("profile", payload)
        if isinstance(response, dict):
            return response
        return {"status": "error", "error": "Invalid response from client"}

    send_command = getattr(client, "send_command", None)
    if callable(send_command):
        command = dict(payload)
        command["type"] = "profile"
        response = send_command(command)
        if isinstance(response, dict):
            return response
        return {"status": "error", "error": "Invalid response from client"}

    raise AttributeError("client must provide execute() or send_command()")


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


def _handle_start(args: argparse.Namespace, client: _ProfileClient) -> int:
    payload = {
        "action": "start",
        "backend": args.backend,
        "interval_ms": max(1, int(round(args.interval * 1000.0))),
        "duration_ms": None if args.duration is None else max(1, int(round(args.duration * 1000.0))),
        "max_samples": args.max_samples,
    }
    response = _send_profile_command(client, payload)
    return _emit_profile_response("profile.start", response)


def _handle_stop(args: argparse.Namespace, client: _ProfileClient) -> int:
    response = _send_profile_command(
        client,
        {"action": "stop", "profile_id": args.profile_id},
    )
    return _emit_profile_response("profile.stop", response)


def _handle_snapshot(args: argparse.Namespace, client: _ProfileClient) -> int:
    response = _send_profile_command(
        client,
        {"action": "snapshot", "profile_id": args.profile_id, "format": args.format},
    )
    return _emit_profile_response("profile.snapshot", response)


def _handle_list(args: argparse.Namespace, client: _ProfileClient) -> int:  # noqa: ARG001
    response = _send_profile_command(client, {"action": "list"})
    return _emit_profile_response("profile.list", response)


def _handle_cleanup(args: argparse.Namespace, client: _ProfileClient) -> int:
    response = _send_profile_command(
        client,
        {
            "action": "cleanup",
            "older_than_secs": args.older_than,
            "max_sessions": args.max_sessions,
        },
    )
    return _emit_profile_response("profile.cleanup", response)


def _handle_export(args: argparse.Namespace, client: _ProfileClient) -> int:
    response = _send_profile_command(
        client,
        {
            "action": "export",
            "profile_id": args.profile_id,
            "format": args.format,
        },
    )
    if response.get("status") != "success":
        return _emit_profile_response("profile.export", response)

    content = response.get("content")
    if args.output and content is not None:
        Path(args.output).write_text(str(content), encoding="utf-8")
        response = dict(response)
        response["output"] = args.output
    return _emit_profile_response("profile.export", response)
