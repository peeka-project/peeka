"""Diagnostic case CLI handlers."""

import json
import sys

from peeka.cli.command_runner import run_command
from peeka.cli.responses import response_error_message as _response_error_message
from peeka.core.output import OutputFormatter


def cmd_dx(args) -> int:
    if not args.dx_action:
        OutputFormatter.error("dx", error="Missing dx subcommand")
        return 1

    try:
        if args.dx_action == "create":
            return cmd_dx_create(args)
        elif args.dx_action == "list":
            return cmd_dx_list(args)
        elif args.dx_action == "status":
            return cmd_dx_status(args)
        elif args.dx_action == "add":
            return cmd_dx_add(args)
        elif args.dx_action == "summary":
            return cmd_dx_summary(args)
        elif args.dx_action == "export":
            return cmd_dx_export(args)
        elif args.dx_action == "close":
            return cmd_dx_close(args)
        else:
            OutputFormatter.error("dx", error=f"Unknown dx action: {args.dx_action}")
            return 1
    except Exception as e:
        OutputFormatter.error("dx", error=str(e))
        return 1


def cmd_dx_create(args) -> int:
    return run_command(
        args,
        "dx.create",
        build_command=lambda a: {
            "type": "dx",
            "action": "create",
            "target_id": a.target,
            "title": a.title,
            "client_session_id": a.client,
        },
        render_success=_render_dx_create_success,
        render_error=_render_dx_create_error,
        error_exit_codes={"DX_CASE_INVALID": 2},
    )


def cmd_dx_list(args) -> int:
    return run_command(
        args,
        "dx.list",
        build_command=lambda a: {
            "type": "dx",
            "action": "list",
            "target_id": a.target,
            "client_session_id": a.client,
            "status": a.status,
        },
        render_success=_render_dx_list_success,
        render_error=_render_dx_list_error,
    )


def cmd_dx_status(args) -> int:
    return run_command(
        args,
        "dx.status",
        build_command=lambda a: {
            "type": "dx",
            "action": "status",
            "dx_case_id": a.dx_case,
            "client_session_id": getattr(a, "client", None),
        },
        render_success=_render_dx_status_success,
        render_error=_render_dx_status_error,
        error_exit_codes={"DX_CASE_NOT_FOUND": 2},
    )


def cmd_dx_add(args) -> int:
    try:
        return run_command(
            args,
            "dx.add",
            build_command=_build_dx_add_command,
            render_success=_render_dx_add_success,
            render_error=_render_dx_add_error,
            error_exit_codes={"DX_CASE_INVALID": 2, "DX_CASE_NOT_FOUND": 2},
        )
    except json.JSONDecodeError as e:
        OutputFormatter.error("dx.add", error=str(e), error_code="DX_CASE_INVALID")
        return 2


def cmd_dx_summary(args) -> int:
    return run_command(
        args,
        "dx.summary",
        build_command=lambda a: {
            "type": "dx",
            "action": "summary",
            "dx_case_id": a.dx_case,
            "client_session_id": getattr(a, "client", None),
        },
        render_success=_render_dx_summary_success,
        render_error=_render_dx_summary_error,
        error_exit_codes={"DX_CASE_NOT_FOUND": 2},
    )


def cmd_dx_export(args) -> int:
    return run_command(
        args,
        "dx.export",
        build_command=lambda a: {
            "type": "dx",
            "action": "export",
            "dx_case_id": a.dx_case,
            "output_path": a.output_path,
            "client_session_id": getattr(a, "client", None),
        },
        render_success=_render_dx_export_success,
        render_error=_render_dx_export_error,
        error_exit_codes={"DX_CASE_NOT_FOUND": 2, "DX_EXPORT_FAILED": 2},
    )


def cmd_dx_close(args) -> int:
    return run_command(
        args,
        "dx.close",
        build_command=lambda a: {
            "type": "dx",
            "action": "close",
            "dx_case_id": a.dx_case,
            "client_session_id": getattr(a, "client", None),
        },
        render_success=_render_dx_close_success,
        render_error=_render_dx_close_error,
        error_exit_codes={"DX_CASE_NOT_FOUND": 2},
    )


def _build_dx_add_command(args):
    payload = json.loads(args.payload_json)
    return {
        "type": "dx",
        "action": "add",
        "dx_case_id": args.dx_case,
        "section_type": args.section_type,
        "title": args.title,
        "payload": payload,
        "object_ref_type": args.object_ref_type,
        "object_ref_id": args.object_ref_id,
        "client_session_id": getattr(args, "client", None),
    }


def _render_dx_create_success(args, response) -> None:
    data = response.get("data", {})
    if args.format == "json":
        OutputFormatter.success("dx.create", data=data)
    else:
        print(f"DX case created: {data.get('dx_case_id')}", file=sys.stderr)


def _render_dx_create_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("dx.create", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_dx_list_success(args, response) -> None:
    cases = response.get("data", {}).get("cases", [])
    if args.format == "json":
        for dx_case in cases:
            OutputFormatter.event("dx.discovered", data=dx_case)
    else:
        if not cases:
            print("No DX cases found.", file=sys.stderr)
        else:
            print(f"{'DX_CASE_ID':<20} {'TARGET':<20} {'STATUS':<12} {'TITLE':<30}")
            print("-" * 84)
            for dx_case in cases:
                print(
                    f"{dx_case.get('dx_case_id', '-'):<20} {dx_case.get('target_id', '-'):<20} "
                    f"{dx_case.get('status', '-'):<12} {dx_case.get('title', '-'):<30}"
                )


def _render_dx_list_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("dx.list", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_dx_status_success(args, response) -> None:
    data = response.get("data", {})
    if args.format == "json":
        OutputFormatter.success("dx.status", data=data)
    else:
        for key, value in data.items():
            print(f"{key:<20} {value}")


def _render_dx_status_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("dx.status", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_dx_add_success(args, response) -> None:
    data = response.get("data", {})
    if args.format == "json":
        OutputFormatter.success("dx.add", data=data)
    else:
        print(f"Added section to DX case {data.get('dx_case_id')}", file=sys.stderr)


def _render_dx_add_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("dx.add", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_dx_summary_success(args, response) -> None:
    data = response.get("data", {})
    if args.format == "json":
        OutputFormatter.success("dx.summary", data=data)
    else:
        print(data.get("text_summary", ""))


def _render_dx_summary_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("dx.summary", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_dx_export_success(args, response) -> None:
    data = response.get("data", {})
    if args.format == "json":
        OutputFormatter.success("dx.export", data=data)
    else:
        print(f"Exported DX case to {data.get('output_path')}", file=sys.stderr)


def _render_dx_export_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("dx.export", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_dx_close_success(args, response) -> None:
    data = response.get("data", {})
    if args.format == "json":
        OutputFormatter.success("dx.close", data=data)
    else:
        print(f"Closed DX case {data.get('dx_case_id')}", file=sys.stderr)


def _render_dx_close_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("dx.close", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
