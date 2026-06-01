"""
Main CLI Entry Point
Provides command-line interface for Peeka
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import peeka
from peeka.cli._client_helper import ephemeral_client
from peeka.core.attach import ProcessAttacher
from peeka.core.client import StreamingAgentClient
from peeka.core.output import OutputFormatter
from peeka.core.output import configure_logging
from peeka.core.targets import discover_targets
from peeka.core.targets import get_target
from peeka.core.targets import cleanup_stale_targets
from peeka.core.targets import detach_target

configure_logging()


def _find_pid_by_name(name: str) -> int:
    if not name:
        raise ValueError("Process name is required when pid is not provided")
    proc_root = Path("/proc")
    for entry in proc_root.iterdir():
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        cmdline_path = entry / "cmdline"
        comm_path = entry / "comm"
        try:
            if cmdline_path.exists():
                cmdline = cmdline_path.read_text(errors="ignore").replace("\x00", " ")
                if name in cmdline:
                    return int(entry.name)
            if comm_path.exists():
                comm = comm_path.read_text(errors="ignore").strip()
                if comm == name:
                    return int(entry.name)
        except Exception:
            continue
    raise ValueError(f"Process with name '{name}' not found")


def _resolve_pid(args) -> int:
    if args.pid:
        return args.pid
    if getattr(args, "name", None):
        return _find_pid_by_name(args.name)
    raise ValueError("Either --pid or --name must be provided")


def _find_active_session() -> Optional[str]:
    """
    Find the active Peeka session socket.
    Returns socket path if an agent is attached, None otherwise.
    """
    socket_dir = Path("/tmp")
    for sock_file in socket_dir.glob("peeka_*.sock"):
        if sock_file.is_socket():
            session_id = sock_file.stem.replace("peeka_", "")
            pid_file = socket_dir / f"peeka_{session_id}.pid"

            if pid_file.exists():
                try:
                    attached_pid = int(pid_file.read_text().strip())
                    try:
                        os.kill(attached_pid, 0)
                        return str(sock_file)
                    except (ProcessLookupError, PermissionError):
                        pid_file.unlink(missing_ok=True)
                        sock_file.unlink(missing_ok=True)
                except (ValueError, OSError):
                    continue
    return None


def _check_agent_attached() -> Tuple[str, int]:
    """
    Check if agent is attached to any process.
    Returns (socket_path, pid) tuple.
    Raises ValueError with clear message if not attached.
    """
    socket_path = _find_active_session()
    if socket_path is None:
        raise ValueError(
            "Not attached to any process.\nPlease run: peeka-cli attach <pid>"
        )

    session_id = Path(socket_path).stem.replace("peeka_", "")
    pid_file = Path(f"/tmp/peeka_{session_id}.pid")
    attached_pid = int(pid_file.read_text().strip())

    return (socket_path, attached_pid)


def _socket_path_to_target_id(socket_path: str) -> str:
    """Derive target_id from socket path."""
    session_id = Path(socket_path).stem.replace("peeka_", "")
    return f"target_{session_id[:8]}"


def _parse_duration(duration_str: str) -> int:
    """Parse duration string into seconds.
    
    Supports:
        - Bare integers (interpreted as seconds)
        - Ns (N seconds)
        - Nm (N minutes)
        - Nh (N hours)
    
    Args:
        duration_str: Duration string to parse.
    
    Returns:
        Duration in seconds.
    
    Raises:
        argparse.ArgumentTypeError: If duration_str is invalid.
    """
    if not duration_str:
        raise argparse.ArgumentTypeError("Duration cannot be empty")
    
    duration_str = duration_str.strip()
    
    # Try bare integer
    try:
        seconds = int(duration_str)
        if seconds < 0:
            raise argparse.ArgumentTypeError("Duration must be non-negative")
        return seconds
    except ValueError:
        pass
    
    # Try unit-suffixed form
    if len(duration_str) < 2:
        raise argparse.ArgumentTypeError(f"Invalid duration format: {duration_str}")
    
    value_str = duration_str[:-1]
    unit = duration_str[-1].lower()
    
    try:
        value = int(value_str)
        if value < 0:
            raise argparse.ArgumentTypeError("Duration must be non-negative")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid duration value: {value_str}")
    
    if unit == "s":
        return value
    elif unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    else:
        raise argparse.ArgumentTypeError(f"Invalid duration unit: {unit} (use s, m, or h)")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="peeka-cli",
        description="Peeka - Python Diagnostic Tool based on PEP 768",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  peeka-cli attach 12345                  # Attach to process 12345
  peeka-cli watch "mymodule.func"         # Watch function calls (must attach first)
  peeka-cli stack "mod.func"              # Stack trace (must attach first)
  peeka-cli detach                        # Detach from current process
  peeka-cli reset                         # Reset all enhancements
  peeka-cli run myscript.py arg1 -- watch "module.function" --success  # Run script and watch function from start
        """,
    )

    parser.add_argument("--version", action="version", version=f"%(prog)s {peeka.__version__}")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    attach_parser = subparsers.add_parser(
        "attach", help="Attach to a running Python process"
    )
    attach_parser.add_argument("pid", type=int, help="Process ID to attach to")

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
    top_parser.set_defaults(func=cmd_top)

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
    _ = subparsers.add_parser("detach", help="Detach from the target process")
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

    target_parser = subparsers.add_parser(
        "target", help="Manage Peeka target agents"
    )
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
        "current", help="Get the current target (exit 0 if exactly 1 alive, exit 1 if 0, exit 2 if >1)"
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
        "session", help="[DEPRECATED] Alias to 'target' command; use 'peeka-cli target' instead"
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

    client_parser = subparsers.add_parser(
        "client", help="Manage client sessions for target agents"
    )
    client_subparsers = client_parser.add_subparsers(
        dest="client_action", help="Client subcommands"
    )

    client_create_parser = client_subparsers.add_parser(
        "create", help="Create a client session"
    )
    client_create_parser.add_argument(
        "--target",
        type=str,
        required=True,
        help="Target ID for the client session",
    )
    client_create_parser.add_argument(
        "--source",
        type=str,
        required=True,
        choices=["cli", "tui", "mcp", "api", "internal"],
        help="Source of the client request",
    )
    client_create_parser.add_argument(
        "--user",
        type=str,
        default=None,
        help="Optional user ID associated with the client",
    )
    client_create_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    client_list_parser = client_subparsers.add_parser(
        "list", help="List all client sessions"
    )
    client_list_parser.add_argument(
        "--target",
        type=str,
        default=None,
        help="Optional target ID filter",
    )
    client_list_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    client_status_parser = client_subparsers.add_parser(
        "status", help="Get status of a specific client session"
    )
    client_status_parser.add_argument(
        "--client",
        type=str,
        required=True,
        help="Client session ID",
    )
    client_status_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    client_close_parser = client_subparsers.add_parser(
        "close", help="Close a client session"
    )
    client_close_parser.add_argument(
        "--client",
        type=str,
        required=True,
        help="Client session ID",
    )
    client_close_parser.add_argument(
        "--format",
        type=str,
        choices=["json", "table"],
        default="table",
        help="Output format (default: table)",
    )

    job_parser = subparsers.add_parser(
        "job", help="Manage command jobs"
    )
    job_subparsers = job_parser.add_subparsers(
        dest="job_action", help="Job subcommands"
    )

    job_list_parser = job_subparsers.add_parser(
        "list", help="List command jobs"
    )
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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "attach":
            return cmd_attach(args)
        elif args.command == "detach":
            return cmd_detach(args)
        elif args.command == "watch":
            return cmd_watch(args)
        elif args.command == "trace":
            return cmd_trace(args)
        elif args.command == "stack":
            return cmd_stack(args)
        elif args.command == "logger":
            return cmd_logger(args)
        elif args.command == "monitor":
            return cmd_monitor(args)
        elif args.command == "sc":
            return cmd_sc(args)
        elif args.command == "sm":
            return cmd_sm(args)
        elif args.command == "memory":
            return cmd_memory(args)
        elif args.command == "inspect":
            return cmd_vmtool(args)
        elif args.command == "reset":
            return cmd_reset(args)
        elif args.command == "thread":
            return cmd_thread(args)
        elif args.command == "patch-status":
            return cmd_patch_status(args)
        elif args.command == "top":
            return cmd_top(args)
        elif args.command == "run":
            return cmd_run(args)
        elif args.command == "target":
            return cmd_target(args)
        elif args.command == "session":
            return cmd_session(args)
        elif args.command == "client":
            return cmd_client(args)
        elif args.command == "job":
            return cmd_job(args)
        else:
            OutputFormatter.error("peeka", error=f"Unknown command: {args.command}")
            return 1

    except KeyboardInterrupt:
        print("\n", file=sys.stderr)
        return 130
    except Exception as e:
        OutputFormatter.error("peeka", error=str(e))
        return 1


