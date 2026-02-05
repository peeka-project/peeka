"""
AutoComplete Input Widget - Input with fuzzy completion dropdown.
"""

from typing import Awaitable, Callable, List, Optional, Union

from textual.app import ComposeResult
from textual.events import Key
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option

try:
    from textual.fuzzy import Matcher
except ImportError:
    Matcher = None


class AutoCompleteInput(Widget):
    """Input widget with auto-completion dropdown."""

    DEFAULT_CSS = """
    AutoCompleteInput {
        width: 1fr;
        height: 3;
        layout: vertical;
    }
    
    AutoCompleteInput > #ac-input {
        width: 100%;
        height: 3;
    }
    
    AutoCompleteInput > #ac-dropdown {
        max-height: 10;
        border: solid $accent;
        background: $surface;
        display: none;
    }
    """

    class Selected(Message):
        """Emitted when a completion is selected."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def __init__(
        self,
        placeholder: str = "",
            completions_callback: Optional[
                Callable[[str], Union[List[str], Awaitable[List[str]]]]
            ] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.placeholder = placeholder
        self._completions_callback = completions_callback
        self._completions: List[str] = []
        self._matcher = Matcher if Matcher else None

    def compose(self) -> ComposeResult:
        yield Input(placeholder=self.placeholder, id="ac-input")
        yield OptionList(id="ac-dropdown")

    def on_mount(self) -> None:
        """Hide dropdown initially."""
        self.query_one("#ac-dropdown").display = False

    async def on_input_changed(self, event: Input.Changed) -> None:
        """Update completions when input changes."""
        text = event.value
        dropdown = self.query_one("#ac-dropdown", OptionList)

        if not text or len(text) < 2:
            dropdown.display = False
            return

        # Get completions from callback
        if self._completions_callback:
            self._completions = await self._get_completions(text)

        # Filter with fuzzy matching
        filtered = self._filter_completions(text)

        if filtered:
            dropdown.clear_options()
            for item in filtered[:10]:  # Limit to 10 items
                dropdown.add_option(Option(item))
            dropdown.display = True
        else:
            dropdown.display = False

    async def _get_completions(self, prefix: str) -> List[str]:
        """Get completions from callback."""
        if self._completions_callback:
            result = self._completions_callback(prefix)
            if hasattr(result, "__await__"):
                result = await result  # type: ignore
            return result  # type: ignore
        return []

    def _filter_completions(self, query: str) -> List[str]:
        """Filter completions using fuzzy matching."""
        if not self._completions:
            return []

        if self._matcher:
            matcher = self._matcher(query, case_sensitive=False)
            matches = []
            for item in self._completions:
                score = matcher.match(item)
                if score > 0:
                    matches.append((score, item))
            matches.sort(reverse=True, key=lambda x: x[0])
            return [m[1] for m in matches]
        else:
            query_lower = query.lower()
            return [c for c in self._completions if query_lower in c.lower()]

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle completion selection."""
        value = str(event.option.prompt)
        self.query_one("#ac-input", Input).value = value
        self.query_one("#ac-dropdown").display = False
        self.post_message(self.Selected(value))

    async def on_key(self, event: Key) -> None:
        """Handle Tab key to accept completion."""
        dropdown = self.query_one("#ac-dropdown", OptionList)

        if event.key == "tab" and dropdown.display and dropdown.option_count > 0:
            # Accept the highlighted option (or first if none highlighted)
            highlighted = dropdown.highlighted
            if highlighted is not None:
                option = dropdown.get_option_at_index(highlighted)
            else:
                option = dropdown.get_option_at_index(0)

            value = str(option.prompt)
            self.query_one("#ac-input", Input).value = value
            dropdown.display = False
            self.post_message(self.Selected(value))
            event.prevent_default()
            event.stop()

    @property
    def value(self) -> str:
        """Get current input value."""
        return self.query_one("#ac-input", Input).value

    @value.setter
    def value(self, new_value: str) -> None:
        """Set input value."""
        self.query_one("#ac-input", Input).value = new_value
