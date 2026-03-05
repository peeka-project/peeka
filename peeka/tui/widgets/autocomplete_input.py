"""AutoComplete Input Widget - Input with fuzzy completion dropdown."""

from typing import Callable, List, Optional, Union

from textual.app import ComposeResult
from textual.events import Key
from textual.message import Message
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option

try:
    from textual.fuzzy import Matcher
except ImportError:
    Matcher = None

_DEBOUNCE_SECONDS = 0.3


class AutoCompleteInput(Widget):
    """Input widget with auto-completion dropdown."""

    DEFAULT_CSS = """
    AutoCompleteInput {
        width: 1fr;
        height: auto;
        layout: vertical;
    }

    AutoCompleteInput > #ac-input {
        width: 100%;
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
        completions_callback: Optional[Callable[[str], Union[List[str]]]] = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.placeholder = placeholder
        self._completions_callback = completions_callback
        self._completions: List[str] = []
        self._matcher = Matcher if Matcher else None
        self._debounce_timer: Optional[Timer] = None
        self._pending_prefix: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield Input(placeholder=self.placeholder, id="ac-input")
        yield OptionList(id="ac-dropdown")

    def on_mount(self) -> None:
        """Hide dropdown initially."""
        self.query_one("#ac-dropdown").display = False

    async def on_input_changed(self, event: Input.Changed) -> None:
        text = event.value
        dropdown = self.query_one("#ac-dropdown", OptionList)

        if self._debounce_timer is not None:
            self._debounce_timer.stop()
            self._debounce_timer = None

        if not text:
            dropdown.display = False
            return

        if self._completions:
            filtered = self._filter_completions(text)
            if filtered:
                dropdown.clear_options()
                for item in filtered[:10]:
                    dropdown.add_option(Option(item))
                dropdown.display = True
            else:
                dropdown.display = False

        self._pending_prefix = text
        self._debounce_timer = self.set_timer(
            _DEBOUNCE_SECONDS,
            self._trigger_fetch,
        )

    def _trigger_fetch(self) -> None:
        prefix = self._pending_prefix
        if not prefix:
            return

        def _fetch_sync() -> None:
            if self._completions_callback:
                items = self._completions_callback(prefix)
            else:
                items = []
            if self._pending_prefix != prefix:
                return
            self._completions = items
            self.app.call_from_thread(self._apply_completions, prefix)

        self.run_worker(_fetch_sync, thread=True, exclusive=True, group="autocomplete")

    def _apply_completions(self, prefix: str) -> None:
        try:
            current_text = self.query_one("#ac-input", Input).value
        except Exception:
            return
        if current_text != prefix:
            prefix = current_text

        if not prefix:
            return

        dropdown = self.query_one("#ac-dropdown", OptionList)
        filtered = self._filter_completions(prefix)

        if filtered:
            dropdown.clear_options()
            for item in filtered[:10]:
                dropdown.add_option(Option(item))
            dropdown.display = True
        else:
            dropdown.display = False

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
