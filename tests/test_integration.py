import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Optional

import pytest


def _recv_exact(sock: socket.socket, size: int) -> bytes:
    chunks = []
    remaining = size
    while remaining > 0:
        chunk = sock.recv(remaining)
        if not chunk:
            return b""
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _recv_json_response(sock: socket.socket) -> dict:
    """Read a JSON command response, skipping broadcast LOG/OBS frames."""
    length_bytes = _recv_exact(sock, 4)
    while length_bytes in (b"LOG:", b"OBS:"):
        frame_len_bytes = _recv_exact(sock, 4)
        frame_len = int.from_bytes(frame_len_bytes, "big")
        _recv_exact(sock, frame_len)
        length_bytes = _recv_exact(sock, 4)

    length = int.from_bytes(length_bytes, "big")
    response_data = _recv_exact(sock, length)
    return json.loads(response_data.decode("utf-8"))


class TestAgentIntegration:
    @pytest.fixture
    def temp_socket_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            yield str(Path(tmpdir) / "test.sock")

    def test_agent_starts_and_accepts_connections(self, temp_socket_path):
        session_id = "test_session"
        socket_path = f"/tmp/peeka_{session_id}.sock"
        ready_path = f"/tmp/peeka_{session_id}.ready"
        agent: Optional["PeekaAgent"] = None

        Path(socket_path).unlink(missing_ok=True)
        Path(ready_path).unlink(missing_ok=True)

        try:
            from peeka.core.agent import PeekaAgent

            agent = PeekaAgent(session_id, attached_pid=None)
            agent.start()

            for _ in range(50):
                if Path(ready_path).exists():
                    break
                time.sleep(0.1)

            assert Path(ready_path).exists()
            assert Path(socket_path).exists()

            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(2.0)
                sock.connect(socket_path)

                command = {"type": "watch", "action": "status"}
                payload = json.dumps(command).encode("utf-8")
                sock.sendall(len(payload).to_bytes(4, "big"))
                sock.sendall(payload)

                response = _recv_json_response(sock)

                assert response["status"] == "success"
                assert "watches" in response

        finally:
            if agent:
                agent.stop()
            Path(socket_path).unlink(missing_ok=True)
            Path(ready_path).unlink(missing_ok=True)

    def test_watch_command_integration(self):
        session_id = "test_watch_int"
        socket_path = f"/tmp/peeka_{session_id}.sock"
        ready_path = f"/tmp/peeka_{session_id}.ready"
        agent: Optional["PeekaAgent"] = None

        Path(socket_path).unlink(missing_ok=True)
        Path(ready_path).unlink(missing_ok=True)

        try:

            def sample_function(x):
                return x * 2

            test_module = type(sys)("test_int_module")
            test_module.sample_function = sample_function
            sys.modules["test_int_module"] = test_module

            from peeka.core.agent import PeekaAgent

            agent = PeekaAgent(session_id)
            agent.start()

            for _ in range(50):
                if Path(ready_path).exists():
                    break
                time.sleep(0.1)

            from peeka.core.client import AgentClient

            client = AgentClient(socket_path)

            start_response = client.send_command(
                {
                    "type": "watch",
                    "action": "start",
                    "pattern": "test_int_module.sample_function",
                    "depth": 2,
                    "times": 3,
                }
            )

            assert start_response["status"] == "success"
            watch_id = start_response["watch_id"]

            result = test_module.sample_function(5)
            assert result == 10

            time.sleep(0.1)

            status_response = client.send_command({"type": "watch", "action": "status"})

            assert status_response["status"] == "success"
            assert len(status_response["watches"]) == 1

            stop_response = client.send_command(
                {"type": "watch", "action": "stop", "watch_id": watch_id}
            )

            assert stop_response["status"] == "success"
            assert stop_response["observation_count"] == 1

        finally:
            if agent:
                agent.stop()
            Path(socket_path).unlink(missing_ok=True)
            Path(ready_path).unlink(missing_ok=True)
            if "test_int_module" in sys.modules:
                del sys.modules["test_int_module"]


