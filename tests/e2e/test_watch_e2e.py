import time
from pathlib import Path

import pytest

pytestmark = [pytest.mark.e2e]


def skip_if_no_attach_capability(has_ptrace_permission, has_pep768, has_gdb):
    if not has_ptrace_permission:
        pytest.skip("No ptrace permission")
    if not has_pep768 and not has_gdb:
        pytest.skip("Neither PEP 768 nor GDB available")


class TestWatchE2E:
    def test_watch_with_condition_filter(
            self,
            target_process,
            has_ptrace_permission,
            has_pep768,
            has_gdb,
            cleanup_peeka_files,
    ):
        skip_if_no_attach_capability(has_ptrace_permission, has_pep768, has_gdb)

        from peeka.core.attach import ProcessAttacher
        from peeka.core.client import StreamingAgentClient

        pid = target_process["pid"]
        attacher = ProcessAttacher(pid)

        try:
            assert attacher.attach() is True
        except RuntimeError as e:
            pytest.skip(f"Attach failed: {e}")

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
                "times": 10,
                "condition": "params[0] > 50",
            }
        )

        assert response["status"] == "success"
        watch_id = response["watch_id"]

        observations = []
        start_time = time.time()
        try:
            for obs in client.stream_observations():
                observations.append(obs)
                if len(observations) >= 2 or (time.time() - start_time) > 15:
                    break
        except Exception:
            pass

        for obs in observations:
            if "args" in obs:
                first_arg = obs["args"][0] if obs["args"] else 0
                assert first_arg > 50, f"Condition filter failed: got {first_arg}"

        client.send_command({"type": "watch", "action": "stop", "watch_id": watch_id})
        client.disconnect()

    def test_watch_stop_removes_instrumentation(
            self,
            target_process,
            has_ptrace_permission,
            has_pep768,
            has_gdb,
            cleanup_peeka_files,
    ):
        skip_if_no_attach_capability(has_ptrace_permission, has_pep768, has_gdb)

        from peeka.core.attach import ProcessAttacher
        from peeka.core.client import AgentClient

        pid = target_process["pid"]
        attacher = ProcessAttacher(pid)

        try:
            assert attacher.attach() is True
        except RuntimeError as e:
            pytest.skip(f"Attach failed: {e}")

        socket_path = attacher.get_socket_path()

        for _ in range(50):
            if Path(socket_path).exists():
                break
            time.sleep(0.1)

        client = AgentClient(socket_path)

        start_response = client.send_command(
            {
                "type": "watch",
                "action": "start",
                "pattern": "__main__.Calculator.multiply",
                "times": -1,
            }
        )
        assert start_response["status"] == "success"
        watch_id = start_response["watch_id"]

        status_response = client.send_command({"type": "watch", "action": "status"})
        assert len(status_response["watches"]) == 1

        stop_response = client.send_command(
            {"type": "watch", "action": "stop", "watch_id": watch_id}
        )
        assert stop_response["status"] == "success"

        status_after = client.send_command({"type": "watch", "action": "status"})
        assert len(status_after["watches"]) == 0
