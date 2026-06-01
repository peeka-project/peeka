# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportPrivateUsage=false, reportPrivateLocalImportUsage=false, reportUnknownLambdaType=false, reportUnusedCallResult=false

import threading
import time
from typing import Any, Dict, Generator, List, Tuple

import pytest

from peeka.core import agent as agent_module
from peeka.core.agent import PeekaAgent
from peeka.core.client_sessions import ClientRegistry
from peeka.core.jobs import JobRegistry


@pytest.fixture(autouse=True)
def reset_registries(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Dict[str, Any], None, None]:
    job_registry = JobRegistry()
    client_registry = ClientRegistry()
    monkeypatch.setattr(agent_module, "job_registry", job_registry)
    monkeypatch.setattr(agent_module, "_client_registry", client_registry, raising=False)
    yield {"job_registry": job_registry, "client_registry": client_registry}
    agent_module._client_registry = None


def _new_agent(session_id: str) -> PeekaAgent:
    return PeekaAgent(session_id=session_id, attached_pid=12345)


class TestMutationLock:
    def test_mutation_lock_serializes_two_concurrent_resets(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _new_agent("test-mutation-serialize")
        handler = agent._get_handler("reset")
        assert handler is not None

        start_barrier = threading.Barrier(3)
        event_lock = threading.Lock()
        events: List[Tuple[str, float]] = []
        responses: List[Dict[str, Any]] = []

        def execute(_: Dict[str, Any]) -> Dict[str, Any]:
            with event_lock:
                events.append(("start", time.monotonic()))
            time.sleep(0.2)
            with event_lock:
                events.append(("end", time.monotonic()))
            return {"status": "success", "data": {"reset": True}}

        monkeypatch.setattr(handler, "execute", execute)

        def dispatch() -> None:
            _ = start_barrier.wait(timeout=5.0)
            responses.append(
                agent._execute_command({"type": "reset", "action": "all"})
            )

        threads = [threading.Thread(target=dispatch) for _ in range(2)]
        for thread in threads:
            thread.start()
        _ = start_barrier.wait(timeout=5.0)
        for thread in threads:
            thread.join(timeout=5.0)

        assert all(not thread.is_alive() for thread in threads)
        assert [event[0] for event in events] == ["start", "end", "start", "end"]
        assert events[2][1] >= events[1][1]
        assert len(responses) == 2
        assert all(response["status"] == "success" for response in responses)

    def test_mutation_lock_timeout_returns_job_already_running(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _new_agent("test-mutation-timeout")
        handler = agent._get_handler("reset")
        assert handler is not None

        entered_event = threading.Event()
        release_event = threading.Event()
        first_response: List[Dict[str, Any]] = []

        def execute(_: Dict[str, Any]) -> Dict[str, Any]:
            entered_event.set()
            release_event.wait(timeout=10.0)
            return {"status": "success", "data": {"reset": True}}

        monkeypatch.setattr(handler, "execute", execute)

        def run_first() -> None:
            first_response.append(
                agent._execute_command({"type": "reset", "action": "all"})
            )

        thread = threading.Thread(target=run_first)
        thread.start()
        assert entered_event.wait(timeout=5.0)
        assert len(agent_module.job_registry.list()) == 1

        second_result = agent._execute_command({"type": "reset", "action": "all"})

        assert second_result["status"] == "error"
        assert second_result["error_code"] == "JOB_ALREADY_RUNNING"
        assert second_result["message"] == "mutation in progress"
        assert len(agent_module.job_registry.list()) == 1

        release_event.set()
        thread.join(timeout=12.0)

        assert not thread.is_alive()
        assert first_response[0]["status"] == "success"

    def test_foreground_rule_blocks_second_command_same_client(
        self, monkeypatch: pytest.MonkeyPatch, reset_registries: Dict[str, Any]
    ) -> None:
        agent = _new_agent("test-foreground-block")
        client = reset_registries["client_registry"].create(
            agent._target_id_for_jobs(), "cli"
        )
        handler = agent._get_handler("trace")
        assert handler is not None

        entered_event = threading.Event()
        release_event = threading.Event()
        first_response: List[Dict[str, Any]] = []

        def execute(_: Dict[str, Any]) -> Dict[str, Any]:
            entered_event.set()
            release_event.wait(timeout=5.0)
            return {"status": "success", "data": {"trace": True}}

        monkeypatch.setattr(handler, "execute", execute)

        def run_first() -> None:
            first_response.append(
                agent._execute_command(
                    {
                        "type": "trace",
                        "action": "start",
                        "pattern": "module.func",
                        "client_session_id": client.client_session_id,
                    }
                )
            )

        thread = threading.Thread(target=run_first)
        thread.start()
        assert entered_event.wait(timeout=5.0)
        assert len(agent_module.job_registry.list()) == 1

        second_result = agent._execute_command(
            {
                "type": "trace",
                "action": "start",
                "pattern": "module.other",
                "client_session_id": client.client_session_id,
            }
        )

        assert second_result["status"] == "error"
        assert second_result["error_code"] == "JOB_ALREADY_RUNNING"
        assert len(agent_module.job_registry.list()) == 1

        release_event.set()
        thread.join(timeout=5.0)

        assert not thread.is_alive()
        assert first_response[0]["status"] == "success"

    def test_background_flag_bypasses_foreground_check(
        self, monkeypatch: pytest.MonkeyPatch, reset_registries: Dict[str, Any]
    ) -> None:
        agent = _new_agent("test-foreground-background")
        client = reset_registries["client_registry"].create(
            agent._target_id_for_jobs(), "cli"
        )
        trace_handler = agent._get_handler("trace")
        stack_handler = agent._get_handler("stack")
        assert trace_handler is not None
        assert stack_handler is not None

        entered_event = threading.Event()
        release_event = threading.Event()

        def trace_execute(_: Dict[str, Any]) -> Dict[str, Any]:
            entered_event.set()
            release_event.wait(timeout=5.0)
            return {"status": "success", "data": {"trace": True}}

        def stack_execute(_: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "success", "data": {"stack": True}}

        monkeypatch.setattr(trace_handler, "execute", trace_execute)
        monkeypatch.setattr(stack_handler, "execute", stack_execute)

        thread = threading.Thread(
            target=lambda: agent._execute_command(
                {
                    "type": "trace",
                    "action": "start",
                    "pattern": "module.func",
                    "client_session_id": client.client_session_id,
                }
            )
        )
        thread.start()
        assert entered_event.wait(timeout=5.0)

        second_result = agent._execute_command(
            {
                "type": "stack",
                "action": "capture",
                "pattern": "module.stack",
                "client_session_id": client.client_session_id,
                "background": True,
            }
        )

        assert second_result["status"] == "success"
        job = agent_module.job_registry.get(second_result["job_id"])
        assert job is not None
        assert job.foreground is False
        assert job.status == "completed"

        release_event.set()
        thread.join(timeout=5.0)
        assert not thread.is_alive()

    def test_snapshot_concurrent_command_not_blocked_by_foreground(
        self, monkeypatch: pytest.MonkeyPatch, reset_registries: Dict[str, Any]
    ) -> None:
        agent = _new_agent("test-foreground-snapshot")
        client = reset_registries["client_registry"].create(
            agent._target_id_for_jobs(), "cli"
        )
        trace_handler = agent._get_handler("trace")
        memory_handler = agent._get_handler("memory")
        assert trace_handler is not None
        assert memory_handler is not None

        entered_event = threading.Event()
        release_event = threading.Event()

        def trace_execute(_: Dict[str, Any]) -> Dict[str, Any]:
            entered_event.set()
            release_event.wait(timeout=5.0)
            return {"status": "success", "data": {"trace": True}}

        def memory_execute(_: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "success", "data": {"memory": True}}

        monkeypatch.setattr(trace_handler, "execute", trace_execute)
        monkeypatch.setattr(memory_handler, "execute", memory_execute)

        thread = threading.Thread(
            target=lambda: agent._execute_command(
                {
                    "type": "trace",
                    "action": "start",
                    "pattern": "module.func",
                    "client_session_id": client.client_session_id,
                }
            )
        )
        thread.start()
        assert entered_event.wait(timeout=5.0)

        result = agent._execute_command(
            {
                "type": "memory",
                "action": "overview",
                "client_session_id": client.client_session_id,
            }
        )

        assert result["status"] == "success"
        job = agent_module.job_registry.get(result["job_id"])
        assert job is not None
        assert job.status == "completed"

        release_event.set()
        thread.join(timeout=5.0)
        assert not thread.is_alive()

    def test_foreground_job_id_set_and_cleared(
        self, monkeypatch: pytest.MonkeyPatch, reset_registries: Dict[str, Any]
    ) -> None:
        agent = _new_agent("test-foreground-set-clear")
        client_registry = reset_registries["client_registry"]
        client = client_registry.create(agent._target_id_for_jobs(), "cli")
        handler = agent._get_handler("stack")
        assert handler is not None

        observed_job_ids: List[str] = []

        def execute(_: Dict[str, Any]) -> Dict[str, Any]:
            live_client = client_registry.get(client.client_session_id)
            assert live_client is not None
            observed_job_ids.append(str(live_client.foreground_job_id))
            return {"status": "success", "data": {"stack": True}}

        monkeypatch.setattr(handler, "execute", execute)

        result = agent._execute_command(
            {
                "type": "stack",
                "action": "capture",
                "pattern": "module.func",
                "client_session_id": client.client_session_id,
            }
        )

        refreshed_client = client_registry.get(client.client_session_id)
        assert result["status"] == "success"
        assert observed_job_ids == [result["job_id"]]
        assert refreshed_client is not None
        assert refreshed_client.foreground_job_id is None

    def test_streaming_probe_keeps_foreground_id_set(
        self, monkeypatch: pytest.MonkeyPatch, reset_registries: Dict[str, Any]
    ) -> None:
        agent = _new_agent("test-foreground-streaming")
        client_registry = reset_registries["client_registry"]
        client = client_registry.create(agent._target_id_for_jobs(), "cli")
        handler = agent._get_handler("trace")
        assert handler is not None

        monkeypatch.setattr(
            handler,
            "execute",
            lambda _: {"status": "success", "data": {"trace": True}},
        )

        result = agent._execute_command(
            {
                "type": "trace",
                "action": "start",
                "pattern": "module.func",
                "client_session_id": client.client_session_id,
            }
        )

        refreshed_client = client_registry.get(client.client_session_id)
        assert result["status"] == "success"
        assert refreshed_client is not None
        assert refreshed_client.foreground_job_id == result["job_id"]

    def test_empty_client_session_id_skips_foreground_rule(
        self, monkeypatch: pytest.MonkeyPatch, reset_registries: Dict[str, Any]
    ) -> None:
        agent = _new_agent("test-empty-client-session")
        client = reset_registries["client_registry"].create(
            agent._target_id_for_jobs(), "cli"
        )
        handler = agent._get_handler("trace")
        assert handler is not None

        entered_event = threading.Event()
        release_event = threading.Event()

        def execute(command: Dict[str, Any]) -> Dict[str, Any]:
            if command.get("client_session_id"):
                entered_event.set()
                release_event.wait(timeout=5.0)
            return {"status": "success", "data": {"trace": True}}

        monkeypatch.setattr(handler, "execute", execute)

        thread = threading.Thread(
            target=lambda: agent._execute_command(
                {
                    "type": "trace",
                    "action": "start",
                    "pattern": "module.func",
                    "client_session_id": client.client_session_id,
                }
            )
        )
        thread.start()
        assert entered_event.wait(timeout=5.0)

        result = agent._execute_command(
            {"type": "trace", "action": "start", "pattern": "module.free"}
        )

        assert result["status"] == "success"
        assert "error_code" not in result

        release_event.set()
        thread.join(timeout=5.0)
        assert not thread.is_alive()

    def test_mutation_lock_released_on_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _new_agent("test-mutation-exception")
        handler = agent._get_handler("reset")
        assert handler is not None

        calls = {"count": 0}

        def execute(_: Dict[str, Any]) -> Dict[str, Any]:
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("boom")
            return {"status": "success", "data": {"reset": True}}

        monkeypatch.setattr(handler, "execute", execute)

        first_result = agent._execute_command({"type": "reset", "action": "all"})
        second_result = agent._execute_command({"type": "reset", "action": "all"})

        assert first_result["status"] == "error"
        assert second_result["status"] == "success"
