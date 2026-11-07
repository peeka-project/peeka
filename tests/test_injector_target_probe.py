"""Unit tests for the target-side C extension loadability probe."""

import logging
import subprocess
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from peeka.core import attach
from peeka.core.attach import ProcessAttacher

SO = "/opt/peeka/peeka/core/_inject.abi3.so"
GLIBC_ERR = (
    "Traceback (most recent call last):\n"
    '  File "/usr/lib/python3.8/ctypes/__init__.py", line 373, in __init__\n'
    "OSError: /lib/x86_64-linux-gnu/libc.so.6: version `GLIBC_2.34' not found "
    f"(required by {SO})\n"
)


def _readlink_factory(exe="/usr/bin/python3.8", same_ns=True):
    def fake_readlink(path):
        if path.endswith("/exe"):
            return exe
        if path == "/proc/self/ns/mnt":
            return "mnt:[1]"
        if path.endswith("/ns/mnt"):
            return "mnt:[1]" if same_ns else "mnt:[2]"
        raise OSError(path)

    return fake_readlink


def _completed(returncode=0, stderr="", stdout=""):
    return SimpleNamespace(returncode=returncode, stderr=stderr, stdout=stdout)


@pytest.fixture(autouse=True)
def _linux():
    with patch.object(attach.sys, "platform", "linux"):
        yield


class TestProbeInjectorInTarget:
    def test_loadable_same_namespace_runs_target_exe(self):
        with patch.object(attach.os, "readlink", side_effect=_readlink_factory()), patch.object(
            attach.subprocess, "run", return_value=_completed(0)
        ) as run:
            assert attach._probe_injector_in_target(123, SO) == (True, "")
        cmd = run.call_args[0][0]
        assert cmd[0] == "/usr/bin/python3.8"
        assert cmd[-1] == SO
        assert "ctypes.CDLL" in cmd[cmd.index("-c") + 1]
        assert run.call_args[1]["timeout"] == attach._INJECTOR_PROBE_TIMEOUT

    def test_glibc_mismatch_reports_reason(self):
        with patch.object(attach.os, "readlink", side_effect=_readlink_factory()), patch.object(
            attach.subprocess, "run", return_value=_completed(1, stderr=GLIBC_ERR)
        ):
            assert attach._probe_injector_in_target(123, SO) == (
                False,
                "GLIBC_2.34 not found",
            )

    def test_cross_namespace_uses_nsenter(self):
        with patch.object(
            attach.os, "readlink", side_effect=_readlink_factory(same_ns=False)
        ), patch.object(attach.os, "access", return_value=True) as access, patch.object(
            attach.shutil, "which", return_value="/usr/bin/nsenter"
        ), patch.object(attach.subprocess, "run", return_value=_completed(0)) as run:
            assert attach._probe_injector_in_target(123, SO) == (True, "")
        access.assert_called_once_with("/proc/123/root/usr/bin/python3.8", attach.os.X_OK)
        cmd = run.call_args[0][0]
        assert cmd[:5] == ["/usr/bin/nsenter", "--target=123", "--mount", "--", "/usr/bin/python3.8"]

    def test_cross_namespace_without_permission_is_inconclusive(self):
        with patch.object(
            attach.os, "readlink", side_effect=_readlink_factory(same_ns=False)
        ), patch.object(attach.os, "access", return_value=True), patch.object(
            attach.shutil, "which", return_value="/usr/bin/nsenter"
        ), patch.object(
            attach.subprocess,
            "run",
            return_value=_completed(1, stderr="nsenter: reassociate to namespace 'ns/mnt' failed: Operation not permitted"),
        ):
            loadable, reason = attach._probe_injector_in_target(123, SO)
        assert loadable is None
        assert "permission" in reason

    def test_cross_namespace_exe_not_executable_is_inconclusive(self):
        with patch.object(
            attach.os, "readlink", side_effect=_readlink_factory(same_ns=False)
        ), patch.object(attach.os, "access", return_value=False), patch.object(
            attach.subprocess, "run"
        ) as run:
            loadable, _ = attach._probe_injector_in_target(123, SO)
        assert loadable is None
        run.assert_not_called()

    def test_unreadable_exe_is_inconclusive(self):
        with patch.object(attach.os, "readlink", side_effect=PermissionError("denied")), patch.object(
            attach.subprocess, "run"
        ) as run:
            loadable, _ = attach._probe_injector_in_target(123, SO)
        assert loadable is None
        run.assert_not_called()

    def test_non_python_executable_is_not_run(self):
        with patch.object(
            attach.os, "readlink", side_effect=_readlink_factory(exe="/usr/bin/uwsgi")
        ), patch.object(attach.subprocess, "run") as run:
            loadable, _ = attach._probe_injector_in_target(123, SO)
        assert loadable is None
        run.assert_not_called()

    def test_timeout_is_inconclusive(self):
        with patch.object(attach.os, "readlink", side_effect=_readlink_factory()), patch.object(
            attach.subprocess, "run", side_effect=subprocess.TimeoutExpired("python", 5)
        ):
            loadable, reason = attach._probe_injector_in_target(123, SO)
        assert loadable is None
        assert "timed out" in reason

    def test_exec_error_is_inconclusive(self):
        with patch.object(attach.os, "readlink", side_effect=_readlink_factory()), patch.object(
            attach.subprocess, "run", side_effect=PermissionError("exec denied")
        ):
            loadable, _ = attach._probe_injector_in_target(123, SO)
        assert loadable is None

    def test_unrelated_failure_is_inconclusive(self):
        with patch.object(attach.os, "readlink", side_effect=_readlink_factory()), patch.object(
            attach.subprocess,
            "run",
            return_value=_completed(1, stderr="ModuleNotFoundError: No module named '_ctypes'"),
        ):
            loadable, _ = attach._probe_injector_in_target(123, SO)
        assert loadable is None

    def test_non_linux_skips(self):
        with patch.object(attach.sys, "platform", "darwin"), patch.object(
            attach.subprocess, "run"
        ) as run:
            loadable, _ = attach._probe_injector_in_target(123, SO)
        assert loadable is None
        run.assert_not_called()


