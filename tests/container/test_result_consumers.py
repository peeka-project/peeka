"""Container E2E tests for result consumer isolation and lifecycle."""

import json
import shlex
from typing import Any, Dict, List

import pytest

from tests.container.conftest import exec_in_container

pytestmark = [pytest.mark.container, pytest.mark.timeout(180)]


def _run_cli_json(container: Any, cmd: str, timeout: int = 20) -> List[Dict[str, Any]]:
    exit_code, output = exec_in_container(
        container,
        f"python -m peeka.cli.main {cmd}",
        timeout=timeout,
    )
    assert exit_code == 0, output
    lines = [line for line in output.strip().split("\n") if line.startswith("{")]
    assert lines, output
    return [json.loads(line) for line in lines]


def _discover_target_id(container: Any) -> str:
    target_query = (
        "cd /app && python - <<'PY'\n"
        "from peeka.core.targets import discover_targets\n"
        "targets = discover_targets()\n"
        "assert targets\n"
        "print(targets[0].target_id)\n"
        "PY"
    )
    target_exit, target_output = exec_in_container(container, target_query, timeout=20)
    assert target_exit == 0, target_output
    target_id = target_output.strip().splitlines()[-1].strip()
    assert target_id.startswith("target_"), f"Unexpected target_id: {target_id!r}"
    return target_id


