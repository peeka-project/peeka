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
| `1` | Dashboard - Process overview |
| `2` | Watch - Function observation |
| `3` | Trace - Call tree tracing |
| `4` | Stack - Call stack tracing |
| `5` | Monitor - Performance stats |
| `6` | Memory - Memory analysis |
| `7` | Logger - Logger management |
| `8` | Inspect - Object inspection |
| `9` | Threads - Thread management |
| `0` | Top - Top processes |

## Process Selector

| Key | Action |
|-----|--------|
| `R` | Refresh process list |
| `Enter` | Attach to selected process |
| `↑/↓` | Navigate processes |

## View-Specific Bindings

### Dashboard View
- `r` - Refresh

### Watch View
- `Enter` - Start Watch
- `Delete` - Stop All

### Trace View
- `Enter` - Start Trace
- `Delete` - Stop All
- `c` - Clear Tree
- Color-coded timing:
  - 🟢 Green: < 10ms
  - 🟡 Yellow: 10-100ms
  - 🔴 Red: >= 100ms

### Stack View
- `Enter` - Start Stack
- `Delete` - Stop All

### Monitor View
- `Enter` - Start Monitor
- `Delete` - Stop All

### Memory View
- `r` - Refresh
- `T` (Shift+T) - Toggle Tracking

### Logger View
- `r` - Refresh

### Inspect View
- `Enter` - Inspect

### Threads View
- `r` - Refresh

### Top View
- `r` - Reset Stats

## Tips

- Use number keys 1-9, 0 to switch between tabs
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
