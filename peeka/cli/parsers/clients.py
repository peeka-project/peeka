"""Parser declarations for clients CLI commands."""

from typing import Any


def add_client_parsers(subparsers: Any) -> None:
    client_parser = subparsers.add_parser(
        "client", help="Manage client sessions for target agents"
    )
    client_subparsers = client_parser.add_subparsers(
        dest="client_action", help="Client subcommands"
    )

    client_create_parser = client_subparsers.add_parser(
        "create", help="Create a client session"
    )
    client_create_parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Target ID for the client session",
    )
    client_create_parser.add_argument(
        "--source",
        type=str,
        required=True,
        choices=["cli", "tui", "mcp", "api", "internal"],
        help="Source of the client request",
    )
    client_create_parser.add_argument(
        "--user",
        type=str,
        default=None,
        help="Optional user ID associated with the client",
    )
    client_create_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    client_list_parser = client_subparsers.add_parser(
        "list", help="List all client sessions"
    )
    client_list_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Optional target ID filter",
    )
    client_list_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    client_status_parser = client_subparsers.add_parser(
        "status", help="Get status of a specific client session"
    )
    client_status_parser.add_argument(
        "--client",
        type=str,
        required=True,
        help="Client session ID",
    )
    client_status_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    client_close_parser = client_subparsers.add_parser(
        "close", help="Close a client session"
    )
    client_close_parser.add_argument(
        "--client",
        type=str,
        required=True,
        help="Client session ID",
    )
    client_close_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
