"""Parser declarations for probes CLI commands."""

from typing import Any

from peeka.cli.parsers.types import _parse_duration


def add_probe_parsers(subparsers: Any) -> None:
    probe_parser = subparsers.add_parser("probe", help="Manage probe runs")
    probe_subparsers = probe_parser.add_subparsers(
        dest="probe_action", help="Probe subcommands"
    )

    probe_list_parser = probe_subparsers.add_parser("list", help="List probe runs")
    probe_list_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Filter by target ID",
    )
    probe_list_parser.add_argument(
        "--type",
        dest="probe_type",
        type=str,
        default=None,
        help="Filter by probe type (watch, trace, etc.)",
    )
    probe_list_parser.add_argument(
        "--status",
        type=str,
        default=None,
        help="Filter by probe status",
    )
    probe_list_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    probe_status_parser = probe_subparsers.add_parser(
        "status", help="Get status of a specific probe"
    )
    probe_status_parser.add_argument(
        "--probe",
        type=str,
        required=True,
        help="Probe ID",
    )
    probe_status_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Target ID that owns the probe",
    )
    probe_status_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    probe_inspect_parser = probe_subparsers.add_parser(
        "inspect", help="Inspect a specific probe with events"
    )
    probe_inspect_parser.add_argument(
        "--probe",
        type=str,
        required=True,
        help="Probe ID",
    )
    probe_inspect_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Target ID that owns the probe",
    )
    probe_inspect_parser.add_argument(
        "--events",
        type=int,
        default=100,
        help="Number of recent events to return (default: 100)",
    )
    probe_inspect_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    probe_stop_parser = probe_subparsers.add_parser("stop", help="Stop a running probe")
    probe_stop_parser.add_argument(
        "--probe",
        type=str,
        required=True,
        help="Probe ID",
    )
    probe_stop_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Target ID that owns the probe",
    )
    probe_stop_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    probe_cleanup_parser = probe_subparsers.add_parser(
        "cleanup", help="Clean up old probes"
    )
    probe_cleanup_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Clean up probes for a specific target",
    )
    probe_cleanup_parser.add_argument(
        "--all",
        action="store_true",
        help="Also clean up created/paused probes (never active)",
    )
    probe_cleanup_parser.add_argument(
        "--older-than",
        type=_parse_duration,
        default=600,
        help="Clean up probes older than duration (default: 10m)",
    )
    probe_cleanup_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
