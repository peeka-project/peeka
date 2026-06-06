"""Client session CLI handlers."""

import sys

from peeka.cli.context import _connect_streaming_agent
from peeka.core.output import OutputFormatter


def cmd_client(args) -> int:
    if not args.client_action:
        OutputFormatter.error("client", error="Missing client subcommand")
        return 1

    try:
        if args.client_action == "create":
            return cmd_client_create(args)
        elif args.client_action == "list":
            return cmd_client_list(args)
        elif args.client_action == "status":
            return cmd_client_status(args)
        elif args.client_action == "close":
            return cmd_client_close(args)
        else:
            OutputFormatter.error(
                "client", error=f"Unknown client action: {args.client_action}"
            )
            return 1
    except Exception as e:
        OutputFormatter.error("client", error=str(e))
        return 1


def cmd_client_create(args) -> int:
    streaming_client = _connect_streaming_agent("client.create", args.target)
    if streaming_client is None:
        return 1

    command = {
        "type": "client",
        "action": "create",
        "target_id": args.target,
        "source": args.source,
        "user_id": args.user,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("client.create", data=data)
        else:
            print(
                f"Client session created: {data.get('client_session_id')}",
                file=sys.stderr,
            )
            print(f"Target: {data.get('target_id')}", file=sys.stderr)
            print(f"Source: {data.get('source')}", file=sys.stderr)
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Client create failed")
        if args.format == "json":
            OutputFormatter.error("client.create", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "UNSUPPORTED_CAPABILITY" else 1


def cmd_client_list(args) -> int:
    streaming_client = _connect_streaming_agent("client.list", args.target)
    if streaming_client is None:
        return 1

    command = {
        "type": "client",
        "action": "list",
        "target_id": args.target,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        clients = data.get("clients", [])

        if args.format == "json":
            for client in clients:
                OutputFormatter.event("client.discovered", data=client)
        else:
            if not clients:
                print("No client sessions found.", file=sys.stderr)
            else:
                print(
                    f"{'Client ID':<20} {'Target ID':<20} {'Source':<10} {'Status':<15} {'User':<20}"
                )
                print("-" * 85)
                for client in clients:
                    user_id = client.get("user_id") or "-"
                    print(
                        f"{client.get('client_session_id'):<20} "
                        f"{client.get('target_id'):<20} "
                        f"{client.get('source'):<10} "
                        f"{client.get('input_status'):<15} "
                        f"{user_id:<20}"
                    )
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Client list failed")
        if args.format == "json":
            OutputFormatter.error("client.list", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 1


def cmd_client_status(args) -> int:
    streaming_client = _connect_streaming_agent("client.status")
    if streaming_client is None:
        return 1

    command = {
        "type": "client",
        "action": "status",
        "client_session_id": args.client,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("client.status", data=data)
        else:
            print(f"Client Session ID: {data.get('client_session_id')}")
            print(f"Target ID: {data.get('target_id')}")
            print(f"Source: {data.get('source')}")
            print(f"Input Status: {data.get('input_status')}")
            print(f"User ID: {data.get('user_id') or '-'}")
            print(f"Foreground Job ID: {data.get('foreground_job_id') or '-'}")
            print(f"Created At: {data.get('created_at')}")
            print(f"Last Access At: {data.get('last_access_at')}")
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Client status query failed")
        if args.format == "json":
            OutputFormatter.error("client.status", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "CLIENT_NOT_FOUND" else 1


def cmd_client_close(args) -> int:
    streaming_client = _connect_streaming_agent("client.close")
    if streaming_client is None:
        return 1

    command = {
        "type": "client",
        "action": "close",
        "client_session_id": args.client,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("client.close", data=data)
        else:
            print(f"Client session closed: {args.client}", file=sys.stderr)
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Client close failed")
        if args.format == "json":
            OutputFormatter.error("client.close", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "CLIENT_NOT_FOUND" else 1
