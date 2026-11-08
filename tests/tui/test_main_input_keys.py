"""Keyboard behavior of MainScreen around text inputs (Esc, Enter, Tab)."""

import pytest
from textual.widgets import Input, OptionList, Tabs

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
            assert app.focused is main_screen.query_one("WatchView")

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
            assert app.focused is main_screen.query_one("WatchView")


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


class TestTabReachesInputAfterSwitch:
    """After a digit-key tab switch, one Tab focuses the view's first input."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    @pytest.mark.parametrize(
        "key,selector",
        [
            ("2", "#watch-pattern #ac-input"),
            ("3", "#trace-pattern #ac-input"),
            ("4", "#stack-pattern #ac-input"),
            ("5", "#monitor-pattern #ac-input"),
            ("8", "#inspect-path"),
        ],
    )
    async def test_single_tab_focuses_first_input(self, monkeypatch, key, selector):
        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = await _push_main(app, pilot, monkeypatch)

            await pilot.press(key)
            await pilot.pause()
            assert app.focused is main_screen.query_one("#main-content").active_pane.children[0]

            await pilot.press("tab")
            await pilot.pause()

            assert app.focused is main_screen.query_one(selector, Input)

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_digit_keys_still_switch_tabs_when_view_focused(self, monkeypatch):
        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = await _push_main(app, pilot, monkeypatch)
            tabbed = main_screen.query_one("#main-content")

            for key, tab_id in (("2", "watch"), ("3", "trace"), ("1", "dashboard")):
                await pilot.press(key)
                await pilot.pause()
                assert tabbed.active == tab_id


VIEW_BINDING_CASES = [
    ("2", "WatchView", "action_stop_watches", "delete"),
    ("3", "TraceView", "action_stop_traces", "delete"),
    ("3", "TraceView", "action_drill_trace", "t"),
    ("4", "StackView", "action_stop_stacks", "delete"),
    ("5", "MonitorView", "action_stop_monitors", "delete"),
    ("1", "DashboardView", "action_refresh", "r"),
    ("7", "LoggerView", "action_refresh", "r"),
    ("0", "TopView", "action_reset_stats", "r"),
]


class TestViewBindingsWithoutTyping:
    """A view's own bindings work right after a tab switch and after Esc."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    @pytest.mark.parametrize("tab_key,view_name,action,key", VIEW_BINDING_CASES)
    async def test_view_binding_after_tab_switch(self, monkeypatch, tab_key, view_name, action, key):
        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = await _push_main(app, pilot, monkeypatch)
            view = main_screen.query_one(view_name)
            calls = []
            monkeypatch.setattr(view, action, lambda: calls.append(action))

            await pilot.press(tab_key)
            await pilot.pause()
            await pilot.press(key)
            await pilot.pause()

            assert calls == [action]
            assert app.screen is main_screen

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_delete_after_escape_from_input_stops_all(self, monkeypatch):
        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = await _push_main(app, pilot, monkeypatch)
            view = main_screen.query_one("WatchView")
            calls = []
            monkeypatch.setattr(view, "action_stop_watches", lambda: calls.append("stop"))

            await pilot.press("2")
            await pilot.pause()
            main_screen.query_one("#watch-pattern #ac-input", Input).focus()
            await pilot.pause()

            await pilot.press("escape")
            await pilot.pause()
            await pilot.press("delete")
            await pilot.pause()

            assert calls == ["stop"]
            assert app.screen is main_screen

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_profile_sub_tab_binding_after_switch(self, monkeypatch):
        """Jumping straight to a nested sub-tab focuses the view inside it."""
        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = await _push_main(app, pilot, monkeypatch)
            view = main_screen.query_one("ProfileView")
            calls = []
            monkeypatch.setattr(view, "action_refresh", lambda: calls.append("refresh"))

            main_screen.action_switch_tab("top-profile")
            await pilot.pause()
            assert app.focused is view

            await pilot.press("r")
            await pilot.pause()
            assert calls == ["refresh"]

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_sub_tab_strip_keeps_focus_when_switching_sub_tabs(self, monkeypatch):
        app = PeekaApp()
        async with app.run_test(size=(140, 30)) as pilot:
            main_screen = await _push_main(app, pilot, monkeypatch)
            await pilot.press("0")
            await pilot.pause()

            nested = main_screen.query_one("#top-content")
            strip = nested.query_one(Tabs)
            strip.focus()
            await pilot.pause()

            await pilot.press("right")
            await pilot.pause()

            assert nested.active == "top-profile"
            assert app.focused is strip
