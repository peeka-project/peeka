"""
PeekaApp - Main TUI Application
"""

import asyncio
import signal
import threading
import time
import uuid

from typing import Any, Callable, Dict, List, Optional

from textual.app import App
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
    ACTIVITY_LIMIT = 500

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
        self._activity_entries: List[Dict[str, Any]] = []
        self._activity_listeners: List[Callable[[Dict[str, Any]], None]] = []
        self._activity_lock = threading.Lock()
        self._activity_seq = 0
        self.client_instance_id = f"tui-{uuid.uuid4().hex[:6]}"

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

        # Register signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGHUP, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.ensure_future(self.action_quit()))

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

    @staticmethod
    def _normalize_activity_level(severity: str) -> str:
        """Map Textual notification severities to log-style levels."""
        level_map = {
            "information": "INFO",
            "warning": "WARNING",
            "error": "ERROR",
        }
        return level_map.get(str(severity).lower(), str(severity).upper())

    def record_client_activity(
        self, level: str, message: str, source: str = "client"
    ) -> None:
        """Store a client-side activity entry and notify listeners."""
        entry = {
            "level": level.upper(),
            "message": message,
            "source": source,
            "timestamp": time.time(),
        }

        with self._activity_lock:
            self._activity_seq += 1
            entry["seq"] = self._activity_seq
            self._activity_entries.append(dict(entry))
            if len(self._activity_entries) > self.ACTIVITY_LIMIT:
                self._activity_entries = self._activity_entries[-self.ACTIVITY_LIMIT :]
            listeners = list(self._activity_listeners)

        for listener in listeners:
            try:
                listener(dict(entry))
            except Exception:
                continue

    def get_client_activity_entries(self, after_seq: int = 0) -> List[Dict[str, Any]]:
        """Return buffered client activity entries after a sequence number."""
        with self._activity_lock:
            return [
                dict(entry)
                for entry in self._activity_entries
                if int(entry.get("seq", 0)) > after_seq
            ]

    def register_activity_listener(
        self, listener: Callable[[Dict[str, Any]], None]
    ) -> None:
        """Subscribe to future client activity entries."""
        with self._activity_lock:
            if listener not in self._activity_listeners:
                self._activity_listeners.append(listener)

    def unregister_activity_listener(
        self, listener: Callable[[Dict[str, Any]], None]
    ) -> None:
        """Remove a previously registered activity listener."""
        with self._activity_lock:
            if listener in self._activity_listeners:
                self._activity_listeners.remove(listener)

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: str = "information",
        timeout: Optional[float] = None,
        markup: bool = True,
    ) -> None:
        """Mirror Textual notifications into the client activity buffer."""
        rendered_message = f"{title}: {message}" if title else message
        self.record_client_activity(
            self._normalize_activity_level(severity),
            rendered_message,
        )
        super().notify(
            message,
            title=title,
            severity=severity,
            timeout=timeout,
            markup=markup,
        )

    async def action_quit(self) -> None:
        from peeka.tui.screens.main import MainScreen

        for screen in self.screen_stack:
            if isinstance(screen, MainScreen):
                screen._cleanup_all_views()
                break
        self.exit()
