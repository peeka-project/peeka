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
_EVIDENCE_DIR_FIX = ".sisyphus/evidence/py314-gevent-watch-limit-fix"
_EVIDENCE_DIR_BASE = ".sisyphus/evidence"
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


def _extract_probe_id(records: List[Dict[str, Any]]) -> Optional[str]:
    for record in records:
        probe_id = record.get("probe_id")
        if probe_id:
            return str(probe_id)
    return None


def _try_query_internal_count(
    container: object, probe_id: Optional[str]
) -> Optional[int]:
    if not probe_id:
        return None
    exit_code, output = exec_in_container(
        container,
        f"python -m peeka.cli.main probe inspect --probe {probe_id} --format json",
        timeout=10,
    )
    if exit_code != 0:
        return None
    for record in _json_lines(output):
        for field in ("count", "observation_count", "total_count"):
            val = record.get(field)
            if val is not None:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    pass
        data = record.get("data", {})
        if isinstance(data, dict):
            for field in ("count", "observation_count", "total_count"):
                val = data.get(field)
                if val is not None:
                    try:
                        return int(val)
                    except (ValueError, TypeError):
                        pass
    return None


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


class TestWatchLimitFixRegression:
    def test_watch_no_stall_py314_gevent_n100(self, py314_container: object):
        n = 100
        os.makedirs(_EVIDENCE_DIR_FIX, exist_ok=True)
        pid = _start_gevent_target(py314_container, interval=0.01)
        try:
            _attach(py314_container, pid)

            started = time.monotonic()
            exit_code, output = exec_in_container(
                py314_container,
                f"python -m peeka.cli.main watch 'index.handler' -n {n}",
                timeout=60,
            )
            elapsed_s = time.monotonic() - started

            records = list(_json_lines(output))
            observations = [r for r in records if r.get("type") == "observation"]
            cli_printed_count = len(observations)
            probe_id = _extract_probe_id(observations)
            internal_count = _try_query_internal_count(py314_container, probe_id)

            watch_started = next(
                (r for r in records if r.get("event") == "watch_started"), None
            )
            gevent_state: Optional[str] = None
            if watch_started:
                meta = watch_started.get("meta", {})
                gevent_state = meta.get("gevent_state")

            evidence: Dict[str, Any] = {
                "test": "test_watch_no_stall_py314_gevent_n100",
                "n": n,
                "exit_code": exit_code,
                "timed_out": exit_code == 124,
                "duration": elapsed_s,
                "cli_printed_count": cli_printed_count,
                "internal_count": internal_count,
                "gevent_state": gevent_state,
                "probe_id": probe_id,
                "raw_lines_first_5": output.strip().splitlines()[:5],
            }
            evidence_path = os.path.join(_EVIDENCE_DIR_FIX, "task-9-py314-no-stall.log")
            with open(evidence_path, "w", encoding="utf-8") as fh:
                json.dump(evidence, fh, indent=2, sort_keys=True)
                fh.write("\n")

            assert exit_code == 0, (
                f"watch -n {n} timed out or failed (exit_code={exit_code}). "
                f"cli_printed_count={cli_printed_count}, elapsed={elapsed_s:.1f}s. "
                "Stall bug present: wrapper silenced itself before CLI received N obs."
            )
            assert cli_printed_count == n, (
                f"Expected {n} observations, got {cli_printed_count}. "
                f"exit_code={exit_code}, elapsed={elapsed_s:.1f}s, "
                f"internal_count={internal_count}."
            )
        finally:
            exec_in_container(
                py314_container,
                (
                    f"kill {pid} 2>/dev/null; "
                    "pkill -9 -f gevent_attach_target.py 2>/dev/null; "
                    f"rm -f {_TARGET_LOG} {_TARGET_PID}; true"
                ),
                timeout=10,
            )
            cleanup_peeka_files_in_container(py314_container)

    def test_watch_n_counts_printed_not_agent(self, py314_container: object):
        n = 100
        os.makedirs(_EVIDENCE_DIR_FIX, exist_ok=True)
        pid = _start_gevent_target(py314_container, interval=0.01)
        try:
            _attach(py314_container, pid)

            started = time.monotonic()
            exit_code, output = exec_in_container(
                py314_container,
                f"python -m peeka.cli.main watch 'index.handler' -n {n}",
                timeout=60,
            )
            elapsed_s = time.monotonic() - started

            records = list(_json_lines(output))
            observations = [r for r in records if r.get("type") == "observation"]
            cli_printed_count = len(observations)
            probe_id = _extract_probe_id(observations)
            internal_count = _try_query_internal_count(py314_container, probe_id)

            evidence: Dict[str, Any] = {
                "test": "test_watch_n_counts_printed_not_agent",
                "n": n,
                "exit_code": exit_code,
                "timed_out": exit_code == 124,
                "duration": elapsed_s,
                "cli_printed_count": cli_printed_count,
                "internal_count": internal_count,
                "count_assertion": cli_printed_count == n,
                "count_mismatch": cli_printed_count != n,
                "probe_id": probe_id,
            }
            evidence_path = os.path.join(_EVIDENCE_DIR_FIX, "task-9-count-assertion.json")
            with open(evidence_path, "w", encoding="utf-8") as fh:
                json.dump(evidence, fh, indent=2, sort_keys=True)
                fh.write("\n")

            assert exit_code == 0, (
                f"Watch timed out (exit_code={exit_code}), "
                f"cli_printed_count={cli_printed_count}."
            )
            assert cli_printed_count == n, (
                f"CLI must print exactly {n} observations (the -n value), "
                f"got {cli_printed_count}. "
                f"internal_count={internal_count}. "
                "CLI counted_limit must control stop, not agent internal gate."
            )
        finally:
            exec_in_container(
                py314_container,
                (
                    f"kill {pid} 2>/dev/null; "
                    "pkill -9 -f gevent_attach_target.py 2>/dev/null; "
                    f"rm -f {_TARGET_LOG} {_TARGET_PID}; true"
                ),
                timeout=10,
            )
            cleanup_peeka_files_in_container(py314_container)

    def test_watch_n1_terminates_py314_gevent(self, py314_container: object):
        n = 1
        os.makedirs(_EVIDENCE_DIR_FIX, exist_ok=True)
        pid = _start_gevent_target(py314_container, interval=0.01)
        try:
            _attach(py314_container, pid)

            started = time.monotonic()
            exit_code, output = exec_in_container(
                py314_container,
                f"python -m peeka.cli.main watch 'index.handler' -n {n}",
                timeout=60,
            )
            elapsed_s = time.monotonic() - started

            records = list(_json_lines(output))
            observations = [r for r in records if r.get("type") == "observation"]
            cli_printed_count = len(observations)
            probe_id = _extract_probe_id(observations)

            evidence: Dict[str, Any] = {
                "test": "test_watch_n1_terminates_py314_gevent",
                "n": n,
                "exit_code": exit_code,
                "timed_out": exit_code == 124,
                "duration": elapsed_s,
                "cli_printed_count": cli_printed_count,
                "probe_id": probe_id,
                "raw_lines_first_5": output.strip().splitlines()[:5],
            }
            evidence_path = os.path.join(_EVIDENCE_DIR_FIX, "task-5-py314-n1-terminates.json")
            with open(evidence_path, "w", encoding="utf-8") as fh:
                json.dump(evidence, fh, indent=2, sort_keys=True)
                fh.write("\n")

            assert exit_code == 0, (
                f"watch -n {n} timed out or failed (exit_code={exit_code}). "
                f"cli_printed_count={cli_printed_count}, elapsed={elapsed_s:.1f}s."
            )
            assert cli_printed_count == n, (
                f"Expected exactly {n} observation, got {cli_printed_count}. "
                f"exit_code={exit_code}, elapsed={elapsed_s:.1f}s."
            )
            assert elapsed_s < 60, (
                f"watch -n {n} took too long: {elapsed_s:.1f}s. "
                "Should terminate near-instantly after 1 observation."
            )
        finally:
            exec_in_container(
                py314_container,
                (
                    f"kill {pid} 2>/dev/null; "
                    "pkill -9 -f gevent_attach_target.py 2>/dev/null; "
                    f"rm -f {_TARGET_LOG} {_TARGET_PID}; true"
                ),
                timeout=10,
            )
            cleanup_peeka_files_in_container(py314_container)