def cmd_attach(args) -> int:
    target_pid = args.pid
    OutputFormatter.status(f"Attaching to process {target_pid}")

    attacher = ProcessAttacher(target_pid, suppress_startup_messages=True)

    try:
        if attacher.attach():
            OutputFormatter.success(
                "attach", data={"pid": target_pid, "socket": attacher.get_socket_path()}
            )
            return 0
        else:
            OutputFormatter.error(
                "attach", error="Failed to attach to process", pid=target_pid
            )
            return 1
    except Exception as e:
        OutputFormatter.error("attach", error=str(e), pid=target_pid)
        return 1
    finally:
        attacher.cleanup()


def cmd_detach(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("detach", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "detach", error=connect_result.get("error", "Connection failed")
        )
        return 1

    response = streaming_client.send_command({"type": "detach"})

    if response.get("status") == "success":
        OutputFormatter.success(
            "detach",
            data={
                "pid": attached_pid,
                "message": response.get(
                    "message", f"Detached from process {attached_pid}"
                ),
            },
        )
    else:
        OutputFormatter.error("detach", error=response.get("error", "Detach failed"))

    streaming_client.disconnect()

    session_id = Path(socket_path).stem.replace("peeka_", "")
    pid_file = Path(f"/tmp/peeka_{session_id}.pid")
    ready_file = Path(f"/tmp/peeka_{session_id}.ready")
    sock_file = Path(socket_path)

    pid_file.unlink(missing_ok=True)
    ready_file.unlink(missing_ok=True)
    sock_file.unlink(missing_ok=True)

    return 0 if response.get("status") == "success" else 1


def cmd_watch(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("watch", error=str(e))
        return 1

    streaming_client: Optional[StreamingAgentClient] = None
    watch_id: Optional[str] = None
    pattern: Optional[str] = None

    def cleanup_watch(signum=None, frame=None):
        nonlocal streaming_client, watch_id, pattern
        if streaming_client and watch_id:
            try:
                streaming_client.send_command(
                    {"type": "watch", "action": "stop", "watch_id": watch_id}
                )
                streaming_client.send_command(
                    {"type": "reset", "action": "reset", "pattern": pattern}
                )
            except Exception:
                pass
            streaming_client.disconnect()
        if signum is not None:
            sys.exit(130)

    signal.signal(signal.SIGINT, cleanup_watch)
    signal.signal(signal.SIGTERM, cleanup_watch)

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "watch", error=connect_result.get("error", "Connection failed")
        )
        return 1

    pattern = args.pattern

    if not hasattr(args, "client") or args.client is None:
        target_id = _socket_path_to_target_id(socket_path)
        try:
            with ephemeral_client(target_id) as cid:
                command = {
                    "type": "watch",
                    "action": "start",
                    "client_session_id": cid,
                    "pattern": pattern,
                    "depth": args.depth,
                    "times": args.times,
                    "before": args.before,
                    "exception": args.exception,
                    "success": args.success,
                    "finish": args.finish,
                    "condition_express": args.condition_express,
                }

                response = streaming_client.send_command(command)

                if response.get("status") != "success":
                    OutputFormatter.error(
                        "watch", error=response.get("error", "Watch start failed")
                    )
                    streaming_client.disconnect()
                    return 1

                watch_id = response.get("watch_id")

                start_data = {"watch_id": watch_id, "pattern": pattern}
                target_info = response.get("target")
                if target_info:
                    start_data["target"] = target_info
                OutputFormatter.event("watch_started", data=start_data)
                sys.stdout.flush()

                observation_count = 0

                try:
                    for observation in streaming_client.stream_observations():
                        print(json.dumps(observation))
                        sys.stdout.flush()

                        if args.times > 0:
                            observation_count += 1
                            if observation_count >= args.times:
                                break

                finally:
                    cleanup_watch()

                return 0
        except Exception as e:
            OutputFormatter.error("watch", error=str(e))
            cleanup_watch()
            return 1
    else:
        command = {
            "type": "watch",
            "action": "start",
            "client_session_id": args.client,
            "pattern": pattern,
            "depth": args.depth,
            "times": args.times,
            "before": args.before,
            "exception": args.exception,
            "success": args.success,
            "finish": args.finish,
            "condition_express": args.condition_express,
        }

        response = streaming_client.send_command(command)

        if response.get("status") != "success":
            OutputFormatter.error(
                "watch", error=response.get("error", "Watch start failed")
            )
            streaming_client.disconnect()
            return 1

        watch_id = response.get("watch_id")

        start_data = {"watch_id": watch_id, "pattern": pattern}
        target_info = response.get("target")
        if target_info:
            start_data["target"] = target_info
        OutputFormatter.event("watch_started", data=start_data)
        sys.stdout.flush()

        observation_count = 0

        try:
            for observation in streaming_client.stream_observations():
                print(json.dumps(observation))
                sys.stdout.flush()

                if args.times > 0:
                    observation_count += 1
                    if observation_count >= args.times:
                        break

        finally:
            cleanup_watch()

        return 0


def cmd_trace(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("trace", error=str(e))
        return 1

    streaming_client: Optional[StreamingAgentClient] = None
    trace_id: Optional[str] = None
    pattern: Optional[str] = None

    def cleanup_trace(signum=None, frame=None):
        nonlocal streaming_client, trace_id, pattern
        if streaming_client and trace_id:
            try:
                streaming_client.send_command(
                    {"type": "trace", "action": "stop", "watch_id": trace_id}
                )
                streaming_client.send_command(
                    {"type": "reset", "action": "reset", "pattern": pattern}
                )
            except Exception:
                pass
            streaming_client.disconnect()
        if signum is not None:
            sys.exit(130)

    signal.signal(signal.SIGINT, cleanup_trace)
    signal.signal(signal.SIGTERM, cleanup_trace)

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "trace", error=connect_result.get("error", "Connection failed")
        )
        return 1

    pattern = args.pattern

    if not hasattr(args, "client") or args.client is None:
        target_id = _socket_path_to_target_id(socket_path)
        try:
            with ephemeral_client(target_id) as cid:
                command = {
                    "type": "trace",
                    "action": "start",
                    "client_session_id": cid,
                    "pattern": pattern,
                    "depth": args.depth,
                    "times": args.times,
                    "condition_express": args.condition_express,
                    "skip_builtin": args.skip_builtin,
                    "min_duration": args.min_duration,
                }

                response = streaming_client.send_command(command)

                if response.get("status") != "success":
                    OutputFormatter.error(
                        "trace", error=response.get("error", "Trace start failed")
                    )
                    streaming_client.disconnect()
                    return 1

                trace_id = response.get("watch_id")

                OutputFormatter.event(
                    "trace_started",
                    data={"trace_id": trace_id, "pattern": pattern},
                    meta=response.get("meta"),
                )
                sys.stdout.flush()

                try:
                    for observation in streaming_client.stream_observations():
                        print(json.dumps(observation))
                        sys.stdout.flush()

                        if args.times > 0:
                            count = observation.get("count", 0)
                            if count >= args.times:
                                break

                finally:
                    cleanup_trace()

                return 0
        except Exception as e:
            OutputFormatter.error("trace", error=str(e))
            cleanup_trace()
            return 1
    else:
        command = {
            "type": "trace",
            "action": "start",
            "client_session_id": args.client,
            "pattern": pattern,
            "depth": args.depth,
            "times": args.times,
            "condition_express": args.condition_express,
            "skip_builtin": args.skip_builtin,
            "min_duration": args.min_duration,
        }

        response = streaming_client.send_command(command)

        if response.get("status") != "success":
            OutputFormatter.error(
                "trace", error=response.get("error", "Trace start failed")
            )
            streaming_client.disconnect()
            return 1

        trace_id = response.get("watch_id")

        OutputFormatter.event(
            "trace_started",
            data={"trace_id": trace_id, "pattern": pattern},
            meta=response.get("meta"),
        )
        sys.stdout.flush()

        try:
            for observation in streaming_client.stream_observations():
                print(json.dumps(observation))
                sys.stdout.flush()

                if args.times > 0:
                    count = observation.get("count", 0)
                    if count >= args.times:
                        break

        finally:
            cleanup_trace()

        return 0


def cmd_stack(args) -> int:
    # TODO(client-session): wrap with ephemeral_client per boulder client-session.md T4
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("stack", error=str(e))
        return 1

    streaming_client: Optional[StreamingAgentClient] = None
    stack_id: Optional[str] = None
    pattern: Optional[str] = None

    def cleanup_stack(signum=None, frame=None):
        nonlocal streaming_client, stack_id, pattern
        if streaming_client and stack_id:
            try:
                streaming_client.send_command(
                    {"type": "stack", "action": "stop", "stack_id": stack_id}
                )
                streaming_client.send_command(
                    {"type": "reset", "action": "reset", "pattern": pattern}
                )
            except Exception:
                pass
            streaming_client.disconnect()
        if signum is not None:
            sys.exit(130)

    signal.signal(signal.SIGINT, cleanup_stack)
    signal.signal(signal.SIGTERM, cleanup_stack)

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "stack", error=connect_result.get("error", "Connection failed")
        )
        return 1

    pattern = args.pattern

    command = {
        "type": "stack",
        "action": "start",
        "pattern": pattern,
        "depth": args.depth,
        "times": args.times,
        "condition_express": args.condition_express,
    }

    response = streaming_client.send_command(command)

    if response.get("status") != "success":
        OutputFormatter.error(
            "stack", error=response.get("error", "Stack start failed")
        )
        streaming_client.disconnect()
        return 1

    stack_id = response.get("stack_id")

    OutputFormatter.event(
        "stack_started", data={"stack_id": stack_id, "pattern": pattern}
    )
    sys.stdout.flush()

    try:
        for observation in streaming_client.stream_observations():
            print(json.dumps(observation))
            sys.stdout.flush()

            if args.times > 0:
                count = observation.get("count", 0)
                if count >= args.times:
                    break

    finally:
        cleanup_stack()

    return 0


