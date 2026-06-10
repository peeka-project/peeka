"""Tests for TUI style/layout - verify compact controls and panel classes."""

from pathlib import Path

import pytest
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Input, RichLog, Static

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.screens.process_selector import ProcessSelectorScreen
from peeka.tui.views.dashboard import DashboardView
from peeka.tui.views.watch import WatchView
from peeka.tui.views.trace import TraceView
from peeka.tui.views.stack import StackView
from peeka.tui.views.monitor import MonitorView
from peeka.tui.views.logger import LoggerView
from peeka.tui.views.inspect import InspectView
from peeka.tui.views.memory import MemoryView
from peeka.tui.views.thread import ThreadView
from peeka.tui.views.top import TopView
from peeka.tui.widgets.autocomplete_input import AutoCompleteInput


PROJECT_ROOT = Path(__file__).parents[2]
STYLE_PATH = PROJECT_ROOT / "peeka" / "tui" / "styles" / "peeka.tcss"


def _right_edge(widget) -> int:
    """Return the widget's rightmost rendered column."""
    return widget.region.x + widget.region.width


def _assert_inside_width(widget, width: int) -> None:
    """Assert a widget is visible and contained in the app width."""
    assert widget.region.width > 0
    assert widget.region.x >= 0
    assert _right_edge(widget) <= width


def _assert_control_bar_usable(width: int, inputs, actions) -> None:
    """Assert a compact command bar keeps inputs usable and actions in bounds."""
    for widget, min_width in inputs:
        assert widget.region.width >= min_width
        _assert_inside_width(widget, width)
    for widget in actions:
        _assert_inside_width(widget, width)


class TestPanelStyles:
    """Verify panel focus is expressed by borders, not body fills."""

    def test_panel_body_backgrounds_are_transparent(self):
        """Panel and focused panel bodies inherit the surrounding background."""
        css = STYLE_PATH.read_text()

        assert ".panel {" in css
        assert ".panel:focus" in css
        assert ".panel DataTable" in css
        assert ".panel DataTable:focus" in css
        assert ".panel RichLog:focus" in css
        assert "background: transparent;" in css
        assert ".panel {\n    padding: 0 1;\n    margin: 0;\n    border: round #6f7280;" in css

    def test_panel_borders_and_titles_have_visible_contrast(self):
        """Unfocused panels use visible border/title colors; focus uses primary."""
        css = STYLE_PATH.read_text()

        assert "border: round #6f7280;" in css
        assert "border-title-color: #8a8f98;" in css
        assert "border-title-style: bold;" in css
        assert "border: round $primary;" in css
        assert "border-title-color: $primary;" in css


