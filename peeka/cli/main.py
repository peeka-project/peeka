"""
Main CLI Entry Point
Provides command-line interface for Peeka
"""

import argparse
import json
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


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="peeka",
        description="Peeka - Python Diagnostic Tool based on PEP 768",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  peeka attach 12345                    # Attach to process 12345
  peeka watch -p 12345 "mymodule.func"  # Watch function calls (streaming JSON)
  peeka watch --name python "mod.func"  # Watch by process name
  peeka version                         # Show version
        """,
    )

    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    attach_parser = subparsers.add_parser(
        "attach", help="Attach to a running Python process"
    )
    attach_parser.add_argument("--pid", "-p", type=int, help="Process ID to attach to")
    attach_parser.add_argument("--name", type=str, help="Process name to attach to")

    watch_parser = subparsers.add_parser(
        "watch", help="Watch function calls in target process"
    )
    watch_parser.add_argument("--pid", "-p", type=int, help="Process ID")
    watch_parser.add_argument("--name", type=str, help="Process name to attach to")
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
        "-c",
        "--condition",
        type=str,
        help='Condition expression (e.g., "params[0] > 100")',
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == "attach":
            return cmd_attach(args)
        elif args.command == "watch":
            return cmd_watch(args)
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
    target_pid = _resolve_pid(args)
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


def cmd_watch(args) -> int:
    target_pid = _resolve_pid(args)

    attacher = ProcessAttacher(target_pid)

    if not attacher.attach():
        print('{"error": "Failed to attach to process"}', file=sys.stderr)
        attacher.cleanup()
        return 1

    socket_path = attacher.get_socket_path()
    streaming_client: Optional[StreamingAgentClient] = None
    watch_id: Optional[str] = None

    def cleanup_watch(signum=None, frame=None):
        nonlocal streaming_client, watch_id
        if streaming_client and watch_id:
            try:
                streaming_client.send_command(
                    {"type": "watch", "action": "stop", "watch_id": watch_id}
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
        attacher.cleanup()
        return 1

    command = {
        "type": "watch",
        "action": "start",
        "pattern": args.pattern,
        "depth": args.depth,
        "times": args.times,
    }

    if args.condition:
        command["condition"] = args.condition

    response = streaming_client.send_command(command)

    if response.get("status") != "success":
        print(json.dumps({"error": response.get("error", "Watch start failed")}))
        streaming_client.disconnect()
        attacher.cleanup()
        return 1

    watch_id = response.get("watch_id")

    print(
        json.dumps(
            {"event": "watch_started", "watch_id": watch_id, "pattern": args.pattern}
        )
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


if __name__ == "__main__":
    sys.exit(main())
