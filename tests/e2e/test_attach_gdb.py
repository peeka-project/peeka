import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.gdb,
    pytest.mark.skipif(
        hasattr(sys, "remote_exec"), reason="PEP 768 available - GDB fallback not used"
    ),
]


class TestGDBFallbackAttach:
    def test_gdb_attach_creates_socket(
            self, target_process, has_ptrace_permission, has_gdb, cleanup_peeka_files
    ):
        if not has_ptrace_permission:
            pytest.skip("No ptrace permission (ptrace_scope != 0)")
        if not has_gdb:
            pytest.skip("GDB not installed")

        from peeka.core.attach import ProcessAttacher

        pid = target_process["pid"]
        attacher = ProcessAttacher(pid)

        try:
            result = attacher.attach()
        except RuntimeError as e:
            if "debug symbols" in str(e).lower() or "no symbol" in str(e).lower():
                pytest.skip(f"Python debug symbols not available: {e}")
            raise

        assert result is True, "ProcessAttacher.attach() should return True"

        socket_path = Path(attacher.get_socket_path())

        for _ in range(50):
            if socket_path.exists():
                break
            time.sleep(0.1)

        assert socket_path.exists(), f"Socket should exist at {socket_path}"

    def test_gdb_attach_agent_responds(
            self, target_process, has_ptrace_permission, has_gdb, cleanup_peeka_files
    ):
        if not has_ptrace_permission:
            pytest.skip("No ptrace permission")
        if not has_gdb:
            pytest.skip("GDB not installed")

        from peeka.core.attach import ProcessAttacher
        from peeka.core.client import AgentClient

        pid = target_process["pid"]
        attacher = ProcessAttacher(pid)

        try:
            assert attacher.attach() is True
        except RuntimeError as e:
            if "debug symbols" in str(e).lower():
                pytest.skip(f"Python debug symbols not available: {e}")
            raise

        socket_path = attacher.get_socket_path()

        for _ in range(50):
            if Path(socket_path).exists():
                break
            time.sleep(0.1)

        client = AgentClient(socket_path)
        response = client.send_command({"type": "watch", "action": "status"})

        assert response["status"] == "success"
