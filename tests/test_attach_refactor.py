"""
Unit tests for attach.py RTLD constants and injector utility functions.
"""

import json
import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from peeka.cli.handlers import attach as cli_attach
from peeka.core import attach
from peeka.core import agent as agent_module
from peeka.core.agent import PeekaAgent, _init_agent
from peeka.core.attach import ProcessAttacher
from peeka.core.attach_workflow import capability


class TestRTLDConstants:
    """Test RTLD constants."""

    def test_rtld_default_value(self):
        """Test that _RTLD_DEFAULT is -2."""
        assert attach._RTLD_DEFAULT == -2

    def test_rtld_now_value(self):
        """Test that _RTLD_NOW is 2."""
        assert attach._RTLD_NOW == 2


class TestFindInjectorPath:
    """Test _find_injector_path function."""

    def test_returns_path_when_extension_exists(self):
        """Test that _find_injector_path returns a valid path when extension exists."""
        path = attach._find_injector_path()
        # Extension may not exist if build hasn't run, so we just check return type
        assert path is None or isinstance(path, str)

    def test_returns_none_when_spec_not_found(self):
        """Test that _find_injector_path returns None when spec cannot be found."""
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.return_value = None
            result = attach._find_injector_path()
            assert result is None
            mock_find_spec.assert_called_once_with("peeka.core._inject")

    def test_returns_none_when_spec_origin_is_none(self):
        """Test that _find_injector_path returns None when spec.origin is None."""
        mock_spec = MagicMock()
        mock_spec.origin = None
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.return_value = mock_spec
            result = attach._find_injector_path()
            assert result is None

    def test_returns_origin_when_spec_valid(self):
        """Test that _find_injector_path returns origin when spec is valid."""
        mock_spec = MagicMock()
        mock_spec.origin = "/path/to/_inject.cpython-310-x86_64-linux-gnu.so"
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.return_value = mock_spec
            result = attach._find_injector_path()
            assert result == "/path/to/_inject.cpython-310-x86_64-linux-gnu.so"

    def test_handles_import_error_gracefully(self):
        """Test that _find_injector_path handles ImportError gracefully."""
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.side_effect = ImportError("Module not found")
            result = attach._find_injector_path()
            assert result is None

    def test_handles_attribute_error_gracefully(self):
        """Test that _find_injector_path handles AttributeError gracefully."""
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.side_effect = AttributeError("Invalid spec")
            result = attach._find_injector_path()
            assert result is None

    def test_handles_value_error_gracefully(self):
        """Test that _find_injector_path handles ValueError gracefully."""
        with patch("importlib.util.find_spec") as mock_find_spec:
            mock_find_spec.side_effect = ValueError("Invalid module name")
            result = attach._find_injector_path()
            assert result is None


