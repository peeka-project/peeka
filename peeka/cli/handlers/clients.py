"""Client session CLI handlers."""

import sys

from peeka.cli.command_runner import run_command
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
    return run_command(
        args,
        "client.create",
        build_command=lambda a: {
            "type": "client",
            "action": "create",
            "target_id": a.target,
            "source": a.source,
            "user_id": a.user,
        },
        render_success=_render_client_create_success,
        error_exit_codes={"UNSUPPORTED_CAPABILITY": 2},
    )


def cmd_client_list(args) -> int:
    return run_command(
        args,
        "client.list",
        build_command=lambda a: {
            "type": "client",
            "action": "list",
            "target_id": a.target,
        },
        render_success=_render_client_list_success,
    )


def cmd_client_status(args) -> int:
    return run_command(
        args,
        "client.status",
        build_command=lambda a: {
            "type": "client",
            "action": "status",
            "client_session_id": a.client,
        },
        render_success=_render_client_status_success,
        error_exit_codes={"CLIENT_NOT_FOUND": 2},
    )


def cmd_client_close(args) -> int:
    return run_command(
        args,
        "client.close",
        build_command=lambda a: {
            "type": "client",
            "action": "close",
            "client_session_id": a.client,
        },
        render_success=_render_client_close_success,
        error_exit_codes={"CLIENT_NOT_FOUND": 2},
    )


def _render_client_create_success(args, response) -> None:
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


def _render_client_list_success(args, response) -> None:
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


def _render_client_status_success(args, response) -> None:
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


def _render_client_close_success(args, response) -> None:
    data = response.get("data", {})
    if args.format == "json":
        OutputFormatter.success("client.close", data=data)
    else:
        print(f"Client session closed: {args.client}", file=sys.stderr)
