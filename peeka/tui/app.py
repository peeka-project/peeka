"""
PeekaApp - Main TUI Application
"""

from typing import Dict, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.theme import Theme

from peeka.tui.screens.process_selector import ProcessSelectorScreen

# Module constants
DEFAULT_THEME = "dracula"

PEEKA_CUSTOM_THEMES = ["peeka-hc-dark", "peeka-hc-light"]

BUILTIN_THEMES = {
    "textual-dark": {"dark": True},
    "textual-light": {"dark": False},
    "nord": {"dark": True},
    "gruvbox": {"dark": True},
    "catppuccin-mocha": {"dark": True},
    "textual-ansi": {"dark": True},
    "dracula": {"dark": True},
    "tokyo-night": {"dark": True},
    "monokai": {"dark": True},
    "flexoki": {"dark": True},
    "catppuccin-latte": {"dark": False},
    "solarized-light": {"dark": False},
    "solarized-dark": {"dark": True},
    "rose-pine": {"dark": True},
    "rose-pine-moon": {"dark": True},
    "rose-pine-dawn": {"dark": False},
    "atom-one-dark": {"dark": True},
    "atom-one-light": {"dark": False},
}


class PeekaApp(App):
    """Peeka TUI Application."""

    TITLE = "Peeka"
    SUB_TITLE = "Python Runtime Diagnostics"
    CSS_PATH = "styles/peeka.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("?", "help", "Help"),
    ]

    def __init__(self, theme: Optional[str] = None) -> None:
        """Initialize PeekaApp.

        Args:
            theme: Theme name to use. Defaults to None, which resolves to "dracula".
        """
        super().__init__()
        self._theme_name = theme if theme is not None else DEFAULT_THEME

    def on_mount(self) -> None:
        """Called when app is mounted."""
        # Register high-contrast dark theme
        self.register_theme(
            Theme(
                name="peeka-hc-dark",
                primary="#FFFFFF",
                secondary="#00FFFF",
                accent="#FFD700",
                foreground="#FFFFFF",
                background="#000000",
                success="#00FF00",
                warning="#FFFF00",
                error="#FF0000",
                surface="#1A1A1A",
                panel="#262626",
                dark=True,
            )
        )
        # Register high-contrast light theme
        self.register_theme(
            Theme(
                name="peeka-hc-light",
                primary="#0000CC",
                secondary="#660099",
                accent="#CC6600",
                foreground="#000000",
                background="#FFFFFF",
                success="#006600",
                warning="#996600",
                error="#CC0000",
                surface="#F0F0F0",
                panel="#E0E0E0",
                dark=False,
            )
        )
        self.theme = self._theme_name

        self.push_screen(ProcessSelectorScreen())

    def get_css_variables(self) -> Dict[str, str]:
        variables = super().get_css_variables()
        primary = variables.get("primary", "")
        if primary:
            variables["border-blurred"] = primary + "70"
        return variables

    def action_help(self) -> None:
        from peeka.tui.screens.help import HelpScreen

        self.push_screen(HelpScreen())

    async def action_quit(self) -> None:
        from peeka.tui.screens.main import MainScreen

        for screen in self.screen_stack:
            if isinstance(screen, MainScreen):
                screen._cleanup_all_views()
                break
        self.exit()