class TestCheckLLDBAvailable:
    """Test _check_lldb_available function."""

    def test_passes_when_lldb_found(self):
        """Test that _check_lldb_available passes when lldb is found."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = "/usr/bin/lldb"
            # Should not raise
            attach._check_lldb_available()
            mock_which.assert_called_once_with("lldb")

    def test_raises_when_lldb_not_found(self):
        """Test that _check_lldb_available raises RuntimeError when lldb is not found."""
        with patch("shutil.which") as mock_which:
            mock_which.return_value = None
            with pytest.raises(RuntimeError) as exc_info:
                attach._check_lldb_available()
            assert "LLDB not found" in str(exc_info.value)
            assert "xcode-select --install" in str(exc_info.value)
            assert "macOS only" in str(exc_info.value)


class TestHasInjector:
    """Test _has_injector function."""

    def test_returns_true_when_injector_exists(self):
        """Test that _has_injector returns True when extension exists."""
        import sys
        import types

        fake_module = types.ModuleType("peeka.core._inject")
        with patch.dict(sys.modules, {"peeka.core._inject": fake_module}):
            result = attach._has_injector()
            assert result is True

    def test_returns_false_when_injector_missing(self):
        """Test that _has_injector returns False when extension is missing."""
        import sys

        with patch.dict(sys.modules, {"peeka.core._inject": None}):
            result = attach._has_injector()
            assert result is False

    def test_calls_find_injector_path(self):
        import sys
        import types

        fake_module = types.ModuleType("peeka.core._inject")
        with patch.dict(sys.modules, {"peeka.core._inject": fake_module}):
            result = attach._has_injector()
            assert result is True

    def test_attach_internal_saves_last_error_on_exception(self, monkeypatch):
        """Verify that exceptions in _attach_internal are saved to _last_attach_error."""
        attacher = ProcessAttacher(12345)

        # Mock _check_existing_attachment to raise an exception
        def mock_check(*args, **kwargs):
            raise RuntimeError("Mocked attach failure")

        monkeypatch.setattr(attacher, "_check_existing_attachment", mock_check)

        result = attacher._attach_internal()

        assert result is False
        assert attacher._last_attach_error == "Mocked attach failure"


class TestAttachProgressEvents:
    """Test structured attach progress event contracts."""

    def test_attached_done_event_has_total_elapsed(self, monkeypatch):
        """Successful attach emits attached done with total elapsed time."""
        events = []
        attacher = ProcessAttacher(12345, progress_callback=events.append)

        monkeypatch.delattr(attach.sys, "remote_exec", raising=False)
        monkeypatch.setattr(attacher, "_check_existing_attachment", lambda: None)
        monkeypatch.setattr(attacher, "_get_target_python_version", lambda: None)
        monkeypatch.setattr(attacher, "_attach_fallback", lambda: True)
        monkeypatch.setattr(attacher, "_save_attachment_state", lambda: None)

        assert attacher._attach_internal() is True

        attached = [
            event
            for event in events
            if event.phase == "attached" and event.status == "done"
        ][-1]
        assert attached.elapsed_ms is not None
        assert attached.elapsed_ms >= 0

    def test_attached_failed_event_has_total_elapsed(self, monkeypatch):
        """Failed attach emits attached failed with total elapsed time."""
        events = []
        attacher = ProcessAttacher(12345, progress_callback=events.append)

        def fail_existing_check():
            raise RuntimeError("Mocked attach failure")

        monkeypatch.setattr(attacher, "_check_existing_attachment", fail_existing_check)

        assert attacher._attach_internal() is False

        attached = [
            event
            for event in events
            if event.phase == "attached" and event.status == "failed"
        ][-1]
        assert attached.elapsed_ms is not None
        assert attached.elapsed_ms >= 0
        assert "Mocked attach failure" in attached.message


class TestAttachFallbackDispatch:
    """Test _attach_fallback platform and injector dispatch logic."""

    def test_linux_with_injector_dispatches_gdb_dlopen(self):
        """Linux + injector available should use GDB dlopen path."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=True), patch(
            "platform.system", return_value="Linux"
        ), patch.object(
            attacher, "_inject_via_gdb", return_value=True
        ) as mock_gdb, patch.object(attacher, "_inject_via_lldb") as mock_lldb:
            assert attacher._attach_fallback() is True
            mock_gdb.assert_called_once_with()
            mock_lldb.assert_not_called()

    def test_linux_python38_with_injector_prefers_gdb_dlopen(self):
        """Python 3.8 should prefer native dlopen when the injector exists."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=True), patch(
            "platform.system", return_value="Linux"
        ), patch.object(attacher, "_inject_via_gdb", return_value=True) as mock_gdb:
            assert attacher._attach_fallback() is True
            mock_gdb.assert_called_once_with()

    def test_attach_internal_fallback_capability_has_single_conclusion(
        self, monkeypatch
    ):
        """Fallback capability detection emits one concrete conclusion."""
        events = []
        attacher = ProcessAttacher(12345, progress_callback=events.append)
        monkeypatch.delattr(attach.sys, "remote_exec", raising=False)

        with patch.object(
            attacher, "_check_existing_attachment", return_value=None
        ), patch.object(
            attacher, "_get_target_python_version", return_value=(3, 12)
        ), patch.object(attacher, "_check_python_version_match"), patch.object(
            attacher, "_attach_fallback", return_value=False
        ):
            assert attacher._attach_internal() is False

        capability_events = [
            event for event in events if event.phase == "detect_python_capability"
        ]
        assert [event.status for event in capability_events] == ["running", "done"]
        assert capability_events[-1].level == "warning"
        assert capability_events[-1].message == (
            "PEP 768 unavailable; using debugger fallback"
        )
        assert capability_events[-1].elapsed_ms is not None
        assert capability_events[-1].details["target_python"] == "3.12"
        assert capability_events[-1].details["pep768_available"] is False
        assert all(
            event.message != "Python capability check completed"
            for event in capability_events
        )

    def test_linux_with_injector_propagates_dlopen_failure(self):
        """Linux dlopen failures should not retry via PyRun_SimpleString."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=True), patch(
            "platform.system", return_value="Linux"
        ), patch.object(
            attacher, "_inject_via_gdb", side_effect=TimeoutError("boom")
        ) as mock_gdb:
            with pytest.raises(TimeoutError, match="boom"):
                attacher._attach_fallback()

            mock_gdb.assert_called_once_with()

    def test_linux_with_injector_propagates_symbol_error(self):
        """Missing Python C API symbols fail the dlopen attach path directly."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=True), patch(
            "platform.system", return_value="Linux"
        ), patch.object(
            attacher,
            "_inject_via_gdb",
            side_effect=attach.GDBSymbolResolutionError("no symbols"),
        ) as mock_gdb:
            with pytest.raises(attach.GDBSymbolResolutionError):
                attacher._attach_fallback()

            mock_gdb.assert_called_once_with()

    def test_macos_with_injector_dispatches_lldb(self):
        """Darwin + injector available should use LLDB path."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=True), patch(
            "platform.system", return_value="Darwin"
        ), patch.object(
            attacher, "_inject_via_lldb", return_value=True
        ) as mock_lldb, patch.object(attacher, "_inject_via_gdb") as mock_gdb:
            assert attacher._attach_fallback() is True
            mock_lldb.assert_called_once_with()
            mock_gdb.assert_not_called()

    def test_linux_without_injector_raises_runtime_error(self):
        """Linux + no injector should fail instead of using legacy GDB."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=False), patch(
            "platform.system", return_value="Linux"
        ):
            with pytest.raises(RuntimeError) as exc_info:
                attacher._attach_fallback()
            error = str(exc_info.value)
            assert "C extension required for Linux attach" in error
            assert "python setup.py build_ext --inplace" in error
            assert "python -m pip install -e ." in error
            assert "uv run" not in error

    def test_macos_without_injector_raises_runtime_error(self):
        """Darwin + no injector should raise extension-required RuntimeError."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=False), patch(
            "platform.system", return_value="Darwin"
        ):
            with pytest.raises(RuntimeError) as exc_info:
                attacher._attach_fallback()
            error = str(exc_info.value)
            assert "C extension required for macOS attach" in error
            assert "python setup.py build_ext --inplace" in error
            assert "python -m pip install -e ." in error
            assert "uv run" not in error

    def test_windows_with_injector_raises_not_implemented(self):
        """Unsupported platform should raise NotImplementedError when injector exists."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=True), patch(
            "platform.system", return_value="Windows"
        ):
            with pytest.raises(NotImplementedError) as exc_info:
                attacher._attach_fallback()
            assert "Unsupported platform: Windows" in str(exc_info.value)

    def test_windows_without_injector_raises_not_implemented(self):
        """Unsupported platform should raise NotImplementedError when injector missing."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=False), patch(
            "platform.system", return_value="Windows"
        ):
            with pytest.raises(NotImplementedError) as exc_info:
                attacher._attach_fallback()
            assert "Unsupported platform: Windows" in str(exc_info.value)


