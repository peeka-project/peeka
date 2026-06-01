"""Tests for agent target.hello and target.status handlers."""

import sys
import time
from pathlib import Path
from typing import Any, Dict

import pytest


class MockAgent:
    """Minimal agent mock for testing target handlers."""

    def __init__(
        self,
        session_id: str = "test-session-12345678",
        attached_pid: int = 99999,
        agent_mode: str = "injected",
        injection_mode: str = "pep768",
    ):
        self.session_id = session_id
        self.attached_pid = attached_pid
        self.agent_mode = agent_mode
        self.injection_mode = injection_mode
        self.running = True
        self._recent_errors = []
        self._last_seen_at = time.time()

        import threading

        self._error_ring_lock = threading.Lock()

    def _add_recent_error(self, error_entry: Dict[str, Any]) -> None:
        """Add an error entry to the ring buffer (max 5)."""
        with self._error_ring_lock:
            self._recent_errors.append(error_entry)
            if len(self._recent_errors) > 5:
                self._recent_errors.pop(0)

    def _handle_target_hello(self) -> Dict[str, Any]:
        """Handle target.hello command - returns basic target information."""
        try:
            import peeka
            from peeka.core.targets import TARGET_SCHEMA_VERSION

            target_id = f"target_{self.session_id[:8]}"
            python_version = (
                f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            )

            return {
                "status": "success",
                "schema_version": TARGET_SCHEMA_VERSION,
                "target_id": target_id,
                "pid": self.attached_pid or 0,
                "python_version": python_version,
                "peeka_version": peeka.__version__,
                "capabilities": {},
                "runtime": {},
                "state": "alive",
                "agent_mode": self.agent_mode,
                "injection_mode": self.injection_mode,
            }
        except Exception as e:
            import traceback

            return {
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

    def _handle_target_status(self) -> Dict[str, Any]:
        """Handle target.status command - returns hello payload + last_seen_at + recent_errors."""
        try:
            self._last_seen_at = time.time()

            hello_payload = self._handle_target_hello()
            if hello_payload.get("status") != "success":
                return hello_payload

            with self._error_ring_lock:
                recent_errors = list(self._recent_errors)

            hello_payload["last_seen_at"] = self._last_seen_at
            hello_payload["recent_errors"] = recent_errors

            return hello_payload
        except Exception as e:
            import traceback

            return {
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }


class TestTargetHandlers:
    def test_target_hello_response_shape(self):
        """Verify target.hello returns all required fields."""
        agent = MockAgent()
        result = agent._handle_target_hello()

        assert result["status"] == "success"
        assert "schema_version" in result
        assert result["schema_version"] == "1"
        assert result["target_id"] == "target_test-ses"
        assert result["pid"] == 99999
        assert "python_version" in result
        assert "peeka_version" in result
        assert "capabilities" in result
        assert isinstance(result["capabilities"], dict)
        assert "runtime" in result
        assert isinstance(result["runtime"], dict)
        assert result["state"] == "alive"
        assert result["agent_mode"] == "injected"
        assert result["injection_mode"] == "pep768"

    def test_target_hello_python_version_format(self):
        """Verify python_version is in major.minor.micro format."""
        agent = MockAgent()
        result = agent._handle_target_hello()

        python_version = result["python_version"]
        parts = python_version.split(".")
        assert len(parts) == 3
        assert all(part.isdigit() for part in parts)

    def test_target_hello_different_modes(self):
        """Verify hello respects agent_mode and injection_mode parameters."""
        agent = MockAgent(agent_mode="preinstalled", injection_mode="gdb_dlopen")
        result = agent._handle_target_hello()

        assert result["agent_mode"] == "preinstalled"
        assert result["injection_mode"] == "gdb_dlopen"

    def test_target_status_includes_hello_fields(self):
        """Verify status returns all hello fields plus extensions."""
        agent = MockAgent()
        result = agent._handle_target_status()

        assert result["status"] == "success"
        assert result["target_id"] == "target_test-ses"
        assert result["pid"] == 99999
        assert result["state"] == "alive"
        assert "last_seen_at" in result
        assert isinstance(result["last_seen_at"], float)
        assert result["last_seen_at"] > 0
        assert "recent_errors" in result
        assert isinstance(result["recent_errors"], list)

    def test_target_status_recent_errors_empty_by_default(self):
        """Verify recent_errors starts empty."""
        agent = MockAgent()
        result = agent._handle_target_status()

        assert result["recent_errors"] == []

    def test_target_status_recent_errors_populated(self):
        """Verify recent_errors contains error entries after errors."""
        agent = MockAgent()

        agent._add_recent_error(
            {
                "timestamp": time.time(),
                "code": "TEST_ERROR_1",
                "message": "First test error",
            }
        )
        agent._add_recent_error(
            {
                "timestamp": time.time(),
                "code": "TEST_ERROR_2",
                "message": "Second test error",
            }
        )

        result = agent._handle_target_status()

        assert len(result["recent_errors"]) == 2
        assert result["recent_errors"][0]["code"] == "TEST_ERROR_1"
        assert result["recent_errors"][1]["code"] == "TEST_ERROR_2"

    def test_target_status_recent_errors_ring_buffer_max_5(self):
        """Verify recent_errors ring buffer keeps only last 5 entries."""
        agent = MockAgent()

        for i in range(8):
            agent._add_recent_error(
                {"timestamp": time.time(), "code": f"ERR_{i}", "message": f"Error {i}"}
            )

        result = agent._handle_target_status()

        assert len(result["recent_errors"]) == 5
        assert result["recent_errors"][0]["code"] == "ERR_3"
        assert result["recent_errors"][4]["code"] == "ERR_7"

    def test_target_status_updates_last_seen_at(self):
        """Verify status updates last_seen_at on each call."""
        agent = MockAgent()

        result1 = agent._handle_target_status()
        time.sleep(0.01)
        result2 = agent._handle_target_status()

        assert result2["last_seen_at"] > result1["last_seen_at"]

    def test_legacy_ping_shape_matches_hello(self):
        """Verify legacy ping command would return same shape as hello."""
        agent = MockAgent()
        hello_result = agent._handle_target_hello()

        expected_keys = {
            "status",
            "schema_version",
            "target_id",
            "pid",
            "python_version",
            "peeka_version",
            "capabilities",
            "runtime",
            "state",
            "agent_mode",
            "injection_mode",
        }
        assert set(hello_result.keys()) == expected_keys


class TestTargetHandlersIntegration:
    """Integration tests with real PeekaAgent if available."""

    def test_real_agent_target_hello(self, tmp_path: Path):
        """Test target.hello with real agent instance."""
        try:
            from peeka.core.agent import PeekaAgent
        except ImportError:
            pytest.skip("PeekaAgent not available")

        session_id = f"test-hello-{int(time.time())}"
        agent = PeekaAgent(
            session_id=session_id,
            attached_pid=12345,
            agent_mode="injected",
            injection_mode="pep768",
        )

        result = agent._handle_target_hello()

        assert result["status"] == "success"
        assert result["target_id"] == f"target_{session_id[:8]}"
        assert result["pid"] == 12345
        assert result["agent_mode"] == "injected"
        assert result["injection_mode"] == "pep768"

    def test_real_agent_target_status(self, tmp_path: Path):
        """Test target.status with real agent instance."""
        try:
            from peeka.core.agent import PeekaAgent
        except ImportError:
            pytest.skip("PeekaAgent not available")

        session_id = f"test-status-{int(time.time())}"
        agent = PeekaAgent(session_id=session_id, attached_pid=67890)

        agent._add_recent_error(
            {"timestamp": time.time(), "code": "TEST", "message": "test error"}
        )

        result = agent._handle_target_status()

        assert result["status"] == "success"
        assert "last_seen_at" in result
        assert len(result["recent_errors"]) == 1
        assert result["recent_errors"][0]["code"] == "TEST"

    def test_real_agent_execute_command_target_hello(self, tmp_path: Path):
        """Test _execute_command dispatch for target.hello."""
        try:
            from peeka.core.agent import PeekaAgent
        except ImportError:
            pytest.skip("PeekaAgent not available")

        session_id = f"test-dispatch-hello-{int(time.time())}"
        agent = PeekaAgent(session_id=session_id, attached_pid=11111)

        command = {"type": "target", "action": "hello"}
        result = agent._execute_command(command)

        assert result["status"] == "success"
        assert result["target_id"] == f"target_{session_id[:8]}"

    def test_real_agent_execute_command_target_status(self, tmp_path: Path):
        """Test _execute_command dispatch for target.status."""
        try:
            from peeka.core.agent import PeekaAgent
        except ImportError:
            pytest.skip("PeekaAgent not available")

        session_id = f"test-dispatch-status-{int(time.time())}"
        agent = PeekaAgent(session_id=session_id, attached_pid=22222)

        command = {"type": "target", "action": "status"}
        result = agent._execute_command(command)

        assert result["status"] == "success"
        assert "last_seen_at" in result
        assert "recent_errors" in result

    def test_real_agent_execute_command_legacy_ping(self, tmp_path: Path):
        """Test legacy {"command":"ping"} still works."""
        try:
            from peeka.core.agent import PeekaAgent
        except ImportError:
            pytest.skip("PeekaAgent not available")

        session_id = f"test-ping-{int(time.time())}"
        agent = PeekaAgent(session_id=session_id, attached_pid=33333)

        command = {"command": "ping"}
        result = agent._execute_command(command)

        assert result["status"] == "success"
        assert result["target_id"] == f"target_{session_id[:8]}"
        assert result["state"] == "alive"
