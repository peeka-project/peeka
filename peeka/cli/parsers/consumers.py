"""Parser declarations for consumers CLI commands."""

from typing import Any


def add_consumer_parsers(subparsers: Any) -> None:
    consumer_parser = subparsers.add_parser("consumer", help="Manage result consumers")
    consumer_subparsers = consumer_parser.add_subparsers(
        dest="consumer_action", help="Consumer subcommands"
    )

    consumer_create_parser = consumer_subparsers.add_parser(
        "create", help="Create a result consumer"
    )
    consumer_create_parser.add_argument(
        "--target", type=str, required=True, help="Target ID"
    )
    consumer_create_parser.add_argument(
        "--source",
        type=str,
        required=True,
        choices=["cli", "tui", "mcp", "api", "internal"],
        help="Source of the consumer request",
    )
    consumer_create_parser.add_argument(
        "--scope-type",
        type=str,
        required=True,
        choices=["job", "probe", "target"],
        help="Scope type bound to this consumer",
    )
    consumer_create_parser.add_argument(
        "--scope-id",
        type=str,
        required=True,
        help="Scope identifier (job/probe/target id)",
    )
    consumer_create_parser.add_argument(
        "--client",
        type=str,
        default=None,
        help="Optional owning client session ID",
    )
    consumer_create_parser.add_argument(
        "--max-buffer-size",
        type=int,
        default=1000,
        help="Maximum buffered records",
    )
    consumer_create_parser.add_argument(
        "--backpressure-policy",
        type=str,
        choices=["drop_oldest", "drop_newest", "fail"],
        default="drop_oldest",
        help="Backpressure policy when the consumer buffer is full",
    )
    consumer_create_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    consumer_list_parser = consumer_subparsers.add_parser(
        "list", help="List result consumers"
    )
    consumer_list_parser.add_argument(
        "--target", type=str, default=None, help="Filter by target ID"
    )
    consumer_list_parser.add_argument(
        "--client", type=str, default=None, help="Filter by client session ID"
    )
    consumer_list_parser.add_argument(
        "--scope-type",
        type=str,
        choices=["job", "probe", "target"],
        default=None,
        help="Filter by scope type",
    )
    consumer_list_parser.add_argument(
        "--scope-id", type=str, default=None, help="Filter by scope ID"
    )
    consumer_list_parser.add_argument(
        "--status", type=str, default=None, help="Filter by consumer status"
    )
    consumer_list_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    consumer_status_parser = consumer_subparsers.add_parser(
        "status", help="Get status of a result consumer"
    )
    consumer_status_parser.add_argument(
        "--consumer", type=str, required=True, help="Consumer ID"
    )
    consumer_status_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Target ID that owns the consumer",
    )
    consumer_status_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    consumer_status_parser.add_argument(
        "--client",
        type=str,
        default=None,
        help="Optional owning client session ID for access control",
    )

    consumer_drain_parser = consumer_subparsers.add_parser(
        "drain", help="Drain buffered records from a consumer"
    )
    consumer_drain_parser.add_argument(
        "--consumer", type=str, required=True, help="Consumer ID"
    )
    consumer_drain_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Target ID that owns the consumer",
    )
    consumer_drain_parser.add_argument(
        "--limit", type=int, default=100, help="Maximum records to return"
    )
    consumer_drain_parser.add_argument(
        "--after-sequence",
        type=int,
        default=None,
        help="Return records with sequence greater than this value",
    )
    consumer_drain_parser.add_argument(
        "--timeout-ms",
        type=int,
        default=0,
        help="Wait for new records for up to this many milliseconds",
    )
    consumer_drain_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    consumer_drain_parser.add_argument(
        "--client",
        type=str,
        default=None,
        help="Optional owning client session ID for access control",
    )

    consumer_close_parser = consumer_subparsers.add_parser(
        "close", help="Close a result consumer"
    )
    consumer_close_parser.add_argument(
        "--consumer", type=str, required=True, help="Consumer ID"
    )
    consumer_close_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Target ID that owns the consumer",
    )
    consumer_close_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    consumer_close_parser.add_argument(
        "--client",
        type=str,
        default=None,
        help="Optional owning client session ID for access control",
    )

    consumer_cleanup_parser = consumer_subparsers.add_parser(
        "cleanup", help="Cleanup closed/failed result consumers"
    )
    consumer_cleanup_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Clean up consumers for a specific target",
    )
    consumer_cleanup_parser.add_argument(
        "--all", action="store_true", help="Remove active consumers too"
    )
    consumer_cleanup_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    consumer_cleanup_parser.add_argument(
        "--client",
        type=str,
        default=None,
        help="Optional owning client session ID for access control",
    )