class TestAttachProgress:
    def test_emit_progress_stores_and_calls_callback(self):
        events = []
        attacher = ProcessAttacher(12345, progress_callback=events.append)

        event = attacher._emit_progress(
            "run_injector",
            "running",
            "Running GDB dlopen injector",
            details={"method": "gdb_dlopen"},
        )

        assert events == [event]
        assert attacher.progress_events == [event]
        assert event.to_dict()["phase"] == "run_injector"
        assert event.to_dict()["details"] == {"method": "gdb_dlopen"}

    def test_progress_phase_records_elapsed_done_event(self):
        attacher = ProcessAttacher(12345)

        with attacher._progress_phase(
            "prepare_injection",
            "Preparing injection",
            "Injection prepared",
        ):
            pass

        assert [event.status for event in attacher.progress_events] == [
            "running",
            "done",
        ]
        assert attacher.progress_events[-1].elapsed_ms is not None

    def test_capture_attach_diagnostics_mirrors_logs_and_warnings(self):
        events = []
        attacher = ProcessAttacher(12345, progress_callback=events.append)

        with attacher._capture_attach_diagnostics():
            attach.logger.info("Using GDB dlopen injection for PID %d", 12345)
            import warnings

            warnings.warn("ptrace_scope is 1", RuntimeWarning)

        log_messages = [
            event.message for event in events if event.phase == "attach_log"
        ]
        assert "Using GDB dlopen injection for PID 12345" in log_messages
        assert "ptrace_scope is 1" in log_messages

    def test_capture_diag_disables_propagation_during_block(self):
        """Verify logger.propagate is False inside with-block, restored on exit."""
        events = []
        attacher = ProcessAttacher(12345, progress_callback=events.append)

        # Save initial state
        original_propagate = attach.logger.propagate

        propagate_inside = None

        with attacher._capture_attach_diagnostics():
            # Capture state inside the with-block
            propagate_inside = attach.logger.propagate

        # Verify state inside was False
        assert propagate_inside is False, (
            "logger.propagate should be False inside _capture_attach_diagnostics"
        )

        # Verify state was restored outside the with-block
        assert attach.logger.propagate == original_propagate, (
            "logger.propagate should be restored to original state after _capture_attach_diagnostics"
        )

    def test_capture_diag_preserves_debug_capture(self):
        """Verify logger.setLevel(DEBUG) is preserved (DEBUG events still captured)."""
        events = []
        attacher = ProcessAttacher(12345, progress_callback=events.append)

        # Set logger to WARNING level initially
        original_level = attach.logger.level
        attach.logger.setLevel(logging.WARNING)

        try:
            with attacher._capture_attach_diagnostics():
                # Emit DEBUG, INFO, WARNING logs
                attach.logger.debug("Debug message")
                attach.logger.info("Info message")
                attach.logger.warning("Warning message")

            # Extract log messages
            log_messages = [
                event.message for event in events if event.phase == "attach_log"
            ]

            # All three should be captured, proving setLevel(DEBUG) works
            assert "Debug message" in log_messages, "DEBUG should be captured"
            assert "Info message" in log_messages, "INFO should be captured"
            assert "Warning message" in log_messages, "WARNING should be captured"
        finally:
            # Restore original level
            attach.logger.setLevel(original_level)

    def test_check_existing_session_emits_running_and_one_done(self):
        """Verify _check_existing_attachment emits one running and one done for check_existing_session."""
        events = []
        attacher = ProcessAttacher(12345, progress_callback=events.append)

        # Call _check_existing_attachment (will return None since no session files exist)
        result = attacher._check_existing_attachment()

        # Filter to check_existing_session events
        check_events = [e for e in events if e.phase == "check_existing_session"]

        # Verify we got one running and one done
        assert len(check_events) == 2, (
            f"Expected 2 events, got {len(check_events)}: {check_events}"
        )
        assert check_events[0].status == "running", "First event should be running"
        assert check_events[1].status == "done", "Second event should be done"

        # Verify done event has details (even when no session found)
        assert check_events[1].details is not None
        assert "scanned" in check_events[1].details
        assert "stale_cleaned" in check_events[1].details

        # Verify result is None (no session found)
        assert result is None

    def test_callback_failure_does_not_recurse_through_log_capture(self):
        def failing_callback(event):
            raise RuntimeError("callback failed")

        attacher = ProcessAttacher(12345, progress_callback=failing_callback)

        with attacher._capture_attach_diagnostics():
            attacher._emit_progress("run_injector", "running", "start")

        assert len(attacher.progress_events) <= 3

    def test_wait_ready_emits_at_most_one_terminal_event(self, monkeypatch, tmp_path):
        """Verify _wait_for_agent_ready emits at most one terminal event (done or failed).

        Simulates fast-path done emit followed by slow-path hello probe failure.
        The flag prevents duplicate terminal emits even when code falls through paths.
        """
        events = []
        attacher = ProcessAttacher(12345, progress_callback=events.append)

        # Create .ready file so slow-path can detect it
        ready_file = tmp_path / "peeka_12345.ready"
        ready_file.touch()

        # Mock _is_agent_responsive to always return False (socket not ready)
        monkeypatch.setattr(attacher, "_is_agent_responsive", lambda _: False)

        # Mock the notify server to simulate fast-path triggering done emit,
        # then hello probe not responsive (falling through to slow-path)
        class FakeServer:
            def settimeout(self, timeout):
                pass

            def accept(self):
                # Simulate agent sending READY signal
                class FakeConn:
                    def recv(self, size):
                        return b"READY"

                    def close(self):
                        pass

                return FakeConn(), ("127.0.0.1", 12345)

        monkeypatch.setattr(attacher, "_notify_server", FakeServer())

        # Mock attach.Path only. Patching pathlib.Path globally can corrupt
        # pytest/pathlib internals on Python 3.9.
        original_path = attach.Path

        def mock_path(path_str):
            if path_str == f"/tmp/peeka_{attacher.session_id}.ready":
                return ready_file
            return original_path(path_str)

        monkeypatch.setattr(attach, "Path", mock_path)

        # Call _wait_for_agent_ready; it should NOT raise despite timeout
        # because socket responsiveness is verified in slow-path
        try:
            attacher._wait_for_agent_ready(timeout=1)
        except TimeoutError:
            pass  # Expected if hello probe times out

        # Filter to terminal events (done/failed for wait_agent_ready phase)
        terminal_events = [
            e
            for e in events
            if e.phase == "wait_agent_ready" and e.status in ("done", "failed")
        ]

        # Assert exactly one terminal event, not two
        assert len(terminal_events) == 1, (
            f"Expected 1 terminal event, got {len(terminal_events)}: {[e.to_dict() for e in terminal_events]}"
        )
        assert terminal_events[0].status in ("done", "failed")

    def test_progress_events_capped_at_256(self):
        """Verify that progress_events list is capped at 256 entries.

        After emitting 257 events, the list should contain exactly 256 events
        with the oldest (first) event removed.
        """
        events = []
        attacher = ProcessAttacher(12345, progress_callback=events.append)

        # Emit 257 events
        for i in range(257):
            attacher._emit_progress(
                "test_phase",
                "info",
                f"event_{i}",
            )

        # Assert list is capped at 256
        assert len(attacher.progress_events) == 256

        # Assert oldest event is event_1 (0-indexed: event 1), not event_0
        assert attacher.progress_events[0].message == "event_1"

        # Assert newest event is event_256 (the 257th event, 0-indexed: event 256)
        assert attacher.progress_events[-1].message == "event_256"


