import argparse
import importlib

import pytest

from peeka.cli._client_helper import ephemeral_client


cli_main = importlib.import_module("peeka.cli.main")


class MockAgentClient:
    def __init__(self):
        self.commands_sent = []

    def send_command(self, command):
        self.commands_sent.append(command)
        if command.get("action") == "create":
            return {
                "status": "success",
                "data": {
                    "client_session_id": "client_12345678",
                    "target_id": command.get("target_id"),
                    "source": command.get("source"),
                },
            }
        if command.get("action") == "close":
            return {"status": "success", "data": {"closed": True}}
        return {"status": "error", "error_code": "TRANSPORT_ERROR", "message": "Unknown action"}


class TestEphemeralClient:
    def test_ephemeral_client_creates_and_closes(self):
        target_id = "target_abcdef12"
        mock_agent = MockAgentClient()

        with ephemeral_client(target_id, agent_client=mock_agent) as cid:
            assert cid == "client_12345678"

        assert len(mock_agent.commands_sent) == 2
        create_cmd = mock_agent.commands_sent[0]
        assert create_cmd["type"] == "client"
        assert create_cmd["action"] == "create"
        assert create_cmd["target_id"] == target_id
        assert create_cmd["source"] == "cli"

        close_cmd = mock_agent.commands_sent[1]
        assert close_cmd["type"] == "client"
        assert close_cmd["action"] == "close"
        assert close_cmd["client_session_id"] == "client_12345678"

    def test_ephemeral_client_creates_owned_streaming_client_when_missing(self, monkeypatch):
        class MockTarget:
            socket_path = "/tmp/peeka_owned.sock"

        class MockStreamingAgentClient:
            def __init__(self, socket_path):
                self.socket_path = socket_path
                self.commands_sent = []
                self.disconnected = False

            def connect(self):
                return {"status": "success"}

            def send_command(self, command):
                self.commands_sent.append(command)
                if command["action"] == "create":
                    return {"status": "success", "data": {"client_session_id": "client_owned"}}
                return {"status": "success", "data": {"closed": True}}

            def disconnect(self):
                self.disconnected = True

        created_clients = []

        def build_client(socket_path):
            client = MockStreamingAgentClient(socket_path)
            created_clients.append(client)
            return client

        monkeypatch.setattr("peeka.cli._client_helper.get_target", lambda target_id: MockTarget())
        monkeypatch.setattr("peeka.cli._client_helper.StreamingAgentClient", build_client)

        with ephemeral_client("target_abcdef12") as cid:
            assert cid == "client_owned"

        assert len(created_clients) == 1
        client = created_clients[0]
        assert client.socket_path == "/tmp/peeka_owned.sock"
        assert client.commands_sent[0]["action"] == "create"
        assert client.commands_sent[1]["action"] == "close"
        assert client.disconnected is True

    def test_ephemeral_client_closes_on_exception(self):
        target_id = "target_abcdef12"
        mock_agent = MockAgentClient()

        with pytest.raises(RuntimeError, match="Test exception"):
            with ephemeral_client(target_id, agent_client=mock_agent) as cid:
                assert cid == "client_12345678"
                raise RuntimeError("Test exception")

        assert len(mock_agent.commands_sent) == 2
        assert mock_agent.commands_sent[1]["action"] == "close"

    def test_ephemeral_client_closes_on_keyboard_interrupt(self):
        target_id = "target_abcdef12"
        mock_agent = MockAgentClient()

        with pytest.raises(KeyboardInterrupt):
            with ephemeral_client(target_id, agent_client=mock_agent) as cid:
                assert cid == "client_12345678"
                raise KeyboardInterrupt

        assert len(mock_agent.commands_sent) == 2
        assert mock_agent.commands_sent[1]["action"] == "close"


