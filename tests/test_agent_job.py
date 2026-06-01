# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

from typing import Any, Dict, Generator

import pytest

from peeka.core import agent as agent_module
from peeka.core.agent import PeekaAgent
from peeka.core.client_sessions import ClientRegistry
from peeka.core.jobs import JobRegistry


@pytest.fixture(autouse=True)
def reset_agent_job_registries(
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


class TestAgentJobEndpoints:
    def test_job_list_no_jobs_returns_empty(self) -> None:
        agent = _new_agent("test-job-list-empty")

        result = agent._execute_command({"type": "job", "action": "list"})

        assert result["status"] == "success"
        assert result["data"]["jobs"] == []

    def test_job_list_returns_all_jobs_after_dispatches(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _new_agent("test-job-list-all")
        handler = agent._get_handler("memory")
        assert handler is not None

        def succeed(_: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "success", "data": {"overview": {}}}

        monkeypatch.setattr(handler, "execute", succeed)

        result1 = agent._execute_command({"type": "memory", "action": "overview"})
        result2 = agent._execute_command({"type": "memory", "action": "overview"})

        assert result1["status"] == "success"
        assert result2["status"] == "success"

        result = agent._execute_command({"type": "job", "action": "list"})

        assert result["status"] == "success"
        jobs = result["data"]["jobs"]
        assert len(jobs) == 2
        assert jobs[0]["id"] == result1["job_id"]
        assert jobs[1]["id"] == result2["job_id"]

    def test_job_list_filters_by_target_client_status(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _new_agent("test-job-list-filters")
        target_id = agent._target_id_for_jobs()
        handler = agent._get_handler("memory")
        assert handler is not None

        def succeed(_: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "success", "data": {"overview": {}}}

        monkeypatch.setattr(handler, "execute", succeed)

        result1 = agent._execute_command(
            {
                "type": "memory",
                "action": "overview",
                "client_session_id": "client_a",
            }
        )
        result2 = agent._execute_command(
            {
                "type": "memory",
                "action": "overview",
                "client_session_id": "client_b",
            }
        )

        assert result1["status"] == "success"
        assert result2["status"] == "success"

        result = agent._execute_command(
            {
                "type": "job",
                "action": "list",
                "target_id": target_id,
            }
        )
        assert result["status"] == "success"
        assert len(result["data"]["jobs"]) == 2

        result = agent._execute_command(
            {
                "type": "job",
                "action": "list",
                "client_session_id": "client_a",
            }
        )
        assert result["status"] == "success"
        jobs = result["data"]["jobs"]
        assert len(jobs) == 1
        assert jobs[0]["id"] == result1["job_id"]

        result = agent._execute_command(
            {
                "type": "job",
                "action": "list",
                "status": "completed",
            }
        )
        assert result["status"] == "success"
        assert len(result["data"]["jobs"]) == 2

    def test_job_status_missing_job_id_returns_error(self) -> None:
        agent = _new_agent("test-job-status-missing")

        result = agent._execute_command({"type": "job", "action": "status"})

        assert result["status"] == "error"
        assert result["error_code"] == "JOB_NOT_FOUND"
        assert "required" in result["message"]

    def test_job_status_unknown_job_returns_not_found(self) -> None:
        agent = _new_agent("test-job-status-unknown")

        result = agent._execute_command(
            {"type": "job", "action": "status", "job_id": "job_nonexistent"}
        )

        assert result["status"] == "error"
        assert result["error_code"] == "JOB_NOT_FOUND"
        assert "not found" in result["message"]

    def test_job_status_returns_summary_keys(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _new_agent("test-job-status-summary")
        handler = agent._get_handler("memory")
        assert handler is not None

        def succeed(_: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "success", "data": {"overview": {}}}

        monkeypatch.setattr(handler, "execute", succeed)

        dispatch_result = agent._execute_command({"type": "memory", "action": "overview"})
        job_id = dispatch_result["job_id"]

        result = agent._execute_command(
            {"type": "job", "action": "status", "job_id": job_id}
        )

        assert result["status"] == "success"
        job = result["data"]["job"]
        assert job["id"] == job_id
        assert job["status"] == "completed"
        assert job["category"] == "snapshot"
        assert "updated_at" in job
        assert "completed_at" in job
        assert job["last_error"] is None

    def test_job_inspect_returns_full_dict_including_params_and_result_summary(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _new_agent("test-job-inspect-full")
        handler = agent._get_handler("memory")
        assert handler is not None

        def succeed(_: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "success", "data": {"overview": {"heap": 1024}}}

        monkeypatch.setattr(handler, "execute", succeed)

        dispatch_result = agent._execute_command({"type": "memory", "action": "overview"})
        job_id = dispatch_result["job_id"]

        result = agent._execute_command(
            {"type": "job", "action": "inspect", "job_id": job_id}
        )

        assert result["status"] == "success"
        job = result["data"]["job"]
        assert job["id"] == job_id
        assert job["schema_version"] == "1"
        assert job["command_type"] == "memory"
        assert job["action"] == "overview"
        assert job["params"] == {}
        assert job["result_summary"] == {"overview": {"heap": 1024}}

    def test_job_interrupt_unknown_returns_not_found(self) -> None:
        agent = _new_agent("test-job-interrupt-unknown")

        result = agent._execute_command(
            {"type": "job", "action": "interrupt", "job_id": "job_nonexistent"}
        )

        assert result["status"] == "error"
        assert result["error_code"] == "JOB_NOT_FOUND"

    def test_job_interrupt_terminal_returns_unsupported(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _new_agent("test-job-interrupt-terminal")
        handler = agent._get_handler("memory")
        assert handler is not None

        def succeed(_: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "success", "data": {"overview": {}}}

        monkeypatch.setattr(handler, "execute", succeed)

        dispatch_result = agent._execute_command({"type": "memory", "action": "overview"})
        job_id = dispatch_result["job_id"]

        result = agent._execute_command(
            {"type": "job", "action": "interrupt", "job_id": job_id}
        )

        assert result["status"] == "error"
        assert result["error_code"] == "UNSUPPORTED_CAPABILITY"
        assert "terminal state" in result["message"]

    def test_job_interrupt_probe_transitions_to_interrupted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _new_agent("test-job-interrupt-probe")
        handler = agent._get_handler("trace")
        assert handler is not None

        def succeed(_: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "success", "data": {"trace_id": "trace_123"}}

        monkeypatch.setattr(handler, "execute", succeed)

        dispatch_result = agent._execute_command(
            {"type": "trace", "action": "start", "pattern": "some.func"}
        )
        job_id = dispatch_result["job_id"]
        job = agent_module.job_registry.get(job_id)
        assert job is not None
        assert job.status == "streaming"

        result = agent._execute_command(
            {"type": "job", "action": "interrupt", "job_id": job_id}
        )

        assert result["status"] == "success"
        assert result["data"]["job_id"] == job_id
        assert result["data"]["status"] == "interrupted"

        job = agent_module.job_registry.get(job_id)
        assert job is not None
        assert job.status == "interrupted"

    def test_job_interrupt_snapshot_returns_unsupported(self) -> None:
        agent = _new_agent("test-job-interrupt-snapshot")

        job = agent_module.job_registry.create(
            target_id=agent._target_id_for_jobs(),
            client_session_id="client_test",
            command_type="memory",
            action="overview",
            category="snapshot",
        )
        agent_module.job_registry.set_status(job.id, "running")

        result = agent._execute_command(
            {"type": "job", "action": "interrupt", "job_id": job.id}
        )

        assert result["status"] == "error"
        assert result["error_code"] == "UNSUPPORTED_CAPABILITY"
        assert "snapshot" in result["message"]

    def test_job_interrupt_mutation_returns_unsupported(self) -> None:
        agent = _new_agent("test-job-interrupt-mutation")

        job = agent_module.job_registry.create(
            target_id=agent._target_id_for_jobs(),
            client_session_id="client_test",
            command_type="reset",
            action="all",
            category="mutation",
        )
        agent_module.job_registry.set_status(job.id, "running")

        result = agent._execute_command(
            {"type": "job", "action": "interrupt", "job_id": job.id}
        )

        assert result["status"] == "error"
        assert result["error_code"] == "UNSUPPORTED_CAPABILITY"
        assert "mutation" in result["message"]

    def test_job_interrupt_clears_client_foreground_job_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        agent = _new_agent("test-job-interrupt-clears-fg")
        client_registry = agent_module._client_registry
        assert client_registry is not None

        client = client_registry.create(
            target_id=agent._target_id_for_jobs(),
            source="cli",
            user_id=None,
        )
        client_session_id = client.client_session_id

        handler = agent._get_handler("trace")
        assert handler is not None

        def succeed(_: Dict[str, Any]) -> Dict[str, Any]:
            return {"status": "success", "data": {"trace_id": "trace_123"}}

        monkeypatch.setattr(handler, "execute", succeed)

        dispatch_result = agent._execute_command(
            {
                "type": "trace",
                "action": "start",
                "pattern": "some.func",
                "client_session_id": client_session_id,
            }
        )
        job_id = dispatch_result["job_id"]

        updated_client = client_registry.get(client_session_id)
        assert updated_client is not None
        assert updated_client.foreground_job_id == job_id

        result = agent._execute_command(
            {"type": "job", "action": "interrupt", "job_id": job_id}
        )

        assert result["status"] == "success"

        updated_client = client_registry.get(client_session_id)
        assert updated_client is not None
        assert updated_client.foreground_job_id is None

    def test_job_cleanup_removes_only_old_terminal_jobs(self) -> None:
        import time
        agent = _new_agent("test-job-cleanup-old")

        now = time.time()

        job1 = agent_module.job_registry.create(
            target_id=agent._target_id_for_jobs(),
            client_session_id="client_test",
            command_type="memory",
            action="overview",
            category="snapshot",
        )
        agent_module.job_registry.set_status(job1.id, "running")
        agent_module.job_registry.set_status(job1.id, "completed")
        job1.updated_at = now - 200
        job1.completed_at = now - 200

        job2 = agent_module.job_registry.create(
            target_id=agent._target_id_for_jobs(),
            client_session_id="client_test",
            command_type="memory",
            action="overview",
            category="snapshot",
        )
        agent_module.job_registry.set_status(job2.id, "running")
        agent_module.job_registry.set_status(job2.id, "completed")

        result = agent._execute_command(
            {
                "type": "job",
                "action": "cleanup",
                "older_than_seconds": 100,
            }
        )

        assert result["status"] == "success"
        removed = result["data"]["removed"]
        assert job1.id in removed
        assert job2.id not in removed

        assert agent_module.job_registry.get(job1.id) is None
        assert agent_module.job_registry.get(job2.id) is not None

    def test_job_cleanup_respects_completed_only_filter(self) -> None:
        import time
        agent = _new_agent("test-job-cleanup-completed")

        now = time.time()

        job1 = agent_module.job_registry.create(
            target_id=agent._target_id_for_jobs(),
            client_session_id="client_test",
            command_type="memory",
            action="overview",
            category="snapshot",
        )
        agent_module.job_registry.set_status(job1.id, "running")
        agent_module.job_registry.set_status(job1.id, "completed")
        job1.updated_at = now - 200
        job1.completed_at = now - 200

        job2 = agent_module.job_registry.create(
            target_id=agent._target_id_for_jobs(),
            client_session_id="client_test",
            command_type="memory",
            action="overview",
            category="snapshot",
        )
        agent_module.job_registry.set_status(job2.id, "running")
        agent_module.job_registry.set_status(job2.id, "failed", last_error={"code": "X", "message": "boom"})
        job2.updated_at = now - 200
        job2.completed_at = now - 200

        result = agent._execute_command(
            {
                "type": "job",
                "action": "cleanup",
                "older_than_seconds": 100,
                "completed_only": True,
            }
        )

        assert result["status"] == "success"
        removed = result["data"]["removed"]
        assert job1.id in removed
        assert job2.id not in removed

    def test_job_cleanup_respects_target_filter(self) -> None:
        import time
        agent = _new_agent("test-job-cleanup-target")
        target_id = agent._target_id_for_jobs()

        now = time.time()

        job1 = agent_module.job_registry.create(
            target_id="target_other",
            client_session_id="client_test",
            command_type="memory",
            action="overview",
            category="snapshot",
        )
        agent_module.job_registry.set_status(job1.id, "running")
        agent_module.job_registry.set_status(job1.id, "completed")
        job1.updated_at = now - 200
        job1.completed_at = now - 200

        job2 = agent_module.job_registry.create(
            target_id=target_id,
            client_session_id="client_test",
            command_type="memory",
            action="overview",
            category="snapshot",
        )
        agent_module.job_registry.set_status(job2.id, "running")
        agent_module.job_registry.set_status(job2.id, "completed")
        job2.updated_at = now - 200
        job2.completed_at = now - 200

        result = agent._execute_command(
            {
                "type": "job",
                "action": "cleanup",
                "older_than_seconds": 100,
                "target_id": target_id,
            }
        )

        assert result["status"] == "success"
        removed = result["data"]["removed"]
        assert job1.id not in removed
        assert job2.id in removed

    def test_job_cleanup_default_older_than_is_600s(self) -> None:
        import time
        agent = _new_agent("test-job-cleanup-default")

        now = time.time()

        job = agent_module.job_registry.create(
            target_id=agent._target_id_for_jobs(),
            client_session_id="client_test",
            command_type="memory",
            action="overview",
            category="snapshot",
        )
        agent_module.job_registry.set_status(job.id, "running")
        agent_module.job_registry.set_status(job.id, "completed")
        job.updated_at = now - 50
        job.completed_at = now - 50

        result = agent._execute_command(
            {"type": "job", "action": "cleanup", "older_than_seconds": 100}
        )

        assert result["status"] == "success"
        removed = result["data"]["removed"]
        assert job.id not in removed
        assert agent_module.job_registry.get(job.id) is not None

        job.updated_at = now - 200
        job.completed_at = now - 200

        result = agent._execute_command(
            {"type": "job", "action": "cleanup", "older_than_seconds": 100}
        )

        assert result["status"] == "success"
        removed = result["data"]["removed"]
        assert job.id in removed
        assert agent_module.job_registry.get(job.id) is None

    def test_unknown_job_action_returns_unsupported_capability(self) -> None:
        agent = _new_agent("test-job-unknown-action")

        result = agent._execute_command(
            {"type": "job", "action": "unsupported_action"}
        )

        assert result["status"] == "error"
        assert result["error_code"] == "UNSUPPORTED_CAPABILITY"
        assert "Unknown job action" in result["message"]