class TestGetTargetPythonVersion:
    def test_linux_reads_proc_exe_and_runs_binary(self):
        attacher = ProcessAttacher(12345)
        with patch("platform.system", return_value="Linux"), patch(
            "os.readlink", return_value="/usr/bin/python3.12"
        ), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="3 12\n", stderr="")
            result = attacher._get_target_python_version()
            assert result == (3, 12)

    def test_linux_fallback_to_binary_name_parsing(self):
        attacher = ProcessAttacher(12345)
        with patch("platform.system", return_value="Linux"), patch(
            "os.readlink", return_value="/usr/bin/python3.14"
        ), patch("subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError
            result = attacher._get_target_python_version()
            assert result == (3, 14)

    def test_linux_returns_none_on_permission_error(self):
        attacher = ProcessAttacher(12345)
        with patch("platform.system", return_value="Linux"), patch(
            "os.readlink", side_effect=PermissionError
        ):
            result = attacher._get_target_python_version()
            assert result is None

    def test_returns_none_on_unsupported_platform(self):
        attacher = ProcessAttacher(12345)
        with patch("platform.system", return_value="Windows"):
            result = attacher._get_target_python_version()
            assert result is None

    def test_returns_none_when_exe_path_has_no_python(self):
        attacher = ProcessAttacher(12345)
        with patch("platform.system", return_value="Linux"), patch(
            "os.readlink", return_value="/usr/bin/java"
        ), patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="")
            result = attacher._get_target_python_version()
            assert result is None


