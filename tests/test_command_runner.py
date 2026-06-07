import argparse
from typing import Any, Dict

import peeka.cli.connection as cli_connection
import peeka.cli.command_runner as command_runner_module
from peeka.cli.command_runner import run_command


class MockClient:
    def __init__(self, response: Dict[str, Any]) -> None:
        self._response = response
        self.last_command: Dict[str, Any] = {}
        self.disconnected = False

    def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        self.last_command = command
        return self._response

    def disconnect(self) -> None:
        self.disconnected = True


class TestRunCommandSuccess:
    def test_returns_zero_and_calls_render(self, monkeypatch) -> None:
        response = {"status": "success", "data": {"x": 1}}
        mock_client = MockClient(response)
        monkeypatch.setattr(
            command_runner_module,
            "_connect_streaming_agent",
            lambda cmd, tid, **kwargs: mock_client,
        )

        rendered = []
        args = argparse.Namespace(target="t1")

        rc = run_command(
            args,
            "test.cmd",
            build_command=lambda a: {"type": "test"},
            render_success=lambda a, r: rendered.append(r),
        )

        assert rc == 0
        assert rendered == [response]
        assert mock_client.disconnected is True

    def test_disconnect_called_even_on_send_error(self, monkeypatch) -> None:
        class BrokenClient:
            disconnected = False

            def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
                raise RuntimeError("socket lost")

            def disconnect(self) -> None:
                BrokenClient.disconnected = True

        monkeypatch.setattr(
            command_runner_module,
            "_connect_streaming_agent",
            lambda cmd, tid, **kwargs: BrokenClient(),
        )

        args = argparse.Namespace(target=None)
        try:
            run_command(
                args,
                "test.cmd",
                build_command=lambda a: {},
                render_success=lambda a, r: None,
            )
        except RuntimeError:
            pass

        assert BrokenClient.disconnected is True


class TestRunCommandConnectionFailure:
    def test_returns_one_when_connect_fails(self, monkeypatch) -> None:
        monkeypatch.setattr(
            command_runner_module,
            "_connect_streaming_agent",
            lambda cmd, tid, **kwargs: None,
        )

        build_called = []
        args = argparse.Namespace()

        rc = run_command(
            args,
            "test.cmd",
            build_command=lambda a: build_called.append(True) or {},
            render_success=lambda a, r: None,
        )

        assert rc == 1
        assert build_called == []

    def test_uses_getattr_target_from_args(self, monkeypatch) -> None:
        captured = []
        monkeypatch.setattr(
            command_runner_module,
            "_connect_streaming_agent",
            lambda cmd, tid, **kwargs: captured.append((cmd, tid, kwargs)) or None,
        )

        args = argparse.Namespace(target="my-target")
        run_command(
            args,
            "my.cmd",
            build_command=lambda a: {},
            render_success=lambda a, r: None,
        )

        assert captured == [
            ("my.cmd", "my-target", {"require_unambiguous_default": True})
        ]

    def test_target_defaults_to_none_when_absent(self, monkeypatch) -> None:
        captured = []
        monkeypatch.setattr(
            command_runner_module,
            "_connect_streaming_agent",
            lambda cmd, tid, **kwargs: captured.append((tid, kwargs)) or None,
        )

        args = argparse.Namespace()
        run_command(
            args,
            "my.cmd",
            build_command=lambda a: {},
            render_success=lambda a, r: None,
        )

        assert captured == [(None, {"require_unambiguous_default": False})]

    def test_target_none_requires_unambiguous_default_when_attr_present(
        self, monkeypatch
    ) -> None:
        captured = []
        monkeypatch.setattr(
            command_runner_module,
            "_connect_streaming_agent",
            lambda cmd, tid, **kwargs: captured.append((tid, kwargs)) or None,
        )

        args = argparse.Namespace(target=None)
        run_command(
            args,
            "my.cmd",
            build_command=lambda a: {},
            render_success=lambda a, r: None,
        )

        assert captured == [(None, {"require_unambiguous_default": True})]


