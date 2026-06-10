"""Container E2E test: watch a requests.get call under gevent monkey-patching."""

import json
from pathlib import Path

import pytest

from tests.container.conftest import cleanup_peeka_files_in_container, exec_in_container

pytestmark = [pytest.mark.container]

_REQUESTS_TARGET_SRC = """
from gevent import monkey
monkey.patch_all()
import requests
import time
import sys


def fetch_something():
    try:
        r = requests.get("http://localhost:9876/", timeout=2)
        return r.status_code
    except Exception as e:
        return str(e)


print("REQUESTS_TARGET_READY", flush=True)
sys.stdout.flush()
while True:
    fetch_something()
    time.sleep(0.5)
"""

_EVIDENCE_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sisyphus"
    / "evidence"
    / "task-12-requests.log"
)


def _json_lines(output: str):
    for line in output.strip().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _save_evidence(text: str) -> None:
    try:
        _EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _EVIDENCE_PATH.write_text(text, encoding="utf-8")
    except OSError:
        pass


def _write_target(container) -> None:
    escaped = _REQUESTS_TARGET_SRC.replace("'", "'\\''")
    cmd = f"printf '%s' '{escaped}' > /tmp/requests_target.py"
    exit_code, output = exec_in_container(container, cmd, timeout=10)
    assert exit_code == 0, f"Failed to write requests_target.py:\n{output}"


def _start_mock_http_server(container) -> None:
    cmd = (
        "cd /tmp && python -m http.server 9876 >/tmp/httpserver.log 2>&1 &"
        " sleep 0.3"
    )
    exec_in_container(container, cmd, timeout=10)


def _start_requests_target(container, timeout: int = 15) -> str:
    """Start the requests target and return its PID."""
    cmd = f"""
python /tmp/requests_target.py >/tmp/requests_target.log 2>&1 &
echo $! > /tmp/requests_target.pid
PID=$!
for i in $(seq 1 {timeout * 10}); do
    if grep -q "REQUESTS_TARGET_READY" /tmp/requests_target.log 2>/dev/null; then
        echo "READY"
        break
    fi
    sleep 0.1
done
if ! grep -q "REQUESTS_TARGET_READY" /tmp/requests_target.log 2>/dev/null; then
    kill $PID 2>/dev/null || true
    cat /tmp/requests_target.log >&2
    exit 1
fi
cat /tmp/requests_target.pid
""".strip()
    exit_code, output = exec_in_container(container, cmd, timeout=timeout + 5)
    assert exit_code == 0, f"requests target startup failed:\n{output}"
    pid = output.strip().splitlines()[-1].strip()
    assert pid.isdigit(), f"Invalid requests target PID: {pid!r}"
    return pid


def _attach(container, pid: str) -> None:
    exit_code, output = exec_in_container(
        container, f"python -m peeka.cli.main attach {pid}", timeout=30
    )
    assert exit_code == 0, f"Attach failed:\n{output}"


class TestGeventCompatRequests:
    """Watch requests.get calls under gevent monkey-patching."""

    def test_watch_requests_under_gevent(self, gdb_container):
        """Watch fetch_something: expects ≥1 observation from a gevent-patched target."""
        container = gdb_container
        evidence_lines = []

        _write_target(container)
        _start_mock_http_server(container)
        pid = _start_requests_target(container)
        evidence_lines.append(f"pid={pid}")

        try:
            _attach(container, pid)
            evidence_lines.append("attach=ok")

            exit_code, watch_output = exec_in_container(
                container,
                "python -m peeka.cli.main watch 'requests_target.fetch_something' -n 3",
                timeout=30,
            )
            assert exit_code == 0, f"Watch command failed:\n{watch_output}"

            records = list(_json_lines(watch_output))
            evidence_lines.append(f"jsonl_records={len(records)}")

            observations = [r for r in records if r.get("type") == "observation"]
            evidence_lines.append(f"observations={len(observations)}")
            assert observations, f"No observations collected:\n{watch_output}"

            for obs in observations:
                assert "watch_id" in obs, f"Observation missing watch_id:\n{obs}"

            watch_started = next(
                (r for r in records if r.get("event") == "watch_started"), None
            )
            if watch_started:
                meta = watch_started.get("meta", {})
                assert meta.get("gevent_state") in (
                    "patched",
                    "active_hub",
                ), f"Unexpected gevent_state: {meta.get('gevent_state')}"

            evidence_lines.append("result=PASS")

        finally:
            exec_in_container(
                container,
                (
                    f"kill {pid} 2>/dev/null; "
                    "pkill -9 -f requests_target.py 2>/dev/null; "
                    "pkill -9 -f 'http.server' 2>/dev/null; "
                    "rm -f /tmp/requests_target.py /tmp/requests_target.log "
                    "/tmp/requests_target.pid /tmp/httpserver.log; true"
                ),
                timeout=10,
            )
            cleanup_peeka_files_in_container(container)
            _save_evidence("\n".join(evidence_lines) + "\n")