class TestStreamingClientIntegration:
    def test_streaming_receives_observations(self):
        session_id = "test_stream"
        socket_path = f"/tmp/peeka_{session_id}.sock"
        ready_path = f"/tmp/peeka_{session_id}.ready"
        agent: Optional["PeekaAgent"] = None

        Path(socket_path).unlink(missing_ok=True)
        Path(ready_path).unlink(missing_ok=True)

        try:

            def sample_function(x):
                return x + 1

            test_module = type(sys)("test_stream_module")
            test_module.sample_function = sample_function
            sys.modules["test_stream_module"] = test_module

            from peeka.core.agent import PeekaAgent

            agent = PeekaAgent(session_id, attached_pid=None)
            agent.start()

            for _ in range(50):
                if Path(ready_path).exists():
                    break
                time.sleep(0.1)

            from peeka.core.client import StreamingAgentClient

            client = StreamingAgentClient(socket_path, timeout=2.0)
            connect_result = client.connect()
            assert connect_result["status"] == "success"

            start_response = client.send_command(
                {
                    "type": "watch",
                    "action": "start",
                    "pattern": "test_stream_module.sample_function",
                    "depth": 2,
                    "times": 2,
                }
            )
            assert start_response["status"] == "success"
            watch_id = start_response["watch_id"]

            observations = []

            def collect_observations():
                for obs in client.stream_observations():
                    observations.append(obs)
                    if len(observations) >= 2:
                        break

            collector_thread = threading.Thread(target=collect_observations)
            collector_thread.start()

            time.sleep(0.2)

            test_module.sample_function(10)
            test_module.sample_function(20)

            collector_thread.join(timeout=3.0)

            assert len(observations) >= 1

            client.send_command(
                {"type": "watch", "action": "stop", "watch_id": watch_id}
            )
            client.disconnect()

        finally:
            if agent:
                agent.stop()
            Path(socket_path).unlink(missing_ok=True)
            Path(ready_path).unlink(missing_ok=True)
            if "test_stream_module" in sys.modules:
                del sys.modules["test_stream_module"]


class TestWatchCommandWithCondition:
    def test_condition_filters_observations(self):
        session_id = "test_cond"
        socket_path = f"/tmp/peeka_{session_id}.sock"
        ready_path = f"/tmp/peeka_{session_id}.ready"
        agent: Optional["PeekaAgent"] = None

        Path(socket_path).unlink(missing_ok=True)
        Path(ready_path).unlink(missing_ok=True)

        try:

            def sample_function(value):
                return value * 2

            test_module = type(sys)("test_cond_module")
            test_module.sample_function = sample_function
            sys.modules["test_cond_module"] = test_module

            from peeka.core.agent import PeekaAgent

            agent = PeekaAgent(session_id, attached_pid=None)
            agent.start()

            for _ in range(50):
                if Path(ready_path).exists():
                    break
                time.sleep(0.1)

            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(2.0)
                sock.connect(socket_path)

                start_cmd = {
                    "type": "watch",
                    "action": "start",
                    "pattern": "test_cond_module.sample_function",
                    "depth": 2,
                    "times": -1,
                    "condition": "params[0] > 50",
                }
                payload = json.dumps(start_cmd).encode("utf-8")
                sock.sendall(len(payload).to_bytes(4, "big"))
                sock.sendall(payload)

                response = _recv_json_response(sock)

                assert response["status"] == "success"
                watch_id = response["watch_id"]

                test_module.sample_function(10)
                test_module.sample_function(30)
                test_module.sample_function(100)
                test_module.sample_function(5)

                stats = agent.observer.get_watch_stats(watch_id)
                assert stats is not None
                assert stats["count"] == 1

        finally:
            if agent:
                agent.stop()
            Path(socket_path).unlink(missing_ok=True)
            Path(ready_path).unlink(missing_ok=True)
            if "test_cond_module" in sys.modules:
                del sys.modules["test_cond_module"]