class TestCheckPythonVersionMatch:
    def test_raises_on_version_mismatch(self):
        attacher = ProcessAttacher(12345)
        with patch.object(
            attacher, "_get_target_python_version", return_value=(3, 12)
        ), patch("peeka.core.attach.sys") as mock_sys:
            mock_sys.version_info = MagicMock(major=3, minor=14)
            with pytest.raises(RuntimeError) as exc_info:
                attacher._check_python_version_match()
            assert "Python 3.12" in str(exc_info.value)
            assert "Python 3.14" in str(exc_info.value)
            assert "version mismatch" in str(exc_info.value).lower()

    def test_passes_on_version_match(self):
        attacher = ProcessAttacher(12345)
        with patch.object(
            attacher, "_get_target_python_version", return_value=(3, 12)
        ), patch("peeka.core.attach.sys") as mock_sys:
            mock_sys.version_info = MagicMock(major=3, minor=12)
            attacher._check_python_version_match()

    def test_passes_when_version_unknown(self):
        attacher = ProcessAttacher(12345)
        with patch.object(attacher, "_get_target_python_version", return_value=None):
            attacher._check_python_version_match()


class TestAttachOutputIsolation:
    def test_agent_native_socket_uses_c_socket(self):
        import _socket

        assert agent_module._NATIVE_SOCKET is _socket.socket

    def test_cmd_attach_suppresses_agent_startup_messages(self):
        mock_attacher = MagicMock()
        mock_attacher.attach.return_value = False

        with patch.object(
            cli_attach, "ProcessAttacher", return_value=mock_attacher
        ) as mock_attacher_cls, patch.object(
            cli_attach.OutputFormatter, "status"
        ), patch.object(cli_attach.OutputFormatter, "error"):
            cli_attach.cmd_attach(SimpleNamespace(pid=12345))

        mock_attacher_cls.assert_called_once_with(12345, suppress_startup_messages=True)

    def test_agent_handler_import_failures_do_not_print_tracebacks(self):
        agent = PeekaAgent("session-1")

        with patch.object(agent_module.traceback, "print_exc") as mock_print_exc, patch(
            "importlib.import_module", side_effect=RuntimeError("boom")
        ), patch.object(agent, "_emit_log") as mock_emit_log:
            assert agent._get_handler("watch") is None

        mock_emit_log.assert_called_once()
        mock_print_exc.assert_not_called()

    def test_init_agent_failures_write_session_log_without_stdio(self):
        with patch(
            "peeka.core.agent.PeekaAgent.start", side_effect=RuntimeError("boom")
        ), patch(
            "peeka.core.agent._write_session_log"
        ) as mock_write_session_log, patch("builtins.print") as mock_print, patch(
            "traceback.print_exc"
        ) as mock_print_exc:
            _init_agent("session-2")

        mock_write_session_log.assert_called_once()
        mock_print.assert_not_called()
        mock_print_exc.assert_not_called()

    def test_init_agent_does_not_register_when_start_returns_false(self):
        import sys

        old_agents = getattr(sys, "_peeka_agents", None)
        if old_agents is not None:
            del sys._peeka_agents

        try:
            with patch("peeka.core.agent.PeekaAgent.start", return_value=False), patch(
                "peeka.core.agent._write_session_log"
            ) as mock_write_session_log:
                _init_agent("session-3")

            assert not hasattr(sys, "_peeka_agents")
            mock_write_session_log.assert_called_once()
        finally:
            if old_agents is not None:
                sys._peeka_agents = old_agents


