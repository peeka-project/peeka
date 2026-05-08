"""
Container E2E tests for gevent attach regression.

REGRESSION CONTEXT:
  Gevent monkey-patching can cause BlockingSwitchOutError during agent startup
  if the agent's socket operations are not properly handled. This test verifies
  that attach and watch operations succeed without blocking errors when the
  target process uses gevent.

TEST COVERAGE:
  - Python 3.8 (GDB-based attachment)
  - Python 3.12 (GDB-based attachment)
  - NOT Python 3.14 (PEP 768 native attachment — gevent not applicable)

COMMAND TO RUN:
  uv run pytest tests/container/test_attach_gevent.py -v -m "container and gevent" --timeout=180

EXPECTED BEHAVIOR:
  - Helper starts gevent target with deterministic ready markers
  - Attach command succeeds and returns socket path
  - Watch command captures observations without blocking errors
  - Target log contains NO BlockingSwitchOutError or agent initialization failures
  - Cleanup removes all temp files and processes

FAILURE DIAGNOSTICS:
  If a test fails, assertion messages include:
  - Attach CLI output (JSONL)
  - Watch CLI output (JSONL)
  - Target log (/tmp/gevent-target.log)
  - Agent log (/tmp/peeka_*.log) if present
  This provides full context for debugging ready timeouts, watch failures, or blocking errors.
"""

import json

import pytest

from tests.container.conftest import exec_in_container, cleanup_peeka_files_in_container

pytestmark = [pytest.mark.container, pytest.mark.gevent]

ATTACH_TIMEOUT_SECONDS = 150


def start_gevent_target_in_container(container, timeout: int = 10) -> str:
    """Start gevent target in container and wait for ready signal.

    Args:
        container: DockerContainer instance
        timeout: Maximum wait time for ready signal in seconds

    Returns:
        PID of gevent target process as string

    Raises:
        AssertionError: If target fails to start or PID is invalid
    """
    # Clear stale files first
    exec_in_container(container, "rm -f /tmp/peeka_* /tmp/gevent-target.*", timeout=5)
    exec_in_container(
        container,
        "find /app -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true",
        timeout=10,
    )

    # Start gevent target in background
    shell_cmd = f"""
python /app/examples/gevent_attach_target.py --interval 0.01 >/tmp/gevent-target.log 2>&1 &
echo $! > /tmp/gevent-target.pid
PID=$!

# Poll for ready markers (threading patched + socket patched + GEVENT_TARGET_READY)
for i in $(seq 1 {timeout}0); do
    if grep -q "threading patched: True" /tmp/gevent-target.log 2>/dev/null && \
       grep -q "socket patched: True" /tmp/gevent-target.log 2>/dev/null && \
       grep -q "GEVENT_TARGET_READY" /tmp/gevent-target.log 2>/dev/null; then
        echo "READY"
        break
    fi
    sleep 0.1
done

# Verify ready markers appeared
if ! grep -q "GEVENT_TARGET_READY" /tmp/gevent-target.log 2>/dev/null; then
    kill $PID 2>/dev/null || true
    echo "TIMEOUT: Gevent target failed to start within {timeout} seconds" >&2
    cat /tmp/gevent-target.log >&2
    exit 1
fi

cat /tmp/gevent-target.pid
""".strip()

    exit_code, output = exec_in_container(container, shell_cmd, timeout=timeout + 5)

    assert exit_code == 0, f"Gevent target startup failed:\n{output}"

    # Extract PID from last line
    lines = output.strip().split("\n")
    pid = lines[-1].strip()

    assert pid.isdigit(), f"Invalid PID: {pid}"

    return pid


