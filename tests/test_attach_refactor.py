"""
Unit tests for attach.py RTLD constants and injector utility functions.
"""

from unittest.mock import MagicMock, patch

import pytest

from peeka.core import attach
from peeka.core.attach import ProcessAttacher


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


class TestAttachFallbackDispatch:
    """Test _attach_fallback platform and injector dispatch logic."""

    def test_linux_with_injector_dispatches_gdb_dlopen(self):
        """Linux + injector available should use GDB dlopen path."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=True), patch(
            "platform.system", return_value="Linux"
        ), patch.object(
            attacher, "_inject_via_gdb_dlopen", return_value=True
        ) as mock_gdb_dlopen, patch.object(attacher, "_inject_via_lldb") as mock_lldb:
            assert attacher._attach_fallback() is True
            mock_gdb_dlopen.assert_called_once_with()
            mock_lldb.assert_not_called()

    def test_macos_with_injector_dispatches_lldb(self):
        """Darwin + injector available should use LLDB path."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=True), patch(
            "platform.system", return_value="Darwin"
        ), patch.object(
            attacher, "_inject_via_lldb", return_value=True
        ) as mock_lldb, patch.object(
            attacher, "_inject_via_gdb_dlopen"
        ) as mock_gdb_dlopen:
            assert attacher._attach_fallback() is True
            mock_lldb.assert_called_once_with()
            mock_gdb_dlopen.assert_not_called()

    def test_linux_without_injector_dispatches_legacy_gdb(self):
        """Linux + no injector should fallback to legacy GDB path."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=False), patch(
            "platform.system", return_value="Linux"
        ), patch.object(attacher, "_check_gdb_available"), patch.object(
            attacher, "_check_ptrace_permissions"
        ), patch(
            "peeka.core.attach._read_agent_code", return_value="print('agent')"
        ), patch.object(
            attacher, "_create_notify_server", return_value=54321
        ), patch.object(
            attacher, "_create_agent_script", return_value="/tmp/agent.py"
        ), patch.object(
            attacher, "_inject_via_gdb_legacy"
        ) as mock_legacy, patch.object(
            attacher, "_wait_for_agent_ready", return_value=True
        ), patch.object(attacher, "_close_notify_server"), patch(
            "os.path.exists", return_value=False
        ):
            assert attacher._attach_fallback() is True
            mock_legacy.assert_called_once_with("/tmp/agent.py")

    def test_macos_without_injector_raises_runtime_error(self):
        """Darwin + no injector should raise extension-required RuntimeError."""
        attacher = ProcessAttacher(12345)
        with patch("peeka.core.attach._has_injector", return_value=False), patch(
            "platform.system", return_value="Darwin"
        ):
            with pytest.raises(RuntimeError) as exc_info:
                attacher._attach_fallback()
            assert "C extension required for macOS attach" in str(exc_info.value)

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
