import pytest

from peeka.core.agent import PeekaAgent


class FakeSnapshotHandler:
    category = "snapshot"
    allows_concurrent = False

    def __init__(self, agent: PeekaAgent) -> None:
        self.agent = agent

    def execute(self, command):
        return {"status": "success", "data": {"value": command.get("value", 0)}}


class FakeErrorHandler:
    category = "snapshot"
    allows_concurrent = False

    def __init__(self, agent: PeekaAgent) -> None:
        self.agent = agent

    def execute(self, command):
        return {
            "status": "error",
            "error_code": "COMMAND_ERROR",
            "message": "boom",
        }


@pytest.fixture(autouse=True)
def reset_registries():
    from peeka.core import agent

    agent._client_registry = None
    agent._consumer_registry = None
    yield
    agent._client_registry = None
    agent._consumer_registry = None


class TestConsumerIntegration:
    def test_job_execution_appends_to_target_scoped_consumer(self) -> None:
        agent = PeekaAgent(session_id="test-consumer-job", attached_pid=12345)
        agent.command_handlers["fakecmd"] = FakeSnapshotHandler(agent)

        create_consumer = agent._execute_command(
            {
                "type": "consumer",
                "action": "create",
                "target_id": "target_test-con",
                "source": "cli",
                "scope_type": "target",
                "scope_id": "target_test-con",
            }
        )
        assert create_consumer["status"] == "success"
        consumer_id = create_consumer["data"]["consumer_id"]

        result = agent._execute_command(
            {"type": "fakecmd", "action": "run", "value": 42}
        )
        assert result["status"] == "success"

        drained = agent._execute_command(
            {
                "type": "consumer",
                "action": "drain",
                "consumer_id": consumer_id,
                "limit": 10,
            }
        )
        assert drained["status"] == "success"
        records = drained["data"]["records"]
        assert len(records) == 1
        assert records[0]["source_type"] == "job"
        assert records[0]["payload"]["data"]["value"] == 42

    def test_job_error_appends_error_record(self) -> None:
        agent = PeekaAgent(session_id="test-consumer-joberr", attached_pid=12345)
        agent.command_handlers["fakeerr"] = FakeErrorHandler(agent)

        create_consumer = agent._execute_command(
            {
                "type": "consumer",
                "action": "create",
                "target_id": "target_test-con",
                "source": "cli",
                "scope_type": "target",
                "scope_id": "target_test-con",
            }
        )
        consumer_id = create_consumer["data"]["consumer_id"]

        result = agent._execute_command({"type": "fakeerr", "action": "run"})
        assert result["status"] == "error"

        drained = agent._execute_command(
            {
                "type": "consumer",
                "action": "drain",
                "consumer_id": consumer_id,
                "limit": 10,
            }
        )
        records = drained["data"]["records"]
        assert len(records) == 1
        assert records[0]["record_type"] == "error"
        assert records[0]["payload"]["message"] == "boom"

    def test_probe_event_appends_to_probe_scoped_consumer(self) -> None:
        agent = PeekaAgent(session_id="test-consumer-probe", attached_pid=12345)
        probe = agent.probe_registry.create(
            target_id="target_test-con",
            client_session_id="",
            job_id="job_1",
            type="watch",
            pattern="pkg.fn",
            config=None,
        )
        create_consumer = agent._execute_command(
            {
                "type": "consumer",
                "action": "create",
                "target_id": "target_test-con",
                "source": "cli",
                "scope_type": "probe",
                "scope_id": probe.id,
            }
        )
        consumer_id = create_consumer["data"]["consumer_id"]

        event = agent.probe_registry.record_event(probe.id, {"value": 7})
        assert event is not None

        drained = agent._execute_command(
            {
                "type": "consumer",
                "action": "drain",
                "consumer_id": consumer_id,
                "limit": 10,
            }
        )
        records = drained["data"]["records"]
        assert len(records) == 1
        assert records[0]["source_type"] == "probe"
        assert records[0]["payload"]["event_id"] == event.event_id


def test_script_namespace_uses_canonical_consumer_registry():
    from pathlib import Path
    from peeka.core import agent

    namespace = {"__name__": "injected_agent", "__file__": agent.__file__}
    exec(compile(Path(agent.__file__).read_text(), agent.__file__, "exec"), namespace)
    assert namespace["_get_consumer_registry"]() is agent._get_consumer_registry()


def test_recv_exact_handles_fragmented_header_and_eof():
    import socket
    from peeka.core.agent import _recv_exact

    left, right = socket.socketpair()
    try:
        left.sendall(b"ab")
        left.sendall(b"cd")
        assert _recv_exact(right, 4) == b"abcd"
        left.close()
        assert _recv_exact(right, 4) == b""
    finally:
        left.close()
        right.close()


def test_oversized_command_closes_connection():
    import socket
    import threading
    from peeka.core.agent import PeekaAgent, _MAX_COMMAND_FRAME_BYTES

    agent = PeekaAgent("frame-limit-test")
    left, right = socket.socketpair()
    thread = threading.Thread(target=agent._handle_client, args=(right, 1))
    thread.start()
    left.sendall((_MAX_COMMAND_FRAME_BYTES + 1).to_bytes(4, "big"))
    thread.join(2)
    try:
        assert not thread.is_alive()
        assert left.recv(1) == b""
    finally:
        left.close()
        agent.stop()


def test_stop_interrupts_blocked_client():
    import socket
    import threading
    import time
    from peeka.core.agent import PeekaAgent

    agent = PeekaAgent("socket-stop-test")
    left, right = socket.socketpair()
    thread = threading.Thread(target=agent._handle_client, args=(right, 1))
    thread.start()
    deadline = time.monotonic() + 2
    while not agent._snapshot_client_connections() and time.monotonic() < deadline:
        time.sleep(0.001)
    try:
        agent.stop()
        thread.join(2)
        assert not thread.is_alive()
        assert left.recv(1) == b""
    finally:
        left.close()