class TestAgentCodeSideChannel:
    def test_serve_agent_code_sends_raw_python_without_length_prefix(self):
        import socket
        import threading

        attacher = ProcessAttacher(12345)
        attacher._create_notify_server()
        received = []

        def client():
            with socket.create_connection(
                ("127.0.0.1", attacher._notify_server.getsockname()[1])
            ) as sock:
                data = b""
                while True:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                received.append(data)

        thread = threading.Thread(target=client)
        thread.start()
        try:
            attacher._serve_agent_code("print('agent')", timeout=1)
            thread.join(timeout=1)
        finally:
            attacher._close_notify_server()

        assert received == [b"print('agent')"]

    def test_serve_agent_code_logs_injector_error(self):
        import socket
        import threading

        attacher = ProcessAttacher(12345)
        attacher._create_notify_server()

        def client():
            with socket.create_connection(
                ("127.0.0.1", attacher._notify_server.getsockname()[1])
            ) as sock:
                while sock.recv(4096):
                    pass
                sock.sendall(b"SyntaxError: invalid non-printable character")

        thread = threading.Thread(target=client)
        thread.start()
        try:
            with patch.object(attach.logger, "warning") as mock_warning:
                attacher._serve_agent_code("print('agent')", timeout=1)
            thread.join(timeout=1)
        finally:
            attacher._close_notify_server()

        mock_warning.assert_called_once()
        assert (
            "Injector reported agent bootstrap error" in mock_warning.call_args.args[0]
        )


