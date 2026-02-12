"""
Container E2E tests for attach/detach lifecycle.

Tests core attach/detach operations in Docker containers against both:
- Python 3.12 (GDB-based attachment)
- Python 3.14 (PEP 768 native attachment)
"""

import json
import pytest

from tests.container.conftest import exec_in_container, cleanup_peeka_files_in_container

pytestmark = [pytest.mark.container]


class TestContainerAttach:
    """Test attach/detach operations in containerized environments."""

    def test_attach_success(self, container_target):
        """Verify successful attachment to target process."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Execute attach command
        exit_code, output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )

        # Parse JSONL output
        lines = [l for l in output.strip().split("\n") if l.strip()]
        json_lines = [l for l in lines if l.startswith("{")]

        success_line = None
        for line in json_lines:
            try:
                data = json.loads(line)
                if data.get("type") == "success" and data.get("command") == "attach":
                    success_line = data
                    break
            except json.JSONDecodeError:
                continue

        assert success_line is not None, f"No success line found in output:\n{output}"
        assert "data" in success_line, (
            f"Missing 'data' field in success line: {success_line}"
        )
        assert "socket" in success_line["data"], (
            f"Missing 'socket' in data: {success_line['data']}"
        )

    def test_attach_creates_socket_file(self, container_target):
        """Verify that attach creates a Unix socket file in /tmp."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach to target
        exit_code, output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )

        # Verify socket file exists
        exit_code, ls_output = exec_in_container(
            container, "ls /tmp/peeka_*.sock", timeout=5
        )

        assert exit_code == 0, f"Socket file not found in /tmp. ls output:\n{ls_output}"
        assert ".sock" in ls_output, f"No .sock file in output:\n{ls_output}"

    def test_detach_after_attach(self, container_target):
        """Verify successful detachment after attaching."""
        container = container_target["container"]
        pid = container_target["pid"]

        # First attach
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Then detach
        exit_code, detach_output = exec_in_container(
            container, "python -m peeka.cli.main detach", timeout=10
        )

        # Verify detach success (either explicit success or detach message)
        output_lower = detach_output.lower()
        assert (
            exit_code == 0 or "success" in output_lower or "detach" in output_lower
        ), f"Detach operation failed:\n{detach_output}"

    def test_attach_invalid_pid(self, container_target):
        """Verify graceful failure when attaching to invalid PID."""
        container = container_target["container"]

        # Attempt to attach to non-existent PID
        exit_code, output = exec_in_container(
            container, "python -m peeka.cli.main attach 99999", timeout=30
        )

        # Should fail gracefully
        assert exit_code != 0 or "error" in output.lower(), (
            f"Expected failure for invalid PID, got:\n{output}"
        )

    def test_attach_twice_same_pid(self, container_target):
        """Verify behavior when attaching to same PID twice."""
        container = container_target["container"]
        pid = container_target["pid"]

        # First attach
        exit_code1, output1 = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code1 == 0, f"First attach failed:\n{output1}"

        # Second attach to same PID
        exit_code2, output2 = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )

        # Either succeeds with reuse message or fails gracefully (no crash)
        # Both are acceptable behaviors - key is no segfault/crash
        output2_lower = output2.lower()
        acceptable = (
            exit_code2 == 0
            or "already" in output2_lower
            or "attached" in output2_lower
            or "error" in output2_lower
        )
        assert acceptable, f"Unexpected behavior on double attach:\n{output2}"

    def test_attach_process_cleanup(self, container_target):
        """Verify target process remains healthy after attach/detach cycle."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach
        exit_code, _ = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, "Attach failed"

        # Detach
        exit_code, _ = exec_in_container(
            container, "python -m peeka.cli.main detach", timeout=10
        )

        # Verify target process still running
        exit_code, output = exec_in_container(
            container, f"test -d /proc/{pid} && echo alive", timeout=5
        )

        assert exit_code == 0, f"Target process {pid} died after detach cycle"
        assert "alive" in output, f"Process {pid} not running after detach cycle"

    def test_attach_socket_cleanup_on_detach(self, container_target):
        """Verify socket file is cleaned up after detach."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach
        exit_code, output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, "Attach failed"

        # Parse socket path from output
        lines = [l for l in output.strip().split("\n") if l.strip()]
        json_lines = [l for l in lines if l.startswith("{")]

        socket_path = None
        for line in json_lines:
            try:
                data = json.loads(line)
                if data.get("type") == "success" and "socket" in data.get("data", {}):
                    socket_path = data["data"]["socket"]
                    break
            except json.JSONDecodeError:
                continue

        assert socket_path is not None, (
            f"Could not find socket path in output:\n{output}"
        )

        # Detach
        exit_code, _ = exec_in_container(
            container, "python -m peeka.cli.main detach", timeout=10
        )

        # Verify socket file removed
        exit_code, ls_output = exec_in_container(
            container, f"ls {socket_path}", timeout=5
        )

        # ls should fail (socket removed) OR return "No such file"
        assert exit_code != 0 or "No such file" in ls_output, (
            f"Socket file {socket_path} still exists after detach"
        )
