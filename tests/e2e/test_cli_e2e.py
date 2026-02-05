import json
import subprocess
import sys

import pytest

pytestmark = [pytest.mark.e2e]


class TestCLIE2E:
    def test_cli_attach_command(
            self,
            target_process,
            has_ptrace_permission,
            has_pep768,
            has_gdb,
            cleanup_peeka_files,
    ):
        if not has_ptrace_permission:
            pytest.skip("No ptrace permission")
        if not has_pep768 and not has_gdb:
            pytest.skip("Neither PEP 768 nor GDB available")

        pid = target_process["pid"]

        result = subprocess.run(
            [sys.executable, "-m", "peeka.cli", "attach", str(pid)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        lines = [l for l in result.stdout.strip().split("\n") if l.strip()]
        json_lines = [l for l in lines if l.startswith("{")]

        success_line = None
        for line in json_lines:
            try:
                data = json.loads(line)
                if data.get("type") == "success":
                    success_line = data
                    break
            except json.JSONDecodeError:
                continue

        assert success_line is not None, (
            f"Should have success output. Got: {result.stdout}"
        )
        assert success_line["command"] == "attach"
        assert "socket" in success_line.get("data", {})

    def test_cli_watch_command_with_times(
            self,
            target_process,
            has_ptrace_permission,
            has_pep768,
            has_gdb,
            cleanup_peeka_files,
    ):
        if not has_ptrace_permission:
            pytest.skip("No ptrace permission")
        if not has_pep768 and not has_gdb:
            pytest.skip("Neither PEP 768 nor GDB available")

        pid = target_process["pid"]

        attach_result = subprocess.run(
            [sys.executable, "-m", "peeka.cli", "attach", str(pid)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if (
                "error" in attach_result.stdout.lower()
                and "success" not in attach_result.stdout.lower()
        ):
            pytest.skip(f"Attach failed: {attach_result.stdout}")

        try:
            watch_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "peeka.cli",
                    "watch",
                    "__main__.Calculator.add",
                    "-n",
                    "3",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except subprocess.TimeoutExpired:
            pass

        assert (
                "watch_started" in watch_result.stdout
                or "observation" in watch_result.stdout
        )

    def test_cli_detach_command(
            self,
            target_process,
            has_ptrace_permission,
            has_pep768,
            has_gdb,
            cleanup_peeka_files,
    ):
        if not has_ptrace_permission:
            pytest.skip("No ptrace permission")
        if not has_pep768 and not has_gdb:
            pytest.skip("Neither PEP 768 nor GDB available")

        pid = target_process["pid"]

        subprocess.run(
            [sys.executable, "-m", "peeka.cli", "attach", str(pid)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        detach_result = subprocess.run(
            [sys.executable, "-m", "peeka.cli", "detach"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        assert (
                "success" in detach_result.stdout.lower()
                or "detach" in detach_result.stdout.lower()
        )