class TestGeventAttachRegression:
    """Test attach/watch against gevent monkey-patched targets."""

    @pytest.fixture(scope="function", params=["py38", "gdb"])
    def gevent_target(self, request):
        """Start gevent target in Python 3.8 or 3.12 container.

        Yields:
            Dict with keys: container (DockerContainer), pid (str), type (str)
        """
        target_type = request.param
        if target_type == "py38":
            container = request.getfixturevalue("py38_container")
        else:  # gdb
            container = request.getfixturevalue("gdb_container")

        pid = start_gevent_target_in_container(container)
        yield {"container": container, "pid": pid, "type": target_type}

        # Cleanup: kill target and remove temp files
        exec_in_container(container, f"kill {pid} 2>/dev/null || true", timeout=5)
        cleanup_peeka_files_in_container(container)
        exec_in_container(container, "rm -f /tmp/gevent-target.*", timeout=5)

    def test_gevent_attach_and_watch_no_blocking_error(self, gevent_target):
        """Verify attach and watch succeed without BlockingSwitchOutError."""
        container = gevent_target["container"]
        pid = gevent_target["pid"]
        target_type = gevent_target["type"]

        # Execute attach command
        exit_code, attach_output = exec_in_container(
            container,
            f"python -m peeka.cli.main attach {pid}",
            timeout=ATTACH_TIMEOUT_SECONDS,
        )

        # Parse JSONL output from attach
        lines = [l for l in attach_output.strip().split("\n") if l.strip()]
        json_lines = [l for l in lines if l.startswith("{")]

        success_line = None
        for line in json_lines:
            try:
                data = json.loads(line)
                if data.get("type") == "success" and data.get("command") == "attach":
                    success_line = data
                    break
            except json.JSONDecodeError:
                continue

        # Fetch target log for diagnostics
        _, target_log = exec_in_container(
            container, "cat /tmp/gevent-target.log 2>/dev/null || echo EMPTY", timeout=5
        )

        assert success_line is not None, (
            f"[{target_type}] No attach success line found.\n"
            f"Attach output:\n{attach_output}\n"
            f"Target log:\n{target_log}"
        )
        assert "data" in success_line, (
            f"[{target_type}] Missing 'data' field in success line: {success_line}\n"
            f"Attach output:\n{attach_output}\n"
            f"Target log:\n{target_log}"
        )
        assert "socket" in success_line["data"], (
            f"[{target_type}] Missing 'socket' in data: {success_line['data']}\n"
            f"Attach output:\n{attach_output}\n"
            f"Target log:\n{target_log}"
        )

        # Execute watch command
        exit_code, watch_output = exec_in_container(
            container,
            'python -m peeka.cli.main watch "index.handler" -n 3',
            timeout=30,
        )

        assert exit_code == 0, (
            f"[{target_type}] Watch command did not exit successfully.\n"
            f"Exit code: {exit_code}\n"
            f"Watch output:\n{watch_output}\n"
            f"Attach output:\n{attach_output}\n"
            f"Target log:\n{target_log}"
        )

        # Parse JSONL output from watch
        watch_lines = [l for l in watch_output.strip().split("\n") if l.strip()]
        watch_json_lines = [l for l in watch_lines if l.startswith("{")]

        has_watch_started = False
        has_observation = False

        for line in watch_json_lines:
            try:
                data = json.loads(line)
                if data.get("event") == "watch_started":
                    has_watch_started = True
                if data.get("type") == "observation":
                    has_observation = True
            except json.JSONDecodeError:
                continue

        assert has_watch_started or has_observation, (
            f"[{target_type}] No valid watch events found.\n"
            f"Watch output:\n{watch_output}\n"
            f"Attach output:\n{attach_output}\n"
            f"Target log:\n{target_log}"
        )

        # Inspect target log for absence of failure signatures
        failure_signatures = [
            "BlockingSwitchOutError",
            "Agent initialization timeout",
            "[peeka Agent] Start failed",
        ]

        for signature in failure_signatures:
            assert signature not in target_log, (
                f"[{target_type}] Found failure signature '{signature}' in target log.\n"
                f"Target log:\n{target_log}\n"
                f"Attach output:\n{attach_output}\n"
                f"Watch output:\n{watch_output}"
            )

        # Inspect agent log (if exists) for absence of failure signatures
        exit_code, agent_log_check = exec_in_container(
            container, "ls /tmp/peeka_*.log 2>/dev/null || echo NONE", timeout=5
        )

        if "NONE" not in agent_log_check:
            # Get first agent log file
            exit_code, agent_log = exec_in_container(
                container,
                "cat $(ls /tmp/peeka_*.log | head -1) 2>/dev/null || echo EMPTY",
                timeout=5,
            )

            if "EMPTY" not in agent_log:
                for signature in failure_signatures:
                    assert signature not in agent_log, (
                        f"[{target_type}] Found failure signature '{signature}' in agent log.\n"
                        f"Agent log:\n{agent_log}\n"
                        f"Target log:\n{target_log}\n"
                        f"Attach output:\n{attach_output}\n"
                        f"Watch output:\n{watch_output}"
                    )

        # Success: attach and watch completed without regression signatures
        print(
            f"\n[{target_type}] SUCCESS: Attach and watch completed without blocking errors"
        )
        print(f"  Attach: {success_line['data']['socket']}")
        print(
            f"  Watch: {'watch_started' if has_watch_started else 'observations'} confirmed"
        )

    def test_gevent_helper_starts_target(self, request):
        """Verify helper successfully starts gevent target in both containers."""
        for container_type in ["py38_container", "gdb_container"]:
            container = request.getfixturevalue(container_type)

            # Start target using helper
            pid = start_gevent_target_in_container(container)

            # Verify PID is numeric
            assert pid.isdigit(), f"[{container_type}] Invalid PID: {pid}"

            # Verify target process is running
            exit_code, ps_output = exec_in_container(
                container, f"test -d /proc/{pid} && echo ALIVE", timeout=5
            )

            assert exit_code == 0, f"[{container_type}] Process {pid} not found"
            assert "ALIVE" in ps_output, (
                f"[{container_type}] Process {pid} not running"
            )

            # Verify log contains patch status
            exit_code, log_content = exec_in_container(
                container, "cat /tmp/gevent-target.log", timeout=5
            )

            assert "threading patched: True" in log_content, (
                f"[{container_type}] Missing threading patch status in log"
            )
            assert "socket patched: True" in log_content, (
                f"[{container_type}] Missing socket patch status in log"
            )
            assert "GEVENT_TARGET_READY" in log_content, (
                f"[{container_type}] Missing GEVENT_TARGET_READY marker in log"
            )

            # Cleanup
            exec_in_container(container, f"kill {pid} 2>/dev/null || true", timeout=5)
            exec_in_container(container, "rm -f /tmp/gevent-target.*", timeout=5)

            print(f"\n[{container_type}] SUCCESS: Helper started gevent target (PID={pid})")

    def test_gevent_cleanup_removes_files(self, request):
        """Verify cleanup removes target process and temp files."""
        for container_type in ["py38_container", "gdb_container"]:
            container = request.getfixturevalue(container_type)

            # Start target
            pid = start_gevent_target_in_container(container)

            # Attach to create peeka files
            exec_in_container(
                container, f"python -m peeka.cli.main attach {pid}", timeout=30
            )

            # Cleanup
            exec_in_container(container, f"kill {pid} 2>/dev/null || true", timeout=5)
            cleanup_peeka_files_in_container(container)
            exec_in_container(container, "rm -f /tmp/gevent-target.*", timeout=5)

            # Verify process killed
            exit_code, _ = exec_in_container(
                container, f"test -d /proc/{pid} && echo ALIVE", timeout=5
            )

            assert exit_code != 0, (
                f"[{container_type}] Process {pid} still running after cleanup"
            )

            # Verify peeka files removed
            exit_code, ls_output = exec_in_container(
                container, "ls /tmp/peeka_* 2>/dev/null || echo NONE", timeout=5
            )

            assert "NONE" in ls_output, (
                f"[{container_type}] Peeka files still exist after cleanup:\n{ls_output}"
            )

            # Verify target files removed
            exit_code, ls_output = exec_in_container(
                container, "ls /tmp/gevent-target.* 2>/dev/null || echo NONE", timeout=5
            )

            assert "NONE" in ls_output, (
                f"[{container_type}] Target files still exist after cleanup:\n{ls_output}"
            )

            print(f"\n[{container_type}] SUCCESS: Cleanup removed all files and process")
