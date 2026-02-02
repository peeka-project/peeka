"""
Main CLI Entry Point
Provides command-line interface for Peeka
"""

import argparse
import json
import os
import signal
import sys
from pathlib import Path
from typing import Optional

from peeka.core.attach import ProcessAttacher
from peeka.core.client import StreamingAgentClient


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


def _check_agent_attached() -> tuple[str, int]:
    """
    Check if agent is attached to any process.
    Returns (socket_path, pid) tuple.
    Raises ValueError with clear message if not attached.
    """
    socket_path = _find_active_session()
    if socket_path is None:
        raise ValueError("Not attached to any process.\nPlease run: peeka attach <pid>")

    session_id = Path(socket_path).stem.replace("peeka_", "")
    pid_file = Path(f"/tmp/peeka_{session_id}.pid")
    attached_pid = int(pid_file.read_text().strip())

    return (socket_path, attached_pid)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="peeka",
        description="Peeka - Python Diagnostic Tool based on PEP 768",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  peeka attach 12345                  # Attach to process 12345
  peeka watch "mymodule.func"         # Watch function calls (must attach first)
  peeka stack "mod.func"              # Stack trace (must attach first)
  peeka detach                        # Detach from current process
  peeka reset                         # Reset all enhancements
        """,
    )

    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

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
        "--condition-express",
        dest="condition_express",
        type=str,
        help='Condition expression (e.g., "params[0] > 100")',
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
        "--condition-express",
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
        choices=["overview", "start", "stop", "top", "dump", "gc"],
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

    detach_parser = subparsers.add_parser(
        "detach", help="Detach from the target process"
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
        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            return 1

    except KeyboardInterrupt:
        print("\n", file=sys.stderr)
        return 130
    except Exception as e:
        print(f'{{"error": "{e}"}}', file=sys.stderr)
        return 1


def cmd_attach(args) -> int:
    target_pid = args.pid
    print(f"[Peeka] Attaching to process {target_pid}...", file=sys.stderr)

    attacher = ProcessAttacher(target_pid)

    try:
        if attacher.attach():
            print("[Peeka] Successfully attached!", file=sys.stderr)
            print(f"[Peeka] Socket path: {attacher.get_socket_path()}", file=sys.stderr)
            return 0
        else:
            print("[Peeka] Failed to attach", file=sys.stderr)
            return 1
    finally:
        attacher.cleanup()


def cmd_detach(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        print(json.dumps({"error": connect_result.get("error", "Connection failed")}))
        return 1

    response = streaming_client.send_command({"type": "detach"})
    print(json.dumps(response))

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
        print(json.dumps({"error": str(e)}), file=sys.stderr)
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
        print(json.dumps({"error": connect_result.get("error", "Connection failed")}))
        return 1

    pattern = args.pattern

    command = {
        "type": "watch",
        "action": "start",
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
        print(json.dumps({"error": response.get("error", "Watch start failed")}))
        streaming_client.disconnect()
        return 1

    watch_id = response.get("watch_id")

    print(
        json.dumps({"event": "watch_started", "watch_id": watch_id, "pattern": pattern})
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
        cleanup_watch()

    return 0


def cmd_stack(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
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
        print(json.dumps({"error": connect_result.get("error", "Connection failed")}))
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
        print(json.dumps({"error": response.get("error", "Stack start failed")}))
        streaming_client.disconnect()
        return 1

    stack_id = response.get("stack_id")

    print(
        json.dumps({"event": "stack_started", "stack_id": stack_id, "pattern": pattern})
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
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        print(json.dumps({"error": connect_result.get("error", "Connection failed")}))
        return 1

    command = {
        "type": "logger",
        "action": args.action,
        "logger": args.logger,
        "level": args.level,
        "pattern": args.pattern,
    }

    response = streaming_client.send_command(command)
    print(json.dumps(response))

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_memory(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        print(json.dumps({"error": connect_result.get("error", "Connection failed")}))
        return 1

    command = {
        "type": "memory",
        "action": args.action,
        "nframe": args.nframe,
        "limit": args.limit,
        "group_by": args.group_by,
        "filename": args.filename,
    }

    response = streaming_client.send_command(command)
    print(json.dumps(response))

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_vmtool(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        print(json.dumps({"error": connect_result.get("error", "Connection failed")}))
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
    print(json.dumps(response))

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_reset(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        print(json.dumps({"error": connect_result.get("error", "Connection failed")}))
        return 1

    action = "list" if args.list else "reset"

    command = {
        "type": "reset",
        "action": action,
        "pattern": args.pattern,
    }

    response = streaming_client.send_command(command)
    print(json.dumps(response))

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_monitor(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
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
        print(json.dumps({"error": connect_result.get("error", "Connection failed")}))
        return 1

    pattern = args.pattern

    command = {
        "type": "monitor",
        "action": "start",
        "pattern": pattern,
        "interval": args.interval,
        "cycles": args.cycles,
    }

    response = streaming_client.send_command(command)

    if response.get("status") != "success":
        print(json.dumps({"error": response.get("error", "Monitor start failed")}))
        streaming_client.disconnect()
        return 1

    monitor_id = response.get("monitor_id")

    print(
        json.dumps(
            {
                "event": "monitor_started",
                "monitor_id": monitor_id,
                "pattern": pattern,
            }
        )
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


def cmd_sc(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        print(json.dumps({"error": connect_result.get("error", "Connection failed")}))
        return 1

    command = {
        "type": "sc",
        "pattern": args.pattern,
        "detail": args.detail,
        "limit": args.limit,
    }

    response = streaming_client.send_command(command)
    print(json.dumps(response))

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


def cmd_sm(args) -> int:
    try:
        socket_path, attached_pid = _check_agent_attached()
    except ValueError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1

    streaming_client = StreamingAgentClient(socket_path)
    connect_result = streaming_client.connect()

    if connect_result.get("status") != "success":
        print(json.dumps({"error": connect_result.get("error", "Connection failed")}))
        return 1

    command = {
        "type": "sm",
        "class_pattern": args.class_pattern,
        "method_pattern": args.method_pattern,
        "detail": args.detail,
    }

    response = streaming_client.send_command(command)
    print(json.dumps(response))

    streaming_client.disconnect()

    return 0 if response.get("status") == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
