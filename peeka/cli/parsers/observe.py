"""Parser declarations for observe CLI commands."""

from typing import Any


def add_observe_parsers(subparsers: Any) -> None:
    watch_parser = subparsers.add_parser(
        "watch", help="Watch function calls in target process (must attach first)"
    )
    watch_parser.add_argument(
        "pattern", help='Function pattern to watch (e.g., "mymodule.MyClass.method")'
    )
    watch_parser.add_argument(
        "-x", "--depth", type=int, default=2, help="Output depth for nested objects"
    )
    watch_parser.add_argument(
        "-n",
        "--times",
        type=int,
        default=-1,
        help="Number of times to capture (-1 for infinite)",
    )
    watch_parser.add_argument(
        "-b", "--before", action="store_true", help="Observe before function execution"
    )
    watch_parser.add_argument(
        "-e", "--exception", action="store_true", help="Observe on exception"
    )
    watch_parser.add_argument(
        "-s", "--success", action="store_true", help="Observe on success"
    )
    watch_parser.add_argument(
        "-f",
        "--finish",
        action="store_true",
        default=True,
        help="Observe on finish (both success and exception) (default: True)",
    )
    watch_parser.add_argument(
        "--condition",
        dest="condition_express",
        type=str,
        help='Condition expression (e.g., "params[0] > 100")',
    )
    watch_parser.add_argument(
        "--client",
        type=str,
        help="Existing client session ID (optional; auto-creates ephemeral if not provided)",
    )

    trace_parser = subparsers.add_parser(
        "trace", help="Trace function call tree and timing (must attach first)"
    )
    trace_parser.add_argument(
        "pattern", help='Function pattern to trace (e.g., "mymodule.MyClass.method")'
    )
    trace_parser.add_argument(
        "-d",
        "--depth",
        type=int,
        default=3,
        help="Trace depth (max call levels, default: 3)",
    )
    trace_parser.add_argument(
        "-n",
        "--times",
        type=int,
        default=-1,
        help="Number of times to capture (-1 for infinite)",
    )
    trace_parser.add_argument(
        "--condition",
        dest="condition_express",
        type=str,
        help='Condition expression (e.g., "cost > 50")',
    )
    trace_parser.add_argument(
        "--skip-builtin",
        dest="skip_builtin",
        type=lambda x: x.lower() in ("true", "1", "yes"),
        default=True,
        help="Skip built-in functions (default: True)",
    )
    trace_parser.add_argument(
        "--min-duration",
        dest="min_duration",
        type=float,
        default=0,
        help="Minimum duration in ms to record (default: 0)",
    )
    trace_parser.add_argument(
        "--client",
        type=str,
        help="Existing client session ID (optional; auto-creates ephemeral if not provided)",
    )

    stack_parser = subparsers.add_parser(
        "stack", help="Get stack trace of function calls (must attach first)"
    )
    stack_parser.add_argument(
        "pattern", help='Function pattern (e.g., "mymodule.MyClass.method")'
    )
    stack_parser.add_argument(
        "-n",
        "--times",
        type=int,
        default=-1,
        help="Number of times to capture (-1 for infinite)",
    )
    stack_parser.add_argument(
        "--condition",
        dest="condition_express",
        type=str,
        help='Condition expression (e.g., "params[0] > 100")',
    )
    stack_parser.add_argument(
        "--depth",
        type=int,
        default=10,
        help="Stack depth limit (default: 10)",
    )


    monitor_parser = subparsers.add_parser(
        "monitor", help="Monitor function calls at intervals (must attach first)"
    )
    monitor_parser.add_argument(
        "pattern", help='Function pattern (e.g., "mymodule.MyClass.method")'
    )
    monitor_parser.add_argument(
        "--interval",
        type=int,
        default=60,
        help="Seconds between outputs (default: 60)",
    )
    monitor_parser.add_argument(
        "-c",
        "--cycles",
        type=int,
        default=-1,
        help="Number of cycles (-1 for infinite)",
    )

    top_parser = subparsers.add_parser(
        "top", help="Function-level sampling profiler (like py-spy top)"
    )
    top_parser.add_argument(
        "--interval",
        "-i",
        type=float,
        default=0.01,
        help="Sampling interval in seconds (default: 0.01)",
    )
    top_parser.add_argument(
        "--cycles",
        "-c",
        type=int,
        default=-1,
        help="Number of display cycles before auto-stop (default: -1 for infinite)",
    )
    top_parser.add_argument(
        "--sort",
        type=str,
        default="own",
        choices=["own", "total", "own-time", "total-time"],
        help="Sort column: own (default), total, own-time, total-time",
    )
    top_parser.add_argument(
        "--no-filter-peeka",
        action="store_true",
        help="Disable peeka thread filtering (default: filter enabled)",
    )
    top_parser.set_defaults(func="top")
