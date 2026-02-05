import sys
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.py314,
    pytest.mark.skipif(
        not hasattr(sys, "remote_exec"),
        reason="PEP 768 (sys.remote_exec) not available - requires Python 3.14+",
    ),
]


class TestPEP768Attach:
    def test_attach_creates_socket_and_ready_file(
            self, target_process, has_ptrace_permission, cleanup_peeka_files
    ):
        if not has_ptrace_permission:
            pytest.skip("No ptrace permission (ptrace_scope != 0)")

        from peeka.core.attach import ProcessAttacher

        pid = target_process["pid"]
        attacher = ProcessAttacher(pid)

        result = attacher.attach()
        assert result is True, "ProcessAttacher.attach() should return True"

        socket_path = Path(attacher.get_socket_path())
        ready_path = Path(f"/tmp/peeka_{attacher.session_id}.ready")
        pid_path = Path(f"/tmp/peeka_{attacher.session_id}.pid")

        for _ in range(50):
            if socket_path.exists():
                break
            time.sleep(0.1)

        assert socket_path.exists(), f"Socket should exist at {socket_path}"
        assert ready_path.exists(), f"Ready file should exist at {ready_path}"
        assert pid_path.exists(), f"PID file should exist at {pid_path}"

    def test_attach_agent_accepts_connections(
            self, target_process, has_ptrace_permission, cleanup_peeka_files
    ):
        if not has_ptrace_permission:
            pytest.skip("No ptrace permission")

        from peeka.core.attach import ProcessAttacher
        from peeka.core.client import AgentClient

        pid = target_process["pid"]
        attacher = ProcessAttacher(pid)

        assert attacher.attach() is True

        socket_path = attacher.get_socket_path()

        for _ in range(50):
            if Path(socket_path).exists():
                break
            time.sleep(0.1)

        client = AgentClient(socket_path)
        response = client.send_command({"type": "watch", "action": "status"})

        assert response["status"] == "success"
        assert "watches" in response

    def test_attach_and_watch_receives_observations(
            self, target_process, has_ptrace_permission, cleanup_peeka_files
    ):
        if not has_ptrace_permission:
            pytest.skip("No ptrace permission")

        from peeka.core.attach import ProcessAttacher
        from peeka.core.client import StreamingAgentClient

        pid = target_process["pid"]
        attacher = ProcessAttacher(pid)

        assert attacher.attach() is True

        socket_path = attacher.get_socket_path()

        for _ in range(50):
            if Path(socket_path).exists():
                break
            time.sleep(0.1)

        client = StreamingAgentClient(socket_path, timeout=10.0)
        connect_result = client.connect()
        assert connect_result["status"] == "success"

        response = client.send_command(
            {
                "type": "watch",
                "action": "start",
                "pattern": "__main__.Calculator.add",
                "depth": 2,
                "times": 5,
            }
        )

        assert response["status"] == "success"
        watch_id = response["watch_id"]

        observations = []
        try:
            for obs in client.stream_observations():
                observations.append(obs)
                if len(observations) >= 3:
                    break
        except Exception:
            pass

        assert len(observations) >= 1, "Should receive at least one observation"

        obs = observations[0]
        assert "func_name" in obs or "function" in obs

        client.send_command({"type": "watch", "action": "stop", "watch_id": watch_id})
        client.disconnect()
