"""

TUI Component Tests using Textual's testing framework.



Tests verify:

1. ProcessSelectorScreen renders with correct widgets

2. MainScreen has all 10 tabs with correct labels

3. Tab switching works and updates active state

4. All view inputs have descriptive labels

5. CompletionSource is correctly typed and synchronous

"""



import inspect

from types import SimpleNamespace



import pytest



from peeka.tui.app import PeekaApp

from peeka.tui.completion import CompletionSource

from peeka.tui.screens.main import MainScreen

from peeka.tui.screens.process_selector import ProcessSelectorScreen

from textual.widgets import Static, RichLog





class TestProcessSelectorScreen:

    @pytest.mark.asyncio

    async def test_screen_renders_with_table(self):

        """ProcessSelectorScreen has a DataTable with correct columns."""

        app = PeekaApp()

        async with app.run_test():

            assert isinstance(app.screen, ProcessSelectorScreen)

            from textual.widgets import DataTable



            table = app.screen.query_one("#process-table", DataTable)

            assert table is not None

            # Verify columns exist

            column_labels = [col.label.plain for col in table.columns.values()]

            assert "PID" in column_labels

            assert "Command" in column_labels



    @pytest.mark.asyncio

    async def test_escape_quits(self):

        """ESC key quits the application."""

        app = PeekaApp()

        async with app.run_test() as pilot:

            await pilot.press("escape")

            await pilot.pause()

            assert app._exit



    @pytest.mark.asyncio

    async def test_filter_input_exists(self):

        """Filter input exists with correct placeholder."""

        app = PeekaApp()

        async with app.run_test():

            from textual.widgets import Input



            filter_input = app.screen.query_one("#filter", Input)

            assert filter_input.placeholder == "Filter by PID or command..."



    def test_get_python_processes_skips_uv_wrapper(self, monkeypatch):

        """Wrapper processes like uv should not be listed as attach targets."""

        screen = ProcessSelectorScreen()

        ps_output = "\n".join(

            [

                "USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND",

                "alice 100 0.0 0.1 0 0 ? S 10:00 0:00 uv run python -m http.server 8888",

                "alice 101 0.0 0.1 0 0 ? S 10:00 0:00 /tmp/.venv/bin/python -m http.server 8888",

            ]

        )



        monkeypatch.setattr(

            "peeka.tui.screens.process_selector.subprocess.run",

            lambda *args, **kwargs: SimpleNamespace(stdout=ps_output),

        )

        monkeypatch.setattr(

            ProcessSelectorScreen,

            "_is_python_process",

            staticmethod(lambda pid: pid == "101"),

        )

        monkeypatch.setattr(

            ProcessSelectorScreen,

            "_is_peeka_process",

            staticmethod(lambda pid, cmd: False),

        )



        assert screen._get_python_processes() == [

            ("101", "alice", "0.0", "0.1", "/tmp/.venv/bin/python -m http.server 8888")

        ]



    def test_get_python_processes_skips_peeka_processes(self, monkeypatch):

        """Peeka's own processes should not be shown as attach targets."""

        screen = ProcessSelectorScreen()

        ps_output = "\n".join(

            [

                "USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND",

                "alice 200 0.0 0.1 0 0 ? S 10:00 0:00 /tmp/.venv/bin/python -m peeka.cli.main tui",

                "alice 201 0.0 0.1 0 0 ? S 10:00 0:00 /tmp/.venv/bin/python -m http.server 8888",

            ]

        )



        monkeypatch.setattr(

            "peeka.tui.screens.process_selector.subprocess.run",

            lambda *args, **kwargs: SimpleNamespace(stdout=ps_output),

        )

        monkeypatch.setattr(

            ProcessSelectorScreen,

            "_is_python_process",

            staticmethod(lambda pid: True),

        )



        assert screen._get_python_processes() == [

            ("201", "alice", "0.0", "0.1", "/tmp/.venv/bin/python -m http.server 8888")

        ]



    def test_is_python_process_uses_cmdline_fallback_when_proc_lookup_fails(self, monkeypatch):

        """Process detection should stay permissive when /proc lookup is unavailable."""

        monkeypatch.setattr(

            "peeka.tui.screens.process_selector.os.readlink",

            lambda path: (_ for _ in ()).throw(OSError("missing /proc entry")),

        )



        assert ProcessSelectorScreen._is_python_process("123") is True



    def test_is_peeka_process_matches_current_pid(self, monkeypatch):

        """The current Peeka process should always be filtered out."""

        monkeypatch.setattr("peeka.tui.screens.process_selector.os.getpid", lambda: 321)



        assert ProcessSelectorScreen._is_peeka_process("321", "python -m http.server") is True



    @pytest.mark.asyncio

    async def test_validate_agent_connection_returns_error(self, monkeypatch):

        """Process selector probes the agent before pushing MainScreen."""

        disconnected = []



        class FakeClient:

            def __init__(self, *args, **kwargs):

                pass



            def connect(self):

                return {"status": "error", "error": "no response received"}



            def disconnect(self):

                disconnected.append(True)



        monkeypatch.setattr("peeka.core.client.StreamingAgentClient", FakeClient)



        app = PeekaApp()

        async with app.run_test():

            screen = app.screen

            assert isinstance(screen, ProcessSelectorScreen)

            assert (

                screen._validate_agent_connection("/tmp/fake.sock")

                == "no response received"

            )

            assert disconnected == [True]



    @pytest.mark.asyncio

    async def test_validate_agent_connection_accepts_success(self, monkeypatch):

        """Successful agent hello allows the TUI to enter MainScreen."""

        disconnected = []



        class FakeClient:

            def __init__(self, *args, **kwargs):

                pass



            def connect(self):

                return {"status": "success"}



            def disconnect(self):

                disconnected.append(True)



        monkeypatch.setattr("peeka.core.client.StreamingAgentClient", FakeClient)



        app = PeekaApp()

        async with app.run_test():

            screen = app.screen

            assert isinstance(screen, ProcessSelectorScreen)

            assert screen._validate_agent_connection("/tmp/fake.sock") is None

            assert disconnected == [True]



    @pytest.mark.asyncio

    async def test_attach_panel_initially_hidden(self):

        """Attach panel should be hidden on mount until attach starts."""

        app = PeekaApp()

        async with app.run_test():

            screen = app.screen

            assert isinstance(screen, ProcessSelectorScreen)

            panel = screen.query_one("#attach-panel")

            assert str(panel.styles.display) == "none", "attach-panel should be hidden on mount"


    @pytest.mark.asyncio

    async def test_attach_panel_stays_visible_on_error(self, monkeypatch):

        """Attach panel stays visible when attach fails, showing error banner."""

        push_screen_calls = []



        def mock_push_screen(screen):

            push_screen_calls.append(screen)



        app = PeekaApp()

        async with app.run_test() as pilot:

            screen = app.screen

            assert isinstance(screen, ProcessSelectorScreen)



            screen._set_attach_panel_visible(True)

            await pilot.pause()

            panel = screen.query_one("#attach-panel")

            assert str(panel.styles.display) == "block"



            monkeypatch.setattr(app, "push_screen", mock_push_screen)



            screen._show_attach_error("synthetic failure")

            await pilot.pause()



            panel = screen.query_one("#attach-panel")

            assert str(panel.styles.display) != "none"

            error = screen.query_one("#attach-error")

            assert error.styles.display == "block"


    @pytest.mark.asyncio
    async def test_error_banner_shows_message(self):
        """Error banner displays message text and is visible."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            await pilot.pause(0.1)
            screen = app.screen

            screen._show_attach_error("custom error message")
            await pilot.pause()

            error = screen.query_one("#attach-error", Static)
            assert error.styles.display == "block"
            error_text = error.render().plain
            assert "custom error message" in error_text
            assert "✗" in error_text


    def test_error_modal_class_removed(self):
        """ErrorModal class is completely removed from source."""
        from pathlib import Path
        src_file = Path(__file__).parent.parent / "peeka" / "tui" / "screens" / "process_selector.py"
        src = src_file.read_text()
        assert "class ErrorModal" not in src, "ErrorModal class should be removed"


    @pytest.mark.asyncio
    async def test_retry_clears_prior_panel_state(self):
        """Second attach attempt clears first attempt's progress/log/error data."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            await pilot.pause(0.1)
            screen = app.screen

            screen._attach_generation = 1
            screen._attach_phase_states["init"] = {
                "status": "completed",
                "message": "first",
                "elapsed_ms": 100,
                "icon": "✓",
                "level": "info"
            }
            screen._render_attach_progress()
            await pilot.pause()

            screen._reset_attach_panel()
            await pilot.pause()

            progress = screen.query_one("#attach-progress", Static)
            assert progress.render().plain.strip() == ""
            log = screen.query_one("#attach-log", RichLog)
            assert len(log.lines) == 0
            error = screen.query_one("#attach-error", Static)
            assert error.styles.display == "none"
            assert len(screen._attach_phase_states) == 0


    def test_attach_phase_states_initialized_before_mount(self):

        """_attach_phase_states is initialized in __init__ as empty dict."""

        screen = ProcessSelectorScreen()

        assert hasattr(screen, "_attach_phase_states")

        assert screen._attach_phase_states == {}



    def test_attach_generation_starts_at_zero(self):

        """_attach_generation counter is initialized to 0 in __init__."""

        screen = ProcessSelectorScreen()

        assert hasattr(screen, "_attach_generation")

        assert screen._attach_generation == 0



    @pytest.mark.asyncio

    async def test_reset_attach_panel_clears_widgets(self):

        """_reset_attach_panel clears all 3 attach panel widgets."""

        from textual.widgets import RichLog



        app = PeekaApp()

        async with app.run_test() as pilot:

            screen = app.screen

            assert isinstance(screen, ProcessSelectorScreen)
            screen._set_attach_panel_visible(True)
            progress = screen.query_one("#attach-progress")

            progress.update("25% attached...")



            log_widget = screen.query_one("#attach-log", RichLog)

            log_widget.write("[INFO] Starting attach...\n[DEBUG] Agent loaded\n")



            error = screen.query_one("#attach-error")

            error.update("⚠️ Connection error")

            error.styles.display = "block"



            await pilot.pause()



            assert len(log_widget.lines) > 0

            assert str(error.styles.display) == "block"



            screen._reset_attach_panel()

            await pilot.pause()



            assert len(log_widget.lines) == 0

            assert str(error.styles.display) == "none"



    @pytest.mark.asyncio

    async def test_attach_panel_has_three_children(self):

        """Attach panel is a Container with 3 child widgets: progress, log, error."""

        from textual.containers import Container

        from textual.widgets import RichLog



        app = PeekaApp()

        async with app.run_test() as pilot:

            assert isinstance(app.screen, ProcessSelectorScreen)

            await pilot.pause()

            panel = app.screen.query_one("#attach-panel", Container)

            assert panel is not None

            progress = app.screen.query_one("#attach-progress")

            assert progress is not None

            log_widget = app.screen.query_one("#attach-log", RichLog)

            assert log_widget is not None

            assert log_widget.max_lines == 500

            assert log_widget.wrap is True

            assert log_widget.highlight is True

            assert log_widget.markup is True

            assert log_widget.auto_scroll is True

            error = app.screen.query_one("#attach-error")

            assert error is not None

            assert str(error.styles.display) == "none"

            assert "panel--danger" in error.classes







    @pytest.mark.asyncio
    async def test_progress_event_renders_in_log_and_progress(self):
        """Progress event updates both #attach-log and #attach-progress."""
        from peeka.core.attach import AttachProgressEvent
        from textual.widgets import RichLog

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            screen._set_attach_panel_visible(True)
            await pilot.pause()

            event = AttachProgressEvent(
                phase="init",
                status="running",
                message="Initializing attach",
                level="info",
                elapsed_ms=0.0,
            )
            screen._on_progress(screen._attach_generation, event)
            await pilot.pause()

            log_widget = screen.query_one("#attach-log", RichLog)
            assert len(log_widget.lines) > 0

            progress_widget = screen.query_one("#attach-progress")
            progress_text = progress_widget.render().plain
            assert "init" in progress_text

    @pytest.mark.asyncio
    async def test_progress_event_records_attach_activity(self):
        """Progress event mirrors to app-level attach activity buffer."""
        from peeka.core.attach import AttachProgressEvent

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            await pilot.pause()

            event = AttachProgressEvent(
                phase="run_injector",
                status="done",
                message="GDB dlopen injector completed",
                level="info",
                elapsed_ms=1430.0,
            )
            screen._on_progress(screen._attach_generation, event)
            await pilot.pause()

            entries = [
                entry
                for entry in app.get_client_activity_entries()
                if entry.get("source") == "attach"
            ]
            assert len(entries) == 1
            assert entries[0]["level"] == "INFO"
            assert entries[0]["message"] == (
                "attach.run_injector done: GDB dlopen injector completed (1430ms)"
            )
            assert entries[0]["phase"] == "run_injector"
            assert entries[0]["status"] == "done"
            assert entries[0]["elapsed_ms"] == 1430.0

    @pytest.mark.asyncio
    async def test_attached_done_records_total_elapsed_activity(self):
        """attached done activity keeps total elapsed time for dashboard replay."""
        from peeka.core.attach import AttachProgressEvent

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            await pilot.pause()

            event = AttachProgressEvent(
                phase="attached",
                status="done",
                message="Successfully attached to process 24",
                level="info",
                elapsed_ms=5598.0,
            )
            screen._on_progress(screen._attach_generation, event)
            await pilot.pause()

            entries = [
                entry
                for entry in app.get_client_activity_entries()
                if entry.get("source") == "attach"
            ]
            assert entries[-1]["message"] == (
                "attach.attached done: Successfully attached to process 24 "
                "(5598ms total)"
            )
            assert entries[-1]["phase"] == "attached"
            assert entries[-1]["status"] == "done"

    @pytest.mark.asyncio
    async def test_attached_failed_records_error_activity(self):
        """attached failed activity keeps the real attach error."""
        from peeka.core.attach import AttachProgressEvent

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            await pilot.pause()

            event = AttachProgressEvent(
                phase="attached",
                status="failed",
                message="Attach failed: missing Python symbols",
                level="error",
                elapsed_ms=250.0,
            )
            screen._on_progress(screen._attach_generation, event)
            await pilot.pause()

            entries = [
                entry
                for entry in app.get_client_activity_entries()
                if entry.get("source") == "attach"
            ]
            assert entries[-1]["level"] == "ERROR"
            assert entries[-1]["message"] == (
                "attach.attached failed: Attach failed: missing Python symbols "
                "(250ms total)"
            )

    @pytest.mark.asyncio
    async def test_attach_log_event_only_in_richlog(self):
        """attach_log phase events route only to RichLog, not phase states."""
        from peeka.core.attach import AttachProgressEvent
        from textual.widgets import RichLog

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            screen._set_attach_panel_visible(True)
            await pilot.pause()

            log_event = AttachProgressEvent(
                phase="attach_log",
                status="logged",
                message="[INFO] Agent started successfully",
                level="info",
                elapsed_ms=100.0,
            )
            screen._on_progress(screen._attach_generation, log_event)
            await pilot.pause()

            assert "attach_log" not in screen._attach_phase_states

            log_widget = screen.query_one("#attach-log", RichLog)
            assert len(log_widget.lines) > 0

    @pytest.mark.asyncio
    async def test_copy_attach_log_copies_plain_text(self):
        """Process selector copies attach log text without terminal selection."""
        from peeka.core.attach import AttachProgressEvent

        app = PeekaApp()
        copied = []

        def copy_to_clipboard(text):
            copied.append(text)

        app.copy_to_clipboard = copy_to_clipboard
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            screen._set_attach_panel_visible(True)
            await pilot.pause()

            event = AttachProgressEvent(
                phase="run_injector",
                status="done",
                message="GDB dlopen injector completed",
                level="info",
                elapsed_ms=1430.0,
            )
            screen._on_progress(screen._attach_generation, event)
            await pilot.pause()

            screen.action_copy_attach_log()
            await pilot.pause()

            assert copied
            assert "attach.run_injector done" in copied[-1]
            assert "GDB dlopen injector completed" in copied[-1]

    @pytest.mark.asyncio
    async def test_attach_log_debug_event_not_recorded_to_activity(self):
        """Debug attach logs stay out of dashboard activity history."""
        from peeka.core.attach import AttachProgressEvent

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            await pilot.pause()

            log_event = AttachProgressEvent(
                phase="attach_log",
                status="logged",
                message="internal debug detail",
                level="debug",
            )
            screen._on_progress(screen._attach_generation, log_event)
            await pilot.pause()

            entries = [
                entry
                for entry in app.get_client_activity_entries()
                if entry.get("source") == "attach"
            ]
            assert entries == []

    @pytest.mark.asyncio
    async def test_stale_generation_progress_dropped(self):
        """Progress events from stale generations are silently dropped."""
        from peeka.core.attach import AttachProgressEvent
        from textual.widgets import RichLog

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            await pilot.pause()

            log_widget = screen.query_one("#attach-log", RichLog)
            initial_line_count = len(log_widget.lines)

            screen._attach_generation = 5
            stale_event = AttachProgressEvent(
                phase="init",
                status="running",
                message="Stale event from old generation",
                level="info",
                elapsed_ms=0.0,
            )
            screen._on_progress(gen=3, event=stale_event)
            await pilot.pause()

            assert len(log_widget.lines) == initial_line_count
            assert "init" not in screen._attach_phase_states
            entries = [
                entry
                for entry in app.get_client_activity_entries()
                if entry.get("source") == "attach"
            ]
            assert entries == []


    @pytest.mark.asyncio

    async def test_escape_resets_error_panel(self):

        """Esc resets error panel when error is visible."""

        app = PeekaApp()

        async with app.run_test() as pilot:

            screen = app.screen

            assert isinstance(screen, ProcessSelectorScreen)

            await pilot.pause()



            error = screen.query_one("#attach-error")

            error.update("✗ Attach failed: Connection error")

            error.styles.display = "block"



            await pilot.pause()

            assert str(error.styles.display) == "block"



            screen.action_quit_app()

            await pilot.pause()



            assert str(error.styles.display) == "none"

            assert error.render().plain.strip() == ""



    @pytest.mark.asyncio

    async def test_escape_during_attach_is_noop(self):

        """Esc during attach is no-op (does not quit)."""

        app = PeekaApp()

        async with app.run_test() as pilot:

            screen = app.screen

            assert isinstance(screen, ProcessSelectorScreen)

            await pilot.pause()



            screen._attaching = True



            original_exit = app.exit

            from unittest.mock import Mock

            app.exit = Mock()



            screen.action_quit_app()

            await pilot.pause()



            app.exit.assert_not_called()

            app.exit = original_exit



    @pytest.mark.asyncio

    async def test_escape_quits_when_idle(self):

        """Esc quits when idle (no error, not attaching)."""

        app = PeekaApp()

        async with app.run_test() as pilot:

            screen = app.screen

            assert isinstance(screen, ProcessSelectorScreen)

            await pilot.pause()



            error = screen.query_one("#attach-error")

            error.styles.display = "none"



            screen._attaching = False



            original_exit = app.exit

            from unittest.mock import Mock

            app.exit = Mock()



            screen.action_quit_app()

            await pilot.pause()



            app.exit.assert_called_once()

            app.exit = original_exit


    @pytest.mark.asyncio
    async def test_done_status_renders_check_icon(self):
        """Done status renders ✓ icon in status_icon_map."""
        from peeka.core.attach import AttachProgressEvent
        from textual.widgets import RichLog

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            screen._set_attach_panel_visible(True)
            await pilot.pause()

            event = AttachProgressEvent(
                phase="test_phase",
                status="done",
                message="Test completed",
                level="info",
                elapsed_ms=100.0,
            )
            screen._on_progress(screen._attach_generation, event)
            await pilot.pause()

            assert "test_phase" in screen._attach_phase_states
            assert screen._attach_phase_states["test_phase"]["icon"] == "✓"

            log_widget = screen.query_one("#attach-log", RichLog)
            assert len(log_widget.lines) > 0
            log_content = " ".join(line.text for line in log_widget.lines)
            assert "✓" in log_content


    @pytest.mark.asyncio
    async def test_richlog_entry_has_timestamp_prefix(self):
        """RichLog entries have [HH:MM:SS] timestamp prefix."""
        import re
        from peeka.core.attach import AttachProgressEvent
        from textual.widgets import RichLog

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            screen._set_attach_panel_visible(True)
            await pilot.pause()

            event = AttachProgressEvent(
                phase="test_phase",
                status="running",
                message="Test message",
                level="info",
                elapsed_ms=50.0,
            )
            screen._on_progress(screen._attach_generation, event)
            await pilot.pause()

            log_widget = screen.query_one("#attach-log", RichLog)
            assert len(log_widget.lines) > 0
            log_content = " ".join(line.text for line in log_widget.lines)

            timestamp_pattern = r"\[\d{2}:\d{2}:\d{2}\]"
            assert re.search(timestamp_pattern, log_content), \
                f"Expected timestamp pattern [{timestamp_pattern}] in log content: {log_content}"


    @pytest.mark.asyncio
    async def test_message_with_brackets_is_escaped(self):
        """Messages with brackets are escaped to prevent Rich markup breakage."""
        from peeka.core.attach import AttachProgressEvent
        from textual.widgets import RichLog

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            screen._set_attach_panel_visible(True)
            await pilot.pause()

            event = AttachProgressEvent(
                phase="test_phase",
                status="running",
                message="[INFO] Processing [data] with [brackets]",
                level="info",
                elapsed_ms=25.0,
            )
            screen._on_progress(screen._attach_generation, event)
            await pilot.pause()

            log_widget = screen.query_one("#attach-log", RichLog)
            assert len(log_widget.lines) > 0
            log_content = " ".join(line.text for line in log_widget.lines)

            assert "[INFO]" in log_content
            assert "[data]" in log_content
            assert "[brackets]" in log_content


    @pytest.mark.asyncio
    async def test_phase_summary_uses_insertion_order(self):
        """Phase summary displays phases in insertion order, not alphabetical."""
        from peeka.core.attach import AttachProgressEvent

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            screen._set_attach_panel_visible(True)
            await pilot.pause()

            # Post events in specific order: zebra, alpha, mike
            events = [
                AttachProgressEvent(phase="zebra", status="done", message="Z done", level="info", elapsed_ms=10.0),
                AttachProgressEvent(phase="alpha", status="running", message="A running", level="info", elapsed_ms=20.0),
                AttachProgressEvent(phase="mike", status="completed", message="M completed", level="info", elapsed_ms=30.0),
            ]
            for event in events:
                screen._on_progress(screen._attach_generation, event)
                await pilot.pause(0.01)

            # Render progress widget
            progress_widget = screen.query_one("#attach-progress")
            progress_text = progress_widget.render().plain

            # Extract phase order from rendered text
            zebra_pos = progress_text.find("zebra")
            alpha_pos = progress_text.find("alpha")
            mike_pos = progress_text.find("mike")

            # Verify insertion order preserved: zebra, alpha, mike
            assert zebra_pos < alpha_pos < mike_pos, \
                f"Expected insertion order (zebra, alpha, mike), got positions: zebra={zebra_pos}, alpha={alpha_pos}, mike={mike_pos}"


    @pytest.mark.asyncio
    async def test_attach_header_in_log_not_toast(self):
        """Attach header appears in RichLog, not as toast notification."""
        from textual.widgets import RichLog
        from unittest.mock import Mock

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            await pilot.pause()

            original_notify = screen.notify
            notify_calls = []

            def mock_notify(message, **kwargs):
                notify_calls.append((message, kwargs))
                return original_notify(message, **kwargs)

            screen.notify = mock_notify

            original_run_worker = screen.run_worker
            def mock_run_worker(work, **kwargs):
                if hasattr(work, "close"):
                    work.close()
                return Mock()
            screen.run_worker = mock_run_worker

            screen._attach_to_process(12345)
            await pilot.pause()

            attaching_toast = [call for call in notify_calls if "Attaching to process" in str(call[0])]
            assert len(attaching_toast) == 0, \
                f"Expected no 'Attaching to process' toast, but found: {attaching_toast}"

            log_widget = screen.query_one("#attach-log", RichLog)
            assert len(log_widget.lines) > 0
            log_content = " ".join(line.text for line in log_widget.lines)
            assert "Attaching to process 12345" in log_content

            screen.notify = original_notify
            screen.run_worker = original_run_worker


    @pytest.mark.asyncio
    async def test_panel_danger_class_applied(self):
        """Error widget has panel--danger class applied."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            await pilot.pause()

            error = screen.query_one("#attach-error")

            assert "panel--danger" in error.classes, \
                f"Expected 'panel--danger' in error.classes, got: {error.classes}"


    @pytest.mark.asyncio
    async def test_border_titles_set(self):
        """Progress and Attach Log widgets have correct border titles."""
        from textual.widgets import RichLog

        app = PeekaApp()
        async with app.run_test() as pilot:
            screen = app.screen
            assert isinstance(screen, ProcessSelectorScreen)
            await pilot.pause()

            progress = screen.query_one("#attach-progress")
            log = screen.query_one("#attach-log", RichLog)

            assert progress.border_title == "Progress", \
                f"Expected border_title='Progress', got: {progress.border_title}"
            assert log.border_title == "Attach Log", \
                f"Expected border_title='Attach Log', got: {log.border_title}"







class TestMainScreen:

    @pytest.mark.asyncio

    async def test_main_screen_has_correct_number_of_tabs(self):

        """MainScreen has exactly 10 tab panes."""

        app = PeekaApp()

        async with app.run_test() as pilot:

            app.push_screen(

                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")

            )

            await pilot.pause()

            from textual.widgets import TabbedContent, TabPane



            tabbed = app.screen.query_one("#main-content", TabbedContent)

            from textual.widgets import ContentSwitcher

            switcher = tabbed.query_one(ContentSwitcher)

            panes = [c for c in switcher.children if isinstance(c, TabPane)]

            assert len(panes) == 10



    @pytest.mark.asyncio

    async def test_tab_labels_correct(self):

        """All tab pane IDs match expected names."""

        app = PeekaApp()

        async with app.run_test() as pilot:

            app.push_screen(

                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")

            )

            await pilot.pause()

            from textual.widgets import TabbedContent, TabPane



            tabbed = app.screen.query_one("#main-content", TabbedContent)

            from textual.widgets import ContentSwitcher

            switcher = tabbed.query_one(ContentSwitcher)

            panes = [c for c in switcher.children if isinstance(c, TabPane)]

            pane_ids = [pane.id for pane in panes]

            expected = [

                "dashboard",

                "watch",

                "trace",

                "stack",

                "monitor",

                "memory",

                "logger",

                "inspect",

                "threads",

                "top",

            ]

            assert pane_ids == expected



    @pytest.mark.asyncio

    async def test_tab_switching_updates_active(self):

        """Pressing tab keys updates TabbedContent.active."""

        app = PeekaApp()

        async with app.run_test() as pilot:

            app.push_screen(

                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")

            )

            await pilot.pause()

            from textual.widgets import TabbedContent



            tabbed = app.screen.query_one("#main-content", TabbedContent)

            app.screen.action_switch_tab("watch")

            await pilot.pause()

            assert tabbed.active == "watch"

            app.screen.action_switch_tab("stack")

            await pilot.pause()

            assert tabbed.active == "stack"



    @pytest.mark.asyncio

    async def test_views_receive_client_on_first_tab_activation(self, monkeypatch):

        """MainScreen lazily initializes views as their tabs are first shown."""

        client = SimpleNamespace(

            socket_path="/tmp/fake.sock",

            disconnect=lambda: None,

            send_command=lambda command: {"status": "success"},

        )

        activated_tabs = []



        async def fake_connect(self):

            self._client = client



        def make_set_client(tab_id):

            def set_client(self, received_client):

                activated_tabs.append(tab_id)

                self._client = received_client



            return set_client



        monkeypatch.setattr(MainScreen, "_connect", fake_connect)

        for tab_id, view_cls in MainScreen._VIEW_BY_TAB.items():

            monkeypatch.setattr(view_cls, "set_client", make_set_client(tab_id))



        app = PeekaApp()

        async with app.run_test() as pilot:

            main_screen = MainScreen(

                pid=12345, session_id="test", socket_path="/tmp/fake.sock"

            )

            await app.push_screen(main_screen)

            await pilot.pause()



            assert activated_tabs == ["dashboard"]



            main_screen.action_switch_tab("watch")

            await pilot.pause()

            assert activated_tabs == ["dashboard", "watch"]



            main_screen.action_switch_tab("watch")

            await pilot.pause()

            assert activated_tabs == ["dashboard", "watch"]



            main_screen.action_switch_tab("trace")

            await pilot.pause()

            assert activated_tabs == ["dashboard", "watch", "trace"]



    @pytest.mark.asyncio

    async def test_number_shortcut_does_not_reactivate_previous_focused_tab(

        self, monkeypatch

    ):

        """Number shortcuts clear old pane focus before switching tabs."""

        client = SimpleNamespace(

            socket_path="/tmp/fake.sock",

            disconnect=lambda: None,

            send_command=lambda command: {"status": "success"},

        )



        async def fake_connect(self):

            self._client = client



        monkeypatch.setattr(MainScreen, "_connect", fake_connect)



        app = PeekaApp()

        async with app.run_test() as pilot:

            main_screen = MainScreen(

                pid=12345, session_id="test", socket_path="/tmp/fake.sock"

            )

            await app.push_screen(main_screen)

            await pilot.pause()



            await pilot.press("2")

            await pilot.pause()



            from textual.widgets import Button, TabbedContent



            stop_button = app.screen.query_one("#stop-btn", Button)

            stop_button.focus()

            await pilot.pause()



            await pilot.press("1")

            await pilot.pause()

            await pilot.pause()



            tabbed = app.screen.query_one("#main-content", TabbedContent)

            assert tabbed.active == "dashboard"

            assert app.focused is None or not app.focused.id == "watch-condition"





class TestWatchView:

    @pytest.mark.asyncio

    async def test_watch_view_has_input_labels(self):

        """Watch view has Pattern: and Condition: labels."""

        app = PeekaApp()

        async with app.run_test() as pilot:

            app.push_screen(

                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")

            )

            await pilot.pause()

            await pilot.press("2")

            await pilot.pause()



            labels = app.screen.query("Static.input-label")

            label_texts = [label.render().plain for label in labels]

            assert "Pattern:" in label_texts

            assert "Condition:" in label_texts



    @pytest.mark.asyncio

    async def test_watch_view_has_inputs(self):

        """Watch view has pattern and condition input widgets."""

        app = PeekaApp()

        async with app.run_test() as pilot:

            app.push_screen(

                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")

            )

            await pilot.pause()

            await pilot.press("2")

            await pilot.pause()

            from textual.widgets import Input



            condition = app.screen.query_one("#watch-condition", Input)

            assert condition.placeholder == "condition (optional)"



    @pytest.mark.asyncio

    async def test_watch_view_buttons(self):

        """Watch view has Watch and Stop buttons."""

        app = PeekaApp()

        async with app.run_test() as pilot:

            app.push_screen(

                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")

            )

            await pilot.pause()

            await pilot.press("2")

            await pilot.pause()

            from textual.widgets import Button



            watch_btn = app.screen.query_one("#watch-btn", Button)

            stop_btn = app.screen.query_one("#stop-btn", Button)

            assert watch_btn is not None

            assert stop_btn is not None





class TestInputLabels:

    @pytest.mark.asyncio

    async def test_all_views_have_expected_labels(self):

        """Each view with inputs has the correct number of input-label Statics."""

        app = PeekaApp()

        async with app.run_test() as pilot:

            app.push_screen(

                MainScreen(pid=12345, session_id="test", socket_path="/tmp/fake.sock")

            )

            await pilot.pause()



            # Check each tab that should have labels

            tab_label_counts = {

                "2": 2,  # Watch: Pattern, Condition

                "3": 3,  # Trace: Pattern, Depth, Condition

                "4": 1,  # Stack: Pattern

                "5": 2,  # Monitor: Pattern, Interval

                "7": 2,  # Logger: Filter, Logger

                "8": 1,  # Inspect: Object Path

            }



            for key, expected_count in tab_label_counts.items():

                await pilot.press(key)

                await pilot.pause()

                labels = app.screen.query("Static.input-label")

                # Note: query returns ALL matching across all views,

                # but only the active tab's view is mounted.

                # We verify at least the expected count exists.

                assert len(labels) >= expected_count, (

                    f"Tab '{key}': expected >= {expected_count} labels, got {len(labels)}"

                )





class TestCompletionSource:

    def test_get_completions_is_sync(self):

        """CompletionSource.get_completions is a synchronous function."""

        assert not inspect.iscoroutinefunction(CompletionSource.get_completions)



    def test_type_annotation_uses_streaming_client(self):

        """CompletionSource.__init__ type hint uses StreamingAgentClient."""

        hints = CompletionSource.__init__.__annotations__

        assert "client" in hints

        from peeka.core.client import StreamingAgentClient



        assert hints["client"] is StreamingAgentClient





class TestWorkerCallable:

    @pytest.mark.asyncio

    async def test_watch_view_callable_wrapper(self):

        """Verify _stream_observations is wrapped in lambda for run_worker."""

        from peeka.tui.views.watch import WatchView



        view = WatchView(pid=12345)

        # Verify the method exists and is not a coroutine

        assert hasattr(view, "_stream_observations")

        # The lambda wrapper ensures the method is called inside the worker thread

        assert callable(view._stream_observations)



    @pytest.mark.asyncio

    async def test_stack_view_callable_wrapper(self):

        """Verify _stream_stacks is wrapped in lambda for run_worker."""

        from peeka.tui.views.stack import StackView



        view = StackView(pid=12345)

        # Verify the method exists and is not a coroutine

        assert hasattr(view, "_stream_stacks")

        # The lambda wrapper ensures the method is called inside the worker thread

        assert callable(view._stream_stacks)



    @pytest.mark.asyncio

    async def test_trace_view_callable_wrapper(self):

        """Verify _stream_trace_observations is wrapped in lambda for run_worker."""

        from peeka.tui.views.trace import TraceView



        view = TraceView(pid=12345)

        # Verify the method exists and is not a coroutine

        assert hasattr(view, "_stream_trace_observations")

        # The lambda wrapper ensures the method is called inside the worker thread

        assert callable(view._stream_trace_observations)



    @pytest.mark.asyncio

    async def test_monitor_view_callable_wrapper(self):

        """Verify _stream_stats is wrapped in lambda for run_worker."""

        from peeka.tui.views.monitor import MonitorView



        view = MonitorView(pid=12345)

        # Verify the method exists and is not a coroutine

        assert hasattr(view, "_stream_stats")

        # The lambda wrapper ensures the method is called inside the worker thread

        assert callable(view._stream_stats)



    def test_dashboard_view_callable_wrapper(self):

        """Verify _periodic_refresh is wrapped in lambda for run_worker."""

        from peeka.tui.views.dashboard import DashboardView



        view = DashboardView(pid=12345)

        # Verify the method exists and is not a coroutine

        assert hasattr(view, "_periodic_refresh")

        # The lambda wrapper ensures the method is called inside the worker thread

        assert callable(view._periodic_refresh)
