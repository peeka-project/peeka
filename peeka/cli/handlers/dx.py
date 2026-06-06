"""Diagnostic case CLI handlers."""

import json
import sys
from typing import Optional

from peeka.cli.context import _connect_streaming_agent
from peeka.cli.responses import response_error_message as _response_error_message
from peeka.core.client import StreamingAgentClient
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


def _connect_dx_client(
    command_name: str,
    target_id: Optional[str] = None,
) -> Optional[StreamingAgentClient]:
    return _connect_streaming_agent(command_name, target_id)


def cmd_dx_create(args) -> int:
    streaming_client = _connect_dx_client("dx.create", args.target)
    if streaming_client is None:
        return 1

    response = streaming_client.send_command(
        {
            "type": "dx",
            "action": "create",
            "target_id": args.target,
            "title": args.title,
            "client_session_id": args.client,
        }
    )
    streaming_client.disconnect()
    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("dx.create", data=data)
        else:
            print(f"DX case created: {data.get('dx_case_id')}", file=sys.stderr)
        return 0
    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "DX case create failed")
    if args.format == "json":
        OutputFormatter.error("dx.create", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return 2 if error_code == "DX_CASE_INVALID" else 1


def cmd_dx_list(args) -> int:
    streaming_client = _connect_dx_client("dx.list", args.target)
    if streaming_client is None:
        return 1

    response = streaming_client.send_command(
        {
            "type": "dx",
            "action": "list",
            "target_id": args.target,
            "client_session_id": args.client,
            "status": args.status,
        }
    )
    streaming_client.disconnect()
    if response.get("status") == "success":
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
        return 0
    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "DX case list failed")
    if args.format == "json":
        OutputFormatter.error("dx.list", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return 1


def cmd_dx_status(args) -> int:
    streaming_client = _connect_dx_client("dx.status")
    if streaming_client is None:
        return 1

    response = streaming_client.send_command(
        {
            "type": "dx",
            "action": "status",
            "dx_case_id": args.dx_case,
            "client_session_id": getattr(args, "client", None),
        }
    )
    streaming_client.disconnect()
    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("dx.status", data=data)
        else:
            for key, value in data.items():
                print(f"{key:<20} {value}")
        return 0
    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "DX case status failed")
    if args.format == "json":
        OutputFormatter.error("dx.status", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return 2 if error_code == "DX_CASE_NOT_FOUND" else 1


def cmd_dx_add(args) -> int:
    streaming_client = _connect_dx_client("dx.add")
    if streaming_client is None:
        return 1

    try:
        payload = json.loads(args.payload_json)
    except json.JSONDecodeError as e:
        OutputFormatter.error("dx.add", error=str(e), error_code="DX_CASE_INVALID")
        streaming_client.disconnect()
        return 2

    response = streaming_client.send_command(
        {
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
    )
    streaming_client.disconnect()
    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("dx.add", data=data)
        else:
            print(f"Added section to DX case {data.get('dx_case_id')}", file=sys.stderr)
        return 0
    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "DX case add failed")
    if args.format == "json":
        OutputFormatter.error("dx.add", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return 2 if error_code in ("DX_CASE_INVALID", "DX_CASE_NOT_FOUND") else 1


def cmd_dx_summary(args) -> int:
    streaming_client = _connect_dx_client("dx.summary")
    if streaming_client is None:
        return 1

    response = streaming_client.send_command(
        {
            "type": "dx",
            "action": "summary",
            "dx_case_id": args.dx_case,
            "client_session_id": getattr(args, "client", None),
        }
    )
    streaming_client.disconnect()
    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("dx.summary", data=data)
        else:
            print(data.get("text_summary", ""))
        return 0
    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "DX case summary failed")
    if args.format == "json":
        OutputFormatter.error("dx.summary", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return 2 if error_code == "DX_CASE_NOT_FOUND" else 1


def cmd_dx_export(args) -> int:
    streaming_client = _connect_dx_client("dx.export")
    if streaming_client is None:
        return 1

    response = streaming_client.send_command(
        {
            "type": "dx",
            "action": "export",
            "dx_case_id": args.dx_case,
            "output_path": args.output_path,
            "client_session_id": getattr(args, "client", None),
        }
    )
    streaming_client.disconnect()
    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("dx.export", data=data)
        else:
            print(f"Exported DX case to {data.get('output_path')}", file=sys.stderr)
        return 0
    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "DX case export failed")
    if args.format == "json":
        OutputFormatter.error("dx.export", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return 2 if error_code in ("DX_CASE_NOT_FOUND", "DX_EXPORT_FAILED") else 1


def cmd_dx_close(args) -> int:
    streaming_client = _connect_dx_client("dx.close")
    if streaming_client is None:
        return 1

    response = streaming_client.send_command(
        {
            "type": "dx",
            "action": "close",
            "dx_case_id": args.dx_case,
            "client_session_id": getattr(args, "client", None),
        }
    )
    streaming_client.disconnect()
    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("dx.close", data=data)
        else:
            print(f"Closed DX case {data.get('dx_case_id')}", file=sys.stderr)
        return 0
    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "DX case close failed")
    if args.format == "json":
        OutputFormatter.error("dx.close", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return 2 if error_code == "DX_CASE_NOT_FOUND" else 1
