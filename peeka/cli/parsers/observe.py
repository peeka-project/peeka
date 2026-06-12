"""Parser declarations for observe CLI commands."""

import argparse
from typing import Any

from peeka.cli.parsers.runtime import build_top_run_parser


def _add_watch_arguments(
    parser: argparse.ArgumentParser,
    include_pattern: bool = True,
    include_client: bool = True,
) -> None:
    if include_pattern:
        parser.add_argument(
            "pattern", help='Function pattern to watch (e.g., "mymodule.MyClass.method")'
        )
    parser.add_argument(
        "-x", "--depth", type=int, default=2, help="Output depth for nested objects"
    )
    parser.add_argument(
        "-n",
        "--times",
        type=int,
        default=-1,
        help="Print N observations then stop (-1 for infinite)",
    )
    parser.add_argument(
        "-b", "--before", action="store_true", help="Observe before function execution"
    )
    parser.add_argument(
        "-e", "--exception", action="store_true", help="Observe on exception"
    )
    parser.add_argument(
        "-s", "--success", action="store_true", help="Observe on success"
    )
    parser.add_argument(
        "-f",
        "--finish",
        action="store_true",
        default=True,
        help="Observe on finish (both success and exception) (default: True)",
    )
    parser.add_argument(
        "--condition",
        dest="condition_express",
        type=str,
        help='Condition expression (e.g., "params[0] > 100")',
    )
    if include_client:
        parser.add_argument(
            "--client",
            type=str,
            help="Existing client session ID (optional; auto-creates ephemeral if not provided)",
        )


def build_watch_run_parser(parser: argparse.ArgumentParser) -> None:
    _add_watch_arguments(parser, include_pattern=False, include_client=False)


def _add_trace_arguments(
    parser: argparse.ArgumentParser,
    include_pattern: bool = True,
    include_client: bool = True,
) -> None:
    if include_pattern:
        parser.add_argument(
            "pattern", help='Function pattern to trace (e.g., "mymodule.MyClass.method")'
        )
    parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=3,
        help="Trace depth (max call levels, default: 3)",
    )
    parser.add_argument(
        "-n",
        "--times",
        type=int,
        default=-1,
        help="Number of times to capture (-1 for infinite)",
    )
    parser.add_argument(
        "--condition",
        dest="condition_express",
        type=str,
        help='Condition expression (e.g., "cost > 50")',
    )
    parser.add_argument(
        "--skip-builtin",
        dest="skip_builtin",
        type=lambda x: x.lower() in ("true", "1", "yes"),
        default=True,
        help="Skip built-in functions (default: True)",
    )
    parser.add_argument(
        "--min-duration",
        dest="min_duration",
        type=float,
        default=0,
        help="Minimum duration in ms to record (default: 0)",
    )
    if include_client:
        parser.add_argument(
            "--client",
            type=str,
            help="Existing client session ID (optional; auto-creates ephemeral if not provided)",
        )


def build_trace_run_parser(parser: argparse.ArgumentParser) -> None:
    _add_trace_arguments(parser, include_pattern=False, include_client=False)


def _add_stack_arguments(
    parser: argparse.ArgumentParser, include_pattern: bool = True
) -> None:
    if include_pattern:
        parser.add_argument(
            "pattern", help='Function pattern (e.g., "mymodule.MyClass.method")'
        )
    parser.add_argument(
        "-n",
        "--times",
        type=int,
        default=-1,
        help="Number of times to capture (-1 for infinite)",
    )
    parser.add_argument(
        "--condition",
        dest="condition_express",
        type=str,
        help='Condition expression (e.g., "params[0] > 100")',
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=10,
        help="Stack depth limit (default: 10)",
    )


def build_stack_run_parser(parser: argparse.ArgumentParser) -> None:
    _add_stack_arguments(parser, include_pattern=False)


def _add_monitor_arguments(
    parser: argparse.ArgumentParser, include_pattern: bool = True
) -> None:
    if include_pattern:
        parser.add_argument(
            "pattern", help='Function pattern (e.g., "mymodule.MyClass.method")'
        )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between outputs (default: 60)",
    )
    parser.add_argument(
        "-c",
        "--cycles",
        type=int,
        default=-1,
        help="Number of cycles (-1 for infinite)",
    )


def build_monitor_run_parser(parser: argparse.ArgumentParser) -> None:
    _add_monitor_arguments(parser, include_pattern=False)


def add_observe_parsers(subparsers: Any) -> None:
    watch_parser = subparsers.add_parser(
        "watch", help="Watch function calls in target process (must attach first)"
    )
    _add_watch_arguments(watch_parser)

    trace_parser = subparsers.add_parser(
        "trace", help="Trace function call tree and timing (must attach first)"
    )
    _add_trace_arguments(trace_parser)

    stack_parser = subparsers.add_parser(
        "stack", help="Get stack trace of function calls (must attach first)"
    )
    _add_stack_arguments(stack_parser)


    monitor_parser = subparsers.add_parser(
        "monitor", help="Monitor function calls at intervals (must attach first)"
    )
    _add_monitor_arguments(monitor_parser)

    top_parser = subparsers.add_parser(
        "top", help="Function-level sampling profiler (like py-spy top)"
    )
    build_top_run_parser(top_parser)
