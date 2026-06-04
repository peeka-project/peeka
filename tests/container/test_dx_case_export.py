"""Container E2E tests for DX case create/export workflow."""

import json
import shlex

import pytest

from tests.container.conftest import exec_in_container

pytestmark = [pytest.mark.container, pytest.mark.timeout(180)]


def _run_cli_json(container, cmd: str, timeout: int = 20):
    exit_code, output = exec_in_container(
        container,
        f"python -m peeka.cli.main {cmd}",
        timeout=timeout,
    )
    assert exit_code == 0, output
    lines = [line for line in output.strip().split("\n") if line.startswith("{")]
    assert lines, output
    return [json.loads(line) for line in lines]


class TestDXCaseExport:
    def test_dx_case_create_export_close_workflow(self, py314_target):
        container = py314_target["container"]
        pid = py314_target["pid"]

        attach_exit, attach_output = exec_in_container(
            container,
            f"python -m peeka.cli.main attach {pid}",
            timeout=30,
        )
        assert attach_exit == 0, attach_output

        target_query = "cd /app && python - <<'PY'\nimport json\nfrom peeka.core.targets import discover_targets\ntargets = discover_targets()\nassert targets\nprint(targets[0].target_id)\nPY"
        target_exit, target_output = exec_in_container(container, target_query, timeout=20)
        assert target_exit == 0, target_output
        target_id = target_output.strip().splitlines()[-1].strip()
        assert target_id.startswith("target_")

        consumer_lines = _run_cli_json(
            container,
            f"consumer create --target {shlex.quote(target_id)} --source cli --scope-type target --scope-id {shlex.quote(target_id)} --format json",
        )
        consumer_id = consumer_lines[0]["data"]["consumer_id"]

        dx_lines = _run_cli_json(
            container,
            f"dx create --target {shlex.quote(target_id)} --title {shlex.quote('E2E DX')} --format json",
        )
        dx_case_id = dx_lines[0]["data"]["dx_case_id"]

        add_lines = _run_cli_json(
            container,
            "dx add --dx-case {} --section-type note --title {} --payload-json {} --object-ref-type consumers --object-ref-id {} --format json".format(
                shlex.quote(dx_case_id),
                shlex.quote("Consumer link"),
                shlex.quote('{"message":"hello"}'),
                shlex.quote(consumer_id),
            ),
        )
        assert add_lines[0]["data"]["dx_case_id"] == dx_case_id

        export_path = f"/tmp/{dx_case_id}.json"
        export_lines = _run_cli_json(
            container,
            f"dx export --dx-case {shlex.quote(dx_case_id)} --output-path {shlex.quote(export_path)} --format json",
        )
        assert export_lines[0]["data"]["output_path"] == export_path

        read_exit, read_output = exec_in_container(container, f"cat {shlex.quote(export_path)}", timeout=10)
        assert read_exit == 0, read_output
        document = json.loads(read_output)
        assert document["dx_case"]["dx_case_id"] == dx_case_id
        assert "schema_version" in document
        assert "target_snapshot" in document
        assert "consumer_snapshots" in document
        assert len(document["consumer_snapshots"]) == 1
        assert document["consumer_snapshots"][0]["consumer_id"] == consumer_id

        close_lines = _run_cli_json(
            container,
            f"dx close --dx-case {shlex.quote(dx_case_id)} --format json",
        )
        assert close_lines[0]["data"]["closed"] is True