class TestEphemeralClientErrorHandling:
    def test_create_failure_raises(self):
        class FailingAgentClient:
            def send_command(self, command):
                if command.get("action") == "create":
                    return {
                        "status": "error",
                        "error_code": "COMMAND_EXECUTION_ERROR",
                        "message": "Target not found",
                    }

        with pytest.raises(RuntimeError, match="COMMAND_EXECUTION_ERROR"):
            with ephemeral_client("target_abcdef12", agent_client=FailingAgentClient()):
                pass

    def test_close_failure_is_swallowed(self, capsys):
        class CloseFailingAgentClient:
            def __init__(self):
                self.commands_sent = []

            def send_command(self, command):
                self.commands_sent.append(command)
                if command.get("action") == "create":
                    return {
                        "status": "success",
                        "data": {"client_session_id": "client_12345678"},
                    }
                raise ConnectionError("Socket closed")

        failing_agent = CloseFailingAgentClient()

        with ephemeral_client("target_abcdef12", agent_client=failing_agent) as cid:
            assert cid == "client_12345678"

        captured = capsys.readouterr()
        assert "Failed to close ephemeral client" in captured.err
        assert len(failing_agent.commands_sent) == 2

    def test_missing_client_session_id_raises(self):
        class MissingIdAgentClient:
            def send_command(self, command):
                if command.get("action") == "create":
                    return {"status": "success", "data": {}}
                return {"status": "success", "data": {"closed": True}}

        with pytest.raises(RuntimeError, match="No client_session_id"):
            with ephemeral_client("target_abcdef12", agent_client=MissingIdAgentClient()):
                pass


class MockStreamingClient:
    def __init__(self, socket_path):
        self.socket_path = socket_path
        self.connected = False
        self.commands_sent = []

    def connect(self):
        self.connected = True
        return {"status": "success"}

    def send_command(self, command):
        self.commands_sent.append(command)
        if command.get("type") == "watch" and command.get("action") == "start":
            return {
                "status": "success",
                "watch_id": "watch_12345",
                "target": {"pid": 9999},
            }
        if command.get("type") == "trace" and command.get("action") == "start":
            return {
                "status": "success",
                "watch_id": "trace_12345",
                "target": {"pid": 9999},
            }
        return {"status": "success"}

    def stream_observations(self):
        return iter([])

    def disconnect(self):
        self.connected = False


class TestWatchTraceClientPropagation:
    def test_cmd_watch_uses_ephemeral_client_session_id(self, monkeypatch):
        streaming_clients = []

        def build_streaming_client(socket_path):
            client = MockStreamingClient(socket_path)
            streaming_clients.append(client)
            return client

        class MockContext:
            def __enter__(self):
                return "client_ephemeral"

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        monkeypatch.setattr(cli_main, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))
        monkeypatch.setattr(cli_main, "StreamingAgentClient", build_streaming_client)
        monkeypatch.setattr(cli_main, "ephemeral_client", lambda target_id: MockContext())

        args = argparse.Namespace(
            pattern="module.fn",
            depth=2,
            times=1,
            before=False,
            exception=False,
            success=False,
            finish=True,
            condition_express=None,
            client=None,
        )

        assert cli_main.cmd_watch(args) == 0
        assert streaming_clients[0].commands_sent[0]["client_session_id"] == "client_ephemeral"

    def test_cmd_watch_uses_explicit_client_session_id(self, monkeypatch):
        streaming_clients = []

        def build_streaming_client(socket_path):
            client = MockStreamingClient(socket_path)
            streaming_clients.append(client)
            return client

        monkeypatch.setattr(cli_main, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))
        monkeypatch.setattr(cli_main, "StreamingAgentClient", build_streaming_client)

        args = argparse.Namespace(
            pattern="module.fn",
            depth=2,
            times=1,
            before=False,
            exception=False,
            success=False,
            finish=True,
            condition_express=None,
            client="client_existing",
        )

        assert cli_main.cmd_watch(args) == 0
        assert streaming_clients[0].commands_sent[0]["client_session_id"] == "client_existing"

    def test_cmd_trace_uses_ephemeral_client_session_id(self, monkeypatch):
        streaming_clients = []

        def build_streaming_client(socket_path):
            client = MockStreamingClient(socket_path)
            streaming_clients.append(client)
            return client

        class MockContext:
            def __enter__(self):
                return "client_trace_ephemeral"

            def __exit__(self, exc_type, exc_val, exc_tb):
                return False

        monkeypatch.setattr(cli_main, "_check_agent_attached", lambda: ("/tmp/peeka_test.sock", 1234))
        monkeypatch.setattr(cli_main, "StreamingAgentClient", build_streaming_client)
        monkeypatch.setattr(cli_main, "ephemeral_client", lambda target_id: MockContext())

        args = argparse.Namespace(
            pattern="module.fn",
            depth=3,
            times=1,
            condition_express=None,
            skip_builtin=True,
            min_duration=0,
            client=None,
        )

        assert cli_main.cmd_trace(args) == 0
        assert streaming_clients[0].commands_sent[0]["client_session_id"] == "client_trace_ephemeral"
