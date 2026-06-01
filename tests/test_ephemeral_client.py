import pytest

from peeka.cli._client_helper import ephemeral_client


class MockAgentClient:
    def __init__(self):
        self.commands_sent = []

    def send_command(self, command):
        self.commands_sent.append(command)
        if command.get("action") == "create":
            return {
                "ok": True,
                "data": {
                    "client_session_id": "client_12345678",
                    "target_id": command.get("target_id"),
                    "source": command.get("source"),
                },
            }
        elif command.get("action") == "close":
            return {"ok": True, "data": {"closed": True}}
        else:
            return {"ok": False, "error_code": "UNKNOWN", "message": "Unknown action"}


class TestEphemeralClient:
    def test_ephemeral_client_creates_and_closes(self):
        target_id = "target_abcdef12"
        mock_agent = MockAgentClient()

        with ephemeral_client(target_id, mock_agent) as cid:
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

    def test_ephemeral_client_closes_on_exception(self):
        target_id = "target_abcdef12"
        mock_agent = MockAgentClient()

        with pytest.raises(RuntimeError, match="Test exception"):
            with ephemeral_client(target_id, mock_agent) as cid:
                assert cid == "client_12345678"
                raise RuntimeError("Test exception")

        assert len(mock_agent.commands_sent) == 2
        close_cmd = mock_agent.commands_sent[1]
        assert close_cmd["action"] == "close"

    def test_ephemeral_client_closes_on_keyboard_interrupt(self, monkeypatch):
        target_id = "target_abcdef12"
        mock_agent = MockAgentClient()

        with pytest.raises(KeyboardInterrupt):
            with ephemeral_client(target_id, mock_agent) as cid:
                assert cid == "client_12345678"
                raise KeyboardInterrupt

        assert len(mock_agent.commands_sent) == 2
        close_cmd = mock_agent.commands_sent[1]
        assert close_cmd["action"] == "close"


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
        return {"status": "success"}

    def stream_observations(self):
        return iter([])

    def disconnect(self):
        self.connected = False


class TestCmdWatchEphemeralIntegration:
    def test_cmd_watch_uses_ephemeral_when_no_client_flag(self, monkeypatch):
        ephemeral_calls = []

        def mock_ephemeral_client(target_id, agent_client):
            class MockContext:
                def __enter__(self):
                    ephemeral_calls.append(("enter", target_id))
                    return "client_ephemeral"

                def __exit__(self, exc_type, exc_val, exc_tb):
                    ephemeral_calls.append(("exit", target_id))

            return MockContext()

        monkeypatch.setattr(
            "peeka.cli._client_helper.ephemeral_client", mock_ephemeral_client
        )

        assert len(ephemeral_calls) == 0

    def test_cmd_watch_skips_ephemeral_when_client_flag_provided(self, monkeypatch):
        ephemeral_calls = []

        def mock_ephemeral_client(target_id, agent_client):
            ephemeral_calls.append(("enter", target_id))
            raise RuntimeError("Should not be called when --client is provided")

        monkeypatch.setattr(
            "peeka.cli._client_helper.ephemeral_client", mock_ephemeral_client
        )

        assert len(ephemeral_calls) == 0


class TestEphemeralClientErrorHandling:
    def test_create_failure_raises(self):
        target_id = "target_abcdef12"

        class FailingAgentClient:
            def send_command(self, command):
                if command.get("action") == "create":
                    return {
                        "ok": False,
                        "error_code": "TARGET_NOT_FOUND",
                        "message": "Target not found",
                    }

        failing_agent = FailingAgentClient()

        with pytest.raises(RuntimeError, match="TARGET_NOT_FOUND"):
            with ephemeral_client(target_id, failing_agent):
                pass

    def test_close_failure_is_swallowed(self, monkeypatch, capsys):
        target_id = "target_abcdef12"

        class CloseFailingAgentClient:
            def __init__(self):
                self.commands_sent = []

            def send_command(self, command):
                self.commands_sent.append(command)
                if command.get("action") == "create":
                    return {
                        "ok": True,
                        "data": {"client_session_id": "client_12345678"},
                    }
                elif command.get("action") == "close":
                    raise ConnectionError("Socket closed")

        failing_agent = CloseFailingAgentClient()

        with ephemeral_client(target_id, failing_agent) as cid:
            assert cid == "client_12345678"

        captured = capsys.readouterr()
        assert "Failed to close ephemeral client" in captured.err
        assert len(failing_agent.commands_sent) == 2

    def test_missing_client_session_id_raises(self):
        target_id = "target_abcdef12"

        class MissingIdAgentClient:
            def send_command(self, command):
                if command.get("action") == "create":
                    return {"ok": True, "data": {}}

        missing_id_agent = MissingIdAgentClient()

        with pytest.raises(RuntimeError, match="No client_session_id"):
            with ephemeral_client(target_id, missing_id_agent):
                pass
