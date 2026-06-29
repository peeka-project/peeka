"""Lightweight attach smoke test for the Python 3.8 GDB container."""

# pyright: reportDeprecated=false, reportAny=false, reportExplicitAny=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false

import json
from typing import Dict, Optional, Tuple, cast

import pytest

from tests.container.conftest import exec_in_container as _exec_in_container


def exec_in_container(container: object, cmd: str, timeout: int = 30) -> Tuple[int, str]:
    """Run a command in a test container."""
    return _exec_in_container(container, cmd, timeout)

pytestmark = [pytest.mark.container]


class TestAttachSmokePy38:
    """Minimal attach coverage for the py38/GDB container path."""

    def test_attach_creates_socket_and_responds_to_patch_status(
        self, py38_target: Dict[str, object]
    ):
        """Attach to the target and verify the agent is reachable."""
        container = py38_target["container"]
        pid = cast(str, py38_target["pid"])

        exit_code, output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{output}"

        socket_path: Optional[str] = None
        for line in output.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            data = cast(Dict[str, object], data)
            if data.get("type") != "success":
                continue
            socket_data = data.get("data")
            if not isinstance(socket_data, dict):
                continue
            socket_path = cast(Optional[str], socket_data.get("socket"))
            break

        assert socket_path, f"No socket path found in attach output:\n{output}"

        exit_code, ls_output = exec_in_container(
            container, f"test -S {socket_path}", timeout=5
        )
        assert exit_code == 0, f"Socket not created: {socket_path}\n{ls_output}"

        exit_code, patch_output = exec_in_container(
            container, "python -m peeka.cli.main patch-status", timeout=30
        )
        assert exit_code == 0, f"patch-status failed after attach:\n{patch_output}"
        assert '"status": "success"' in patch_output
