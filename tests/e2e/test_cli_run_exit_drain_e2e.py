import json
import os
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

pytestmark = [pytest.mark.e2e]

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _can_attach_direct_child() -> bool:
    """Return True if YAMA ptrace_scope allows attaching to a direct child."""
    ptrace_scope = Path("/proc/sys/kernel/yama/ptrace_scope")
    if ptrace_scope.exists():
        try:
            return int(ptrace_scope.read_text().strip()) <= 1
        except (ValueError, PermissionError):
            return False
    return True


def _run_short_exit_target(
    tmp_path: Path,
    command_args: List[str],
    *,
    exit_code: int = 7,
) -> subprocess.CompletedProcess[str]:
    script = tmp_path / "tail_target.py"
    script.write_text(
        "import sys\n\n"
        "def target(value):\n"
        "    return value + 1\n\n"
        "if __name__ == '__main__':\n"
        "    target(1)\n"
        "    target(2)\n"
        f"    sys.exit({exit_code})\n"
    )
    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = (
        f"{PROJECT_ROOT}{os.pathsep}{existing_pythonpath}"
        if existing_pythonpath
        else str(PROJECT_ROOT)
    )
    return subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "run", str(script), "--", *command_args],
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )


class TestCliRunImmediateExitDrainE2E:
    """Verify `peeka run` drains observations before child exit with zero sleep."""

    @pytest.mark.parametrize(
        "command_args",
        [
            ["trace", "tail_target.target", "-n", "4"],
            ["stack", "tail_target.target", "-n", "4"],
            ["watch", "tail_target.target", "-n", "4"],
        ],
        ids=["trace", "stack", "watch"],
    )
    def test_immediate_sys_exit_emits_all_observations_and_preserves_exit_code(
        self,
        tmp_path: Path,
        has_pep768: bool,
        has_gdb: bool,
        command_args: List[str],
    ) -> None:
        if not _can_attach_direct_child():
            pytest.skip("ptrace_scope >= 2: cannot attach to child process")
        if not has_pep768 and not has_gdb:
            pytest.skip("Neither PEP 768 nor GDB available")

        result = _run_short_exit_target(tmp_path, command_args, exit_code=7)

        assert result.returncode == 7, result.stderr
        observations = [
            json.loads(line)
            for line in result.stdout.strip().splitlines()
            if line.strip()
        ]
        assert len(observations) == 2, (result.stdout, result.stderr)
        assert [obs.get("type") for obs in observations] == ["observation", "observation"]
        assert [obs.get("seq") for obs in observations] == [1, 2]