class TestRunCommandError:
    def test_returns_one_on_error_response(self, monkeypatch, capsys) -> None:
        response = {
            "status": "error",
            "error_code": "SOME_ERROR",
            "message": "Something went wrong",
        }
        mock_client = MockClient(response)
        monkeypatch.setattr(
            command_runner_module,
            "_connect_streaming_agent",
            lambda cmd, tid, **kwargs: mock_client,
        )

        rendered = []
        args = argparse.Namespace(target=None)

        rc = run_command(
            args,
            "test.cmd",
            build_command=lambda a: {"type": "test"},
            render_success=lambda a, r: rendered.append(r),
        )

        assert rc == 1
        assert rendered == []
        assert mock_client.disconnected is True

    def test_uses_fallback_error_message(self, monkeypatch, capsys) -> None:
        response = {"status": "error"}
        mock_client = MockClient(response)
        monkeypatch.setattr(
            command_runner_module,
            "_connect_streaming_agent",
            lambda cmd, tid, **kwargs: mock_client,
        )

        args = argparse.Namespace(target=None)
        rc = run_command(
            args,
            "test.cmd",
            build_command=lambda a: {},
            render_success=lambda a, r: None,
            error_message="Custom fallback",
        )

        assert rc == 1
        out = capsys.readouterr().out
        assert "Custom fallback" in out


class TestRunCommandErrorExitCodeMapping:
    def test_returns_mapped_exit_code(self, monkeypatch) -> None:
        response = {
            "status": "error",
            "error_code": "UNSUPPORTED_CAPABILITY",
            "message": "Not supported",
        }
        mock_client = MockClient(response)
        monkeypatch.setattr(
            command_runner_module,
            "_connect_streaming_agent",
            lambda cmd, tid, **kwargs: mock_client,
        )

        args = argparse.Namespace(target=None)
        rc = run_command(
            args,
            "test.cmd",
            build_command=lambda a: {"type": "test"},
            render_success=lambda a, r: None,
            error_exit_codes={"UNSUPPORTED_CAPABILITY": 2},
        )

        assert rc == 2
        assert mock_client.disconnected is True

    def test_returns_one_for_unmapped_error_code(self, monkeypatch) -> None:
        response = {
            "status": "error",
            "error_code": "UNKNOWN_CODE",
            "message": "Oops",
        }
        mock_client = MockClient(response)
        monkeypatch.setattr(
            command_runner_module,
            "_connect_streaming_agent",
            lambda cmd, tid, **kwargs: mock_client,
        )

        args = argparse.Namespace(target=None)
        rc = run_command(
            args,
            "test.cmd",
            build_command=lambda a: {},
            render_success=lambda a, r: None,
            error_exit_codes={"SOME_OTHER_CODE": 3},
        )

        assert rc == 1


class TestTargetAwareConnection:
    def test_unambiguous_default_uses_single_alive_target(self, monkeypatch) -> None:
        class Target:
            target_id = "target_bbbbbbbb"
            socket_path = "/tmp/peeka_bbbbbbbb.sock"
            pid = 2222
            state = "alive"

        monkeypatch.setattr(cli_connection, "discover_targets", lambda: [Target()])
        monkeypatch.setattr(
            cli_connection.cli_sessions,
            "_check_agent_attached",
            lambda: (_ for _ in ()).throw(AssertionError("fallback not expected")),
        )

        socket_path, pid = cli_connection._check_agent_for_target(
            None,
            require_unambiguous_default=True,
        )

        assert socket_path == "/tmp/peeka_bbbbbbbb.sock"
        assert pid == 2222

    def test_unambiguous_default_rejects_multiple_alive_targets(
        self, monkeypatch
    ) -> None:
        class TargetA:
            target_id = "target_aaaaaaaa"
            socket_path = "/tmp/peeka_aaaaaaaa.sock"
            pid = 1111
            state = "alive"

        class TargetB:
            target_id = "target_bbbbbbbb"
            socket_path = "/tmp/peeka_bbbbbbbb.sock"
            pid = 2222
            state = "alive"

        monkeypatch.setattr(
            cli_connection,
            "discover_targets",
            lambda: [TargetA(), TargetB()],
        )

        try:
            cli_connection._check_agent_for_target(
                None,
                require_unambiguous_default=True,
            )
            assert False, "Expected TargetResolutionError"
        except cli_connection.TargetResolutionError as exc:
            assert exc.error_code == "TARGET_AMBIGUOUS"
            assert "target_aaaaaaaa" in str(exc)
            assert "target_bbbbbbbb" in str(exc)
