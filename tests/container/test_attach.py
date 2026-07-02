"""
Container E2E tests for attach/detach lifecycle.

Tests core attach/detach operations in Docker containers against:
- Python 3.8 (GDB-based attachment)
- Python 3.12 (GDB-based attachment)
- Python 3.14 (PEP 768 native attachment)
"""

import base64
import json
import textwrap

import pytest

from tests.container.conftest import exec_in_container

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
        lines = [line for line in output.strip().split("\n") if line.strip()]
        json_lines = [line for line in lines if line.startswith("{")]

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
        lines = [line for line in output.strip().split("\n") if line.strip()]
        json_lines = [line for line in lines if line.startswith("{")]

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


@pytest.mark.container
class TestModuleCacheRefresh:
    """Regression: re-attach must load fresh peeka modules, not stale cached ones."""

    def test_reattach_evicts_stale_peeka_modules(self, py314_target):
        """After detach and re-attach, peeka.* modules must be free of stale attributes."""
        container = py314_target["container"]
        pid = py314_target["pid"]

        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"First attach failed:\n{attach_output}"

        inject_py = textwrap.dedent(
            """
            import sys, os
            for _n, _m in list(sys.modules.items()):
                if _n == "peeka" or _n.startswith("peeka."):
                    _m._STALE_SENTINEL = True
            with open("/tmp/peeka_sentinel_injected.flag", "w") as _f:
                _f.write("ok")
            """
        ).strip()
        inject_b64 = base64.b64encode(inject_py.encode()).decode()
        exec_in_container(
            container,
            f"echo {inject_b64} | base64 -d > /tmp/inject_sentinel.py",
            timeout=5,
        )
        run_inject_cmd = (
            f"python3 -c \"import sys, time, os; "
            f"sys.remote_exec({pid}, '/tmp/inject_sentinel.py'); "
            "time.sleep(2); "
            "print('INJECTED' if os.path.exists('/tmp/peeka_sentinel_injected.flag') else 'TIMEOUT')\""
        )
        exit_code, inject_output = exec_in_container(
            container, run_inject_cmd, timeout=15
        )
        if exit_code != 0 or "INJECTED" not in inject_output:
            pytest.skip(
                f"Could not inject sentinel via PEP 768 sys.remote_exec — "
                f"skipping (output: {inject_output!r})"
            )

        exec_in_container(
            container, "python -m peeka.cli.main detach", timeout=15
        )
        exec_in_container(
            container,
            "rm -f /tmp/peeka_*.sock /tmp/peeka_*.ready /tmp/peeka_agent_*.py 2>/dev/null; true",
            timeout=5,
        )

        exit_code, reattach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Re-attach failed:\n{reattach_output}"

        check_py = textwrap.dedent(
            """
            import sys, os
            found_stale = any(
                hasattr(_m, "_STALE_SENTINEL")
                for _n, _m in sys.modules.items()
                if _n == "peeka" or _n.startswith("peeka.")
            )
            with open("/tmp/peeka_sentinel_check.result", "w") as _f:
                _f.write("STALE" if found_stale else "FRESH")
            """
        ).strip()
        check_b64 = base64.b64encode(check_py.encode()).decode()
        exec_in_container(
            container,
            f"echo {check_b64} | base64 -d > /tmp/check_sentinel.py",
            timeout=5,
        )
        run_check_cmd = (
            f"python3 -c \"import sys, time, os; "
            f"sys.remote_exec({pid}, '/tmp/check_sentinel.py'); "
            "time.sleep(2); "
            "result = open('/tmp/peeka_sentinel_check.result').read().strip() "
            "if os.path.exists('/tmp/peeka_sentinel_check.result') else 'TIMEOUT'; "
            "print(result)\""
        )
        exit_code, check_output = exec_in_container(
            container, run_check_cmd, timeout=15
        )
        result = check_output.strip()

        assert result == "FRESH", (
            f"After re-attach, peeka.* modules still carry the stale sentinel. "
            f"Expected FRESH, got: {result!r}. "
            f"This means the module cache cleanup in _create_agent_script() is NOT working."
        )
