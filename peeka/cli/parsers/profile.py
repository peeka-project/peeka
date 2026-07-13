"""Parser declarations for profile CLI commands."""

from typing import Any


def add_profile_parser(subparsers: Any) -> None:
    """Register the ``profile`` command and its subcommands.

    Args:
        subparsers: Top-level argparse subparsers collection.
    """
    profile_parser = subparsers.add_parser(
        "profile", help="Manage profiling sessions (must attach first)"
    )
    profile_subparsers = profile_parser.add_subparsers(dest="profile_subcommand")

    start_parser = profile_subparsers.add_parser(
        "start", help="Start a profiling session"
    )
    start_parser.add_argument(
        "--backend",
        type=str,
        default="sampling",
        help="Profiler backend (default: sampling)",
    )
    start_parser.add_argument(
        "--interval",
        type=float,
        default=0.01,
        help="Sampling interval in seconds (default: 0.01)",
    )
    start_parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Optional profiling duration in seconds",
    )
    start_parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="Optional maximum sample count",
    )

    stop_parser = profile_subparsers.add_parser(
        "stop", help="Stop a profiling session"
    )
    stop_parser.add_argument("--profile-id", dest="profile_id", required=True)

    snapshot_parser = profile_subparsers.add_parser(
        "snapshot", help="Capture a profile snapshot"
    )
    snapshot_parser.add_argument("--profile-id", dest="profile_id", required=True)
    snapshot_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "text", "speedscope", "perfetto"],
        default="json",
        help="Snapshot output format (default: json)",
    )

    profile_subparsers.add_parser("list", help="List profile sessions")

    cleanup_parser = profile_subparsers.add_parser(
        "cleanup", help="Remove old profile sessions"
    )
    cleanup_parser.add_argument(
        "--older-than",
        dest="older_than",
        type=float,
        default=None,
        help="Remove sessions older than N seconds",
    )
    cleanup_parser.add_argument(
        "--max-sessions",
        dest="max_sessions",
        type=int,
        default=None,
        help="Keep at most N sessions",
    )

    export_parser = profile_subparsers.add_parser(
        "export", help="Export a profile session"
    )
    export_parser.add_argument("--profile-id", dest="profile_id", required=True)
    export_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "text", "speedscope", "perfetto"],
        default="json",
        help="Export format (default: json)",
    )
    export_parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Optional output file path",
    )
