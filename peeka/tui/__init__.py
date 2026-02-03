"""
Peeka TUI - Interactive Terminal User Interface

This module provides a full-featured TUI for Peeka diagnostics.
Requires: pip install peeka[tui]
"""


def main() -> None:
    """Entry point for the peeka TUI command."""
    try:
        from textual.app import App
    except ImportError:
        import sys

        print("Error: TUI dependencies not installed.", file=sys.stderr)
        print("Install with: pip install peeka[tui]", file=sys.stderr)
        sys.exit(1)

    from peeka.tui.app import PeekaApp

    app = PeekaApp()
    app.run()


if __name__ == "__main__":
    main()