class TestButtonSemanticStyles:
    """Verify buttons use restrained, semantic color variants."""

    def test_flat_button_variants_use_restrained_theme_tints(self):
        """Flat semantic buttons use low-opacity theme colors."""
        css = STYLE_PATH.read_text()

        assert "Button.-style-flat.-primary {\n    background: $primary 15%;" in css
        assert "Button.-style-flat.-success {\n    background: $success 15%;" in css
        assert "Button.-style-flat.-warning {\n    background: $warning 18%;" in css
        assert "Button.-style-flat.-error {\n    background: $error 15%;" in css

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_observation_start_buttons_share_success_variant(self):
        """Long-running observation start buttons share the success variant."""
        app = PeekaApp()
        async with app.run_test(size=(140, 24)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            expected = {
                "watch": "#watch-btn",
                "trace": "#trace-btn",
                "stack": "#stack-btn",
                "monitor": "#monitor-btn",
                "memory": "#mem-track-btn",
                "top": "#top-start-btn",
            }

            for tab_id, button_id in expected.items():
                main_screen.action_switch_tab(tab_id)
                await pilot.pause()
                button = app.screen.query_one(button_id, Button)
                assert button.variant == "success"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_query_refresh_buttons_share_primary_variant(self):
        """Refresh, query, snapshot, and export actions share primary."""
        app = PeekaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            expected = {
                "dashboard": ["#dash-refresh-btn"],
                "threads": ["#thread-refresh-btn"],
                "logger": ["#logger-refresh-btn", "#set-level-btn"],
                "inspect": ["#inspect-btn"],
                "memory": [
                    "#mem-gc-refresh-btn",
                    "#mem-alloc-refresh-btn",
                    "#mem-dump-btn",
                    "#mem-snap-btn",
                    "#mem-diff-btn",
                    "#mem-referrers-btn",
                    "#mem-referents-btn",
                ],
            }

            for tab_id, button_ids in expected.items():
                main_screen.action_switch_tab(tab_id)
                await pilot.pause()
                for button_id in button_ids:
                    button = app.screen.query_one(button_id, Button)
                    assert button.variant == "primary"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stop_and_reset_buttons_keep_distinct_variants(self):
        """Stop stays error while clear/reset stays warning."""
        app = PeekaApp()
        async with app.run_test(size=(140, 24)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            expected = {
                "watch": {"#stop-btn": "error"},
                "trace": {"#stop-trace-btn": "error", "#clear-trace-btn": "warning"},
                "stack": {"#stop-stack-btn": "error"},
                "monitor": {"#stop-monitor-btn": "error"},
                "memory": {"#mem-stop-btn": "error", "#mem-reset-btn": "warning"},
                "top": {"#top-stop-btn": "error", "#top-reset-btn": "warning"},
            }

            for tab_id, button_variants in expected.items():
                main_screen.action_switch_tab(tab_id)
                await pilot.pause()
                for button_id, variant in button_variants.items():
                    button = app.screen.query_one(button_id, Button)
                    assert button.variant == variant


class TestProcessSelectorStyles:
    """Verify process selector compact styling (T9)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_filter_has_compact_control_class(self):
        """Process selector filter Input has compact-control class."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = ProcessSelectorScreen()
            await app.push_screen(screen)
            await pilot.pause()

            filter_input = app.screen.query_one("#filter", Input)
            assert "compact-control" in filter_input.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_selector_container_has_panel_class(self):
        """Process selector container has panel class."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = ProcessSelectorScreen()
            await app.push_screen(screen)
            await pilot.pause()

            selector = app.screen.query_one("#process-selector", Container)
            assert "panel" in selector.classes


class TestDashboardStyles:
    """Verify dashboard compact controls and semantic panels (T10)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_controls_have_compact_class(self, mock_client):
        """Dashboard controls have compact-control class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)
            await pilot.pause()

            controls = app.screen.query_one("#dash-controls", Horizontal)
            assert "compact-control" in controls.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_thread_section_has_primary_panel(self, mock_client):
        """Dashboard thread section has panel--primary class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)
            await pilot.pause()

            thread_section = app.screen.query_one("#dash-thread-section", Vertical)
            assert "panel" in thread_section.classes
            assert "panel--primary" in thread_section.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_detail_sections_have_detail_panel(self, mock_client):
        """Dashboard memory/GC/runtime sections have panel--detail class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)
            await pilot.pause()

            # Memory section
            memory_section = app.screen.query_one("#dash-memory-section", Vertical)
            assert "panel" in memory_section.classes
            assert "panel--detail" in memory_section.classes

            # GC section
            gc_section = app.screen.query_one("#dash-gc-section", Vertical)
            assert "panel" in gc_section.classes
            assert "panel--detail" in gc_section.classes

            # Runtime section
            runtime_section = app.screen.query_one("#dash-runtime-section", Vertical)
            assert "panel" in runtime_section.classes
            assert "panel--detail" in runtime_section.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_activity_log_has_stream_panel(self, mock_client):
        """Dashboard activity log section has panel--stream class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)
            await pilot.pause()

            activity_log_section = app.screen.query_one("#dash-activity-log-section", Vertical)
            assert "panel" in activity_log_section.classes
            assert "panel--stream" in activity_log_section.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_dashboard_detail_regions_align(self):
        """Dashboard lower detail regions align into left summary and right log."""
        class DashboardLayoutApp(App[None]):
            CSS_PATH = str(STYLE_PATH)

            def compose(self) -> ComposeResult:
                yield DashboardView(pid=12345)

        app = DashboardLayoutApp()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()

            summary_column = app.query_one("#dash-summary-column", Vertical)
            memory_section = app.query_one("#dash-memory-section", Vertical)
            gc_section = app.query_one("#dash-gc-section", Vertical)
            runtime_section = app.query_one("#dash-runtime-section", Vertical)
            activity_log_section = app.query_one("#dash-activity-log-section", Vertical)

            assert memory_section.region.x == gc_section.region.x
            assert gc_section.region.x == runtime_section.region.x
            assert memory_section.region.y < gc_section.region.y < runtime_section.region.y
            assert summary_column.region.y == activity_log_section.region.y
            assert summary_column.region.height == activity_log_section.region.height
            assert summary_column.region.x + summary_column.region.width <= activity_log_section.region.x

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_dashboard_activity_panel_fits_at_80_columns(self):
        """Dashboard activity panel remains visible and within bounds at 80 columns."""
        class DashboardLayoutApp(App[None]):
            CSS_PATH = str(STYLE_PATH)

            def compose(self) -> ComposeResult:
                yield DashboardView(pid=12345)

        app = DashboardLayoutApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            detail_row = app.query_one("#dash-detail-row", Horizontal)
            summary_column = app.query_one("#dash-summary-column", Vertical)
            activity_log_section = app.query_one("#dash-activity-log-section", Vertical)

            assert detail_row.region.x + detail_row.region.width <= 80
            assert summary_column.region.width > 0
            assert activity_log_section.region.width > 0
            assert activity_log_section.region.y >= detail_row.region.y

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_dashboard_activity_log_wraps_at_80_columns(self):
        """Dashboard activity log wraps long entries within a narrow panel."""
        class DashboardLayoutApp(App[None]):
            CSS_PATH = str(STYLE_PATH)

            def compose(self) -> ComposeResult:
                yield DashboardView(pid=12345)

        app = DashboardLayoutApp()
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()

            activity_log = app.query_one("#dash-activity-log", RichLog)
            activity_panel = app.query_one("#dash-activity-log-section", Vertical)

            assert activity_log.wrap is True
            assert activity_log.min_width == DashboardView.ACTIVITY_LOG_MIN_RENDER_WIDTH
            assert activity_log.region.x >= activity_panel.region.x
            assert activity_log.region.width <= activity_panel.region.width
            assert activity_panel.region.x + activity_panel.region.width <= 80

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_dashboard_activity_log_wraps_at_140_columns(self):
        """Dashboard activity log keeps wrapping enabled on wide layouts."""
        class DashboardLayoutApp(App[None]):
            CSS_PATH = str(STYLE_PATH)

            def compose(self) -> ComposeResult:
                yield DashboardView(pid=12345)

        app = DashboardLayoutApp()
        async with app.run_test(size=(140, 24)) as pilot:
            await pilot.pause()

            activity_log = app.query_one("#dash-activity-log", RichLog)
            activity_panel = app.query_one("#dash-activity-log-section", Vertical)

            assert activity_log.wrap is True
            assert activity_log.min_width == DashboardView.ACTIVITY_LOG_MIN_RENDER_WIDTH
            assert activity_log.region.x >= activity_panel.region.x
            assert activity_log.region.width <= activity_panel.region.width
            assert activity_panel.region.x + activity_panel.region.width <= 140

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_dashboard_activity_log_keeps_fitting_entries_on_one_line(self):
        """Activity entries that fit the visible log width stay on one line."""
        class DashboardLayoutApp(App[None]):
            CSS_PATH = str(STYLE_PATH)

            def compose(self) -> ComposeResult:
                yield DashboardView(pid=12345)

        app = DashboardLayoutApp()
        async with app.run_test(size=(140, 24)) as pilot:
            await pilot.pause()

            dashboard = app.query_one("DashboardView", DashboardView)
            activity_log = app.query_one("#dash-activity-log", RichLog)

            dashboard._write_activity_entry(
                "agent",
                "INFO",
                "[peeka Agent] Ready for commands",
                1714972801.0,
            )
            await pilot.pause()

            rendered = [line.text for line in activity_log.lines]
            assert len(rendered) == 1
            assert "Ready for commands" in rendered[0]

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_dashboard_activity_log_message_uses_default_foreground(self):
        """Activity message text inherits the active theme foreground."""
        class DashboardLayoutApp(App[None]):
            CSS_PATH = str(STYLE_PATH)

            def compose(self) -> ComposeResult:
                yield DashboardView(pid=12345)

        app = DashboardLayoutApp()
        async with app.run_test(size=(140, 24)) as pilot:
            await pilot.pause()

            dashboard = app.query_one("DashboardView", DashboardView)
            activity_log = app.query_one("#dash-activity-log", RichLog)
            captured = []

            def capture_write(content, *args, **kwargs):
                captured.append(content)
                return activity_log

            activity_log.write = capture_write  # type: ignore[method-assign]
            dashboard._write_activity_entry(
                "agent",
                "ERROR",
                "plain message body",
                1714972801.0,
            )

            rendered = captured[-1]
            message_start = rendered.plain.index("plain message body")
            assert all(span.end <= message_start for span in rendered.spans)

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_dashboard_runtime_panel_is_focusable(self):
        """Dashboard runtime panel can receive focus even though it has static text."""
        class DashboardLayoutApp(App[None]):
            CSS_PATH = str(STYLE_PATH)

            def compose(self) -> ComposeResult:
                yield DashboardView(pid=12345)

        app = DashboardLayoutApp()
        async with app.run_test(size=(140, 40)) as pilot:
            await pilot.pause()

            runtime_section = app.query_one("#dash-runtime-section", Vertical)

            assert runtime_section.can_focus is True
            runtime_section.focus()
            await pilot.pause()
            assert app.focused is runtime_section

            runtime_section.blur()
            for _ in range(8):
                await pilot.press("tab")
                if app.focused is runtime_section:
                    break
            assert app.focused is runtime_section