class TestStreamingDisconnectLifecycle:
    def test_streaming_watch_disconnect_py314_gevent(self, py314_container: object) -> None:
        os.makedirs(_EVIDENCE_DIR_BASE, exist_ok=True)
        evidence_path = os.path.join(
            _EVIDENCE_DIR_BASE, "task-7-py314-stream-disconnect.log"
        )

        pid: Optional[str] = None
        wait_output = ""
        got_observation = False
        evidence: Dict[str, Any] = {
            "test": "test_streaming_watch_disconnect_py314_gevent",
            "got_initial_observation": False,
            "kill_exit_code": None,
            "kill_elapsed_s": None,
            "follow_up_exit_code": None,
            "follow_up_observation_count": None,
            "agent_healthy_after_disconnect": False,
        }

        try:
            pid = _start_gevent_target(py314_container, interval=0.01)
            evidence["target_pid"] = pid
            _attach(py314_container, pid)

            start_bg_exit, start_bg_out = exec_in_container(
                py314_container,
                (
                    "python -m peeka.cli.main watch 'index.handler' -n 100 "
                    "> /tmp/watch_disconnect_test.log 2>&1 & echo $!"
                ),
                timeout=10,
            )
            assert start_bg_exit == 0, (
                f"Failed to launch background watch: {start_bg_out}"
            )
            watch_pid = start_bg_out.strip().splitlines()[-1].strip()
            assert watch_pid.isdigit(), (
                f"Expected numeric PID from background watch, got: {watch_pid!r}"
            )
            evidence["watch_pid"] = watch_pid

            _, wait_output = exec_in_container(
                py314_container,
                """for i in $(seq 1 100); do
    if grep -q '"type": "observation"' /tmp/watch_disconnect_test.log 2>/dev/null; then
        echo OBSERVATION_RECEIVED
        break
    fi
    sleep 0.1
done""",
                timeout=15,
            )
            got_observation = "OBSERVATION_RECEIVED" in wait_output
            evidence["got_initial_observation"] = got_observation

            kill_start = time.monotonic()
            kill_exit, kill_output = exec_in_container(
                py314_container,
                f"""kill {watch_pid} 2>/dev/null || true
ELAPSED=0
while kill -0 {watch_pid} 2>/dev/null && [ $ELAPSED -lt 100 ]; do
    sleep 0.1
    ELAPSED=$((ELAPSED + 1))
done
if kill -0 {watch_pid} 2>/dev/null; then
    echo STALL
    exit 1
fi
echo KILLED_OK""",
                timeout=15,
            )
            kill_elapsed = time.monotonic() - kill_start
            evidence["kill_exit_code"] = kill_exit
            evidence["kill_output"] = kill_output.strip()[:300]
            evidence["kill_elapsed_s"] = round(kill_elapsed, 2)

            assert "STALL" not in kill_output, (
                "Watch subprocess did not exit within 10 s after SIGTERM — "
                "agent may be blocking on a dead-client socket. "
                f"kill_output={kill_output!r}"
            )
            assert kill_exit == 0, (
                f"Kill script returned {kill_exit}: {kill_output!r}"
            )

            fu_exit, fu_output = exec_in_container(
                py314_container,
                "python -m peeka.cli.main watch 'index.handler' -n 2",
                timeout=30,
            )
            fu_records = list(_json_lines(fu_output))
            fu_observations = [r for r in fu_records if r.get("type") == "observation"]
            evidence["follow_up_exit_code"] = fu_exit
            evidence["follow_up_observation_count"] = len(fu_observations)
            evidence["agent_healthy_after_disconnect"] = (
                fu_exit == 0 and len(fu_observations) >= 1
            )

        finally:
            if pid:
                exec_in_container(
                    py314_container,
                    (
                        f"kill {pid} 2>/dev/null; "
                        "pkill -9 -f gevent_attach_target.py 2>/dev/null; "
                        "rm -f /tmp/watch_disconnect_test.log "
                        f"{_TARGET_LOG} {_TARGET_PID}; true"
                    ),
                    timeout=10,
                )
            cleanup_peeka_files_in_container(py314_container)
            with open(evidence_path, "w", encoding="utf-8") as fh:
                json.dump(evidence, fh, indent=2, sort_keys=True)
                fh.write("\n")

        assert got_observation, (
            "Stream produced no observations before disconnect — "
            "cannot validate disconnect lifecycle. "
            f"wait_output={wait_output!r}"
        )
        assert evidence["agent_healthy_after_disconnect"], (
            "Agent unhealthy after client disconnect: "
            f"follow_up_exit={evidence['follow_up_exit_code']}, "
            f"follow_up_observations={evidence['follow_up_observation_count']}. "
            f"Evidence: {evidence_path}"
        )
