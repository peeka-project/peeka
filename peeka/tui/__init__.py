"""
Peeka TUI - Interactive Terminal User Interface

This module provides a full-featured TUI for Peeka diagnostics.
Requires: pip install peeka[tui]
"""

import atexit
import argparse
import os
import sys


def main() -> None:
    """Entry point for the peeka TUI command."""
    # Parse arguments before importing textual
    parser = argparse.ArgumentParser(
        prog="peeka", description="Peeka - Python Runtime Diagnostics TUI"
    )
    parser.add_argument(
        "--theme", type=str, default=None, help="Color theme name (default: dracula)"
    )
    parser.add_argument(
        "--list-themes", action="store_true", help="List available themes and exit"
    )
    args = parser.parse_args()

    # Handle --list-themes (before checking for textual)
    if args.list_themes:
        from peeka.tui.app import (
            PEEKA_CUSTOM_THEMES,
            DEFAULT_THEME,
            BUILTIN_THEMES,
        )

        # Print header
        print("Available themes:")
        print()
        print(f"{'name':<25} {'type':<30}")
        print("-" * 55)

        # Print built-in themes
        for name, config in sorted(BUILTIN_THEMES.items()):
            is_dark = config.get("dark", True)
            theme_type = "dark" if is_dark else "light"
            default_marker = " (default)" if name == DEFAULT_THEME else ""
            print(f"{name:<25} {theme_type:<30}{default_marker}")

        # Print custom themes
        for name in sorted(PEEKA_CUSTOM_THEMES):
            # Determine if custom theme is dark/light based on name
            if "dark" in name:
                theme_type = "dark, high-contrast"
            else:
                theme_type = "light, high-contrast"
            default_marker = " (default)" if name == DEFAULT_THEME else ""
            print(f"{name:<25} {theme_type:<30}{default_marker}")

        sys.exit(0)

    # Validate --theme argument
    if args.theme is not None:
        from peeka.tui.app import BUILTIN_THEMES, PEEKA_CUSTOM_THEMES

        valid_themes = set(BUILTIN_THEMES.keys()) | set(PEEKA_CUSTOM_THEMES)
        if args.theme not in valid_themes:
            print(
                f"Error: Unknown theme '{args.theme}'. "
                "Use --list-themes to see available themes.",
                file=sys.stderr,
            )
            sys.exit(1)

    # Check for textual
    try:
        from textual.app import App
    except ImportError:
        print("Error: TUI dependencies not installed.", file=sys.stderr)
        print("Install with: pip install peeka[tui]", file=sys.stderr)
        sys.exit(1)

    from peeka.tui.app import PeekaApp

    # Ensure terminal capability env vars are set (needed in docker exec, ssh, etc.)
    os.environ.setdefault("TERM", "xterm-256color")
    os.environ.setdefault("COLORTERM", "truecolor")

    app = PeekaApp(theme=args.theme)

    # atexit fallback: ensure cleanup runs even if signal handlers don't fire
    def _atexit_cleanup() -> None:
        try:
            from peeka.tui.screens.main import MainScreen
            for screen in app.screen_stack:
                if isinstance(screen, MainScreen):
                    screen._cleanup_all_views()
                    break
        except Exception:
            pass  # Best-effort: swallow to protect target process

    atexit.register(_atexit_cleanup)
    app.run()


if __name__ == "__main__":
    main()