def cmd_logger(args) -> int:
    # TODO(client-session): wrap with ephemeral_client per boulder client-session.md T4
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("logger", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "logger", error=connect_result.get("error", "Connection failed")
        )
        return 1

    command = {
        "type": "logger",
        "action": args.action,
        "name": args.logger,
        "level": args.level,
        "pattern": args.pattern,
    }

    response = streaming_client.send_command(command)

    if response.get("status") == "success":
        OutputFormatter.result("logger", data=response)
    else:
        OutputFormatter.error(
            "logger", error=response.get("error", "Logger command failed")
        )

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_memory(args) -> int:
    # TODO(client-session): wrap with ephemeral_client per boulder client-session.md T4
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("memory", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "memory", error=connect_result.get("error", "Connection failed")
        )
        return 1

    command = {
        "type": "memory",
        "action": args.action,
        "nframe": args.nframe,
        "limit": args.limit,
        "group_by": args.group_by,
        "filename": args.filename,
        "type_name": args.type_name,
        "max_depth": args.max_depth,
        "max_per_level": args.max_per_level,
    }

    response = streaming_client.send_command(command)

    if response.get("status") == "success":
        OutputFormatter.result("memory", data=response)
    else:
        OutputFormatter.error(
            "memory", error=response.get("error", "Memory command failed")
        )

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_thread(args) -> int:
    # TODO(client-session): wrap with ephemeral_client per boulder client-session.md T4
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("thread", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "thread", error=connect_result.get("error", "Connection failed")
        )
        return 1

    if args.tid is not None:
        command = {
            "type": "thread",
            "action": "detail",
            "tid": args.tid,
            "depth": args.depth,
        }
    else:
        command = {
            "type": "thread",
            "action": "list",
            "state": args.state,
            "sort_by": args.sort_by,
        }

    response = streaming_client.send_command(command)

    if response.get("status") == "success":
        OutputFormatter.result("thread", data=response)
    else:
        OutputFormatter.error(
            "thread", error=response.get("error", "Thread command failed")
        )

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_patch_status(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("patch-status", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "patch-status", error=connect_result.get("error", "Connection failed")
        )
        return 1

    command = {
        "type": "patch-status",
    }

    response = streaming_client.send_command(command)

    if response.get("status") == "success":
        OutputFormatter.result("patch-status", data=response)
    else:
        OutputFormatter.error(
            "patch-status", error=response.get("error", "Patch-status command failed")
        )

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_vmtool(args) -> int:
    # TODO(client-session): wrap with ephemeral_client per boulder client-session.md T4
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("vmtool", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "vmtool", error=connect_result.get("error", "Connection failed")
        )
        return 1

    command = {
        "type": "vmtool",
        "action": args.action,
        "target": args.target,
        "class_name": args.class_name,
        "limit": args.limit,
        "depth": args.depth,
        "filter_express": args.filter_express,
        "gc_first": args.gc_first,
    }

    response = streaming_client.send_command(command)

    if response.get("status") == "success":
        OutputFormatter.result("vmtool", data=response)
    else:
        OutputFormatter.error(
            "vmtool", error=response.get("error", "Vmtool command failed")
        )

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_reset(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("reset", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "reset", error=connect_result.get("error", "Connection failed")
        )
        return 1

    action = "list" if args.list else "reset"

    command = {
        "type": "reset",
        "action": action,
        "pattern": args.pattern,
    }

    response = streaming_client.send_command(command)

    if response.get("status") == "success":
        OutputFormatter.result("reset", data=response)
    else:
        OutputFormatter.error(
            "reset", error=response.get("error", "Reset command failed")
        )

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_monitor(args) -> int:
    # TODO(client-session): wrap with ephemeral_client per boulder client-session.md T4
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("monitor", error=str(e))
        return 1

    streaming_client: Optional[StreamingAgentClient] = None
    monitor_id: Optional[str] = None
    pattern: Optional[str] = None

    def cleanup_monitor(signum=None, frame=None):
        nonlocal streaming_client, monitor_id, pattern
        if streaming_client and monitor_id:
            try:
                streaming_client.send_command(
                    {"type": "monitor", "action": "stop", "monitor_id": monitor_id}
                )
                streaming_client.send_command(
                    {"type": "reset", "action": "reset", "pattern": pattern}
                )
            except Exception:
                pass
            streaming_client.disconnect()
        if signum is not None:
            sys.exit(130)

    signal.signal(signal.SIGINT, cleanup_monitor)
    signal.signal(signal.SIGTERM, cleanup_monitor)

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "monitor", error=connect_result.get("error", "Connection failed")
        )
        return 1

    pattern = args.pattern

    command = {
        "type": "monitor",
        "action": "start",
        "pattern": pattern,
        "cycle": args.interval,
        "cycles": args.cycles,
    }

    response = streaming_client.send_command(command)

    if response.get("status") != "success":
        OutputFormatter.error(
            "monitor", error=response.get("error", "Monitor start failed")
        )
        streaming_client.disconnect()
        return 1

    monitor_id = response.get("monitor_id")

    OutputFormatter.event(
        "monitor_started", data={"monitor_id": monitor_id, "pattern": pattern}
    )
    sys.stdout.flush()

    try:
        cycles_count = 0
        for observation in streaming_client.stream_observations():
            print(json.dumps(observation))
            sys.stdout.flush()

            if args.cycles > 0:
                cycles_count += 1
                if cycles_count >= args.cycles:
                    break

    finally:
        cleanup_monitor()

    return 0


def cmd_top(args) -> int:
    # TODO(client-session): wrap with ephemeral_client per boulder client-session.md T4
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("top", error=str(e))
        return 1

    streaming_client: Optional[StreamingAgentClient] = None
    top_id: Optional[str] = None

    def cleanup_top(signum=None, frame=None):
        nonlocal streaming_client, top_id
        if streaming_client and top_id:
            try:
                streaming_client.send_command({"type": "top", "action": "stop"})
            except Exception:
                pass
            streaming_client.disconnect()
        if signum is not None:
            sys.exit(130)

    signal.signal(signal.SIGINT, cleanup_top)
    signal.signal(signal.SIGTERM, cleanup_top)

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "top", error=connect_result.get("error", "Connection failed")
        )
        return 1

    command = {
        "type": "top",
        "action": "start",
        "interval": args.interval,
        "stream": True,
        "filter_peeka": not args.no_filter_peeka,
    }

    response = streaming_client.send_command(command)

    if response.get("status") != "success":
        OutputFormatter.error("top", error=response.get("error", "Top start failed"))
        streaming_client.disconnect()
        return 1

    top_id = response.get("top_id")

    OutputFormatter.event(
        "top_started",
        data={
            "top_id": top_id,
            "interval": args.interval,
            "filter_peeka": not args.no_filter_peeka,
        },
        meta=response.get("meta"),
    )
    sys.stdout.flush()

    try:
        cycles_count = 0
        for observation in streaming_client.stream_observations():
            print(json.dumps(observation))
            sys.stdout.flush()

            if args.cycles > 0:
                cycles_count += 1
                if cycles_count >= args.cycles:
                    break

    finally:
        cleanup_top()

    return 0


