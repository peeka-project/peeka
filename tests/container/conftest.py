"""Testcontainers fixtures for containerized E2E testing.

Provides Docker image building, container lifecycle management, and helper
functions for running target processes inside containers.
"""

import shlex
import time
from typing import Dict, Tuple

import pytest

# Conditionally import testcontainers - skip collection if not available
pytest.importorskip("testcontainers")

from testcontainers.core.container import DockerContainer
from testcontainers.core.image import DockerImage


# Session-scoped image fixtures (build once per test session)


@pytest.fixture(scope="session")
def gdb_image():
    """Use pre-built GDB test image (Python 3.12 + GDB + python3-dbg).

    Build: docker build -f docker/Dockerfile.test-gdb -t peeka-test:gdb .
    """
    return "peeka-test:gdb"


@pytest.fixture(scope="session")
def py314_image():
    """Use pre-built Python 3.14 test image (PEP 768 native attach).

    Build: docker build -f docker/Dockerfile.test-py314 -t peeka-test:py314 .
    """
    return "peeka-test:py314"


# Function-scoped container fixtures (fresh container per test)


@pytest.fixture(scope="function")
def gdb_container(gdb_image):
    """Start GDB-based container with ptrace capabilities."""
    with DockerContainer(str(gdb_image)).with_kwargs(
        cap_add=["SYS_PTRACE"],
        security_opt=["seccomp:unconfined"],
        init=True,
    ) as container:
        container.start()
        yield container


@pytest.fixture(scope="function")
def py314_container(py314_image):
    """Start Python 3.14 container with ptrace capabilities."""
    with DockerContainer(str(py314_image)).with_kwargs(
        cap_add=["SYS_PTRACE"],
        security_opt=["seccomp:unconfined"],
        init=True,
    ) as container:
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
def py314_target(py314_container):
    """Start target process in Python 3.14 container.

    Yields:
        Dict with keys: container (DockerContainer), pid (str)
    """
    pid = start_target_in_container(py314_container)
    yield {"container": py314_container, "pid": pid}
    cleanup_peeka_files_in_container(py314_container)


# Parametrized fixture for dual-version testing


@pytest.fixture(scope="function", params=["gdb", "py314"])
def container_target(request):
    """Parametrized fixture for testing across both container types.

    Yields:
        Dict with keys: container (DockerContainer), pid (str), type (str)
    """
    target_type = request.param
    if target_type == "gdb":
        target = request.getfixturevalue("gdb_target")
    else:
        target = request.getfixturevalue("py314_target")

    target["type"] = target_type
    yield target
