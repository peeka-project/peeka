# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

from typing import Any, Dict, Generator

import pytest

from peeka.core import agent as agent_module
from peeka.core.agent import PeekaAgent
from peeka.core.jobs import JobRegistry


@pytest.fixture(autouse=True)
def reset_dispatcher_registries(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[JobRegistry, None, None]:
    from peeka.core import agent

    registry = JobRegistry()
    monkeypatch.setattr(agent, "job_registry", registry)
    agent._client_registry = None
    yield registry
    agent._client_registry = None


class TestDispatcherJobs:
    def test_snapshot_command_response_has_job_id_and_completed_status(self) -> None:
        agent = PeekaAgent(session_id="test-dispatch-memory", attached_pid=12345)

        result = agent._execute_command({"type": "memory", "action": "overview"})

        assert result["status"] == "success"
        assert "job_id" in result
        job = agent_module.job_registry.get(result["job_id"])
        assert job is not None
        assert job.status == "completed"
        assert job.result_summary

    def test_probe_command_transitions_to_streaming(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = PeekaAgent(session_id="test-dispatch-trace", attached_pid=12345)
        handler = agent._get_handler("trace")
        assert handler is not None

        def succeed(command: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "success", "data": {"x": 1}}

        monkeypatch.setattr(handler, "execute", succeed)

        result = agent._execute_command(
            {"type": "trace", "action": "start", "pattern": "some.func"}
        )

        assert result["status"] == "success"
        job = agent_module.job_registry.get(result["job_id"])
        assert job is not None
        assert job.status == "streaming"
        assert job.result_summary == {"x": 1}

    def test_probe_stop_action_completes_job_and_clears_foreground(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = PeekaAgent(session_id="test-dispatch-trace-stop", attached_pid=12345)
        client_registry = agent_module._get_client_registry()
        client = client_registry.create(agent._target_id_for_jobs(), "cli")
        handler = agent._get_handler("trace")
        assert handler is not None

        def succeed(command: Dict[str, Any]) -> Dict[str, Any]:
            assert command["action"] == "stop"
            return {"status": "success", "watch_id": "trace_123"}

        monkeypatch.setattr(handler, "execute", succeed)

        result = agent._execute_command(
            {
                "type": "trace",
                "action": "stop",
                "watch_id": "trace_123",
                "client_session_id": client.client_session_id,
            }
        )

        refreshed_client = client_registry.get(client.client_session_id)
        job = agent_module.job_registry.get(result["job_id"])
        assert result["status"] == "success"
        assert job is not None
        assert job.status == "completed"
        assert refreshed_client is not None
        assert refreshed_client.foreground_job_id is None

    def test_failed_command_records_last_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = PeekaAgent(session_id="test-dispatch-fail", attached_pid=12345)
        handler = agent._get_handler("memory")
        assert handler is not None

        def raise_boom(command: Dict[str, Any]) -> Dict[str, Any]:
            raise RuntimeError("boom")

        monkeypatch.setattr(handler, "execute", raise_boom)

        result = agent._execute_command({"type": "memory", "action": "overview"})

        assert result["status"] == "error"
        assert "job_id" in result
        job = agent_module.job_registry.get(result["job_id"])
        assert job is not None
        assert job.status == "failed"
        assert job.last_error == {"code": "COMMAND_EXECUTION_ERROR", "message": "boom"}

    def test_command_failure_response_shape_unchanged(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = PeekaAgent(session_id="test-dispatch-shape", attached_pid=12345)
        handler = agent._get_handler("memory")
        assert handler is not None

        def raise_boom(command: Dict[str, Any]) -> Dict[str, Any]:
            raise RuntimeError("boom")

        monkeypatch.setattr(handler, "execute", raise_boom)

        result = agent._execute_command({"type": "memory", "action": "overview"})

        assert result["status"] == "error"
        assert result["error"] == "boom"
        assert "traceback" in result

    def test_handler_returned_error_marks_job_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = PeekaAgent(session_id="test-dispatch-handler-error", attached_pid=12345)
        handler = agent._get_handler("memory")
        assert handler is not None

        def return_error(_: Dict[str, Any]) -> Dict[str, Any]:
            return {
                "status": "error",
                "error_code": "BAD_INPUT",
                "message": "oops",
            }

        monkeypatch.setattr(handler, "execute", return_error)

        result = agent._execute_command({"type": "memory", "action": "overview"})

        assert result["status"] == "error"
        assert result["error_code"] == "BAD_INPUT"
        assert result["message"] == "oops"
        assert "job_id" in result

        job = agent_module.job_registry.get(result["job_id"])
        assert job is not None
        assert job.status == "failed"
        assert job.last_error == {"code": "BAD_INPUT", "message": "oops"}

    def test_unknown_command_type_no_job_created(self) -> None:
        agent = PeekaAgent(session_id="test-dispatch-unknown", attached_pid=12345)

        before_count = len(agent_module.job_registry.list())
        result = agent._execute_command({"type": "nonsense"})

        assert result["status"] == "error"
        assert result["error_code"] == "COMMAND_NOT_FOUND"
        assert "Unknown command type: nonsense" in result["message"]
        assert "COMMAND_NOT_FOUND" in result["error"]
        assert "job_id" not in result
        assert len(agent_module.job_registry.list()) == before_count

    def test_unknown_command_type_returns_command_not_found_envelope(self) -> None:
        agent = PeekaAgent(session_id="test-dispatch-cmd-not-found", attached_pid=12345)

        result = agent._execute_command({"type": "nonsense"})

        assert result["status"] == "error"
        assert result["error_code"] == "COMMAND_NOT_FOUND"
        assert "message" in result
        assert "error" in result
        assert "Unknown command type" in result["message"]

    def test_client_namespace_not_wrapped(self) -> None:
        agent = PeekaAgent(session_id="test-dispatch-client", attached_pid=12345)

        result = agent._execute_command({"type": "client", "action": "list"})

        assert result["status"] == "success"
        assert "job_id" not in result

    def test_target_namespace_not_wrapped(self) -> None:
        agent = PeekaAgent(session_id="test-dispatch-target", attached_pid=12345)

        result = agent._execute_command({"type": "target", "action": "hello"})

        assert result["status"] == "success"
        assert "job_id" not in result

    def test_background_flag_sets_foreground_false(self) -> None:
        agent = PeekaAgent(session_id="test-dispatch-background", attached_pid=12345)

        result = agent._execute_command(
            {"type": "memory", "action": "overview", "background": True}
        )

        job = agent_module.job_registry.get(result["job_id"])
        assert job is not None
        assert job.foreground is False

    def test_params_snapshot_excludes_control_fields(self) -> None:
        agent = PeekaAgent(session_id="test-dispatch-params", attached_pid=12345)

        result = agent._execute_command(
            {
                "type": "memory",
                "action": "overview",
                "client_session_id": "client_xxx",
                "background": True,
            }
        )

        job = agent_module.job_registry.get(result["job_id"])
        assert job is not None
        assert "client_session_id" not in job.params
        assert "background" not in job.params
        assert "action" not in job.params
        assert "type" not in job.params