def cmd_sc(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("sc", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "sc", error=connect_result.get("error", "Connection failed")
        )
        return 1

    command = {
        "type": "sc",
        "pattern": args.pattern,
        "details": args.detail,
        "limit": args.limit,
    }

    response = streaming_client.send_command(command)

    if response.get("status") == "success":
        OutputFormatter.result("sc", data=response)
    else:
        OutputFormatter.error(
            "sc", error=response.get("error", "Search class command failed")
        )

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_sm(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("sm", error=str(e))
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "sm", error=connect_result.get("error", "Connection failed")
        )
        return 1

    command = {
        "type": "sm",
        "pattern": f"{args.class_pattern}.{args.method_pattern}",
        "details": args.detail,
    }

    response = streaming_client.send_command(command)

    if response.get("status") == "success":
        OutputFormatter.result("sm", data=response)
    else:
        OutputFormatter.error(
            "sm", error=response.get("error", "Search method command failed")
        )

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def _build_run_command(
    command_type: str, command_parts: List[str]
) -> Optional[Dict[str, Any]]:
    """
    Build command dict from command parts for supported streaming commands.
    Supports: watch, trace, stack, monitor, top
    """
    # We reuse the existing parsers by creating a tiny subparser just for this
    # This ensures consistency with existing command parsing
    parser = argparse.ArgumentParser(prog=f"peeka-cli run ... -- {command_type}")

    command: Dict[str, Any] = {"type": command_type, "action": "start"}

    if command_type in ("watch", "trace", "stack"):
        if len(command_parts) < 2:
            return None
        command["pattern"] = command_parts[1]
        remaining = command_parts[2:]

        if command_type == "watch":
            parser.add_argument("-x", "--depth", type=int, default=2)
            parser.add_argument("-n", "--times", type=int, default=-1)
            parser.add_argument("-b", "--before", action="store_true")
            parser.add_argument("-e", "--exception", action="store_true")
            parser.add_argument("-s", "--success", action="store_true")
            parser.add_argument("-f", "--finish", action="store_true", default=True)
            parser.add_argument("--condition", dest="condition_express", type=str)
        elif command_type == "trace":
            parser.add_argument("-d", "--depth", type=int, default=3)
            parser.add_argument("-n", "--times", type=int, default=-1)
            parser.add_argument("--condition", dest="condition_express", type=str)
            parser.add_argument(
                "--skip-builtin",
                dest="skip_builtin",
                type=lambda x: x.lower() in ("true", "1", "yes"),
                default=True,
            )
            parser.add_argument(
                "--min-duration", dest="min_duration", type=float, default=0
            )
        elif command_type == "stack":
            parser.add_argument("-n", "--times", type=int, default=-1)
            parser.add_argument("--condition", dest="condition_express", type=str)
            parser.add_argument("--depth", type=int, default=10)

        parsed = parser.parse_args(remaining)
        command.update(vars(parsed))
        return command

    elif command_type == "monitor":
        if not command_parts:
            return None
        command["pattern"] = command_parts[0]
        remaining = command_parts[1:]
        parser.add_argument("--interval", type=int, default=60)
        parser.add_argument("-c", "--cycles", type=int, default=-1)
        parsed = parser.parse_args(remaining)
        command.update(vars(parsed))
        return command

    elif command_type == "top":
        remaining = command_parts
        parser.add_argument("--interval", "-i", type=float, default=0.01)
        parser.add_argument("--cycles", "-c", type=int, default=-1)
        parser.add_argument(
            "--sort",
            type=str,
            default="own",
            choices=["own", "total", "own-time", "total-time"],
        )
        parser.add_argument("--no-filter-peeka", action="store_true", default=False)
        parsed = parser.parse_args(remaining)
        command["interval"] = parsed.interval
        command["cycles"] = parsed.cycles
        command["sort"] = parsed.sort
        command["filter_peeka"] = not parsed.no_filter_peeka
        command["stream"] = True
        return command

    else:
        # Unsupported command
        return None


def cmd_run(args) -> int:
    # We need to find -- manually in sys.argv because argparse removes it from remaining
    # Find index of "run"
    run_idx = None
    for i, arg in enumerate(sys.argv):
        if arg == "run" and i >= 1:  # sys.argv[0] is the program name
            run_idx = i
            break

    if run_idx is None:
        OutputFormatter.error("run", error="Could not find 'run' command in arguments")
        return 1

    # Look for first -- after "run"
    separator_idx = None
    for i in range(run_idx + 1, len(sys.argv)):
        if sys.argv[i] == "--":
            separator_idx = i
            break

    if separator_idx is None:
        OutputFormatter.error(
            "run",
            error="Missing -- separator between script args and command\nUsage: peeka-cli run <script> [args...] -- <command> [args...]",
        )
        return 1

    # args.script_path is already parsed by argparse as the first positional arg after run
    # Everything between run and -- is script_args (including script_path)
    # So script_args is everything between run and --, excluding the script_path itself
    script_args = sys.argv[run_idx + 2 : separator_idx]
    command_parts = sys.argv[separator_idx + 1 :]

    cleaned_script_args = []
    skip_next = False
    for arg in script_args:
        if skip_next:
            skip_next = False
            continue
        if arg == "--output-file":
            skip_next = True
            continue
        cleaned_script_args.append(arg)
    script_args = cleaned_script_args

    if not command_parts:
        OutputFormatter.error(
            "run",
            error="Missing observation command after --\nUsage: peeka-cli run <script> [args...] -- <command> [args...]",
        )
        return 1

    import tempfile
    import uuid

    session_id = str(uuid.uuid4())

    # Absolute path to user script - bootstrap needs it to execute after injection
    abs_script_path = os.path.abspath(args.script_path)
    script_dir = os.path.dirname(abs_script_path)

    import_ready_path = f"/tmp/peeka_{session_id}.import-ready"
    go_path = f"/tmp/peeka_{session_id}.go"

    bootstrap_template_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "core", "bootstrap.py"
    )
    with open(bootstrap_template_path, "r") as f:
        bootstrap_code = f.read()

    bootstrap_code = bootstrap_code.replace("{{SESSION_ID}}", session_id)
    bootstrap_code = bootstrap_code.replace("{{SCRIPT_PATH}}", abs_script_path)
    bootstrap_code = bootstrap_code.replace("{{SCRIPT_DIR}}", script_dir)
    bootstrap_code = bootstrap_code.replace("{{SCRIPT_ARGS}}", repr(script_args))

    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_peeka_bootstrap.py", delete=False
    ) as f:
        f.write(bootstrap_code)
        bootstrap_path = f.name

    output_file = None
    output_dest = sys.stdout
    if getattr(args, "output_file", None):
        output_file = open(args.output_file, "w")
        output_dest = output_file

    def _cleanup_run_files():
        for path in (bootstrap_path, import_ready_path, go_path):
            try:
                os.unlink(path)
            except OSError:
                pass
        if output_file is not None:
            try:
                output_file.close()
            except OSError:
                pass

    # Clean up any old sync files
    for f in [import_ready_path, go_path]:
        try:
            os.unlink(f)
        except Exception:
            pass

    # Spawn the bootstrap process - it will pre-import then wait
    child_args = [sys.executable, bootstrap_path]
    proc = subprocess.Popen(child_args)
    child_pid = proc.pid

    try:
        OutputFormatter.status(
            f"Started bootstrap with PID {child_pid}, waiting for import...",
            file=sys.stderr,
        )

        # Wait for bootstrap to pre-import the user code
        max_wait = 30
        waited = 0
        while waited < max_wait:
            if os.path.exists(import_ready_path):
                break
            time.sleep(0.01)
            waited += 0.01
        else:
            OutputFormatter.error(
                "run",
                error=f"Timed out waiting for bootstrap to pre-import user code after {max_wait}s",
                file=sys.stderr,
            )
            os.kill(child_pid, signal.SIGKILL)
            os.waitpid(child_pid, 0)
            return 1

        OutputFormatter.status(
            f"User code imported, attaching to PID {child_pid}...", file=sys.stderr
        )

        attacher = ProcessAttacher(
            child_pid, suppress_startup_messages=True, session_id=session_id
        )

        try:
            attached = attacher.attach()
            if not attached:
                OutputFormatter.error(
                    "run",
                    error=f"Failed to attach to process {child_pid}",
                    file=sys.stderr,
                )
                try:
                    os.kill(child_pid, signal.SIGKILL)
                    os.waitpid(child_pid, 0)
                except Exception:
                    pass
                attacher.cleanup()
                return 1

            socket_path = attacher.get_socket_path()
            OutputFormatter.status(
                f"Attached to PID {child_pid}, setting up command...", file=sys.stderr
            )

            # Signal handlers: forward to child process then cleanup
            def cleanup_and_exit(signum=None, frame=None):
                exit_code = 0
                try:
                    if signum is not None:
                        os.kill(child_pid, signum)
                    # Detach
                    streaming_client = StreamingAgentClient(socket_path)
                    streaming_client.connect()
                    streaming_client.send_command({"type": "detach"})
                    streaming_client.disconnect()
                    # Cleanup socket/pid files
                    sid = Path(socket_path).stem.replace("peeka_", "")
                    pid_file = Path(f"/tmp/peeka_{sid}.pid")
                    ready_file = Path(f"/tmp/peeka_{sid}.ready")
                    sock_file = Path(socket_path)
                    pid_file.unlink(missing_ok=True)
                    ready_file.unlink(missing_ok=True)
                    sock_file.unlink(missing_ok=True)
                    # Reap child
                    exit_code = 0
                    try:
                        _, exit_code = os.waitpid(child_pid, 0)
                    except ChildProcessError:
                        pass
                except Exception:
                    pass
                finally:
                    attacher.cleanup()
                    if signum is not None:
                        if os.WIFEXITED(exit_code):
                            sys.exit(os.WEXITSTATUS(exit_code))
                        elif os.WIFSIGNALED(exit_code):
                            sys.exit(128 + os.WTERMSIG(exit_code))
                        else:
                            sys.exit(1)

            signal.signal(signal.SIGINT, cleanup_and_exit)
            signal.signal(signal.SIGTERM, cleanup_and_exit)

            # Connect and send command
            streaming_client = StreamingAgentClient(socket_path)
            connect_result = streaming_client.connect()

            if connect_result.get("status") != "success":
                OutputFormatter.error(
                    "run",
                    error=connect_result.get("error", "Connection failed"),
                    file=sys.stderr,
                )
                cleanup_and_exit()
                return 1

            command_type = command_parts[0]
            command = _build_run_command(command_type, command_parts)

            if command is None:
                OutputFormatter.error(
                    "run",
                    error=f"Unsupported command for run: {command_type}\nOnly streaming observation commands (watch/trace/stack/monitor/top) are supported",
                    file=sys.stderr,
                )
                cleanup_and_exit()
                return 1

            response = streaming_client.send_command(command)

            if response.get("status") != "success":
                OutputFormatter.error(
                    "run",
                    error=response.get("error", f"{command_type} start failed"),
                    file=sys.stderr,
                )
                cleanup_and_exit()
                return 1

            watch_id = response.get(
                "watch_id", response.get("monitor_id", response.get("top_id"))
            )
            OutputFormatter.event(
                f"{command_type}_started",
                data={f"{command_type}_id": watch_id, "command": command_parts},
                file=sys.stderr,
            )
            sys.stderr.flush()

            # Signal to bootstrap that command is set up and it's OK to start running
            with open(go_path, "w") as f:
                f.write(str(os.getpid()))

            child_exited = False
            exit_code = 0

            try:
                for observation in streaming_client.stream_observations():
                    print(json.dumps(observation), file=output_dest, flush=True)

                    # Check if child has exited
                    try:
                        pid, status = os.waitpid(child_pid, os.WNOHANG)
                        if pid == child_pid:
                            child_exited = True
                            if os.WIFEXITED(status):
                                exit_code = os.WEXITSTATUS(status)
                            elif os.WIFSIGNALED(status):
                                exit_code = 128 + os.WTERMSIG(status)
                            break
                    except ChildProcessError:
                        child_exited = True
                        exit_code = 1
                        break

                    time.sleep(0.01)
            finally:
                if not child_exited:
                    cleanup_and_exit()

            cleanup_and_exit()
            return exit_code

        except Exception as e:
            try:
                os.kill(child_pid, signal.SIGKILL)
                os.waitpid(child_pid, 0)
            except Exception:
                pass
            OutputFormatter.error("run", error=str(e), file=sys.stderr)
            import traceback

            traceback.print_exc(file=sys.stderr)
            attacher.cleanup()
            return 1

    finally:
        _cleanup_run_files()


