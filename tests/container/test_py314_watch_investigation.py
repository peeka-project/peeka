"""Container investigation harness for py314+gevent watch streaming."""

# pyright: reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportAny=false, reportImplicitStringConcatenation=false, reportUnusedCallResult=false, reportDeprecated=false, reportExplicitAny=false

import json
import os
import time
from typing import Any, Dict, List, Optional, TypedDict

import pytest

from tests.container.conftest import cleanup_peeka_files_in_container, exec_in_container

pytestmark = [pytest.mark.container, pytest.mark.slow, pytest.mark.gevent]

_EVIDENCE_DIR = ".sisyphus/evidence/py314-gevent-streaming"
_TARGET_LOG = "/tmp/gevent_watch_investigation.log"
_TARGET_PID = "/tmp/gevent_watch_investigation.pid"


class HarnessResult(TypedDict):
    exit_code: int
    output: str
    elapsed_s: float
    records: List[Dict[str, Any]]
    observations: List[Dict[str, Any]]
    watch_started: Optional[Dict[str, Any]]
    evidence: Dict[str, Any]
    evidence_path: str


def _json_lines(output: str):
    for line in output.strip().splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _start_gevent_target(container: object, interval: float = 0.01) -> str:
    command = f"""
python /app/examples/gevent_attach_target.py --interval {interval} --duration 0 >{_TARGET_LOG} 2>&1 &
echo $! > {_TARGET_PID}
PID=$!
for i in $(seq 1 150); do
    if grep -q "GEVENT_TARGET_READY" {_TARGET_LOG} 2>/dev/null; then
        break
    fi
    sleep 0.1
done
if ! grep -q "GEVENT_TARGET_READY" {_TARGET_LOG} 2>/dev/null; then
    kill $PID 2>/dev/null || true
    cat {_TARGET_LOG} >&2
    exit 1
fi
cat {_TARGET_PID}
""".strip()
    exit_code, output = exec_in_container(container, command, timeout=20)
    assert exit_code == 0, f"Gevent target startup failed:\n{output}"
    pid = output.strip().splitlines()[-1].strip()
    assert pid.isdigit(), f"Invalid gevent target PID: {pid}"
    return pid


def _attach(container: object, pid: str) -> None:
    exit_code, output = exec_in_container(
        container, f"python -m peeka.cli.main attach {pid}", timeout=30
    )
    assert exit_code == 0, f"Attach failed:\n{output}"


def _extract_watch_id(records: List[Dict[str, Any]]) -> str:
    for record in records:
        watch_id = record.get("watch_id")
        if watch_id is not None:
            return str(watch_id)
        meta = record.get("meta")
        if isinstance(meta, dict):
            watch_id = meta.get("watch_id")
            if watch_id is not None:
                return str(watch_id)
    return ""


def _run_watch_and_write_evidence(
    container: object, n: int, timeout: int, evidence_name: str
)-> HarnessResult:
    pid = _start_gevent_target(container, interval=0.01)
    evidence_path = os.path.join(_EVIDENCE_DIR, evidence_name)

    try:
        _attach(container, pid)

        started = time.monotonic()
        exit_code, output = exec_in_container(
            container,
            f"python -m peeka.cli.main watch 'index.handler' -n {n}",
            timeout=timeout,
        )
        elapsed_s = time.monotonic() - started
        records = list(_json_lines(output))
        observations = [
            record for record in records if record.get("type") == "observation"
        ]
        watch_started = next(
            (record for record in records if record.get("event") == "watch_started"),
            None,
        )
        watch_id = _extract_watch_id(records)
        evidence: Dict[str, Any] = {
            "exit_code": exit_code,
            "timed_out": exit_code == 124,
            "elapsed_s": elapsed_s,
            "observation_count": len(observations),
            "watch_id": watch_id,
            "raw_lines": output.strip().splitlines()[:30],
        }

        os.makedirs(_EVIDENCE_DIR, exist_ok=True)
        with open(evidence_path, "w", encoding="utf-8") as handle:
            json.dump(evidence, handle, indent=2, sort_keys=True)
            handle.write("\n")

        return {
            "exit_code": exit_code,
            "output": output,
            "elapsed_s": elapsed_s,
            "records": records,
            "observations": observations,
            "watch_started": watch_started,
            "evidence": evidence,
            "evidence_path": evidence_path,
        }
    finally:
        exec_in_container(
            container,
            (
                f"kill {pid} 2>/dev/null; "
                "pkill -9 -f gevent_attach_target.py 2>/dev/null; "
                f"rm -f {_TARGET_LOG} {_TARGET_PID}; true"
            ),
            timeout=10,
        )
        cleanup_peeka_files_in_container(container)


class TestPy314WatchInvestigation:
    def test_harness_small_n3(self, py314_container: object):
        result = _run_watch_and_write_evidence(
            py314_container, n=3, timeout=30, evidence_name="task-1-harness-small.json"
        )

        assert result["exit_code"] == 0, f"Watch command failed:\n{result['output']}"
        assert result["watch_started"] is not None, f"No watch_started event:\n{result['output']}"
        assert len(result["observations"]) >= 1, f"No observations collected:\n{result['output']}"
        assert os.path.exists(result["evidence_path"]), "Evidence file was not written"

    def test_harness_large_n_hang(self, py314_container: object):
        result = _run_watch_and_write_evidence(
            py314_container,
            n=100,
            timeout=20,
            evidence_name="task-1-harness-timeout.json",
        )

        assert os.path.exists(result["evidence_path"]), "Evidence file was not written"
        assert result["evidence"]["observation_count"] >= 0
        assert result["evidence"]["raw_lines"] is not None
