"""Parser declarations for runtime CLI commands."""

from typing import Any


def add_runtime_parsers(subparsers: Any) -> None:
    logger_parser = subparsers.add_parser(
        "logger", help="Manage logger configuration (must attach first)"
    )
    logger_parser.add_argument(
        "--action",
        type=str,
        choices=["list", "get", "set"],
        default="list",
        help="Logger action (default: list)",
    )
    logger_parser.add_argument(
        "--logger",
        "--name",
        dest="logger",
        type=str,
        help="Logger name for get/set actions",
    )
    logger_parser.add_argument(
        "--level",
        type=str,
        help="Log level for set action",
    )
    logger_parser.add_argument(
        "--pattern",
        type=str,
        help="fnmatch pattern for list action",
    )


    sc_parser = subparsers.add_parser(
        "sc", help="Search classes in target process (must attach first)"
    )
    sc_parser.add_argument("pattern", help='Class pattern (e.g., "mymodule.*")')
    sc_parser.add_argument(
        "-d",
        "--detail",
        action="store_true",
        help="Show detailed information",
    )
    sc_parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Result limit (default: 50)",
    )

    sm_parser = subparsers.add_parser(
        "sm", help="Search methods in target class (must attach first)"
    )
    sm_parser.add_argument(
        "class_pattern", help='Class pattern (e.g., "mymodule.MyClass")'
    )
    sm_parser.add_argument(
        "--method-pattern",
        type=str,
        default="*",
        help="Method pattern (default: *)",
    )
    sm_parser.add_argument(
        "-d",
        "--detail",
        action="store_true",
        help="Show detailed information",
    )

    memory_parser = subparsers.add_parser(
        "memory", help="Memory analysis and diagnostics (must attach first)"
    )
    memory_parser.add_argument(
        "--action",
        type=str,
        choices=[
            "overview",
            "start",
            "stop",
            "top",
            "dump",
            "gc",
            "snapshot",
            "diff",
            "referrers",
            "referents",
        ],
        default="overview",
        help="Memory action (default: overview)",
    )
    memory_parser.add_argument(
        "--nframe",
        type=int,
        default=25,
        help="Tracemalloc frame depth (default: 25)",
    )
    memory_parser.add_argument(
        "--group-by",
        dest="group_by",
        type=str,
        choices=["lineno", "filename"],
        default="lineno",
        help="Group allocations by lineno or filename (default: lineno)",
    )
    memory_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Result limit for top/gc actions (default: 20)",
    )
    memory_parser.add_argument(
        "--filename",
        type=str,
        help="Output filename for dump action",
    )
    memory_parser.add_argument(
        "--type-name",
        dest="type_name",
        type=str,
        help="Type name for referrers/referents actions (e.g., 'dict', 'MyClass')",
    )
    memory_parser.add_argument(
        "--max-depth",
        dest="max_depth",
        type=int,
        default=2,
        help="Max recursion depth for referrers/referents (1-3, default: 2)",
    )
    memory_parser.add_argument(
        "--max-per-level",
        dest="max_per_level",
        type=int,
        default=10,
        help="Max items per level for referrers/referents (1-20, default: 10)",
    )

    inspect_parser = subparsers.add_parser(
        "inspect", help="Runtime object inspection and analysis (must attach first)"
    )
    inspect_parser.add_argument(
        "--action",
        type=str,
        choices=["get", "instances", "count"],
        default="get",
        help="Inspect action (default: get)",
    )
    inspect_parser.add_argument(
        "--target",
        type=str,
        help="Target object path for get action (e.g., 'module.attr')",
    )
    inspect_parser.add_argument(
        "--type",
        dest="class_name",
        type=str,
        help="Class name for instances/count actions (e.g., 'module.ClassName')",
    )
    inspect_parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Result limit for instances action (default: 10)",
    )
    inspect_parser.add_argument(
        "--depth",
        type=int,
        default=2,
        help="Output depth for nested objects (default: 2)",
    )
    inspect_parser.add_argument(
        "--filter-express",
        dest="filter_express",
        type=str,
        help='Filter expression (e.g., "obj.value > 0")',
    )
    inspect_parser.add_argument(
        "--gc-first",
        dest="gc_first",
        action="store_true",
        help="Force garbage collection before scanning",
    )

    reset_parser = subparsers.add_parser(
        "reset",
        help="Reset enhancements and restore original functions (must attach first)",
    )
    reset_parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="List current enhancements instead of resetting",
    )
    reset_parser.add_argument(
        "pattern",
        nargs="?",
        default=None,
        help="Optional pattern to filter enhancements (supports * and ?)",
    )

    thread_parser = subparsers.add_parser(
        "thread", help="List threads and inspect stacks (must attach first)"
    )
    thread_parser.add_argument(
        "--tid",
        type=int,
        default=None,
        help="Thread ID to show detailed stack trace",
    )
    thread_parser.add_argument(
        "--state",
        type=str,
        choices=["RUNNABLE", "WAITING", "TIMED_WAITING"],
        default=None,
        help="Filter threads by state",
    )
    thread_parser.add_argument(
        "--sort-by",
        dest="sort_by",
        type=str,
        choices=["tid", "name", "state"],
        default="tid",
        help="Sort threads by field (default: tid)",
    )
    thread_parser.add_argument(
        "--depth",
        type=int,
        default=50,
        help="Stack depth limit for detail view (default: 50)",
    )
    patch_status_parser = subparsers.add_parser(
        "patch-status", help="Check runtime monkey-patch status (must attach first)"
    )
    patch_status_parser.add_argument(
        "--pid",
        type=int,
        default=None,
        help="(optional, ignored) Process ID hint; patch-status reports on the currently attached session",
    )
