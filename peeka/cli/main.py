"""
Main CLI Entry Point
Provides command-line interface for Peeka
"""

import argparse
import os
import sys

from peeka.core.attach import ProcessAttacher


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
        'pid',
        type=int,
        help='Process ID to attach to'
    )

    # Watch command
    watch_parser = subparsers.add_parser(
        'watch',
        help='Watch function calls in target process'
    )
    watch_parser.add_argument(
        'pid',
        type=int,
        help='Process ID'
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

    # Demo command
    demo_parser = subparsers.add_parser(
        'demo',
        help='Run demonstration'
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
        elif args.command == 'demo':
            return cmd_demo(args)
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

    try:
        if not attacher.attach():
            print("[Peeka] Failed to attach to process", file=sys.stderr)
            return 1

        # Send watch command
        command = {
            'type': 'watch',
            'action': 'start',
            'pattern': args.pattern,
            'depth': args.depth,
            'times': args.times
        }

        print(f"[Peeka] Command: {command}")
        print("[Peeka] Note: Full watch functionality requires agent communication")
        print("[Peeka] This is a demonstration of the command structure")

        return 0

    finally:
        attacher.cleanup()


def cmd_demo(args):
    """Run demonstration"""
    print("[Peeka] Running demonstration...")
    print()

    # Get current process PID
    pid = os.getpid()
    print(f"[Peeka] Current process PID: {pid}")
    print()

    # Demonstrate attach
    print("=== Demonstrating Attach ===")
    attacher = ProcessAttacher(pid)

    try:
        if attacher.attach():
            print(f"✓ Successfully attached to process {pid}")
            print(f"✓ Session ID: {attacher.session_id}")
            print(f"✓ Socket path: {attacher.get_socket_path()}")
        else:
            print("✗ Failed to attach")
            return 1
    finally:
        print()
        attacher.cleanup()

    print("=== Demo Complete ===")
    print()
    print("Peeka is a Python diagnostic tool based on PEP 768.")
    print("It allows you to attach to running Python processes and")
    print("inspect their behavior without stopping them.")
    print()
    print("Key features:")
    print("  • Process attachment via PEP 768 (Python 3.14+)")
    print("  • Watch function calls and return values")
    print("  • Non-invasive diagnostic commands")
    print("  • Unix domain socket communication")
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
