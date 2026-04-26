"""
E2E test for GDB dlopen injection path.

This test verifies that the new GDB + dlopen + C extension injection
path works end-to-end on Linux systems with Python 3.8-3.13.
"""

import platform
import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(
        platform.system() != "Linux",
        reason="GDB dlopen injection is Linux-specific",
    ),
]


class TestGDBDlopenAttach:
    """Test GDB dlopen injection end-to-end."""

    def test_gdb_dlopen_injection_creates_socket(
        self, target_process, has_ptrace_permission, has_gdb, cleanup_peeka_files
    ):
        """
        Test that GDB dlopen injection creates agent socket.

        This test:
        1. Spawns a target process
        2. Attaches using ProcessAttacher (forces fallback path)
        3. Verifies the agent socket is created
        """
        if not has_ptrace_permission:
            pytest.skip("No ptrace permission (ptrace_scope != 0)")
        if not has_gdb:
            pytest.skip("GDB not installed")

        from peeka.core.attach import ProcessAttacher, _has_injector

        if not _has_injector():
            pytest.skip("C extension not available")

        pid = target_process["pid"]
        attacher = ProcessAttacher(pid)

        # Force fallback even if PEP 768 available
        original_remote_exec = getattr(sys, "remote_exec", None)
        if original_remote_exec:
            delattr(sys, "remote_exec")

        try:
            result = attacher.attach()
        except RuntimeError as e:
            error_msg = str(e).lower()
            if "debug symbols" in error_msg or "no symbol" in error_msg:
                pytest.skip(f"Python debug symbols not available: {e}")
            raise
        finally:
            # Restore remote_exec if it existed
            if original_remote_exec:
                sys.remote_exec = original_remote_exec

        assert result is True, "ProcessAttacher.attach() should return True"

        socket_path = Path(attacher.get_socket_path())

        # Wait for socket to be created
        for _ in range(50):
            if socket_path.exists():
                break
            time.sleep(0.1)

        assert socket_path.exists(), f"Socket should exist at {socket_path}"

    def test_gdb_dlopen_injection_agent_responds(
        self, target_process, has_ptrace_permission, has_gdb, cleanup_peeka_files
    ):
        """
        Test that GDB dlopen-injected agent responds to commands.

        This test:
        1. Spawns a target process
        2. Attaches using ProcessAttacher (forces fallback path)
        3. Sends a command via AgentClient
        4. Verifies the agent responds correctly
        """
        if not has_ptrace_permission:
            pytest.skip("No ptrace permission")
        if not has_gdb:
            pytest.skip("GDB not installed")

        from peeka.core.attach import ProcessAttacher, _has_injector
        from peeka.core.client import AgentClient

        if not _has_injector():
            pytest.skip("C extension not available")

        pid = target_process["pid"]
        attacher = ProcessAttacher(pid)

        # Force fallback even if PEP 768 available
        original_remote_exec = getattr(sys, "remote_exec", None)
        if original_remote_exec:
            delattr(sys, "remote_exec")

        try:
            assert attacher.attach() is True
        except RuntimeError as e:
            error_msg = str(e).lower()
            if "debug symbols" in error_msg or "no symbol" in error_msg:
                pytest.skip(f"Python debug symbols not available: {e}")
            raise
        finally:
            # Restore remote_exec if it existed
            if original_remote_exec:
                sys.remote_exec = original_remote_exec

        socket_path = attacher.get_socket_path()

        # Wait for socket to exist
        for _ in range(50):
            if Path(socket_path).exists():
                break
            time.sleep(0.1)

        # Create client and send test command
        client = AgentClient(socket_path)

        # Send watch status command (simple command that should work)
        response = client.send_command({"type": "watch", "action": "status"})

        assert response["status"] == "success", f"Expected success, got: {response}"

    def test_gdb_dlopen_injection_with_complete_command(
        self, target_process, has_ptrace_permission, has_gdb, cleanup_peeka_files
    ):
        """
        Test GDB dlopen injection with completion command.

        This test verifies that the agent can handle the 'complete' command,
        which is used by CLI/TUI completion features.
        """
        if not has_ptrace_permission:
            pytest.skip("No ptrace permission")
        if not has_gdb:
            pytest.skip("GDB not installed")

        from peeka.core.attach import ProcessAttacher, _has_injector
        from peeka.core.client import AgentClient

        if not _has_injector():
            pytest.skip("C extension not available")

        pid = target_process["pid"]
        attacher = ProcessAttacher(pid)

        # Force fallback even if PEP 768 available
        original_remote_exec = getattr(sys, "remote_exec", None)
        if original_remote_exec:
            delattr(sys, "remote_exec")

        try:
            assert attacher.attach() is True
        except RuntimeError as e:
            error_msg = str(e).lower()
            if "debug symbols" in error_msg or "no symbol" in error_msg:
                pytest.skip(f"Python debug symbols not available: {e}")
            raise
        finally:
            if original_remote_exec:
                sys.remote_exec = original_remote_exec

        socket_path = attacher.get_socket_path()

        for _ in range(50):
            if Path(socket_path).exists():
                break
            time.sleep(0.1)

        client = AgentClient(socket_path)

        # Test completion for "__main__.Calculator"
        response = client.send_command(
            {"type": "complete", "params": {"target": "__main__.Calculator"}}
        )

        assert response["status"] == "success", f"Expected success, got: {response}"
        assert "data" in response
        assert "methods" in response["data"]
        # Verify Calculator methods are found
        methods = response["data"]["methods"]
        assert any("add" in m for m in methods), f"Expected 'add' method in: {methods}"
        assert any("multiply" in m for m in methods), (
            f"Expected 'multiply' method in: {methods}"
        )
