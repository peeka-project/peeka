"""
Command-line interface for PeekA debugger
Allows attaching to processes and executing watch commands
"""
import argparse

from .core.attachment import attacher
from .core.watcher import watch_function, unwatch_function


def create_parser():
    """Create argument parser for PeekA CLI."""
    parser = argparse.ArgumentParser(
        description="PeekA - Python Dynamic Debugger",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s watch -f "test.tool.reverse_string"
  %(prog)s watch -f "mymodule.myfunction" --params --return
  %(prog)s attach 12345
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # Watch command
    watch_parser = subparsers.add_parser('watch', help='Watch a function for calls')
    watch_parser.add_argument('-f', '--function', required=True,
                              help='Function to watch in format "module.function_name"')
    watch_parser.add_argument('--condition', default='true',
                              help='Condition expression to filter when to execute the watch')
    watch_parser.add_argument('--params', action='store_true', default=True,
                              help='Include function parameters in output (default: True)')
    watch_parser.add_argument('--no-params', dest='params', action='store_false',
                              help='Exclude function parameters from output')
    watch_parser.add_argument('--return', dest='return_val', action='store_true', default=True,
                              help='Include return value in output (default: True)')
    watch_parser.add_argument('--no-return', dest='return_val', action='store_false',
                              help='Exclude return value from output')
    watch_parser.add_argument('--exceptions', action='store_true', default=True,
                              help='Include exceptions in output (default: True)')
    watch_parser.add_argument('--no-exceptions', dest='exceptions', action='store_false',
                              help='Exclude exceptions from output')
    watch_parser.add_argument('--mask', action='store_true',
                              help='Mask sensitive information')

    # Attach command
    attach_parser = subparsers.add_parser('attach', help='Attach to a running Python process')
    attach_parser.add_argument('pid', type=int, help='Process ID to attach to')

    # Unwatch command
    unwatch_parser = subparsers.add_parser('unwatch', help='Remove watch from a function')
    unwatch_parser.add_argument('-f', '--function', required=True,
                                help='Function to unwatch in format "module.function_name"')

    # Detach command
    detach_parser = subparsers.add_parser('detach', help='Detach from currently attached process')

    return parser


def execute_watch(args):
    """Execute the watch command."""
    print(f"Setting up watch for function: {args.function}")

    watch_function(
        function_id=args.function,
        condition=args.condition,
        include_params=args.params,
        include_return=args.return_val,
        include_exceptions=args.exceptions,
        mask=args.mask
    )
    print(f"Successfully watching {args.function}")


def execute_attach(args):
    """Execute the attach command."""
    success = attacher.attach(args.pid)
    if success:
        print(f"Attached to process {args.pid}. Ready to execute commands.")
        print("Use 'detach' to disconnect or Ctrl+C to exit.")

        # Interactive command loop
        try:
            while True:
                try:
                    command = input("PeekA> ").strip()
                    if command.lower() in ['exit', 'quit']:
                        break
                    elif command.lower() == 'detach':
                        execute_detach(None)
                        break
                    elif command.startswith('watch -f '):
                        # Extract function name from command like "watch -f module.func"
                        func_name = command.split(' -f ')[1].split()[0]

                        # Extract any additional options
                        options = {}
                        if '--params' in command:
                            options['include_params'] = True
                        if '--no-params' in command:
                            options['include_params'] = False
                        if '--return' in command:
                            options['include_return'] = True
                        if '--no-return' in command:
                            options['include_return'] = False
                        if '--exceptions' in command:
                            options['include_exceptions'] = True
                        if '--no-exceptions' in command:
                            options['include_exceptions'] = False
                        if '--condition' in command:
                            condition_parts = command.split('--condition')
                            if len(condition_parts) > 1:
                                condition = condition_parts[1].split()[0]
                                options['condition'] = condition

                        print(f"Setting up remote watch for: {func_name}")
                        # Use the attacher's remote watch functionality instead of local watch
                        attacher.execute_remote_watch(func_name, **options)
                    elif command == 'help':
                        print("Available commands: watch, detach, exit, quit, help")
                    else:
                        print(f"Unknown command: {command}. Type 'help' for available commands.")
                except KeyboardInterrupt:
                    print("\nExiting...")
                    break
        except KeyboardInterrupt:
            print("\nDetaching from process...")
    else:
        print(f"Failed to attach to process {args.pid}")


def execute_detach(args):
    """Execute the detach command."""
    success = attacher.detach()
    if success:
        print("Successfully detached from process")
    else:
        print("Failed to detach from process or not attached")


def execute_unwatch(args):
    """Execute the unwatch command."""
    print(f"Removing watch from function: {args.function}")
    unwatch_function(args.function)
    print(f"Successfully removed watch from {args.function}")


def main():
    """Main entry point for PeekA CLI."""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == 'watch':
        execute_watch(args)
    elif args.command == 'attach':
        execute_attach(args)
    elif args.command == 'detach':
        execute_detach(args)
    elif args.command == 'unwatch':
        execute_unwatch(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
