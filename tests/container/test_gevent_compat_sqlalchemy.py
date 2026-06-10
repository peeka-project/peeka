"""Container E2E test: watch a SQLAlchemy query function under gevent monkey-patching."""

import json
from pathlib import Path

import pytest

from tests.container.conftest import cleanup_peeka_files_in_container, exec_in_container

pytestmark = [pytest.mark.container]

_SQLALCHEMY_TARGET_SRC = """
from gevent import monkey
monkey.patch_all()
from sqlalchemy import create_engine, text
import time
import sys


def query_db():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).fetchone()
        return result[0]


print("SQLALCHEMY_TARGET_READY", flush=True)
sys.stdout.flush()
while True:
    query_db()
    time.sleep(0.5)
"""

_EVIDENCE_PATH = (
    Path(__file__).resolve().parents[2]
    / ".sisyphus"
    / "evidence"
    / "task-13-sqlalchemy.log"
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
    escaped = _SQLALCHEMY_TARGET_SRC.replace("'", "'\\''")
    cmd = f"printf '%s' '{escaped}' > /tmp/sqlalchemy_target.py"
    exit_code, output = exec_in_container(container, cmd, timeout=10)
    assert exit_code == 0, f"Failed to write sqlalchemy_target.py:\n{output}"


def _start_sqlalchemy_target(container, timeout: int = 15) -> str:
    """Start the SQLAlchemy target and return its PID."""
    cmd = f"""
python /tmp/sqlalchemy_target.py >/tmp/sqlalchemy_target.log 2>&1 &
echo $! > /tmp/sqlalchemy_target.pid
PID=$!
for i in $(seq 1 {timeout * 10}); do
    if grep -q "SQLALCHEMY_TARGET_READY" /tmp/sqlalchemy_target.log 2>/dev/null; then
        echo "READY"
        break
    fi
    sleep 0.1
done
if ! grep -q "SQLALCHEMY_TARGET_READY" /tmp/sqlalchemy_target.log 2>/dev/null; then
    kill $PID 2>/dev/null || true
    cat /tmp/sqlalchemy_target.log >&2
    exit 1
fi
cat /tmp/sqlalchemy_target.pid
""".strip()
    exit_code, output = exec_in_container(container, cmd, timeout=timeout + 5)
    assert exit_code == 0, f"SQLAlchemy target startup failed:\n{output}"
    pid = output.strip().splitlines()[-1].strip()
    assert pid.isdigit(), f"Invalid sqlalchemy target PID: {pid!r}"
    return pid


def _attach(container, pid: str) -> None:
    exit_code, output = exec_in_container(
        container, f"python -m peeka.cli.main attach {pid}", timeout=30
    )
    assert exit_code == 0, f"Attach failed:\n{output}"


class TestGeventCompatSQLAlchemy:
    """Watch SQLAlchemy query calls under gevent monkey-patching."""

    def test_watch_sqlalchemy_under_gevent(self, gdb_container):
        """Watch query_db: expects ≥1 observation from a gevent-patched SQLAlchemy target."""
        container = gdb_container
        evidence_lines = []

        _write_target(container)
        pid = _start_sqlalchemy_target(container)
        evidence_lines.append(f"pid={pid}")

        try:
            _attach(container, pid)
            evidence_lines.append("attach=ok")

            exit_code, watch_output = exec_in_container(
                container,
                "python -m peeka.cli.main watch 'sqlalchemy_target.query_db' -n 3",
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
                    "pkill -9 -f sqlalchemy_target.py 2>/dev/null; "
                    "rm -f /tmp/sqlalchemy_target.py /tmp/sqlalchemy_target.log "
                    "/tmp/sqlalchemy_target.pid; true"
                ),
                timeout=10,
            )
            cleanup_peeka_files_in_container(container)
            _save_evidence("\n".join(evidence_lines) + "\n")
