"""Parser declarations for run CLI commands."""

import argparse
from typing import Any


def add_run_parser(subparsers: Any) -> None:
    run_parser = subparsers.add_parser(
        "run",
        help="Run a Python script with Peeka attached from startup",
        description=(
            "Run a Python script with Peeka attached from startup.\n"
            "Note: On extremely fast scripts that exit in under 100ms, it's possible\n"
            "the target function may execute before Peeka completes injection. This is\n"
            "extremely rare in practice."
        ),
    )
    run_parser.add_argument("script_path", help="Path to the Python script to execute")
    run_parser.add_argument(
        "--output-file",
        dest="output_file",
        type=str,
        default=None,
        help="Write peeka JSONL output to file instead of stdout",
    )
    # Note: We use nargs=argparse.REMAINDER to capture everything after script_path
    # The actual splitting at -- happens manually in cmd_run
    run_parser.add_argument(
        "remaining",
        nargs=argparse.REMAINDER,
        help="Script arguments followed by -- then the observation command",
    )
