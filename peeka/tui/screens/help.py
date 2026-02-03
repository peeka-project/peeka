"""
Help Screen - Keyboard shortcuts and usage information.
"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Markdown


HELP_TEXT = """
# Peeka TUI Help

## Global Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+Q` | Quit application |
| `?` | Show this help |
| `Escape` | Go back / Close modal |

## Main Screen Tabs

| Key | Tab |
|-----|-----|
| `D` | Dashboard - Process overview |
| `W` | Watch - Function observation |
| `S` | Stack - Call stack tracing |
| `M` | Monitor - Performance stats |
| `E` | Memory - Memory analysis |
| `L` | Logger - Logger management |
| `I` | Inspect - Object inspection |

## Process Selector

| Key | Action |
|-----|--------|
| `R` | Refresh process list |
| `Enter` | Attach to selected process |
| `↑/↓` | Navigate processes |

## Watch View

- Enter a function pattern like `module.Class.method`
- Optionally add a condition like `params[0] > 10`
- Click Watch or press Enter to start

## Tips

- Use fuzzy search in input fields (type partial names)
- Observations stream in real-time
- Use `jq` patterns from CLI for advanced filtering
"""


class HelpScreen(ModalScreen):
    """Modal screen showing help information."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    def compose(self) -> ComposeResult:
        yield Container(
            Markdown(HELP_TEXT, id="help-content"),
            id="help-container",
        )

    def action_dismiss(self) -> None:
        """Close the help screen."""
        self.app.pop_screen()