class TestCheckInjectorLoadableInTarget:
    def _attacher(self):
        return ProcessAttacher(pid=4242)

    def test_not_loadable_logs_and_raises_before_gdb(self, caplog):
        attacher = self._attacher()
        with patch.object(attach, "_find_injector_path", return_value=SO), patch.object(
            attach, "_probe_injector_in_target", return_value=(False, "GLIBC_2.34 not found")
        ), caplog.at_level(logging.INFO, logger="peeka.core.attach"):
            with pytest.raises(RuntimeError, match="GLIBC_2.34 not found"):
                attacher._check_injector_loadable_in_target()
        assert (
            "C extension not loadable in target (GLIBC_2.34 not found); skipping dlopen path"
            in caplog.text
        )

    @pytest.mark.parametrize("result", [(True, ""), (None, "probe timed out after 5s")])
    def test_loadable_or_inconclusive_keeps_original_path(self, result):
        attacher = self._attacher()
        with patch.object(attach, "_find_injector_path", return_value=SO), patch.object(
            attach, "_probe_injector_in_target", return_value=result
        ):
            attacher._check_injector_loadable_in_target()

    def test_inject_via_gdb_stops_before_launching_gdb(self):
        attacher = self._attacher()
        with patch.object(attacher, "_check_gdb_available"), patch.object(
            attacher, "_check_ptrace_permissions"
        ), patch.object(attach, "_find_injector_path", return_value=SO), patch.object(
            attach, "_probe_injector_in_target", return_value=(False, "GLIBC_2.34 not found")
        ), patch.object(attacher, "_create_notify_server") as notify, patch(
            "peeka.core.attach_workflow.injectors.subprocess.run"
        ) as run:
            with pytest.raises(RuntimeError, match="not loadable in target"):
                attacher._inject_via_gdb()
        notify.assert_not_called()
        run.assert_not_called()
