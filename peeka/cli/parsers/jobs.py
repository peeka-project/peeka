"""Parser declarations for jobs CLI commands."""

from typing import Any

from peeka.cli.context import _parse_duration


def add_job_parsers(subparsers: Any) -> None:
    job_parser = subparsers.add_parser("job", help="Manage command jobs")
    job_subparsers = job_parser.add_subparsers(
        dest="job_action", help="Job subcommands"
    )

    job_list_parser = job_subparsers.add_parser("list", help="List command jobs")
    job_list_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Filter by target ID",
    )
    job_list_parser.add_argument(
        "--client",
        type=str,
        default=None,
        help="Filter by client session ID",
    )
    job_list_parser.add_argument(
        "--status",
        type=str,
        default=None,
        help="Filter by job status",
    )
    job_list_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    job_status_parser = job_subparsers.add_parser(
        "status", help="Get status of a specific job"
    )
    job_status_parser.add_argument(
        "--job",
        type=str,
        required=True,
        help="Job ID",
    )
    job_status_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    job_inspect_parser = job_subparsers.add_parser(
        "inspect", help="Inspect a specific job with full details"
    )
    job_inspect_parser.add_argument(
        "--job",
        type=str,
        required=True,
        help="Job ID",
    )
    job_inspect_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    job_interrupt_parser = job_subparsers.add_parser(
        "interrupt", help="Interrupt a running job"
    )
    job_interrupt_parser.add_argument(
        "--job",
        type=str,
        required=True,
        help="Job ID",
    )
    job_interrupt_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    job_cleanup_parser = job_subparsers.add_parser(
        "cleanup", help="Clean up completed jobs"
    )
    job_cleanup_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Clean up jobs for a specific target",
    )
    job_cleanup_parser.add_argument(
        "--completed",
        action="store_true",
        help="Only clean up completed jobs",
    )
    job_cleanup_parser.add_argument(
        "--older-than",
        type=_parse_duration,
        default=600,
        help="Clean up jobs older than duration (default: 10m)",
    )
    job_cleanup_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    job_pull_parser = job_subparsers.add_parser(
        "pull", help="[STUB] Pull job results (Phase 5)"
    )
    job_pull_parser.add_argument(
        "--job",
        type=str,
        required=True,
        help="Job ID",
    )
    job_pull_parser.add_argument(
        "--consumer",
        type=str,
        required=True,
        help="Consumer name",
    )
    job_pull_parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
