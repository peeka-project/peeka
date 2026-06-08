"""Container performance regression test for gevent trace CPU spike fix."""

import base64
import json
import textwrap
import time

import pytest

from tests.container.conftest import cleanup_peeka_files_in_container, exec_in_container

pytestmark = [pytest.mark.container]


def _json_lines(output: str):
    for line in output.strip().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _start_large_result_target(container) -> str:
    command = """
python /app/examples/gevent_large_result_target.py --interval 0.01 --duration 0 >/tmp/large_result_target.log 2>&1 &
echo $! > /tmp/large_result_target.pid
PID=$!
for i in $(seq 1 150); do
    if grep -q "GEVENT_LARGE_RESULT_READY" /tmp/large_result_target.log 2>/dev/null; then
        echo "READY"
        break
    fi
    sleep 0.1
done
if ! grep -q "GEVENT_LARGE_RESULT_READY" /tmp/large_result_target.log 2>/dev/null; then
    kill $PID 2>/dev/null || true
    cat /tmp/large_result_target.log >&2
    exit 1
fi
cat /tmp/large_result_target.pid
""".strip()
    exit_code, output = exec_in_container(container, command, timeout=20)
    assert exit_code == 0, f"Large-result target startup failed:\n{output}"
    pid = output.strip().splitlines()[-1].strip()
    assert pid.isdigit(), f"Invalid PID: {pid}"
    return pid


def _write_cpu_sample_script(container, pid: str) -> None:
    # Build the sampling script with the target PID baked in.
    # Uses /proc/<pid>/stat jiffies (fields 13+14) to compute CPU% per second.
    script = textwrap.dedent(
        f"""\
        import time
        import os
        pid = {pid}
        CLK_TCK = os.sysconf("SC_CLK_TCK")
        samples = []
        for _ in range(30):
            stat_path = "/proc/" + str(pid) + "/stat"
            with open(stat_path) as fh:
                fields = fh.read().split()
            utime1 = int(fields[13])
            stime1 = int(fields[14])
            t1 = time.monotonic()
            time.sleep(1.0)
            with open(stat_path) as fh:
                fields = fh.read().split()
            utime2 = int(fields[13])
            stime2 = int(fields[14])
            t2 = time.monotonic()
            cpu_ticks = (utime2 + stime2) - (utime1 + stime1)
            elapsed = t2 - t1
            cpu_pct = (cpu_ticks / CLK_TCK) / elapsed * 100
            samples.append(cpu_pct)
            print("cpu_pct=" + format(cpu_pct, ".1f"), flush=True)
        avg = sum(samples) / len(samples)
        max_cpu = max(samples)
        print("avg=" + format(avg, ".1f") + " max=" + format(max_cpu, ".1f"), flush=True)
        verdict = "PASS" if avg < 50 and max_cpu < 80 else "FAIL"
        print(verdict, flush=True)
        """
    )
    # Use base64 to avoid shell quoting issues when writing the script file.
    encoded = base64.b64encode(script.encode()).decode()
    write_cmd = f"echo '{encoded}' | base64 -d > /tmp/cpu_sample.py"
    exit_code, output = exec_in_container(container, write_cmd, timeout=5)
    assert exit_code == 0, f"Failed to write CPU sample script:\n{output}"


@pytest.mark.container
class TestTraceGeventPerf:
    def test_trace_gevent_cpu_bounded_under_load(self, gdb_container):
        container = gdb_container
        pid = _start_large_result_target(container)
        try:
            exit_code, output = exec_in_container(
                container, f"python -m peeka.cli.main attach {pid}", timeout=30
            )
            assert exit_code == 0, f"Attach failed:\n{output}"

            exec_in_container(
                container,
                (
                    f"python -m peeka.cli.main trace 'index.handler' -n -1"
                    " >/tmp/trace_out.log 2>&1 &"
                ),
                timeout=5,
            )

            time.sleep(1)

            _write_cpu_sample_script(container, pid)
            exit_code, cpu_output = exec_in_container(
                container, "python3 /tmp/cpu_sample.py", timeout=65
            )
            assert exit_code == 0, f"CPU sampling script failed:\n{cpu_output}"

            lines = cpu_output.strip().splitlines()
            verdict = [ln.strip() for ln in lines if ln.strip() in ("PASS", "FAIL")]
            assert verdict, f"No verdict in CPU sampling output:\n{cpu_output}"
            assert verdict[0] == "PASS", f"CPU too high under trace.\n{cpu_output}"

            exit_code2, status = exec_in_container(
                container, "python -m peeka.cli.main patch-status", timeout=10
            )
            assert exit_code2 == 0, f"Agent not responding after trace:\n{status}"

        finally:
            exec_in_container(
                container,
                (
                    f"kill {pid} 2>/dev/null; "
                    "pkill -9 -f gevent_large_result_target.py 2>/dev/null; "
                    "rm -f /tmp/large_result_target.* /tmp/trace_out.log /tmp/cpu_sample.py; "
                    "true"
                ),
                timeout=10,
            )
            cleanup_peeka_files_in_container(container)

    def test_trace_gevent_observation_size_bounded(self, gdb_container):
        container = gdb_container
        pid = _start_large_result_target(container)
        try:
            exit_code, output = exec_in_container(
                container, f"python -m peeka.cli.main attach {pid}", timeout=30
            )
            assert exit_code == 0, f"Attach failed:\n{output}"

            exit_code, output = exec_in_container(
                container,
                "python -m peeka.cli.main trace 'index.handler' -n 3",
                timeout=30,
            )
            assert exit_code == 0, f"Trace failed:\n{output}"

            observations = [r for r in _json_lines(output) if r.get("type") == "observation"]
            assert observations, f"No observations collected:\n{output}"

            for obs in observations:
                if obs.get("call_tree"):
                    node = obs["call_tree"][0]
                    assert "_result" not in node, (
                        f"_result still in observation: {list(node.keys())}"
                    )
                    assert "_exception" not in node, (
                        f"_exception still in observation"
                    )
                obs_json = json.dumps(obs)
                assert len(obs_json.encode()) < 10 * 1024, (
                    f"Observation too large: {len(obs_json.encode())} bytes"
                )

        finally:
            exec_in_container(
                container,
                (
                    f"kill {pid} 2>/dev/null; "
                    "pkill -9 -f gevent_large_result_target.py 2>/dev/null; "
                    "rm -f /tmp/large_result_target.*; "
                    "true"
                ),
                timeout=10,
            )
            cleanup_peeka_files_in_container(container)
