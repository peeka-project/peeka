"""
AutoComplete Input Widget - Input with fuzzy completion dropdown.
"""

from typing import Callable, List, Optional

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option
from textual.widget import Widget

try:
    from textual.fuzzy import Matcher
except ImportError:
    Matcher = None


class AutoCompleteInput(Widget):
    """Input widget with auto-completion dropdown."""

    class Selected(Message):
        """Emitted when a completion is selected."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()

    def __init__(
        self,
        placeholder: str = "",
        completions_callback: Optional[Callable[[str], List[str]]] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.placeholder = placeholder
        self._completions_callback = completions_callback
        self._completions: List[str] = []
        self._matcher = Matcher() if Matcher else None

    def compose(self) -> ComposeResult:
        yield Vertical(
            Input(placeholder=self.placeholder, id="ac-input"),
            OptionList(id="ac-dropdown"),
            id="ac-container",
        )

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
                return await result
            return result
        return []

    def _filter_completions(self, query: str) -> List[str]:
        """Filter completions using fuzzy matching."""
        if not self._completions:
            return []

        if self._matcher:
            # Use Textual's fuzzy matcher
            matches = []
            for item in self._completions:
                score = self._matcher.match(query, item)
                if score > 0:
                    matches.append((score, item))
            matches.sort(reverse=True, key=lambda x: x[0])
            return [m[1] for m in matches]
        else:
            # Fallback: simple prefix matching
            query_lower = query.lower()
            return [c for c in self._completions if query_lower in c.lower()]

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Handle completion selection."""
        value = str(event.option.prompt)
        self.query_one("#ac-input", Input).value = value
        self.query_one("#ac-dropdown").display = False
        self.post_message(self.Selected(value))

    @property
    def value(self) -> str:
        """Get current input value."""
        return self.query_one("#ac-input", Input).value

    @value.setter
    def value(self, new_value: str) -> None:
        """Set input value."""
        self.query_one("#ac-input", Input).value = new_value
