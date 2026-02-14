"""
PeekaApp - Main TUI Application
"""

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.theme import Theme

from peeka.tui.screens.process_selector import ProcessSelectorScreen


class PeekaApp(App):
    """Peeka TUI Application."""

    TITLE = "Peeka"
    SUB_TITLE = "Python Runtime Diagnostics"
    CSS_PATH = "styles/peeka.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("?", "help", "Help"),
    ]

    def on_mount(self) -> None:
        """Called when app is mounted."""
        # Register Catppuccin Mocha theme
        self.register_theme(
            Theme(
                name="catppuccin-mocha",
                primary="#b4befe",  # Lavender
                secondary="#cba6f7",  # Mauve
                accent="#cba6f7",  # Mauve
                foreground="#cdd6f4",  # Text
                background="#1e1e2e",  # Base
                success="#a6e3a1",  # Green
                warning="#f9e2af",  # Yellow
                error="#f38ba8",  # Red
                surface="#313244",  # Surface0
                panel="#313244",  # Surface0
            )
        )
        self.theme = "catppuccin-mocha"

        self.push_screen(ProcessSelectorScreen())

    def action_help(self) -> None:
        """Show help screen."""
        from peeka.tui.screens.help import HelpScreen

        self.push_screen(HelpScreen())
