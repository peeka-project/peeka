import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Generator, Dict, Any, Tuple

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.parent
TARGET_SCRIPTS = Path(__file__).parent / "target_scripts"
EXAMPLES_DIR = PROJECT_ROOT / "examples"
ASYNC_TARGET_FILENAME = "asyncio_attach_target.py"


@pytest.fixture
def has_ptrace_permission() -> bool:
    ptrace_scope = Path("/proc/sys/kernel/yama/ptrace_scope")
    if ptrace_scope.exists():
        try:
            scope = int(ptrace_scope.read_text().strip())
            return scope == 0
        except (ValueError, PermissionError):
            return False
    return True


@pytest.fixture
def has_pep768() -> bool:
    return hasattr(sys, "remote_exec")


@pytest.fixture
def has_gdb() -> bool:
    import shutil

    return shutil.which("gdb") is not None


@pytest.fixture
def target_process(tmp_path) -> Generator[Dict[str, Any], None, None]:
    script = TARGET_SCRIPTS / "simple_loop.py"
    if not script.exists():
        script = tmp_path / "target.py"
        script.write_text("""
import os
import time

class Calculator:
    def add(self, a, b):
        return a + b
    def multiply(self, a, b):
        return a * b

def main():
    pid_file = os.environ.get("PEEKA_TEST_PID_FILE", "/tmp/peeka_e2e_target.pid")
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
    ready_file = os.environ.get("PEEKA_TEST_READY_FILE", "/tmp/peeka_e2e_target.ready")
    open(ready_file, "w").close()
    calc = Calculator()
    counter = 0
    while counter < 10000:
        calc.add(counter, counter + 1)
        calc.multiply(counter, 2)
        counter += 1
        time.sleep(0.1)

if __name__ == "__main__":
    main()
""")

    pid_file = tmp_path / "target.pid"
    ready_file = tmp_path / "target.ready"

    env = os.environ.copy()
    env["PEEKA_TEST_PID_FILE"] = str(pid_file)
    env["PEEKA_TEST_READY_FILE"] = str(ready_file)

    proc = subprocess.Popen(
        [sys.executable, str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )

    for _ in range(50):
        if ready_file.exists():
            break
        time.sleep(0.1)
    else:
        proc.kill()
        pytest.fail("Target process failed to start within 5 seconds")

    yield {
        "process": proc,
        "pid": proc.pid,
        "pid_file": pid_file,
        "ready_file": ready_file,
        "script": script,
    }

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

    pid_file.unlink(missing_ok=True)
    ready_file.unlink(missing_ok=True)


@pytest.fixture
def async_target_process() -> Generator[Tuple[subprocess.Popen, int], None, None]:
    """Spawn asyncio_attach_target.py and yield (process, PID).
    
    Waits up to 15s for ready file; reads PID from file and validates against proc.pid.
    Gracefully terminates on teardown with 8s timeout before kill.
    """
    target_path = EXAMPLES_DIR / ASYNC_TARGET_FILENAME
    if not target_path.exists():
        pytest.fail(f"Target script not found: {target_path}")
    
    ready_dir = tempfile.mkdtemp()
    ready_file = Path(ready_dir) / "ready"
    
    env = os.environ.copy()
    env["PEEKA_TEST_READY_FILE"] = str(ready_file)
    env["PYTHONUNBUFFERED"] = "1"
    
    proc = subprocess.Popen(
        [sys.executable, str(target_path), "--duration", "0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    
    # Poll up to 15s for ready file
    for _ in range(150):
        if ready_file.exists():
            break
        time.sleep(0.1)
    else:
        proc.terminate()
        pytest.fail("asyncio target failed to become ready")
    
    # Read PID from ready file
    pid_content = ready_file.read_text().strip()
    try:
        pid_from_file = int(pid_content)
    except ValueError:
        proc.terminate()
        pytest.fail(f"Invalid PID in ready file: {pid_content}")
    
    # Validate PID matches process
    if pid_from_file != proc.pid:
        proc.terminate()
        pytest.fail(f"PID mismatch: file={pid_from_file}, proc={proc.pid}")
    
    yield (proc, proc.pid)
    
    # Teardown: terminate gracefully, then kill if needed
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
    
    # Cleanup tempdir
    import shutil
    shutil.rmtree(ready_dir, ignore_errors=True)


@pytest.fixture
def cleanup_peeka_files():
    yield
    import glob

    for f in glob.glob("/tmp/peeka_*"):
        try:
            Path(f).unlink()
        except (PermissionError, FileNotFoundError):
            pass

