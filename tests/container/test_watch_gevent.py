"""Container E2E test for watch command under gevent."""

import json

import pytest

from tests.container.conftest import cleanup_peeka_files_in_container, exec_in_container

pytestmark = [pytest.mark.container]


def _json_lines(output: str):
    """Yield parsed JSONL records from command output."""
    for line in output.strip().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _start_gevent_target(container) -> str:
    """Start the gevent target and return its PID."""
    command = """
python /app/examples/gevent_attach_target.py --interval 0.02 --duration 0 >/tmp/gevent_target.log 2>&1 &
echo $! > /tmp/gevent_target.pid
PID=$!
for i in $(seq 1 150); do
    if grep -q "GEVENT_TARGET_READY" /tmp/gevent_target.log 2>/dev/null; then
        echo "READY"
        break
    fi
    sleep 0.1
done
if ! grep -q "GEVENT_TARGET_READY" /tmp/gevent_target.log 2>/dev/null; then
    kill $PID 2>/dev/null || true
    cat /tmp/gevent_target.log >&2
    exit 1
fi
cat /tmp/gevent_target.pid
""".strip()
    exit_code, output = exec_in_container(container, command, timeout=20)
    assert exit_code == 0, f"Gevent target startup failed:\n{output}"
    pid = output.strip().splitlines()[-1].strip()
    assert pid.isdigit(), f"Invalid gevent target PID: {pid}"
    return pid


def _attach(container, pid: str) -> None:
    """Attach Peeka to a target PID."""
    exit_code, output = exec_in_container(
        container, f"python -m peeka.cli.main attach {pid}", timeout=30
    )
    assert exit_code == 0, f"Attach failed:\n{output}"


class TestWatchGevent:
    """Watch command gevent compatibility tests."""

    def test_watch_gevent_returns_observations(self, gdb_container):
        """Watch collects observations from a gevent-patched target."""
        container = gdb_container
        pid = _start_gevent_target(container)

        try:
            _attach(container, pid)

            exit_code, output = exec_in_container(
                container,
                "python -m peeka.cli.main watch 'index.handler' -n 3",
                timeout=20,
            )
            assert exit_code == 0, f"Watch command failed:\n{output}"

            records = list(_json_lines(output))

            observations = [
                record for record in records if record.get("type") == "observation"
            ]
            assert observations, f"No observations in watch output:\n{output}"

            watch_started = next(
                (
                    record
                    for record in records
                    if record.get("event") == "watch_started"
                ),
                None,
            )
            assert watch_started is not None, f"No watch_started event:\n{output}"
            meta = watch_started.get("meta")
            assert isinstance(meta, dict), f"Missing watch meta:\n{watch_started}"
            assert meta["gevent_state"] in (
                "patched",
                "active_hub",
            ), f"Unexpected gevent_state: {meta.get('gevent_state')}"

            for obs in observations:
                assert "watch_id" in obs, (
                    f"Observation missing watch_id field:\n{obs}"
                )

        finally:
            exec_in_container(
                container,
                (
                    f"kill {pid} 2>/dev/null; "
                    "pkill -9 -f gevent_attach_target.py 2>/dev/null; "
                    "rm -f /tmp/gevent_target.*; true"
                ),
                timeout=10,
            )
            cleanup_peeka_files_in_container(container)

    def test_watch_gevent_agent_stays_responsive(self, gdb_container):
        """Agent remains responsive after a watch run against a gevent target."""
        container = gdb_container
        pid = _start_gevent_target(container)

        try:
            _attach(container, pid)

            exit_code, output = exec_in_container(
                container,
                "python -m peeka.cli.main watch 'index.handler' -n 1",
                timeout=20,
            )
            assert exit_code == 0, f"Watch command failed:\n{output}"

            exit_code, status_output = exec_in_container(
                container, "python -m peeka.cli.main patch-status", timeout=10
            )
            assert exit_code == 0, (
                f"Agent did not respond after watch:\n{status_output}"
            )

        finally:
            exec_in_container(
                container,
                (
                    f"kill {pid} 2>/dev/null; "
                    "pkill -9 -f gevent_attach_target.py 2>/dev/null; "
                    "rm -f /tmp/gevent_target.*; true"
                ),
                timeout=10,
            )
            cleanup_peeka_files_in_container(container)
