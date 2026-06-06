"""Parser declarations for dx CLI commands."""

from typing import Any


def add_dx_parsers(subparsers: Any) -> None:
    dx_parser = subparsers.add_parser("dx", help="Manage diagnostic case bundles")
    dx_subparsers = dx_parser.add_subparsers(
        dest="dx_action", help="DX case subcommands"
    )

    dx_create_parser = dx_subparsers.add_parser("create", help="Create a DX case")
    dx_create_parser.add_argument("--target", type=str, required=True, help="Target ID")
    dx_create_parser.add_argument(
        "--title", type=str, required=True, help="DX case title"
    )
    dx_create_parser.add_argument(
        "--client", type=str, default=None, help="Optional client session ID"
    )
    dx_create_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    dx_list_parser = dx_subparsers.add_parser("list", help="List DX cases")
    dx_list_parser.add_argument(
        "--target", type=str, default=None, help="Filter by target ID"
    )
    dx_list_parser.add_argument(
        "--client", type=str, default=None, help="Filter by client session ID"
    )
    dx_list_parser.add_argument(
        "--status", type=str, default=None, help="Filter by DX case status"
    )
    dx_list_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    dx_status_parser = dx_subparsers.add_parser("status", help="Get DX case status")
    dx_status_parser.add_argument(
        "--dx-case", type=str, required=True, help="DX case ID"
    )
    dx_status_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    dx_status_parser.add_argument(
        "--client",
        type=str,
        default=None,
        help="Optional owning client session ID for access control",
    )

    dx_add_parser = dx_subparsers.add_parser("add", help="Add a section to a DX case")
    dx_add_parser.add_argument("--dx-case", type=str, required=True, help="DX case ID")
    dx_add_parser.add_argument(
        "--section-type",
        type=str,
        required=True,
        choices=[
            "target",
            "client",
            "job",
            "probe",
            "consumer",
            "note",
            "error",
            "summary",
        ],
        help="Section type",
    )
    dx_add_parser.add_argument("--title", type=str, required=True, help="Section title")
    dx_add_parser.add_argument(
        "--payload-json",
        type=str,
        default="{}",
        help="JSON payload for the section",
    )
    dx_add_parser.add_argument(
        "--object-ref-type",
        type=str,
        default=None,
        help="Optional object ref collection name",
    )
    dx_add_parser.add_argument(
        "--object-ref-id",
        type=str,
        default=None,
        help="Optional object ref identifier",
    )
    dx_add_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    dx_add_parser.add_argument(
        "--client",
        type=str,
        default=None,
        help="Optional owning client session ID for access control",
    )

    dx_summary_parser = dx_subparsers.add_parser(
        "summary", help="Build DX case summary"
    )
    dx_summary_parser.add_argument(
        "--dx-case", type=str, required=True, help="DX case ID"
    )
    dx_summary_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    dx_summary_parser.add_argument(
        "--client",
        type=str,
        default=None,
        help="Optional owning client session ID for access control",
    )

    dx_export_parser = dx_subparsers.add_parser("export", help="Export a DX case")
    dx_export_parser.add_argument(
        "--dx-case", type=str, required=True, help="DX case ID"
    )
    dx_export_parser.add_argument(
        "--output-path", type=str, default=None, help="Optional export destination path"
    )
    dx_export_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    dx_export_parser.add_argument(
        "--client",
        type=str,
        default=None,
        help="Optional owning client session ID for access control",
    )

    dx_close_parser = dx_subparsers.add_parser("close", help="Close a DX case")
    dx_close_parser.add_argument(
        "--dx-case", type=str, required=True, help="DX case ID"
    )
    dx_close_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )
    dx_close_parser.add_argument(
        "--client",
        type=str,
        default=None,
        help="Optional owning client session ID for access control",
    )
