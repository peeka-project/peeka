"""Container E2E perf baseline test for watch throughput under gevent."""

import json
import time

import pytest

from tests.container.conftest import cleanup_peeka_files_in_container, exec_in_container

pytestmark = [pytest.mark.container, pytest.mark.slow, pytest.mark.gevent]


def _json_lines(output: str):
    for line in output.strip().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _start_gevent_target(container) -> str:
    command = """
python /app/examples/gevent_attach_target.py --interval 0.01 --duration 0 >/tmp/gevent_perf_target.log 2>&1 &
echo $! > /tmp/gevent_perf_target.pid
PID=$!
for i in $(seq 1 150); do
    if grep -q "GEVENT_TARGET_READY" /tmp/gevent_perf_target.log 2>/dev/null; then
        break
    fi
    sleep 0.1
done
if ! grep -q "GEVENT_TARGET_READY" /tmp/gevent_perf_target.log 2>/dev/null; then
    kill $PID 2>/dev/null || true
    cat /tmp/gevent_perf_target.log >&2
    exit 1
fi
cat /tmp/gevent_perf_target.pid
""".strip()
    exit_code, output = exec_in_container(container, command, timeout=20)
    assert exit_code == 0, f"Gevent target startup failed:\n{output}"
    pid = output.strip().splitlines()[-1].strip()
    assert pid.isdigit(), f"Invalid gevent target PID: {pid}"
    return pid


def _attach(container, pid: str) -> None:
    exit_code, output = exec_in_container(
        container, f"python -m peeka.cli.main attach {pid}", timeout=30
    )
    assert exit_code == 0, f"Attach failed:\n{output}"


class TestPerfGeventWatch:
    @pytest.mark.parametrize(
        "container_fixture", ["gdb_container", "py314_container"]
    )
    def test_watch_throughput_gevent_baseline(
        self, container_fixture, request
    ):
        container = request.getfixturevalue(container_fixture)
        pid = _start_gevent_target(container)

        try:
            _attach(container, pid)

            t0 = time.monotonic()
            exit_code, output = exec_in_container(
                container,
                "python -m peeka.cli.main watch 'index.handler' -n 100",
                timeout=120,
            )
            elapsed = time.monotonic() - t0

            assert exit_code == 0, f"Watch command failed:\n{output}"

            records = list(_json_lines(output))
            observations = [r for r in records if r.get("type") == "observation"]
            assert len(observations) >= 1, f"No observations collected:\n{output}"

            watch_started = next(
                (r for r in records if r.get("event") == "watch_started"), None
            )
            assert watch_started is not None, f"No watch_started event:\n{output}"
            meta = watch_started.get("meta", {})
            gevent_state = meta.get("gevent_state", "unknown")
            assert gevent_state in ("patched", "active_hub"), (
                f"gevent_state not patched: {gevent_state}"
            )

            throughput = len(observations) / elapsed if elapsed > 0 else 0
            print(
                f"\nGevent watch throughput: {throughput:.1f} obs/s "
                f"({len(observations)} obs in {elapsed:.1f}s, "
                f"gevent_state={gevent_state})"
            )

            assert throughput > 0

        finally:
            exec_in_container(
                container,
                (
                    f"kill {pid} 2>/dev/null; "
                    "pkill -9 -f gevent_attach_target.py 2>/dev/null; "
                    "rm -f /tmp/gevent_perf_target.*; true"
                ),
                timeout=10,
            )
            cleanup_peeka_files_in_container(container)
