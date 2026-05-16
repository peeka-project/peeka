"""
Container E2E tests for patch-status command with gevent monkey patching.

Tests the patch-status command's ability to detect and report:
- gevent monkey patching status (active, patched modules)
- Thread model classification (greenlet vs native)
- RPL integrity under monkey-patched environment
- No "cannot switch to a different thread" errors in stderr

This test validates the core RPL guarantee: Peeka agent can attach to and
diagnose gevent-patched processes without being affected by the patching.
"""

import json
import pytest

from tests.container.conftest import exec_in_container, cleanup_peeka_files_in_container

pytestmark = [pytest.mark.container]


class TestPatchStatusGevent:
    """Test patch-status command with gevent-monkey-patched target."""

    def test_gevent_attach_and_patch_status(self, gdb_container):
        """Verify patch-status detects gevent patching and RPL integrity."""
        container = gdb_container

        # Start gevent target in background and wait for ready sentinel
        shell_cmd = """
python /app/examples/gevent_attach_target.py --interval 0.1 --duration 0 >/tmp/gevent_target.log 2>&1 &
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
    echo "TIMEOUT: Gevent target failed to start within 15 seconds" >&2
    cat /tmp/gevent_target.log >&2
    exit 1
fi
cat /tmp/gevent_target.pid
""".strip()

        exit_code, output = exec_in_container(container, shell_cmd, timeout=20)
        assert exit_code == 0, f"Gevent target startup failed:\n{output}"

        lines = output.strip().split("\n")
        pid = lines[-1].strip()
        assert pid.isdigit(), f"Invalid PID: {pid}"

        # Attach to gevent process
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Parse attach output to verify success
        attach_lines = [line for line in attach_output.strip().split("\n") if line.strip()]
        attach_json_lines = [line for line in attach_lines if line.startswith("{")]
        attach_success = None
        for line in attach_json_lines:
            try:
                data = json.loads(line)
                if data.get("type") == "success" and data.get("command") == "attach":
                    attach_success = data
                    break
            except json.JSONDecodeError:
                continue

        assert attach_success is not None, (
            f"No attach success line found in output:\n{attach_output}"
        )

        # Run patch-status command
        exit_code, ps_output = exec_in_container(
            container, "python -m peeka.cli.main patch-status", timeout=10
        )
        assert exit_code == 0, f"patch-status command failed:\n{ps_output}"

        # Parse patch-status JSONL output
        ps_lines = [line for line in ps_output.strip().split("\n") if line.strip()]
        ps_json_lines = [line for line in ps_lines if line.startswith("{")]

        result_line = None
        for line in ps_json_lines:
            try:
                data = json.loads(line)
                if data.get("type") == "result" and data.get("command") == "patch-status":
                    result_line = data
                    break
            except json.JSONDecodeError:
                continue

        assert result_line is not None, (
            f"No patch-status result line found in output:\n{ps_output}"
        )

        # Extract the data payload
        assert "data" in result_line, (
            f"Missing 'data' field in result line: {result_line}"
        )
        assert "data" in result_line["data"], (
            f"Missing nested 'data' field in payload: {result_line['data']}"
        )

        payload = result_line["data"]["data"]

        # Save JSONL snapshot for Atlas verification
        evidence_path = "/tmp/task-22-jsonl-snapshot.jsonl"
        container.exec(
            ["bash", "-c", f"cat > {evidence_path} << 'EOF'\n{json.dumps(payload, indent=2)}\nEOF"]
        )

        # Copy evidence to host
        exit_code, cat_output = exec_in_container(
            container, f"cat {evidence_path}", timeout=5
        )
        if exit_code == 0:
            with open(
                "/home/haidao/PycharmProjects/peeka-project/peeka/.sisyphus/evidence/task-22-jsonl-snapshot.jsonl",
                "w"
            ) as f:
                f.write(cat_output)

        # Assertion 1: gevent monkey patch is active
        assert "monkey_patch" in payload, (
            f"Missing 'monkey_patch' field in payload: {payload.keys()}"
        )
        mp_gevent = payload["monkey_patch"]["gevent"]
        
        # Handle two possible formats: string "active" or dict with status
        if isinstance(mp_gevent, str):
            assert mp_gevent == "active", (
                f"Expected gevent='active', got: {mp_gevent}"
            )
        elif isinstance(mp_gevent, dict):
            assert mp_gevent.get("status") == "active", (
                f"Expected gevent.status='active', got: {mp_gevent.get('status')}"
            )
        else:
            raise AssertionError(
                f"Unexpected gevent format (not str or dict): {type(mp_gevent)}"
            )

        # Assertion 2: gevent patched_modules contains socket AND threading
        assert "details" in payload["monkey_patch"], (
            f"Missing 'details' in monkey_patch: {payload['monkey_patch'].keys()}"
        )
        assert "gevent" in payload["monkey_patch"]["details"], (
            f"Missing 'gevent' in details: {payload['monkey_patch']['details'].keys()}"
        )
        gevent_details = payload["monkey_patch"]["details"]["gevent"]
        assert "patched_modules" in gevent_details, (
            f"Missing 'patched_modules' in gevent details: {gevent_details.keys()}"
        )

        patched_modules = gevent_details["patched_modules"]
        assert "socket" in patched_modules, (
            f"Expected 'socket' in patched_modules, got: {patched_modules}"
        )
        assert "threading" in patched_modules, (
            f"Expected 'threading' in patched_modules, got: {patched_modules}"
        )

        # Assertion 3: thread_model classification is "greenlet"
        assert "thread_model" in payload, (
            f"Missing 'thread_model' field in payload: {payload.keys()}"
        )
        classification = payload["thread_model"].get("classification")
        assert classification == "greenlet", (
            f"Expected classification='greenlet', got: {classification}"
        )

        # Assertion 4: RPL integrity is OK
        assert "rpl_integrity" in payload, (
            f"Missing 'rpl_integrity' field in payload: {payload.keys()}"
        )
        rpl_ok = payload["rpl_integrity"].get("ok")
        assert rpl_ok is True, (
            f"Expected rpl_integrity.ok=True, got: {rpl_ok}"
        )

        # Cleanup
        exec_in_container(
            container,
            f"kill {pid} 2>/dev/null; pkill -9 -f gevent_attach_target.py 2>/dev/null; rm -f /tmp/gevent_target.* /tmp/task-22-jsonl-snapshot.jsonl; true",
            timeout=10
        )
        cleanup_peeka_files_in_container(container)

    def test_gevent_watch_no_hub_error(self, gdb_container):
        """Verify simple watch command works against gevent target without hub errors."""
        container = gdb_container

        # Start gevent target
        shell_cmd = """
python /app/examples/gevent_attach_target.py --interval 0.1 --duration 0 >/tmp/gevent_target.log 2>&1 &
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
    exit 1
fi
cat /tmp/gevent_target.pid
""".strip()

        exit_code, output = exec_in_container(container, shell_cmd, timeout=20)
        assert exit_code == 0, f"Gevent target startup failed:\n{output}"

        lines = output.strip().split("\n")
        pid = lines[-1].strip()
        assert pid.isdigit(), f"Invalid PID: {pid}"

        # Attach
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run watch command (watch the handler function)
        exit_code, watch_output = exec_in_container(
            container, "python -m peeka.cli.main watch 'index.handler' -n 3", timeout=10
        )

        # Watch should succeed (exit 0) and NOT contain hub error in stderr
        assert exit_code == 0, f"Watch command failed:\n{watch_output}"
        assert "cannot switch to a different thread" not in watch_output.lower(), (
            f"Hub thread-affinity error detected:\n{watch_output}"
        )

        # Parse watch output to verify observations captured
        watch_lines = [line for line in watch_output.strip().split("\n") if line.strip()]
        watch_json_lines = [line for line in watch_lines if line.startswith("{")]

        observation_count = 0
        for line in watch_json_lines:
            try:
                data = json.loads(line)
                if data.get("type") == "observation":
                    observation_count += 1
            except json.JSONDecodeError:
                continue

        assert observation_count >= 1, (
            f"Expected at least 1 observation, got {observation_count}:\n{watch_output}"
        )

        # Cleanup
        exec_in_container(
            container,
            f"kill {pid} 2>/dev/null; pkill -9 -f gevent_attach_target.py 2>/dev/null; rm -f /tmp/gevent_target.*; true",
            timeout=10
        )
        cleanup_peeka_files_in_container(container)
