"""Parser declarations for attach CLI commands."""

from typing import Any


def add_attach_parsers(subparsers: Any) -> None:
    attach_parser = subparsers.add_parser(
        "attach", help="Attach to a running Python process"
    )
    attach_parser.add_argument("pid", type=int, help="Process ID to attach to")

    _ = subparsers.add_parser("detach", help="Detach from the target process")