class TestWatchViewStyles:
    """Verify watch view compact controls and panel variants (T6, T8)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_controls_have_compact_class(self, mock_client):
        """Watch controls have compact-control class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(mock_client)

            controls = app.screen.query_one("#watch-controls", Horizontal)
            assert "compact-control" in controls.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_controls_remain_usable_at_80_columns(self):
        """Watch inputs keep usable widths in a narrow terminal."""
        app = PeekaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("watch")
            await pilot.pause()

            top_controls = app.screen.query_one("#watch-top-controls", Container)
            pattern = app.screen.query_one("#watch-pattern", AutoCompleteInput)
            condition = app.screen.query_one("#watch-condition", Input)
            condition_controls = app.screen.query_one(
                "#watch-condition-controls", Horizontal
            )
            actions = app.screen.query_one("#watch-action-controls", Horizontal)
            watch_btn = app.screen.query_one("#watch-btn", Button)
            stop_btn = app.screen.query_one("#stop-btn", Button)
            banner = app.screen.query_one("#watch-runtime-banner", Static)

            assert "watch-top-wide" not in top_controls.classes
            assert condition_controls.region.y > top_controls.region.y
            assert actions.region.y > condition_controls.region.y
            assert banner.parent is not top_controls
            _assert_inside_width(top_controls, 80)
            _assert_control_bar_usable(
                80,
                inputs=((pattern, 30), (condition, 20)),
                actions=(watch_btn, stop_btn),
            )

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_controls_share_one_row_on_wide_terminals(self):
        """Watch controls use one row with actions on the right when space allows."""
        app = PeekaApp()
        async with app.run_test(size=(140, 24)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("watch")
            await pilot.pause()

            top_controls = app.screen.query_one("#watch-top-controls", Container)
            controls = app.screen.query_one("#watch-controls", Horizontal)
            condition_controls = app.screen.query_one(
                "#watch-condition-controls", Horizontal
            )
            actions = app.screen.query_one("#watch-action-controls", Horizontal)
            pattern = app.screen.query_one("#watch-pattern", AutoCompleteInput)
            condition = app.screen.query_one("#watch-condition", Input)
            stop_btn = app.screen.query_one("#stop-btn", Button)
            banner = app.screen.query_one("#watch-runtime-banner", Static)

            assert "watch-top-wide" in top_controls.classes
            assert controls.region.y == condition_controls.region.y == actions.region.y
            assert _right_edge(controls) <= condition_controls.region.x
            assert _right_edge(condition_controls) <= actions.region.x
            assert banner.parent is not controls
            _assert_control_bar_usable(
                140,
                inputs=((pattern, 30), (condition, 20)),
                actions=(stop_btn,),
            )

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_view_exports_svg_screenshot_smoke(self):
        """Textual can export a non-empty SVG screenshot for visual artifacts."""
        app = PeekaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("watch")
            await pilot.pause()

            svg = app.export_screenshot(title="watch layout smoke", simplify=True)
            assert svg.lstrip().startswith("<svg")
            assert "</svg>" in svg
            assert len(svg) > 1000

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_list_has_stream_panel(self, mock_client):
        """Watch list panel has panel--stream class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(mock_client)

            watch_list = app.screen.query_one("#watch-list", Vertical)
            assert "panel" in watch_list.classes
            assert "panel--stream" in watch_list.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_observations_panel_has_detail_panel(self, mock_client):
        """Watch observations panel has panel--detail class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            watch_view = app.screen.query_one("WatchView", WatchView)
            watch_view.set_client(mock_client)

            observations_panel = app.screen.query_one("#observations-panel", Vertical)
            assert "panel" in observations_panel.classes
            assert "panel--detail" in observations_panel.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_observation_detail_has_separate_panel(self, mock_client):
        """Watch observation detail is visually separated from the list."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 32)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("watch")
            await pilot.pause()

            observations_panel = app.screen.query_one("#observations-panel", Vertical)
            detail_panel = app.screen.query_one("#observation-detail-panel", Vertical)

            assert "panel" in observations_panel.classes
            assert "panel--detail" in observations_panel.classes
            assert "panel" in detail_panel.classes
            assert "panel--detail" in detail_panel.classes
            assert observations_panel.region.x == detail_panel.region.x
            assert observations_panel.region.width == detail_panel.region.width
            assert observations_panel.region.y + observations_panel.region.height < detail_panel.region.y


class TestTraceViewStyles:
    """Verify trace view compact controls and panel variants (T6, T8)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_controls_have_compact_class(self, mock_client):
        """Trace controls have compact-control class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(mock_client)

            controls = app.screen.query_one("#trace-controls", Horizontal)
            assert "compact-control" in controls.classes

            options = app.screen.query_one("#trace-options-controls", Horizontal)
            assert "compact-control" in options.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_controls_remain_usable_at_80_columns(self):
        """Trace inputs keep usable widths in a narrow terminal."""
        app = PeekaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("trace")
            await pilot.pause()

            pattern = app.screen.query_one("#trace-pattern", AutoCompleteInput)
            depth = app.screen.query_one("#trace-depth", Input)
            condition = app.screen.query_one("#trace-condition", Input)
            actions = app.screen.query_one("#trace-action-controls", Horizontal)
            trace_btn = app.screen.query_one("#trace-btn", Button)

            assert pattern.region.width >= 30
            assert depth.region.width >= 8
            assert condition.region.width >= 20
            assert trace_btn.region.x + trace_btn.region.width <= 80
            assert actions.region.y > condition.region.y

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_controls_share_one_row_on_wide_terminals(self):
        """Trace controls use one row with actions on the right when space allows."""
        app = PeekaApp()
        async with app.run_test(size=(160, 24)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("trace")
            await pilot.pause()

            top_controls = app.screen.query_one("#trace-top-controls", Container)
            controls = app.screen.query_one("#trace-controls", Horizontal)
            options = app.screen.query_one("#trace-options-controls", Horizontal)
            actions = app.screen.query_one("#trace-action-controls", Horizontal)
            clear_btn = app.screen.query_one("#clear-trace-btn", Button)

            assert "trace-top-wide" in top_controls.classes
            assert controls.region.y == options.region.y == actions.region.y
            assert controls.region.x + controls.region.width <= options.region.x
            assert options.region.x + options.region.width <= actions.region.x
            assert clear_btn.region.x + clear_btn.region.width <= 160
            assert actions.region.x >= 120

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_list_has_stream_panel(self, mock_client):
        """Trace list panel has panel--stream class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(mock_client)

            trace_list = app.screen.query_one("#trace-list", Vertical)
            assert "panel" in trace_list.classes
            assert "panel--stream" in trace_list.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_tree_has_detail_panel(self, mock_client):
        """Trace tree panel has panel--detail class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            trace_view = app.screen.query_one("TraceView", TraceView)
            trace_view.set_client(mock_client)

            trace_tree_panel = app.screen.query_one("#trace-tree-panel", Vertical)
            assert "panel" in trace_tree_panel.classes
            assert "panel--detail" in trace_tree_panel.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_trace_stats_has_separate_panel(self, mock_client):
        """Trace stats are visually separated from the call tree."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 32)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("trace")
            await pilot.pause()

            trace_tree_panel = app.screen.query_one("#trace-tree-panel", Vertical)
            stats_panel = app.screen.query_one("#trace-stats-panel", Vertical)

            assert "panel" in trace_tree_panel.classes
            assert "panel--detail" in trace_tree_panel.classes
            assert "panel" in stats_panel.classes
            assert "panel--detail" in stats_panel.classes
            assert trace_tree_panel.region.x == stats_panel.region.x
            assert trace_tree_panel.region.width == stats_panel.region.width
            assert trace_tree_panel.region.y + trace_tree_panel.region.height < stats_panel.region.y


class TestStackViewStyles:
    """Verify stack view compact controls and panel variants (T6, T8)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_controls_have_compact_class(self, mock_client):
        """Stack controls have compact-control class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(mock_client)

            controls = app.screen.query_one("#stack-controls", Horizontal)
            assert "compact-control" in controls.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stack_list_has_stream_panel(self, mock_client):
        """Stack list panel has panel--stream class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(mock_client)

            stack_list = app.screen.query_one("#stack-list", Vertical)
            assert "panel" in stack_list.classes
            assert "panel--stream" in stack_list.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_stack_panel_has_detail_panel(self, mock_client):
        """Stack detail panel has panel--detail class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            stack_view = app.screen.query_one("StackView", StackView)
            stack_view.set_client(mock_client)

            stack_panel = app.screen.query_one("#stack-panel", Vertical)
            assert "panel" in stack_panel.classes
            assert "panel--detail" in stack_panel.classes


class TestStreamViewGeometry:
    """Verify similar stream/detail views keep matching split widths."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_watch_trace_stack_split_widths_match(self):
        """Watch, Trace, and Stack left/right panes use the same geometry."""

        class ProbeApp(App[None]):
            CSS_PATH = STYLE_PATH

            def compose(self) -> ComposeResult:
                with Container(id="main-container"):
                    yield WatchView(pid=12345)
                    yield TraceView(pid=12345)
                    yield StackView(pid=12345)

        app = ProbeApp()
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()

            watch_left = app.query_one("#watch-list", Vertical).region.width
            trace_left = app.query_one("#trace-list", Vertical).region.width
            stack_left = app.query_one("#stack-list", Vertical).region.width

            watch_right = app.query_one("#observations-panel", Vertical).region.width
            trace_right = app.query_one("#trace-detail-column", Vertical).region.width
            stack_right = app.query_one("#stack-panel", Vertical).region.width

            assert trace_left == watch_left == stack_left
            assert trace_right == watch_right == stack_right


class TestMonitorViewStyles:
    """Verify monitor view compact controls (T6)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_controls_have_compact_class(self, mock_client):
        """Monitor controls have compact-control class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            monitor_view = app.screen.query_one("MonitorView", MonitorView)
            monitor_view.set_client(mock_client)

            controls = app.screen.query_one("#monitor-controls", Horizontal)
            assert "compact-control" in controls.classes


class TestLoggerViewStyles:
    """Verify logger view compact controls (T7)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_main_controls_have_compact_class(self, mock_client):
        """Logger main controls have compact-control class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            logger_view = app.screen.query_one("LoggerView", LoggerView)
            logger_view.set_client(mock_client)

            controls = app.screen.query_one("#logger-controls", Horizontal)
            assert "compact-control" in controls.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_set_controls_have_compact_class(self, mock_client):
        """Logger set-level controls have compact-control class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            logger_view = app.screen.query_one("LoggerView", LoggerView)
            logger_view.set_client(mock_client)

            set_controls = app.screen.query_one("#logger-set-controls", Horizontal)
            assert "compact-control" in set_controls.classes


class TestInspectViewStyles:
    """Verify inspect view compact controls and panel variants (T7, T8)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_controls_have_compact_class(self, mock_client):
        """Inspect controls have compact-control class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            inspect_view = app.screen.query_one("InspectView", InspectView)
            inspect_view.set_client(mock_client)

            controls = app.screen.query_one("#inspect-controls", Horizontal)
            assert "compact-control" in controls.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_tree_panel_has_detail_panel(self, mock_client):
        """Inspect tree panel has panel--detail class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            inspect_view = app.screen.query_one("InspectView", InspectView)
            inspect_view.set_client(mock_client)

            tree_panel = app.screen.query_one("#inspect-tree-panel", Vertical)
            assert "panel" in tree_panel.classes
            assert "panel--detail" in tree_panel.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_details_panel_has_detail_panel(self, mock_client):
        """Inspect details panel has panel--detail class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            inspect_view = app.screen.query_one("InspectView", InspectView)
            inspect_view.set_client(mock_client)

            details_panel = app.screen.query_one("#inspect-details-panel", Vertical)
            assert "panel" in details_panel.classes
            assert "panel--detail" in details_panel.classes


class TestMemoryViewStyles:
    """Verify memory view compact controls and panel variants (T7, T8)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_all_control_bars_have_compact_class(self, mock_client):
        """Memory view all control bars have compact-control class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            memory_view = app.screen.query_one("MemoryView", MemoryView)
            memory_view.set_client(mock_client)

            # Status bar (tracking)
            status_bar = app.screen.query_one("#memory-status-bar", Horizontal)
            assert "compact-control" in status_bar.classes

            track_controls = app.screen.query_one("#mem-track-controls", Horizontal)
            assert "compact-control" in track_controls.classes

            # GC controls
            gc_controls = app.screen.query_one("#mem-gc-controls", Horizontal)
            assert "compact-control" in gc_controls.classes

            # Alloc controls
            alloc_controls = app.screen.query_one("#mem-alloc-controls", Horizontal)
            assert "compact-control" in alloc_controls.classes

            # Diff controls
            diff_controls = app.screen.query_one("#mem-diff-controls", Horizontal)
            assert "compact-control" in diff_controls.classes

            # References controls
            ref_controls = app.screen.query_one("#mem-references-controls", Horizontal)
            assert "compact-control" in ref_controls.classes

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_memory_top_controls_fit_at_80_columns(self):
        """Memory status and tracking controls stay within a narrow terminal."""
        app = PeekaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("memory")
            await pilot.pause()

            status_bar = app.screen.query_one("#memory-status-bar", Horizontal)
            track_controls = app.screen.query_one("#mem-track-controls", Horizontal)
            nframe_input = app.screen.query_one("#mem-nframe-input", Input)
            track_btn = app.screen.query_one("#mem-track-btn", Button)

            assert status_bar.region.x + status_bar.region.width <= 80
            assert track_controls.region.x + track_controls.region.width <= 80
            assert nframe_input.region.x + nframe_input.region.width <= 80
            assert track_btn.region.x + track_btn.region.width <= 80
            assert track_controls.region.y > status_bar.region.y

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_memory_top_controls_share_one_row_on_wide_terminals(self):
        """Memory status and tracking controls use one row when space allows."""
        app = PeekaApp()
        async with app.run_test(size=(140, 24)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("memory")
            await pilot.pause()

            top_controls = app.screen.query_one("#memory-top-controls", Container)
            status_bar = app.screen.query_one("#memory-status-bar", Horizontal)
            track_controls = app.screen.query_one("#mem-track-controls", Horizontal)
            gc_status = app.screen.query_one("#mem-gc", Static)
            track_btn = app.screen.query_one("#mem-track-btn", Button)

            assert "memory-top-wide" in top_controls.classes
            assert status_bar.region.y == track_controls.region.y
            assert status_bar.region.x <= 2
            assert track_controls.region.x - (
                status_bar.region.x + status_bar.region.width
            ) >= 20
            assert gc_status.region.x + gc_status.region.width <= status_bar.region.x + status_bar.region.width
            assert status_bar.region.x + status_bar.region.width <= track_controls.region.x
            assert track_btn.region.x + track_btn.region.width <= 140
            assert track_controls.region.x >= 100

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_all_content_wrappers_have_detail_panel(self, mock_client):
        """Memory view all 4 content wrappers have panel--detail class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            memory_view = app.screen.query_one("MemoryView", MemoryView)
            memory_view.set_client(mock_client)

            # GC content wrapper
            gc_content = app.screen.query_one("#mem-gc-content", Vertical)
            assert "panel" in gc_content.classes
            assert "panel--detail" in gc_content.classes

            # Allocations content wrapper
            alloc_content = app.screen.query_one("#mem-allocations-content", Vertical)
            assert "panel" in alloc_content.classes
            assert "panel--detail" in alloc_content.classes

            # Diff content wrapper
            diff_content = app.screen.query_one("#mem-diff-content", Vertical)
            assert "panel" in diff_content.classes
            assert "panel--detail" in diff_content.classes

            # References content wrapper
            ref_content = app.screen.query_one("#mem-references-content", Vertical)
            assert "panel" in ref_content.classes
            assert "panel--detail" in ref_content.classes


class TestThreadViewStyles:
    """Verify thread view compact controls (T7)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_controls_have_compact_class(self, mock_client):
        """Thread controls have compact-control class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            thread_view = app.screen.query_one("ThreadView", ThreadView)
            thread_view.set_client(mock_client)

            controls = app.screen.query_one("#thread-controls", Horizontal)
            assert "compact-control" in controls.classes


class TestTopViewStyles:
    """Verify top view compact controls (T7)."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_controls_have_compact_class(self, mock_client):
        """Top controls have compact-control class."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            top_view = app.screen.query_one("TopView", TopView)
            top_view.set_client(mock_client)

            controls = app.screen.query_one("#top-controls", Horizontal)
            assert "compact-control" in controls.classes
