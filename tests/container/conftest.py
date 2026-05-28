"""Testcontainers fixtures for containerized E2E testing.

Provides Docker image building, container lifecycle management, and helper
functions for running target processes inside containers.

Images only contain base environment (Python + system deps). Host code is
mounted via volume at /app with PYTHONPATH=/app, so Python sources always
reflect the latest checkout. GDB-based containers build the native _inject
extension inside the container before attach tests run.
"""

import shlex
from pathlib import Path
from typing import Tuple

import pytest

pytest.importorskip("testcontainers")

from testcontainers.core.container import DockerContainer

_PROJECT_ROOT = str(Path(__file__).resolve().parents[2])


@pytest.fixture(scope="session")
def gdb_image():
    """Use pre-built GDB test image (Python 3.12 + GDB + python3-dbg).

    Build: docker build --network=host -f docker/test.Dockerfile-3.12 -t peeka-test:3.12 .
    """
    return "peeka-test:3.12"


@pytest.fixture(scope="session")
def py38_image():
    """Use pre-built Python 3.8 test image (GDB + ptrace attach).

    Build: docker build --network=host -f docker/test.Dockerfile-3.8 -t peeka-test:3.8 .
    """
    return "peeka-test:3.8"


@pytest.fixture(scope="session")
def py314_image():
    """Use pre-built Python 3.14 test image (PEP 768 native attach).

    Build: docker build --network=host -f docker/test.Dockerfile-3.14 -t peeka-test:3.14 .
    """
    return "peeka-test:3.14"


@pytest.fixture(scope="function")
def gdb_container(gdb_image):
    """Start GDB-based container with host code bind-mounted at /app."""
    with (
        DockerContainer(str(gdb_image))
        .with_volume_mapping(_PROJECT_ROOT, "/app", mode="rw")
        .with_kwargs(
            cap_add=["SYS_PTRACE"],
            security_opt=["seccomp:unconfined"],
            init=True,
        ) as container
    ):
        container.start()
        ensure_injector_built_in_container(container)
        yield container


@pytest.fixture(scope="function")
def py38_container(py38_image):
    """Start Python 3.8 container with host code bind-mounted at /app."""
    with (
        DockerContainer(str(py38_image))
        .with_volume_mapping(_PROJECT_ROOT, "/app", mode="rw")
        .with_kwargs(
            cap_add=["SYS_PTRACE"],
            security_opt=["seccomp:unconfined"],
            init=True,
        ) as container
    ):
        container.start()
        ensure_injector_built_in_container(container)
        yield container


@pytest.fixture(scope="function")
def py314_container(py314_image):
    """Start Python 3.14 container with host code bind-mounted at /app."""
    with (
        DockerContainer(str(py314_image))
        .with_volume_mapping(_PROJECT_ROOT, "/app", mode="rw")
        .with_kwargs(
            cap_add=["SYS_PTRACE"],
            security_opt=["seccomp:unconfined"],
            init=True,
        ) as container
    ):
        container.start()
        yield container


# Helper functions


def exec_in_container(container, cmd: str, timeout: int = 30) -> Tuple[int, str]:
    """Execute command in container with timeout.

    Args:
        container: DockerContainer instance
        cmd: Shell command to execute
        timeout: Maximum execution time in seconds

    Returns:
        Tuple of (exit_code, output_string)
    """
    exit_code, output_bytes = container.exec(
        ["bash", "-c", f"timeout {timeout} bash -c {shlex.quote(cmd)}"]
    )
    return exit_code, output_bytes.decode("utf-8", errors="replace")


def ensure_injector_built_in_container(container) -> None:
    """Build peeka.core._inject in a GDB test container if it is missing."""
    check_cmd = """
cd /app
python - <<'PY'
import peeka.core._inject as inject
print(inject.__file__)
PY
""".strip()
    exit_code, _ = exec_in_container(container, check_cmd, timeout=10)
    if exit_code == 0:
        return

    build_cmd = "cd /app && python setup.py build_ext --inplace"
    exit_code, output = exec_in_container(container, build_cmd, timeout=120)
    assert exit_code == 0, (
        "Failed to build peeka.core._inject inside the test container.\n"
        f"Command: {build_cmd}\n"
        f"Output:\n{output}"
    )

    exit_code, output = exec_in_container(container, check_cmd, timeout=10)
    assert exit_code == 0, (
        "peeka.core._inject still cannot be imported after container build.\n"
        f"Output:\n{output}"
    )


def start_target_in_container(container, timeout: int = 10) -> str:
    """Start target process in container and wait for ready signal.

    Args:
        container: DockerContainer instance
        timeout: Maximum wait time for ready signal in seconds

    Returns:
        PID of target process as string

    Raises:
        AssertionError: If target fails to start or PID is invalid
    """
    # Build compound shell command:
    # 1. Start target in background, redirect output, capture PID
    # 2. Poll for ready file (timeout*10 iterations @ 100ms = timeout seconds)
    # 3. Return PID
    shell_cmd = f"""
python /app/tests/e2e/target_scripts/simple_loop.py >/tmp/target.log 2>&1 &
echo $! > /tmp/target.pid
PID=$!
for i in $(seq 1 {timeout}0); do
    if [ -f /tmp/peeka_e2e_target.ready ]; then
        echo "READY"
        break
    fi
    sleep 0.1
done
if [ ! -f /tmp/peeka_e2e_target.ready ]; then
    kill $PID 2>/dev/null || true
    echo "TIMEOUT: Target failed to start within {timeout} seconds" >&2
    exit 1
fi
cat /tmp/target.pid
""".strip()

    exit_code, output = exec_in_container(container, shell_cmd, timeout=timeout + 5)

    assert exit_code == 0, f"Target startup failed: {output}"

    # Extract PID from last line
    lines = output.strip().split("\n")
    pid = lines[-1].strip()

    assert pid.isdigit(), f"Invalid PID: {pid}"

    return pid


