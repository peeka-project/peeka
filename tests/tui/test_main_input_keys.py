"""Keyboard behavior of MainScreen around text inputs (Esc, Enter, Tab)."""

import pytest
from textual.widgets import Input, OptionList

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen


async def _no_connect(self) -> None:
    """Skip the real agent connection (and its retry backoff) in tests."""


async def _push_main(app: PeekaApp, pilot, monkeypatch) -> MainScreen:
    monkeypatch.setattr(MainScreen, "_connect", _no_connect)
    main_screen = MainScreen(pid=12345, session_id="test-session", socket_path="/tmp/test.sock")
    await app.push_screen(main_screen)
    await pilot.pause()
    return main_screen


class TestEscapeLeavesTextEntryFirst:
    """Esc while typing must not go back (which detaches and stops watches)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_escape_in_input_blurs_instead_of_going_back(self, monkeypatch):
        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = await _push_main(app, pilot, monkeypatch)
            main_screen.action_switch_tab("watch")
            await pilot.pause()

            pattern_input = main_screen.query_one("#watch-pattern #ac-input", Input)
            pattern_input.focus()
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()

            assert app.screen is main_screen
            assert app.focused is None

            await pilot.press("escape")
            await pilot.pause()

            assert app.screen is not main_screen

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_escape_closes_completion_dropdown_and_keeps_focus(self, monkeypatch):
        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = await _push_main(app, pilot, monkeypatch)
            main_screen.action_switch_tab("watch")
            await pilot.pause()

            pattern_input = main_screen.query_one("#watch-pattern #ac-input", Input)
            pattern_input.focus()
            dropdown = main_screen.query_one("#watch-pattern #ac-dropdown", OptionList)
            dropdown.add_option("demo.Calculator.add")
            dropdown.display = True
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()

            assert app.screen is main_screen
            assert dropdown.display is False
            assert app.focused is pattern_input

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_escape_in_plain_input_blurs(self, monkeypatch):
        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = await _push_main(app, pilot, monkeypatch)
            main_screen.action_switch_tab("watch")
            await pilot.pause()

            condition_input = main_screen.query_one("#watch-condition", Input)
            condition_input.focus()
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()

            assert app.screen is main_screen
            assert app.focused is None


ENTER_CASES = [
    ("watch", "WatchView", "_start_watch", "#watch-pattern #ac-input"),
    ("watch", "WatchView", "_start_watch", "#watch-condition"),
    ("trace", "TraceView", "_start_trace", "#trace-pattern #ac-input"),
    ("trace", "TraceView", "_start_trace", "#trace-min-duration"),
    ("stack", "StackView", "_start_stack", "#stack-pattern #ac-input"),
    ("monitor", "MonitorView", "_start_monitor", "#monitor-pattern #ac-input"),
    ("monitor", "MonitorView", "_start_monitor", "#monitor-interval"),
]


class TestEnterInInputStarts:
    """Enter in a view's input starts the action, same as its button."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    @pytest.mark.parametrize("tab_id,view_name,method,selector", ENTER_CASES)
    async def test_enter_in_input_starts_action(self, monkeypatch, tab_id, view_name, method, selector):
        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = await _push_main(app, pilot, monkeypatch)
            main_screen.action_switch_tab(tab_id)
            await pilot.pause()

            view = main_screen.query_one(view_name)
            calls = []

            async def _record() -> None:
                calls.append(method)

            monkeypatch.setattr(view, method, _record)

            field = main_screen.query_one(selector, Input)
            field.focus()
            await pilot.pause()
            await pilot.press("x")
            await pilot.press("enter")
            await pilot.pause()

            assert calls == [method]
            assert app.screen is main_screen

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_enter_closes_completion_dropdown(self, monkeypatch):
        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = await _push_main(app, pilot, monkeypatch)
            main_screen.action_switch_tab("watch")
            await pilot.pause()

            view = main_screen.query_one("WatchView")

            async def _noop() -> None:
                return None

            monkeypatch.setattr(view, "_start_watch", _noop)

            pattern_input = main_screen.query_one("#watch-pattern #ac-input", Input)
            pattern_input.focus()
            dropdown = main_screen.query_one("#watch-pattern #ac-dropdown", OptionList)
            dropdown.add_option("demo.Calculator.add")
            dropdown.display = True
            await pilot.pause()

            await pilot.press("enter")
            await pilot.pause()

            assert dropdown.display is False

