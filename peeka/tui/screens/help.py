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
| `T` | Trace - Call tree tracing |
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

## Trace View

- Enter a function pattern like `module.Class.method`
- Set trace depth (1-5, default: 3)
- Optionally add a condition like `cost > 50`
- View call tree with color-coded timing:
  - 🟢 Green: < 10ms
  - 🟡 Yellow: 10-100ms
  - 🔴 Red: >= 100ms
- Press `C` to clear tree
- Press `Delete` to stop all traces

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
        help_container = Container(
            Markdown(HELP_TEXT, id="help-content"),
            id="help-container",
        )
        help_container.border_title = "Help"
        help_container.border_subtitle = "Press ESC to close"
        yield help_container

    async def action_dismiss(self, *, result: None = None) -> None:
        """Close the help screen."""
        self.dismiss(result)