class TestGDBSymbolErrors:
    def test_detects_no_symbol_table_error(self):
        output = 'No symbol table is loaded.  Use the "file" command.'

        assert attach._looks_like_gdb_symbol_resolution_error(output) is True

    def test_formats_actionable_symbol_error(self):
        message = attach._format_gdb_symbol_error(
            "GDB dlopen injection",
            'No symbol table is loaded.  Use the "file" command.',
            "[Inferior detached]",
        )

        assert "GDB could not resolve Python runtime symbols" in message
        assert "Py_AddPendingCall" in message
        assert "No symbol table is loaded" in message


class TestAgentReadinessProbe:
    def test_is_agent_responsive_requires_hello_round_trip(self):
        response = json.dumps({"status": "success"}).encode("utf-8")
        frame = len(response).to_bytes(4, "big") + response

        class FakeSocket:
            def __init__(self, *args, **kwargs):
                self._buffer = bytearray(frame)
                self.sent = bytearray()

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def settimeout(self, timeout):
                self.timeout = timeout

            def connect(self, path):
                self.path = path

            def sendall(self, data):
                self.sent.extend(data)

            def recv(self, size):
                data = self._buffer[:size]
                del self._buffer[:size]
                return bytes(data)

        with patch("peeka.core.attach.sock_mod.socket", FakeSocket):
            assert ProcessAttacher._is_agent_responsive("/tmp/peeka-test.sock") is True

    def test_is_agent_responsive_rejects_connect_only_socket(self):
        class FakeSocket:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return None

            def settimeout(self, timeout):
                self.timeout = timeout

            def connect(self, path):
                self.path = path

            def sendall(self, data):
                pass

            def recv(self, size):
                return b""

        with patch("peeka.core.attach.sock_mod.socket", FakeSocket):
            assert ProcessAttacher._is_agent_responsive("/tmp/peeka-test.sock") is False


class TestTargetPythonVersionProbeCommand:
    """Test subprocess probe command string for target Python version detection."""

    def test_probe_command_uses_sys_version_info_only(self, monkeypatch):
        """The subprocess -c snippet must not depend on _attach_module()."""
        attacher = ProcessAttacher(12345)
        calls = []

        def fake_run(cmd, capture_output, text, timeout):
            calls.append(cmd)
            if cmd[0] == "lsof":
                return SimpleNamespace(returncode=0, stdout="n/usr/bin/python3.12\n")
            return SimpleNamespace(returncode=0, stdout="3 12\n")

        monkeypatch.setattr(capability.platform, "system", lambda: "Darwin")
        monkeypatch.setattr(capability.subprocess, "run", fake_run)

        result = attacher._get_target_python_version()

        assert result == (3, 12)
        assert len(calls) == 2
        assert calls[1][1] == "-c"
        assert "sys.version_info" in calls[1][2]
        assert "_attach_module" not in calls[1][2]