class TestResultConsumersContainer:
    def test_consumers_same_target_records_isolated(
        self, py314_target: Dict[str, Any]
    ) -> None:
        container = py314_target["container"]
        pid = py314_target["pid"]

        attach_exit, attach_output = exec_in_container(
            container,
            f"python -m peeka.cli.main attach {pid}",
            timeout=30,
        )
        assert attach_exit == 0, attach_output

        target_id = _discover_target_id(container)

        create_a = _run_cli_json(
            container,
            f"consumer create --target {shlex.quote(target_id)} --source cli "
            f"--scope-type target --scope-id {shlex.quote(target_id)} --format json",
        )
        consumer_a_id = create_a[0]["data"]["consumer_id"]
        assert consumer_a_id.startswith("consumer_")

        create_b = _run_cli_json(
            container,
            f"consumer create --target {shlex.quote(target_id)} --source cli "
            f"--scope-type target --scope-id {shlex.quote(target_id)} --format json",
        )
        consumer_b_id = create_b[0]["data"]["consumer_id"]
        assert consumer_b_id.startswith("consumer_")
        assert consumer_a_id != consumer_b_id

        watch_exit, watch_output = exec_in_container(
            container,
            "python -m peeka.cli.main watch '__main__.Calculator.add' -n 3",
            timeout=30,
        )
        assert watch_exit == 0, watch_output

        drain_a = _run_cli_json(
            container,
            f"consumer drain --consumer {shlex.quote(consumer_a_id)} --format json",
        )
        assert drain_a[0]["data"]["consumer_id"] == consumer_a_id
        records_a = drain_a[1:]
        assert len(records_a) > 0, (
            f"Consumer A received no records after watch. Drain output: {drain_a}"
        )

        drain_b = _run_cli_json(
            container,
            f"consumer drain --consumer {shlex.quote(consumer_b_id)} --format json",
        )
        assert drain_b[0]["data"]["consumer_id"] == consumer_b_id
        records_b = drain_b[1:]
        assert len(records_b) > 0, (
            f"Consumer B received no records independently. Drain output: {drain_b}"
        )

    def test_consumer_drop_oldest_keeps_latest_records(
        self, py314_target: Dict[str, Any]
    ) -> None:
        container = py314_target["container"]
        pid = py314_target["pid"]

        attach_exit, attach_output = exec_in_container(
            container,
            f"python -m peeka.cli.main attach {pid}",
            timeout=30,
        )
        assert attach_exit == 0, attach_output

        target_id = _discover_target_id(container)

        create_lines = _run_cli_json(
            container,
            f"consumer create --target {shlex.quote(target_id)} --source cli "
            f"--scope-type target --scope-id {shlex.quote(target_id)} "
            f"--max-buffer-size 3 --backpressure-policy drop_oldest --format json",
        )
        consumer_id = create_lines[0]["data"]["consumer_id"]

        watch_exit, watch_output = exec_in_container(
            container,
            "python -m peeka.cli.main watch '__main__.Calculator.add' -n 6",
            timeout=40,
        )
        assert watch_exit == 0, watch_output

        drain_lines = _run_cli_json(
            container,
            f"consumer drain --consumer {shlex.quote(consumer_id)} --format json",
        )
        records = drain_lines[1:]

        assert len(records) == 3, (
            f"Expected 3 records (max_buffer_size), got {len(records)}: {records}"
        )
        sequences = [record["sequence"] for record in records]
        assert sequences == sorted(sequences), (
            f"Records not in ascending sequence order: {sequences}"
        )
        assert sequences[0] > 0, (
            f"Expected oldest records to be dropped; got sequences {sequences}"
        )

    def test_consumer_drain_returns_records_in_sequence_order(
        self, py314_target: Dict[str, Any]
    ) -> None:
        container = py314_target["container"]
        pid = py314_target["pid"]

        attach_exit, attach_output = exec_in_container(
            container,
            f"python -m peeka.cli.main attach {pid}",
            timeout=30,
        )
        assert attach_exit == 0, attach_output

        target_id = _discover_target_id(container)

        create_lines = _run_cli_json(
            container,
            f"consumer create --target {shlex.quote(target_id)} --source cli "
            f"--scope-type target --scope-id {shlex.quote(target_id)} --format json",
        )
        consumer_id = create_lines[0]["data"]["consumer_id"]

        watch_exit, watch_output = exec_in_container(
            container,
            "python -m peeka.cli.main watch '__main__.Calculator.add' -n 4",
            timeout=30,
        )
        assert watch_exit == 0, watch_output

        drain_lines = _run_cli_json(
            container,
            f"consumer drain --consumer {shlex.quote(consumer_id)} --format json",
        )
        drain_meta = drain_lines[0]["data"]
        records = drain_lines[1:]

        assert len(records) >= 1, "Consumer must have at least one buffered record"
        sequences = [record["sequence"] for record in records]

        assert sequences == sorted(sequences), (
            f"Sequences not in ascending order: {sequences}"
        )
        assert len(sequences) == len(set(sequences)), (
            f"Duplicate sequence numbers detected: {sequences}"
        )
        assert drain_meta["next_sequence"] == sequences[-1], (
            f"next_sequence {drain_meta['next_sequence']} != last sequence {sequences[-1]}"
        )

    def test_consumer_cleanup_removes_closed_consumers(
        self, py314_target: Dict[str, Any]
    ) -> None:
        container = py314_target["container"]
        pid = py314_target["pid"]

        attach_exit, attach_output = exec_in_container(
            container,
            f"python -m peeka.cli.main attach {pid}",
            timeout=30,
        )
        assert attach_exit == 0, attach_output

        target_id = _discover_target_id(container)

        create_a = _run_cli_json(
            container,
            f"consumer create --target {shlex.quote(target_id)} --source cli "
            f"--scope-type target --scope-id {shlex.quote(target_id)} --format json",
        )
        consumer_a_id = create_a[0]["data"]["consumer_id"]

        create_b = _run_cli_json(
            container,
            f"consumer create --target {shlex.quote(target_id)} --source cli "
            f"--scope-type target --scope-id {shlex.quote(target_id)} --format json",
        )
        consumer_b_id = create_b[0]["data"]["consumer_id"]

        close_lines = _run_cli_json(
            container,
            f"consumer close --consumer {shlex.quote(consumer_a_id)} --format json",
        )
        assert close_lines[0]["data"]["closed"] is True

        cleanup_lines = _run_cli_json(
            container,
            "consumer cleanup --format json",
        )
        removed_ids = cleanup_lines[0]["data"]["removed_ids"]
        assert consumer_a_id in removed_ids, (
            f"Closed consumer {consumer_a_id!r} not in removed_ids: {removed_ids}"
        )

        list_lines = _run_cli_json(
            container,
            f"consumer list --target {shlex.quote(target_id)} --format json",
        )
        listed_ids = [line["data"]["consumer_id"] for line in list_lines]
        assert consumer_a_id not in listed_ids, (
            f"Cleaned-up consumer {consumer_a_id!r} still visible: {listed_ids}"
        )
        assert consumer_b_id in listed_ids, (
            f"Active consumer {consumer_b_id!r} missing from list: {listed_ids}"
        )