def cmd_job(args) -> int:
    if not args.job_action:
        OutputFormatter.error("job", error="Missing job subcommand")
        return 1

    try:
        if args.job_action == "list":
            return cmd_job_list(args)
        elif args.job_action == "status":
            return cmd_job_status(args)
        elif args.job_action == "inspect":
            return cmd_job_inspect(args)
        elif args.job_action == "interrupt":
            return cmd_job_interrupt(args)
        elif args.job_action == "cleanup":
            return cmd_job_cleanup(args)
        elif args.job_action == "pull":
            return cmd_job_pull(args)
        else:
            OutputFormatter.error("job", error=f"Unknown job action: {args.job_action}")
            return 1
    except Exception as e:
        OutputFormatter.error("job", error=str(e))
        return 1


def cmd_job_list(args) -> int:
    try:
        socket_path, _ = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("job.list", error=str(e), error_code="AGENT_UNREACHABLE")
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "job.list",
            error=connect_result.get("error", "Connection failed"),
            error_code="TRANSPORT_ERROR"
        )
        return 1

    command = {
        "type": "job",
        "action": "list",
    }
    if args.target:
        command["target_id"] = args.target
    if args.client:
        command["client_session_id"] = args.client
    if args.status:
        command["status"] = args.status

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        jobs = data.get("jobs", [])
        
        if args.format == "json":
            for job in jobs:
                print(json.dumps(job))
        else:
            if not jobs:
                print("No jobs found.", file=sys.stderr)
            else:
                print(f"{'JOB_ID':<15} {'TARGET':<20} {'CLIENT':<20} {'TYPE/ACTION':<25} {'STATUS':<12} {'CATEGORY':<10} {'UPDATED':<20}")
                print("-" * 142)
                for job in jobs:
                    job_id = job.get("id", "-")
                    target_id = job.get("target_id", "-")
                    client_id = job.get("client_session_id", "-")
                    type_action = f"{job.get('command_type', '-')}/{job.get('action', '-')}"
                    status = job.get("status", "-")
                    category = job.get("category", "-")
                    updated_at = job.get("updated_at", 0)
                    import datetime
                    updated_str = datetime.datetime.fromtimestamp(updated_at).strftime("%Y-%m-%d %H:%M:%S") if updated_at else "-"
                    print(
                        f"{job_id:<15} {target_id:<20} {client_id:<20} {type_action:<25} {status:<12} {category:<10} {updated_str:<20}"
                    )
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Job list failed")
        if args.format == "json":
            OutputFormatter.error("job.list", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 1


def cmd_job_status(args) -> int:
    try:
        socket_path, _ = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("job.status", error=str(e), error_code="AGENT_UNREACHABLE")
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "job.status",
            error=connect_result.get("error", "Connection failed"),
            error_code="TRANSPORT_ERROR"
        )
        return 1

    command = {
        "type": "job",
        "action": "status",
        "job_id": args.job,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        job = data.get("job", {})
        
        if args.format == "json":
            OutputFormatter.success("job.status", data=data)
        else:
            for key, value in job.items():
                print(f"{key:<20} {value}")
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Job status query failed")
        if args.format == "json":
            OutputFormatter.error("job.status", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "JOB_NOT_FOUND" else 1


def cmd_job_inspect(args) -> int:
    try:
        socket_path, _ = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("job.inspect", error=str(e), error_code="AGENT_UNREACHABLE")
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "job.inspect",
            error=connect_result.get("error", "Connection failed"),
            error_code="TRANSPORT_ERROR"
        )
        return 1

    command = {
        "type": "job",
        "action": "inspect",
        "job_id": args.job,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        job = data.get("job", {})
        
        if args.format == "json":
            OutputFormatter.success("job.inspect", data=data)
        else:
            for key, value in job.items():
                if isinstance(value, dict):
                    print(f"{key:<20}")
                    for k, v in value.items():
                        print(f"  {k:<18} {v}")
                else:
                    print(f"{key:<20} {value}")
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Job inspect query failed")
        if args.format == "json":
            OutputFormatter.error("job.inspect", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "JOB_NOT_FOUND" else 1


def cmd_job_interrupt(args) -> int:
    try:
        socket_path, _ = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("job.interrupt", error=str(e), error_code="AGENT_UNREACHABLE")
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "job.interrupt",
            error=connect_result.get("error", "Connection failed"),
            error_code="TRANSPORT_ERROR"
        )
        return 1

    command = {
        "type": "job",
        "action": "interrupt",
        "job_id": args.job,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        
        if args.format == "json":
            OutputFormatter.success("job.interrupt", data=data)
        else:
            job_id = data.get("job_id", args.job)
            new_status = data.get("status", "interrupted")
            print(f"Job {job_id} status: {new_status}", file=sys.stderr)
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Job interrupt failed")
        if args.format == "json":
            OutputFormatter.error("job.interrupt", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code in ("UNSUPPORTED_CAPABILITY", "JOB_NOT_FOUND") else 1


def cmd_job_cleanup(args) -> int:
    try:
        socket_path, _ = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("job.cleanup", error=str(e), error_code="AGENT_UNREACHABLE")
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "job.cleanup",
            error=connect_result.get("error", "Connection failed"),
            error_code="TRANSPORT_ERROR"
        )
        return 1

    command = {
        "type": "job",
        "action": "cleanup",
        "completed_only": args.completed,
        "older_than_seconds": args.older_than,
    }
    if args.target:
        command["target_id"] = args.target

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        removed = data.get("removed", [])
        
        if args.format == "json":
            OutputFormatter.success("job.cleanup", data=data)
        else:
            print(f"Removed {len(removed)} job(s)", file=sys.stderr)
            for job_id in removed:
                print(f"  {job_id}", file=sys.stderr)
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Job cleanup failed")
        if args.format == "json":
            OutputFormatter.error("job.cleanup", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 1


def cmd_job_pull(args) -> int:
    error_payload = {
        "status": "error",
        "error_code": "UNSUPPORTED_CAPABILITY",
        "message": "job pull is not yet implemented (see Phase 5 ResultConsumer boulder)"
    }
    print(json.dumps(error_payload))
    return 2


if __name__ == "__main__":
    sys.exit(main())


def cmd_target(args) -> int:
    if not args.target_action:
        OutputFormatter.error("target", error="Missing target subcommand")
        return 1

    try:
        if args.target_action == "list":
            return cmd_target_list(args)
        elif args.target_action == "current":
            return cmd_target_current(args)
        elif args.target_action == "status":
            return cmd_target_status(args)
        elif args.target_action == "inspect":
            return cmd_target_inspect(args)
        elif args.target_action == "cleanup":
            return cmd_target_cleanup(args)
        elif args.target_action == "detach":
            return cmd_target_detach(args)
        else:
            OutputFormatter.error("target", error=f"Unknown target action: {args.target_action}")
            return 1
    except Exception as e:
        OutputFormatter.error("target", error=str(e))
        return 1


def cmd_target_list(args) -> int:
    targets = discover_targets()

    if args.format == "json":
        for target in targets:
            OutputFormatter.event("target.discovered", data=target.to_dict())
        return 0
    else:
        if not targets:
            print("No targets found.", file=sys.stderr)
            return 0

        print(f"{'Target ID':<20} {'State':<10} {'PID':<10} {'Python':<15} {'Socket':<40}")
        print("-" * 95)
        for target in targets:
            socket_short = Path(target.socket_path).name
            print(
                f"{target.target_id:<20} {target.state:<10} {target.pid:<10} {target.python_version:<15} {socket_short:<40}"
            )
        return 0


def cmd_target_current(args) -> int:
    targets = discover_targets()
    alive_targets = [t for t in targets if t.state == "alive"]

    if len(alive_targets) == 1:
        target = alive_targets[0]
        if args.format == "json":
            OutputFormatter.success("target.current", data=target.to_dict())
        else:
            print(f"Current target: {target.target_id} (PID {target.pid})", file=sys.stderr)
        return 0
    elif len(alive_targets) == 0:
        if args.format == "json":
            OutputFormatter.error("target.current", error="No alive targets found", error_code="TARGET_NOT_FOUND")
        else:
            print("TARGET_NOT_FOUND: No alive targets found", file=sys.stderr)
        return 1
    else:
        if args.format == "json":
            OutputFormatter.error(
                "target.current",
                error=f"Multiple alive targets found: {len(alive_targets)}",
                error_code="TARGET_AMBIGUOUS",
                targets=[t.target_id for t in alive_targets],
            )
        else:
            print(
                f"TARGET_AMBIGUOUS: Multiple alive targets found ({len(alive_targets)}): "
                + ", ".join(t.target_id for t in alive_targets),
                file=sys.stderr,
            )
        return 2


def cmd_target_status(args) -> int:
    target = get_target(args.target)
    if target is None:
        if args.format == "json":
            OutputFormatter.error("target.status", error=f"Target not found: {args.target}", error_code="TARGET_NOT_FOUND")
        else:
            print(f"TARGET_NOT_FOUND: {args.target}", file=sys.stderr)
        return 1

    if args.format == "json":
        OutputFormatter.success("target.status", data=target.to_dict())
        return 0
    else:
        print(f"Target ID: {target.target_id}")
        print(f"State: {target.state}")
        print(f"PID: {target.pid}")
        print(f"Python Version: {target.python_version}")
        print(f"Peeka Version: {target.peeka_version}")
        print(f"Socket: {target.socket_path}")
        print(f"Agent Mode: {target.agent_mode}")
        print(f"Injection Mode: {target.injection_mode}")
        return 0


def cmd_target_inspect(args) -> int:
    target = get_target(args.target)
    if target is None:
        if args.format == "json":
            OutputFormatter.error("target.inspect", error=f"Target not found: {args.target}", error_code="TARGET_NOT_FOUND")
        else:
            print(f"TARGET_NOT_FOUND: {args.target}", file=sys.stderr)
        return 1

    if args.format == "json":
        OutputFormatter.success("target.inspect", data=target.to_dict())
        return 0
    else:
        print(f"Target ID: {target.target_id}")
        print(f"State: {target.state}")
        print(f"PID: {target.pid}")
        print(f"Python Version: {target.python_version}")
        print(f"Peeka Version: {target.peeka_version}")
        print(f"Socket: {target.socket_path}")
        print(f"Agent Mode: {target.agent_mode}")
        print(f"Injection Mode: {target.injection_mode}")
        print(f"Created At: {target.created_at}")
        print(f"Last Seen At: {target.last_seen_at}")
        print(f"Runtime: {json.dumps(target.runtime, indent=2)}")
        print(f"Capabilities: {json.dumps(target.capabilities, indent=2)}")
        print(f"Next Valid Actions: {', '.join(target.next_valid_actions)}")
        return 0


def cmd_target_cleanup(args) -> int:
    result = cleanup_stale_targets(dry_run=args.dry_run, target_id=getattr(args, "target", None))

    if args.format == "json":
        OutputFormatter.success("target.cleanup", data=result)
        return 0
    else:
        removed_count = len(result.get("removed", []))
        skipped_count = len(result.get("skipped", []))
        error_count = len(result.get("errors", []))

        if args.dry_run:
            print(f"Dry run: Would remove {removed_count} stale target(s)", file=sys.stderr)
        else:
            print(f"Removed {removed_count} stale target(s)", file=sys.stderr)

        if skipped_count > 0:
            print(f"Skipped {skipped_count} target(s)", file=sys.stderr)

        if error_count > 0:
            print(f"Errors: {error_count}", file=sys.stderr)
            for error in result.get("errors", []):
                print(f"  {error.get('target_id')}: {error.get('message')}", file=sys.stderr)

        return 0


def cmd_target_detach(args) -> int:
    result = detach_target(args.target, force=args.force)

    if not result.get("ok"):
        error_code = result.get("error_code", "TRANSPORT_ERROR")
        message = result.get("message", "Detach failed")

        if args.format == "json":
            OutputFormatter.error("target.detach", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)

        if error_code == "UNSUPPORTED_CAPABILITY" and not args.force:
            return 2
        return 1

    if args.format == "json":
        OutputFormatter.success("target.detach", data=result)
        return 0
    else:
        print(f"Successfully detached from target {result.get('target_id')}", file=sys.stderr)
        if result.get("errors"):
            print("Warning: Some cleanup errors occurred:", file=sys.stderr)
            for error in result.get("errors", []):
                print(f"  {error.get('path')}: {error.get('message')}", file=sys.stderr)
        return 0


def cmd_session(args) -> int:
    if not args.session_action:
        OutputFormatter.error("session", error="Missing session subcommand")
        return 1

    try:
        if args.session_action == "list":
            return cmd_session_list(args)
        elif args.session_action == "status":
            return cmd_session_status(args)
        elif args.session_action == "detach":
            return cmd_session_detach(args)
        else:
            OutputFormatter.error("session", error=f"Unknown session action: {args.session_action}")
            return 1
    except Exception as e:
        OutputFormatter.error("session", error=str(e))
        return 1


def cmd_session_list(args) -> int:
    print("[deprecated] 'peeka-cli session <X>' is deprecated; use 'peeka-cli target <X>'", file=sys.stderr)
    return cmd_target_list(args)


def cmd_session_status(args) -> int:
    print("[deprecated] 'peeka-cli session <X>' is deprecated; use 'peeka-cli target <X>'", file=sys.stderr)
    return cmd_target_status(args)


def cmd_session_detach(args) -> int:
    print("[deprecated] 'peeka-cli session <X>' is deprecated; use 'peeka-cli target <X>'", file=sys.stderr)
    return cmd_target_detach(args)


def cmd_client(args) -> int:
    if not args.client_action:
        OutputFormatter.error("client", error="Missing client subcommand")
        return 1

    try:
        if args.client_action == "create":
            return cmd_client_create(args)
        elif args.client_action == "list":
            return cmd_client_list(args)
        elif args.client_action == "status":
            return cmd_client_status(args)
        elif args.client_action == "close":
            return cmd_client_close(args)
        else:
            OutputFormatter.error("client", error=f"Unknown client action: {args.client_action}")
            return 1
    except Exception as e:
        OutputFormatter.error("client", error=str(e))
        return 1


def cmd_client_create(args) -> int:
    try:
        socket_path, _ = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("client.create", error=str(e), error_code="AGENT_UNREACHABLE")
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "client.create", 
            error=connect_result.get("error", "Connection failed"),
            error_code="TRANSPORT_ERROR"
        )
        return 1

    command = {
        "type": "client",
        "action": "create",
        "target_id": args.target,
        "source": args.source,
        "user_id": args.user,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("client.create", data=data)
        else:
            print(f"Client session created: {data.get('client_session_id')}", file=sys.stderr)
            print(f"Target: {data.get('target_id')}", file=sys.stderr)
            print(f"Source: {data.get('source')}", file=sys.stderr)
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Client create failed")
        if args.format == "json":
            OutputFormatter.error("client.create", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "UNSUPPORTED_CAPABILITY" else 1


def cmd_client_list(args) -> int:
    try:
        socket_path, _ = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("client.list", error=str(e), error_code="AGENT_UNREACHABLE")
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "client.list", 
            error=connect_result.get("error", "Connection failed"),
            error_code="TRANSPORT_ERROR"
        )
        return 1

    command = {
        "type": "client",
        "action": "list",
        "target_id": args.target,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        clients = data.get("clients", [])
        
        if args.format == "json":
            for client in clients:
                OutputFormatter.event("client.discovered", data=client)
        else:
            if not clients:
                print("No client sessions found.", file=sys.stderr)
            else:
                print(f"{'Client ID':<20} {'Target ID':<20} {'Source':<10} {'Status':<15} {'User':<20}")
                print("-" * 85)
                for client in clients:
                    user_id = client.get("user_id") or "-"
                    print(
                        f"{client.get('client_session_id'):<20} "
                        f"{client.get('target_id'):<20} "
                        f"{client.get('source'):<10} "
                        f"{client.get('input_status'):<15} "
                        f"{user_id:<20}"
                    )
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Client list failed")
        if args.format == "json":
            OutputFormatter.error("client.list", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 1


def cmd_client_status(args) -> int:
    try:
        socket_path, _ = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("client.status", error=str(e), error_code="AGENT_UNREACHABLE")
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "client.status", 
            error=connect_result.get("error", "Connection failed"),
            error_code="TRANSPORT_ERROR"
        )
        return 1

    command = {
        "type": "client",
        "action": "status",
        "client_session_id": args.client,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("client.status", data=data)
        else:
            print(f"Client Session ID: {data.get('client_session_id')}")
            print(f"Target ID: {data.get('target_id')}")
            print(f"Source: {data.get('source')}")
            print(f"Input Status: {data.get('input_status')}")
            print(f"User ID: {data.get('user_id') or '-'}")
            print(f"Foreground Job ID: {data.get('foreground_job_id') or '-'}")
            print(f"Created At: {data.get('created_at')}")
            print(f"Last Access At: {data.get('last_access_at')}")
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Client status query failed")
        if args.format == "json":
            OutputFormatter.error("client.status", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "CLIENT_NOT_FOUND" else 1


def cmd_client_close(args) -> int:
    try:
        socket_path, _ = _check_agent_attached()
    except ValueError as e:
        OutputFormatter.error("client.close", error=str(e), error_code="AGENT_UNREACHABLE")
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        OutputFormatter.error(
            "client.close", 
            error=connect_result.get("error", "Connection failed"),
            error_code="TRANSPORT_ERROR"
        )
        return 1

    command = {
        "type": "client",
        "action": "close",
        "client_session_id": args.client,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("client.close", data=data)
        else:
            print(f"Client session closed: {args.client}", file=sys.stderr)
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Client close failed")
        if args.format == "json":
            OutputFormatter.error("client.close", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "CLIENT_NOT_FOUND" else 1
