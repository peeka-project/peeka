"""Parser declarations for targets CLI commands."""

from typing import Any


def add_target_parsers(subparsers: Any) -> None:
    target_parser = subparsers.add_parser("target", help="Manage Peeka target agents")
    target_subparsers = target_parser.add_subparsers(
        dest="target_action", help="Target subcommands"
    )

    target_list_parser = target_subparsers.add_parser(
        "list", help="List all discovered target agents"
    )
    target_list_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    target_current_parser = target_subparsers.add_parser(
        "current",
        help="Get the current target (exit 0 if exactly 1 alive, exit 1 if 0, exit 2 if >1)",
    )
    target_current_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    target_status_parser = target_subparsers.add_parser(
        "status", help="Get status of a specific target"
    )
    target_status_parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Target ID",
    )
    target_status_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    target_inspect_parser = target_subparsers.add_parser(
        "inspect", help="Inspect a specific target with full details"
    )
    target_inspect_parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Target ID",
    )
    target_inspect_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    target_cleanup_parser = target_subparsers.add_parser(
        "cleanup", help="Clean up stale target marker files"
    )
    target_cleanup_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Clean up a specific target by ID (default: clean all stale targets)",
    )
    target_cleanup_parser.add_argument(
        "--stale-only",
        action="store_true",
        help="Only clean up stale targets (default behavior)",
    )
    target_cleanup_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be cleaned without actually cleaning",
    )
    target_cleanup_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    target_detach_parser = target_subparsers.add_parser(
        "detach", help="Detach from a specific target"
    )
    target_detach_parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Target ID",
    )
    target_detach_parser.add_argument(
        "--force",
        action="store_true",
        help="Force detach even if target is alive",
    )
    target_detach_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    session_parser = subparsers.add_parser(
        "session",
        help="[DEPRECATED] Alias to 'target' command; use 'peeka-cli target' instead",
    )
    session_subparsers = session_parser.add_subparsers(
        dest="session_action", help="Session subcommands"
    )

    session_list_parser = session_subparsers.add_parser(
        "list", help="[DEPRECATED] List all discovered session agents"
    )
    session_list_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    session_status_parser = session_subparsers.add_parser(
        "status", help="[DEPRECATED] Get status of a specific session"
    )
    session_status_parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Target ID",
    )
    session_status_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    session_detach_parser = session_subparsers.add_parser(
        "detach", help="[DEPRECATED] Detach from a specific session"
    )
    session_detach_parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Target ID",
    )
    session_detach_parser.add_argument(
        "--force",
        action="store_true",
        help="Force detach even if target is alive",
    )
    session_detach_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
