"""Reproducer for detach cleanup summary visibility.

The current CLI detach handler reports success even when the agent returns
cleanup summary errors.
"""

import json as _json
from typing import cast

import pytest

import peeka.cli.handlers.attach as attach_module
from peeka.cli.handlers.attach import cmd_detach  # pyright: ignore[reportUnknownVariableType]


class MockStreamingClient:
    def __init__(self, socket_path: str) -> None:
        self.socket_path: str = socket_path
        self.connected: bool = False
        self.disconnected: bool = False
        self.sent_commands: list[dict[str, object]] = []

    def connect(self) -> dict[str, object]:
        self.connected = True
        return {"status": "success"}

    def send_command(self, command: dict[str, object]) -> dict[str, object]:
        self.sent_commands.append(command)
        return {
            "status": "success",
            "cleanup_summary": {
                "step_errors": {"uninject_all": "owner foo failed"},
                "resource_owners": {
                    "errors": [
                        {"handler": "FooCommand", "error": "cleanup blew up"}
                    ]
                },
            },
        }

    def disconnect(self) -> None:
        self.disconnected = True


class TestDetachCleanupSummaryVisibility:
    def test_cmd_detach_reports_cleanup_summary_errors(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr(
            attach_module,
            "_check_agent_attached",
            lambda: ("/tmp/peeka_task_t3.sock", 4321),
        )
        monkeypatch.setattr(attach_module, "StreamingAgentClient", MockStreamingClient)

        result = cmd_detach(object())

        assert result == 2, (
            "detach should return a cleanup-error exit code when cleanup_summary "
            f"contains errors, got {result}"
        )

        captured = capsys.readouterr()
        warning_found = False
        for line in captured.out.splitlines():
            try:
                data = cast(dict[str, object], _json.loads(line))
                if data.get("type") == "warning" and data.get("command") == "detach":
                    warning_found = True
                    break
            except (ValueError, KeyError):
                continue
        assert warning_found, (
            "Expected a JSON warning line on stdout with type='warning' and command='detach', "
            f"got stdout: {captured.out!r}"
        )
