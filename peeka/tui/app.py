"""
PeekaApp - Main TUI Application
"""

from textual.app import App, ComposeResult
from textual.binding import Binding

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
        self.push_screen(ProcessSelectorScreen())

    def action_help(self) -> None:
        """Show help screen."""
        from peeka.tui.screens.help import HelpScreen

        self.push_screen(HelpScreen())
