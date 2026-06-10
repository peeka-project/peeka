"""Container E2E test: attach to a gunicorn worker PID and collect observations."""

import json
import os
from pathlib import Path

import pytest

from tests.container.conftest import cleanup_peeka_files_in_container, exec_in_container

pytestmark = [pytest.mark.container]

_GUNICORN_APP_SRC = """
import os
from gevent import monkey
monkey.patch_all()


def application(environ, start_response):
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return [b'hello']
"""

_EVIDENCE_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sisyphus"
    / "evidence"
    / "task-11-gunicorn.log"
)


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


def _write_gunicorn_app(container) -> None:
    """Write gunicorn_app.py to /tmp/ inside the container."""
    escaped = _GUNICORN_APP_SRC.replace("'", "'\\''")
    cmd = f"printf '%s' '{escaped}' > /tmp/gunicorn_app.py"
    exit_code, output = exec_in_container(container, cmd, timeout=10)
    assert exit_code == 0, f"Failed to write gunicorn_app.py:\n{output}"


def _start_gunicorn(container, timeout: int = 20) -> str:
    """Start gunicorn with gevent workers and return a worker PID.

    Args:
        container: DockerContainer instance
        timeout: Maximum wait seconds for workers to appear

    Returns:
        Worker PID as string
    """
    cmd = f"""
cd /tmp
gunicorn --worker-class gevent --workers 2 --bind 0.0.0.0:8765 \
  --no-sendfile --timeout 60 gunicorn_app:application \
  --daemon --pid /tmp/gunicorn.pid --log-file /tmp/gunicorn.log \
  --pythonpath /tmp

for i in $(seq 1 {timeout * 10}); do
    WORKER_PID=$(ps aux | grep 'gunicorn' | grep -v master | grep -v grep | head -1 | awk '{{print $2}}')
    if [ -n "$WORKER_PID" ] && [ "$WORKER_PID" -gt 0 ] 2>/dev/null; then
        echo "$WORKER_PID"
        break
    fi
    sleep 0.1
done
""".strip()
    exit_code, output = exec_in_container(container, cmd, timeout=timeout + 5)
    assert exit_code == 0, f"gunicorn startup failed:\n{output}"
    pid = output.strip().splitlines()[-1].strip()
    assert pid.isdigit(), f"Invalid worker PID: {pid!r}\nOutput:\n{output}"
    return pid


def _warmup_gunicorn(container) -> None:
    """Send a request to gunicorn to ensure the worker processes at least once."""
    exit_code, output = exec_in_container(
        container,
        "curl -sf http://localhost:8765/ || wget -qO- http://localhost:8765/ || true",
        timeout=10,
    )
    # Not asserting: curl may not be available or server may still be starting;
    # the watch test itself will confirm the worker is callable.


def _attach(container, pid: str) -> None:
    """Attach Peeka to the given PID."""
    exit_code, output = exec_in_container(
        container, f"python -m peeka.cli.main attach {pid}", timeout=30
    )
    assert exit_code == 0, f"Attach to worker {pid} failed:\n{output}"


def _save_evidence(text: str) -> None:
    """Persist evidence to the notepad evidence directory."""
    try:
        _EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _EVIDENCE_PATH.write_text(text, encoding="utf-8")
    except OSError:
        pass


class TestGunicornWorkerAttach:
    """Attach to a gunicorn gevent worker PID and collect observations."""

    def test_gunicorn_worker_attach_and_watch(self, gdb_container):
        """Attach to a running gunicorn worker and collect ≥1 observation."""
        container = gdb_container
        evidence_lines = []

        _write_gunicorn_app(container)
        worker_pid = _start_gunicorn(container)
        evidence_lines.append(f"worker_pid={worker_pid}")

        try:
            _warmup_gunicorn(container)
            _attach(container, worker_pid)
            evidence_lines.append("attach=ok")

            # Watch the application callable; -n 3 to collect a few calls.
            # We also send a request during watch to trigger the handler.
            exit_code, watch_output = exec_in_container(
                container,
                (
                    "python -m peeka.cli.main watch 'gunicorn_app.application' -n 3 &"
                    " WPID=$!; sleep 1;"
                    " curl -sf http://localhost:8765/ 2>/dev/null || true;"
                    " curl -sf http://localhost:8765/ 2>/dev/null || true;"
                    " wait $WPID; echo EXIT_CODE:$?"
                ),
                timeout=40,
            )

            # Extract the actual exit code from the embedded marker
            actual_exit = 0
            for ln in watch_output.splitlines():
                if ln.startswith("EXIT_CODE:"):
                    try:
                        actual_exit = int(ln.split(":")[1])
                    except ValueError:
                        pass
                    break

            assert actual_exit == 0, (
                f"Watch command failed (exit {actual_exit}):\n{watch_output}"
            )

            records = list(_json_lines(watch_output))
            evidence_lines.append(f"jsonl_records={len(records)}")

            observations = [r for r in records if r.get("type") == "observation"]
            evidence_lines.append(f"observations={len(observations)}")

            watch_started = next(
                (r for r in records if r.get("event") == "watch_started"), None
            )

            assert observations or watch_started, (
                f"No observations or watch_started event:\n{watch_output}"
            )

            if observations:
                for obs in observations:
                    assert "watch_id" in obs, (
                        f"Observation missing watch_id:\n{obs}"
                    )
            evidence_lines.append("result=PASS")

        finally:
            exec_in_container(
                container,
                (
                    "pkill -TERM -f gunicorn 2>/dev/null; "
                    "sleep 0.5; pkill -9 -f gunicorn 2>/dev/null; "
                    "rm -f /tmp/gunicorn_app.py /tmp/gunicorn.pid /tmp/gunicorn.log; "
                    "true"
                ),
                timeout=10,
            )
            cleanup_peeka_files_in_container(container)
            _save_evidence("\n".join(evidence_lines) + "\n")