def start_async_target_in_container(container, timeout: int = 15) -> str:
    """Start asyncio target process in container and wait for ready signal.

    Args:
        container: DockerContainer instance
        timeout: Maximum wait time for ready signal in seconds

    Returns:
        PID of target process as string

    Raises:
        AssertionError: If target fails to start or PID is invalid
    """
    # Build compound shell command:
    # 1. Start asyncio target in background, redirect output, capture PID
    # 2. Poll for ready file (timeout*10 iterations @ 100ms = timeout seconds)
    # 3. Return PID
    shell_cmd = f"""
PEEKA_TEST_READY_FILE=/tmp/peeka_async_ready python /app/examples/asyncio_attach_target.py --duration 0 >/tmp/asyncio_target.log 2>&1 &
echo $! > /tmp/asyncio_target.pid
PID=$!
for i in $(seq 1 {timeout}0); do
    if [ -f /tmp/peeka_async_ready ]; then
        echo "READY"
        break
    fi
    sleep 0.1
done
if [ ! -f /tmp/peeka_async_ready ]; then
    kill $PID 2>/dev/null || true
    echo "TIMEOUT: Async target failed to start within {timeout} seconds" >&2
    exit 1
fi
cat /tmp/asyncio_target.pid
""".strip()

    exit_code, output = exec_in_container(container, shell_cmd, timeout=timeout + 5)

    assert exit_code == 0, f"Async target startup failed: {output}"

    # Extract PID from last line
    lines = output.strip().split("\n")
    pid = lines[-1].strip()

    assert pid.isdigit(), f"Invalid PID: {pid}"

    return pid


def cleanup_peeka_files_in_container(container):
    """Remove peeka temporary files from container.

    Args:
        container: DockerContainer instance
    """
    exec_in_container(container, "rm -f /tmp/peeka_*", timeout=5)


# Function-scoped target fixtures (start target + cleanup)


@pytest.fixture(scope="function")
def gdb_target(gdb_container):
    """Start target process in GDB container.

    Yields:
        Dict with keys: container (DockerContainer), pid (str)
    """
    pid = start_target_in_container(gdb_container)
    yield {"container": gdb_container, "pid": pid}
    cleanup_peeka_files_in_container(gdb_container)


@pytest.fixture(scope="function")
def py38_target(py38_container):
    """Start target process in Python 3.8 container.

    Yields:
        Dict with keys: container (DockerContainer), pid (str)
    """
    pid = start_target_in_container(py38_container)
    yield {"container": py38_container, "pid": pid}
    cleanup_peeka_files_in_container(py38_container)


@pytest.fixture(scope="function")
def py314_target(py314_container):
    """Start target process in Python 3.14 container.

    Yields:
        Dict with keys: container (DockerContainer), pid (str)
    """
    pid = start_target_in_container(py314_container)
    yield {"container": py314_container, "pid": pid}
    cleanup_peeka_files_in_container(py314_container)


# Parametrized fixture for dual-version testing


@pytest.fixture(scope="function", params=["py38", "gdb", "py314"])
def container_target(request):
    """Parametrized fixture for testing across container types (all Python versions).

    Yields:
        Dict with keys: container (DockerContainer), pid (str), type (str)
    """
    target_type = request.param
    if target_type == "py38":
        target = request.getfixturevalue("py38_target")
    elif target_type == "gdb":
        target = request.getfixturevalue("gdb_target")
    else:
        target = request.getfixturevalue("py314_target")

    target["type"] = target_type
    yield target


# Async target fixtures (asyncio demo)


@pytest.fixture(scope="function")
def gdb_async_target(gdb_container):
    """Start asyncio target process in GDB container.

    Yields:
        Tuple of (container, pid_str)
    """
    pid = start_async_target_in_container(gdb_container)
    yield (gdb_container, pid)
    exec_in_container(
        gdb_container,
        f"kill -TERM {pid} 2>/dev/null; pkill -9 -f asyncio_attach_target.py 2>/dev/null; rm -f /tmp/peeka_async_ready /tmp/asyncio_target.pid /tmp/asyncio_target.log; true",
        timeout=10,
    )


@pytest.fixture(scope="function")
def py314_async_target(py314_container):
    """Start asyncio target process in Python 3.14 container.

    Yields:
        Tuple of (container, pid_str)
    """
    pid = start_async_target_in_container(py314_container)
    yield (py314_container, pid)
    exec_in_container(
        py314_container,
        f"kill -TERM {pid} 2>/dev/null; pkill -9 -f asyncio_attach_target.py 2>/dev/null; rm -f /tmp/peeka_async_ready /tmp/asyncio_target.pid /tmp/asyncio_target.log; true",
        timeout=10,
    )
