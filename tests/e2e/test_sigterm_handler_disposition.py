import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

TARGET_SCRIPTS = Path(__file__).parent / "target_scripts"


@pytest.mark.e2e
@pytest.mark.timeout(30)
def test_sigterm_default_termination(has_ptrace_permission: bool, tmp_path: Path) -> None:
    if not has_ptrace_permission:
        pytest.skip("ptrace_scope != 0: cannot attach to target process")

    script = TARGET_SCRIPTS / "sigterm_target_default.py"
    proc = subprocess.Popen([sys.executable, str(script)])
    try:
        time.sleep(2.0)
        os.kill(proc.pid, signal.SIGTERM)
        returncode = proc.wait(timeout=5)
        assert returncode == -signal.SIGTERM, (
            f"Expected returncode {-signal.SIGTERM} (SIG_DFL termination), got {returncode}"
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


@pytest.mark.e2e
@pytest.mark.timeout(30)
def test_sigterm_callable_forwarded(has_ptrace_permission: bool, tmp_path: Path) -> None:
    if not has_ptrace_permission:
        pytest.skip("ptrace_scope != 0: cannot attach to target process")

    sentinel = tmp_path / "sigterm_sentinel"
    script = TARGET_SCRIPTS / "sigterm_target_callable.py"
    env = {**os.environ, "PEEKA_SENTINEL_PATH": str(sentinel)}
    proc = subprocess.Popen([sys.executable, str(script)], env=env)
    try:
        time.sleep(2.0)
        os.kill(proc.pid, signal.SIGTERM)
        returncode = proc.wait(timeout=5)
        assert sentinel.exists(), "Sentinel file not written — callable prev handler was not invoked"
        assert returncode == 42, f"Expected returncode 42 from user handler sys.exit(42), got {returncode}"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


@pytest.mark.e2e
@pytest.mark.timeout(30)
def test_sigterm_sig_ign_no_op(has_ptrace_permission: bool, tmp_path: Path) -> None:
    if not has_ptrace_permission:
        pytest.skip("ptrace_scope != 0: cannot attach to target process")

    script = TARGET_SCRIPTS / "sigterm_target_ignore.py"
    proc = subprocess.Popen([sys.executable, str(script)])
    try:
        time.sleep(2.0)
        os.kill(proc.pid, signal.SIGTERM)
        time.sleep(1.0)
        assert proc.poll() is None, (
            "Process exited after SIGTERM but SIG_IGN should keep it alive"
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


@pytest.mark.e2e
@pytest.mark.timeout(30)
def test_sigterm_stop_exception_still_exits(has_ptrace_permission: bool, tmp_path: Path) -> None:
    if not has_ptrace_permission:
        pytest.skip("ptrace_scope != 0: cannot attach to target process")

    script = TARGET_SCRIPTS / "sigterm_target_default.py"
    proc = subprocess.Popen([sys.executable, str(script)])
    try:
        time.sleep(2.0)
        os.kill(proc.pid, signal.SIGTERM)
        returncode = proc.wait(timeout=5)
        assert returncode == -signal.SIGTERM, (
            f"Process must exit via SIG_DFL even if stop() raises; got {returncode}"
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


@pytest.mark.e2e
@pytest.mark.timeout(30)
def test_sigterm_handler_restored_before_stop(has_ptrace_permission: bool, tmp_path: Path) -> None:
    if not has_ptrace_permission:
        pytest.skip("ptrace_scope != 0: cannot attach to target process")

    script = TARGET_SCRIPTS / "sigterm_target_default.py"
    proc = subprocess.Popen([sys.executable, str(script)])
    try:
        time.sleep(2.0)
        os.kill(proc.pid, signal.SIGTERM)
        returncode = proc.wait(timeout=5)
        assert returncode == -signal.SIGTERM, (
            f"Process must exit with SIG_DFL disposition; got {returncode}. "
            "Anti-recursion: if handler not restored before stop(), re-entrant SIGTERM would cause hang."
        )
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
