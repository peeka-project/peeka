"""Reproducer for detach marker cleanup on remote error."""

import tempfile
import uuid
from pathlib import Path
from typing import Callable, cast

import pytest

from peeka.cli.handlers import attach


class MockStreamingClient:
    socket_path: str
    connected: bool
    disconnected: bool
    sent_commands: list[dict[str, object]]

    def __init__(self, socket_path: str) -> None:
        self.socket_path = socket_path
        self.connected = False
        self.disconnected = False
        self.sent_commands = []

    def connect(self) -> dict[str, object]:
        self.connected = True
        return {"status": "success"}

    def send_command(self, command: dict[str, object]) -> dict[str, object]:
        self.sent_commands.append(command)
        return {"status": "error", "message": "detach failed"}

    def disconnect(self) -> None:
        self.disconnected = True


@pytest.mark.unit
class TestDetachMarkerPreservation:
    def test_markers_survive_detach_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with tempfile.TemporaryDirectory(prefix="peeka-detach-marker-") as tmpdir:
            tmp_path = Path(tmpdir)
            session_id = f"marker_{uuid.uuid4().hex}"
            socket_path = tmp_path / f"peeka_{session_id}.sock"
            pid_file = Path(tempfile.gettempdir()) / f"peeka_{session_id}.pid"
            ready_file = Path(tempfile.gettempdir()) / f"peeka_{session_id}.ready"

            _ = socket_path.write_text("")
            _ = pid_file.write_text("12345")
            _ = ready_file.write_text("ready")

            mock_client = MockStreamingClient(str(socket_path))
            def _check_agent_attached() -> tuple[str, int]:
                return str(socket_path), 12345

            def _build_mock_streaming_client(path: str) -> MockStreamingClient:
                _ = path
                return mock_client

            monkeypatch.setattr(attach, "_check_agent_attached", _check_agent_attached)
            monkeypatch.setattr(attach, "StreamingAgentClient", _build_mock_streaming_client)

            run_detach = cast(Callable[[object], int], attach.cmd_detach)
            result = run_detach(object())

            assert result == 1
            assert pid_file.exists(), "pid marker must survive a failed detach"
            assert ready_file.exists(), "ready marker must survive a failed detach"
            assert socket_path.exists(), "socket marker must survive a failed detach"
