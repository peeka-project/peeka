"""
Main CLI Entry Point
Provides command-line interface for Peeka
"""

import argparse
import sys

from peeka.core.attach import ProcessAttacher
from peeka.core.client import AgentClient


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        prog='peeka',
        description='Peeka - Python Diagnostic Tool based on PEP 768',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  peeka attach 12345           # Attach to process 12345
  peeka watch 12345 "mymodule.func"   # Watch function calls
  peeka version                # Show version
        """
    )

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s 0.1.0'
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Attach command
    attach_parser = subparsers.add_parser(
        'attach',
        help='Attach to a running Python process'
    )
    attach_parser.add_argument(
        '--pid', '-p',
        type=int,
        help='Process ID to attach to'
    )
    attach_parser.add_argument(
        '--name',
        type=str,
        help='Process name to attach to'
    )

    # Watch command
    watch_parser = subparsers.add_parser(
        'watch',
        help='Watch function calls in target process'
    )
    watch_parser.add_argument(
        '--pid', '-p',
        type=int,
        help='Process ID'
    )
    attach_parser.add_argument(
        '--name',
        type=str,
        help='Process name to attach to'
    )
    watch_parser.add_argument(
        'pattern',
        help='Function pattern to watch (e.g., "mymodule.MyClass.method")'
    )
    watch_parser.add_argument(
        '-x', '--depth',
        type=int,
        default=2,
        help='Output depth for nested objects (default: 2)'
    )
    watch_parser.add_argument(
        '-n', '--times',
        type=int,
        default=-1,
        help='Number of times to capture (-1 for infinite, default: -1)'
    )



    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    try:
        if args.command == 'attach':
            return cmd_attach(args)
        elif args.command == 'watch':
            return cmd_watch(args)
        else:
            print(f"Unknown command: {args.command}", file=sys.stderr)
            return 1

    except KeyboardInterrupt:
        print("\n[Peeka] Interrupted by user")
        return 130
    except Exception as e:
        print(f"[Peeka] Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def cmd_attach(args):
    """Handle attach command"""
    pid = args.pid
    if not pid:
        # 如果没有传 pid，从用户输入获取
        pid = int(input("Enter the PID of the target process: ").strip())
    print(f"[Peeka] Attaching to process {args.pid}...")

    attacher = ProcessAttacher(args.pid)

    try:
        if attacher.attach():
            print("[Peeka] Successfully attached!")
            print(f"[Peeka] Socket path: {attacher.get_socket_path()}")
            print("[Peeka] You can now send commands to the target process")
            return 0
        else:
            print("[Peeka] Failed to attach", file=sys.stderr)
            return 1
    finally:
        attacher.cleanup()


def cmd_watch(args):
    """Handle watch command"""
    print(f"[Peeka] Watching {args.pattern} in process {args.pid}...")
    print(f"[Peeka] Depth: {args.depth}, Times: {args.times}")

    attacher = ProcessAttacher(args.pid)

    if not attacher.attach():
        print("[Peeka] Failed to attach to process", file=sys.stderr)
        attacher.cleanup()
        return 1

    socket_path = attacher.get_socket_path()
    client = AgentClient(socket_path)

    command = {
        'type': 'watch',
        'action': 'start',
        'pattern': args.pattern,
        'depth': args.depth,
        'times': args.times
    }

    print(f"[Peeka] Sending command to agent at {socket_path}...")
    response = client.send_command(command)

    status = response.get('status')
    if status == 'success':
        print("[Peeka] Watch started")
        if 'message' in response:
            print(f"[Peeka] {response['message']}")
        if 'watch_id' in response:
            print(f"[Peeka] Watch ID: {response['watch_id']}")
        if 'note' in response:
            print(f"[Peeka] Note: {response['note']}")
        # Leave agent running for ongoing watch consumption; no cleanup here
        return 0

    print(f"[Peeka] Agent error: {response.get('error', 'unknown error')}", file=sys.stderr)
    if 'hint' in response:
        print(f"[Peeka] Hint: {response['hint']}", file=sys.stderr)
    attacher.cleanup()
    return 1



if __name__ == '__main__':
    sys.exit(main())
