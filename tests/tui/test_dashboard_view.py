"""Tests for DashboardView - data-flow and error handling."""

from pathlib import Path

import pytest
from textual.widgets import DataTable, RichLog, Static

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.dashboard import DashboardView


def _rich_log_lines(widget: RichLog) -> str:
    """Return the plain-text content currently rendered by a RichLog."""
    return " ".join("\n".join(line.text for line in widget.lines).split())


class TestDashboardView:
    """Test DashboardView widget population from mock client responses."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_set_client_triggers_refresh(self, mock_client):
        """set_client() triggers data refresh and populates widgets."""
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
            await pilot.pause()

            assert len(mock_client.commands_received) >= 2
            command_types = [cmd.get("type") for cmd in mock_client.commands_received]
            assert "vmtool" in command_types
            assert "memory" in command_types

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_memory_stats_display(self, mock_client):
        """Memory stats from mock client appear in dashboard memory DataTable."""
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
            await pilot.pause()

            mem_table = app.screen.query_one("#dash-mem-table", DataTable)
            # Memory table should have rows (rss, vms, traced)
            assert mem_table.row_count >= 2
            # Check that 50.0M (rss = 50 MB) appears in some row
            found_rss = False
            for row_key in mem_table.rows:
                row = mem_table.get_row(row_key)
                row_text = " ".join(str(cell) for cell in row)
                if "50.0M" in row_text and "rss" in row_text:
                    found_rss = True
                    break
            assert found_rss, "RSS memory (50.0M) not found in memory table"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_gc_counts_display(self, mock_client):
        """GC counts from mock memory response populate GC DataTable."""
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
            await pilot.pause()

            gc_table = app.screen.query_one("#dash-gc-table", DataTable)
            assert gc_table.row_count == 3  # gen0, gen1, gen2

            # Collect all row text for verification
            gc_values = []
            for row_key in gc_table.rows:
                row = gc_table.get_row(row_key)
                gc_values.append(" ".join(str(cell) for cell in row))
            gc_text = "\n".join(gc_values)

            assert "700" in gc_text, "gen0 count (700) not found in GC table"
            assert "10" in gc_text, "gen1 count (10) not found in GC table"
            # gen2 count = 1, threshold = 10 — both present
            assert "gen2" in gc_text, "gen2 row not found in GC table"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_uptime_display(self, mock_client):
        """Runtime info section displays uptime."""
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
            await pilot.pause()

            runtime_info = app.screen.query_one("#dash-runtime-info", Static)
            content = runtime_info.render().plain
            assert "uptime" in content

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_refresh_action(self, mock_client):
        """Pressing 'r' triggers refresh and sends new commands."""
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
            await pilot.pause()

            initial_command_count = len(mock_client.commands_received)

            dashboard.action_refresh()
            await pilot.pause()
            await pilot.pause()

            assert len(mock_client.commands_received) > initial_command_count

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_client_error_response(self, mock_client_factory):
        """Dashboard handles error responses gracefully without crashing."""
        error_client = mock_client_factory(
            responses={
                "vmtool": {"status": "error", "error": "vmtool failed"},
                "memory": {"status": "error", "error": "memory failed"},
                "thread": {"status": "error", "error": "thread failed"},
            }
        )
        error_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(error_client)

            await pilot.pause()
            await pilot.pause()

            # Dashboard should not crash; memory table should be empty or have
            # default rows, thread table should be empty
            mem_table = app.screen.query_one("#dash-mem-table", DataTable)
            thread_table = app.screen.query_one("#dash-thread-table", DataTable)
            # Tables exist and didn't crash — that's the key assertion
            assert mem_table is not None
            assert thread_table is not None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_no_client_connected(self):
        """Dashboard with no client shows initial placeholder text."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            # Thread summary should show placeholder dashes
            thread_summary = app.screen.query_one("#dash-thread-summary", Static)
            summary_text = thread_summary.render().plain
            assert "Threads" in summary_text

            # Runtime info should be empty (no data fetched yet)
            runtime_info = app.screen.query_one("#dash-runtime-info", Static)
            runtime_text = runtime_info.render().plain
            # Empty or minimal — no python.version populated
            assert "3.12.0" not in runtime_text

            # Tables should exist and be queryable
            thread_table = app.screen.query_one("#dash-thread-table", DataTable)
            mem_table = app.screen.query_one("#dash-mem-table", DataTable)
            gc_table = app.screen.query_one("#dash-gc-table", DataTable)
            assert thread_table is not None
            assert mem_table is not None
            assert gc_table is not None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_thread_table_display(self, mock_client):
        """Thread data from mock client populates thread DataTable."""
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
            await pilot.pause()

            # Thread summary should show counts
            thread_summary = app.screen.query_one("#dash-thread-summary", Static)
            summary_text = thread_summary.render().plain
            assert "2" in summary_text  # 2 total threads

            # Thread table should have 2 rows
            thread_table = app.screen.query_one("#dash-thread-table", DataTable)
            assert thread_table.row_count == 2

            # Collect all row text
            all_rows_text = []
            for row_key in thread_table.rows:
                row = thread_table.get_row(row_key)
                all_rows_text.append(" ".join(str(cell) for cell in row))
            combined = "\n".join(all_rows_text)

            assert "MainThread" in combined
            assert "Worker-1" in combined
            assert "1234" in combined
            assert "5678" in combined

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_runtime_info_content(self, mock_client):
        """Runtime info shows python version, pid, and other key-value pairs."""
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
            await pilot.pause()

            runtime_info = app.screen.query_one("#dash-runtime-info", Static)
            content = runtime_info.render().plain

            assert "3.12.0" in content  # python version
            assert "12345" in content  # pid
            assert "uptime" in content

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_activity_log_replays_persisted_agent_history(
        self, mock_client_factory, monkeypatch, tmp_path
    ):
        """Dashboard replays persisted agent history before the live stream starts."""
        session_id = "dashboard-history"
        socket_path = f"/tmp/peeka_{session_id}.sock"
        log_path = Path(tmp_path) / f"peeka_{session_id}.log"
        log_path.write_text(
            "\n".join(
                [
                    "1714972800.000 INFO [peeka Agent] Started and listening for connections",
                    "1714972801.000 INFO [peeka Agent] Ready for commands",
                ]
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            "peeka.tui.views.dashboard_activity.tempfile.gettempdir",
            lambda: str(tmp_path),
        )

        client = mock_client_factory()
        client.socket_path = socket_path
        client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id=session_id, socket_path=socket_path
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(client)

            await pilot.pause()
            await pilot.pause()

            rich_log = app.screen.query_one("#dash-activity-log", RichLog)
            content = _rich_log_lines(rich_log)

            assert "AGENT" in content
            assert "Started and listening for connections" in content
            assert "Ready for commands" in content

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_activity_log_includes_buffered_and_live_client_activity(
        self, mock_client
    ):
        """Dashboard merges current-client activity with the agent activity panel."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            app.record_client_activity(
                "INFO", "watch list refreshed", source="watch"
            )

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)

            await pilot.pause()
            app.notify("trace started", severity="warning")
            await pilot.pause()
            await pilot.pause()

            rich_log = app.screen.query_one("#dash-activity-log", RichLog)
            content = _rich_log_lines(rich_log)

            assert "CLIENT" in content
            assert "watch: watch list refreshed" in content
            assert "trace started" in content

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_activity_log_filters_client_connection_lifecycle(self, mock_client):
        """Dashboard hides low-signal client connected/disconnected entries."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            app.record_client_activity("INFO", "connected", source="main")
            app.record_client_activity(
                "INFO",
                "connected to agent session test-session for pid 12345",
                source="main",
            )
            app.record_client_activity("INFO", "connected", source="dashboard-data")
            app.record_client_activity(
                "ERROR", "connect failed: timeout", source="dashboard-data"
            )

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)
            await pilot.pause()
            await pilot.pause()

            rich_log = app.screen.query_one("#dash-activity-log", RichLog)
            content = _rich_log_lines(rich_log)

            assert "connected to agent session test-session" in content
            assert "dashboard-data: connect failed: timeout" in content
            assert "dashboard-data: connected" not in content
            assert "CLIENT INFO connected CLIENT" not in content

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_activity_log_filters_agent_connection_lifecycle(self, mock_client):
        """Dashboard hides agent-side info connection lifecycle entries."""
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
            dashboard.action_clear_activity_log()
            dashboard._write_activity_entry(
                "agent",
                "INFO",
                "[peeka Agent] client tui-test01/dashboard-stream conn#5 "
                "connected (1 total) kind=tui pid=12345",
                1000.0,
            )
            dashboard._write_activity_entry(
                "agent",
                "INFO",
                "[peeka Agent] client tui-test01/dashboard-stream conn#5 disconnected",
                1001.0,
            )
            dashboard._write_activity_entry(
                "agent",
                "INFO",
                "[peeka Agent] Ready for commands",
                1002.0,
            )
            await pilot.pause()

            rich_log = app.screen.query_one("#dash-activity-log", RichLog)
            content = _rich_log_lines(rich_log)

            assert "dashboard-stream conn#5 connected" not in content
            assert "dashboard-stream conn#5 disconnected" not in content
            assert "Ready for commands" in content

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_activity_log_replays_buffered_attach_timeline(self, mock_client):
        """Dashboard replays attach activity emitted before MainScreen mounted."""
        mock_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            app.record_client_activity(
                "INFO",
                "attach.run_injector done: GDB dlopen injector completed (1430ms)",
                source="attach",
                metadata={
                    "phase": "run_injector",
                    "status": "done",
                    "elapsed_ms": 1430.0,
                },
            )
            app.record_client_activity(
                "INFO",
                "attach.attached done: Successfully attached to process 24 (5598ms total)",
                source="attach",
                metadata={
                    "phase": "attached",
                    "status": "done",
                    "elapsed_ms": 5598.0,
                },
            )
            app.record_client_activity(
                "INFO",
                "attach.summary done: total=5598ms, "
                "slowest=wait_agent_ready 3800ms, "
                "timed_phases=2, method=gdb_dlopen",
                source="attach",
                metadata={
                    "phase": "summary",
                    "status": "done",
                    "elapsed_ms": 5598.0,
                    "details": {
                        "slowest_phase": "wait_agent_ready",
                        "slowest_elapsed_ms": 3800.0,
                    },
                },
            )

            main_screen = MainScreen(
                pid=24, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)

            await pilot.pause()
            await pilot.pause()

            rich_log = app.screen.query_one("#dash-activity-log", RichLog)
            content = _rich_log_lines(rich_log)

            assert "CLIENT" in content
            assert "attach: attach.run_injector done" in content
            assert "GDB dlopen injector completed" in content
            assert "attach: attach.attached done" in content
            assert "5598ms total" in content
            assert "attach: attach.summary done" in content
            assert "slowest=wait_agent_ready 3800ms" in content

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_copy_activity_log_copies_plain_text(self, mock_client):
        """Dashboard copies the current activity log without terminal selection."""
        mock_client.connect()

        app = PeekaApp()
        copied = []

        def copy_to_clipboard(text):
            copied.append(text)

        app.copy_to_clipboard = copy_to_clipboard
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(mock_client)
            dashboard._write_activity_entry(
                "client",
                "INFO",
                "attach: attach.run_injector done: GDB dlopen injector completed (1430ms)",
                1000.0,
            )

            dashboard.action_copy_activity_log()
            await pilot.pause()

            assert copied
            assert "CLIENT INFO attach: attach.run_injector done" in copied[-1]
            assert "GDB dlopen injector completed" in copied[-1]
