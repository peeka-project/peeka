# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

from typing import Generator

import pytest

from peeka.core import probes as probes_module
from peeka.core.agent import PeekaAgent
from peeka.core.probes import ProbeRegistry


@pytest.fixture(autouse=True)
def reset_probe_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[ProbeRegistry, None, None]:
    probe_registry = ProbeRegistry()
    monkeypatch.setattr(probes_module, "probe_registry", probe_registry)
    yield probe_registry


def _new_agent(session_id: str) -> PeekaAgent:
    return PeekaAgent(session_id=session_id, attached_pid=12345)


class TestAgentProbeEndpoints:
    def test_probe_list_empty_returns_success(self) -> None:
        agent = _new_agent("test-probe-list-empty")

        result = agent._execute_command({"type": "probe", "action": "list"})

        assert result["status"] == "success"
        assert result["data"]["probes"] == []

    def test_probe_list_filters_by_target_status_type(
        self, reset_probe_registry: ProbeRegistry
    ) -> None:
        agent = _new_agent("test-probe-list-filters")
        target_id = f"target_{agent.session_id[:8]}"

        probe1 = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_a",
            job_id="job_1",
            type="watch",
            pattern="module.func",
            config={},
        )
        reset_probe_registry.set_status(probe1.id, "active")

        probe2 = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_b",
            job_id="job_2",
            type="trace",
            pattern="module.other",
            config={},
        )
        reset_probe_registry.set_status(probe2.id, "active")
        reset_probe_registry.set_status(probe2.id, "stopped")

        result = agent._execute_command(
            {"type": "probe", "action": "list", "target_id": target_id}
        )
        assert result["status"] == "success"
        assert len(result["data"]["probes"]) == 2

        result = agent._execute_command(
            {"type": "probe", "action": "list", "status": "active"}
        )
        assert result["status"] == "success"
        assert len(result["data"]["probes"]) == 1
        assert result["data"]["probes"][0]["id"] == probe1.id

        result = agent._execute_command(
            {"type": "probe", "action": "list", "probe_type": "trace"}
        )
        assert result["status"] == "success"
        assert len(result["data"]["probes"]) == 1
        assert result["data"]["probes"][0]["id"] == probe2.id

    def test_probe_status_returns_probe_dict(
        self, reset_probe_registry: ProbeRegistry
    ) -> None:
        agent = _new_agent("test-probe-status")
        target_id = f"target_{agent.session_id[:8]}"

        probe = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_a",
            job_id="job_1",
            type="watch",
            pattern="module.func",
            config={"max_events": 100},
        )

        result = agent._execute_command(
            {"type": "probe", "action": "status", "probe_id": probe.id}
        )

        assert result["status"] == "success"
        assert result["data"]["probe"]["id"] == probe.id
        assert result["data"]["probe"]["probe_id"] == probe.id
        assert result["data"]["probe"]["type"] == "watch"
        assert result["data"]["probe"]["pattern"] == "module.func"
        assert result["data"]["probe"]["config"] == {"max_events": 100}
        assert "updated_at" in result["data"]["probe"]
        assert "next_valid_actions" in result["data"]["probe"]

    def test_probe_status_exposes_last_error_string_when_failed(
        self, reset_probe_registry: ProbeRegistry
    ) -> None:
        agent = _new_agent("test-probe-status-failed")
        target_id = f"target_{agent.session_id[:8]}"

        probe = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_a",
            job_id="job_1",
            type="watch",
            pattern="module.func",
            config={},
        )
        reset_probe_registry.set_status(probe.id, "active")
        reset_probe_registry.set_status(probe.id, "failed", error="probe boom")

        result = agent._execute_command(
            {"type": "probe", "action": "status", "probe_id": probe.id}
        )

        assert result["status"] == "success"
        assert result["data"]["probe"]["last_error"] == {
            "code": "",
            "message": "probe boom",
        }
        assert result["data"]["probe"]["summary"]["last_error"] == "probe boom"

    def test_probe_status_unknown_returns_PROBE_NOT_FOUND(self) -> None:
        agent = _new_agent("test-probe-status-unknown")

        result = agent._execute_command(
            {"type": "probe", "action": "status", "probe_id": "prb_nonexist"}
        )

        assert result["status"] == "error"
        assert result["error_code"] == "PROBE_NOT_FOUND"
        assert "not found" in result["message"]

    def test_probe_inspect_returns_probe_and_recent_events(
        self, reset_probe_registry: ProbeRegistry
    ) -> None:
        agent = _new_agent("test-probe-inspect")
        target_id = f"target_{agent.session_id[:8]}"

        probe = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_a",
            job_id="job_1",
            type="watch",
            pattern="module.func",
            config={},
        )
        reset_probe_registry.set_status(probe.id, "active")

        reset_probe_registry.record_event(probe.id, {"event": "call", "args": [1, 2]})
        reset_probe_registry.record_event(probe.id, {"event": "return", "value": 3})

        result = agent._execute_command(
            {"type": "probe", "action": "inspect", "probe_id": probe.id}
        )

        assert result["status"] == "success"
        assert result["data"]["probe"]["id"] == probe.id
        assert result["data"]["probe"]["probe_id"] == probe.id
        assert len(result["data"]["events"]) == 2
        assert result["data"]["events"][0]["sequence"] == 0
        assert result["data"]["events"][1]["sequence"] == 1
        assert result["data"]["events"][0]["payload"] == {"event": "call", "args": [1, 2]}
        assert result["data"]["events"][1]["payload"] == {"event": "return", "value": 3}

    def test_probe_inspect_respects_events_limit(
        self, reset_probe_registry: ProbeRegistry
    ) -> None:
        agent = _new_agent("test-probe-inspect-limit")
        target_id = f"target_{agent.session_id[:8]}"

        probe = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_a",
            job_id="job_1",
            type="watch",
            pattern="module.func",
            config={},
        )
        reset_probe_registry.set_status(probe.id, "active")

        for i in range(10):
            reset_probe_registry.record_event(probe.id, {"seq": i})

        result = agent._execute_command(
            {
                "type": "probe",
                "action": "inspect",
                "probe_id": probe.id,
                "events_limit": 3,
            }
        )

        assert result["status"] == "success"
        assert len(result["data"]["events"]) == 3
        assert result["data"]["events"][0]["sequence"] == 7
        assert result["data"]["events"][1]["sequence"] == 8
        assert result["data"]["events"][2]["sequence"] == 9

        result = agent._execute_command(
            {
                "type": "probe",
                "action": "inspect",
                "probe_id": probe.id,
                "events_limit": 200,
            }
        )

        assert result["status"] == "success"
        assert len(result["data"]["events"]) == 10

    def test_probe_inspect_unknown_returns_PROBE_NOT_FOUND(self) -> None:
        agent = _new_agent("test-probe-inspect-unknown")

        result = agent._execute_command(
            {"type": "probe", "action": "inspect", "probe_id": "prb_nonexist"}
        )

        assert result["status"] == "error"
        assert result["error_code"] == "PROBE_NOT_FOUND"

    def test_probe_stop_active_succeeds(
        self, reset_probe_registry: ProbeRegistry
    ) -> None:
        agent = _new_agent("test-probe-stop-active")
        target_id = f"target_{agent.session_id[:8]}"

        probe = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_a",
            job_id="job_1",
            type="watch",
            pattern="module.func",
            config={},
        )
        reset_probe_registry.set_status(probe.id, "active")

        result = agent._execute_command(
            {"type": "probe", "action": "stop", "probe_id": probe.id}
        )

        assert result["status"] == "success"
        assert result["data"]["probe_id"] == probe.id

        refreshed = reset_probe_registry.get(probe.id)
        assert refreshed is not None
        assert refreshed.status == "stopped"

    def test_probe_stop_unknown_returns_PROBE_NOT_FOUND(self) -> None:
        agent = _new_agent("test-probe-stop-unknown")

        result = agent._execute_command(
            {"type": "probe", "action": "stop", "probe_id": "prb_nonexist"}
        )

        assert result["status"] == "error"
        assert result["error_code"] == "PROBE_NOT_FOUND"

    def test_probe_stop_idempotent_on_terminal(
        self, reset_probe_registry: ProbeRegistry
    ) -> None:
        agent = _new_agent("test-probe-stop-idempotent")
        target_id = f"target_{agent.session_id[:8]}"

        probe = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_a",
            job_id="job_1",
            type="watch",
            pattern="module.func",
            config={},
        )
        reset_probe_registry.set_status(probe.id, "active")
        reset_probe_registry.set_status(probe.id, "stopped")

        result = agent._execute_command(
            {"type": "probe", "action": "stop", "probe_id": probe.id}
        )

        assert result["status"] == "success"
        assert result["data"]["probe_id"] == probe.id
        assert "already in terminal state" in result["data"]["summary"]

    def test_probe_pause_returns_UNSUPPORTED_CAPABILITY(self) -> None:
        agent = _new_agent("test-probe-pause-unsupported")

        result = agent._execute_command(
            {"type": "probe", "action": "pause", "probe_id": "prb_12345678"}
        )

        assert result["status"] == "error"
        assert result["error_code"] == "UNSUPPORTED_CAPABILITY"
        assert "not yet implemented" in result["message"]

    def test_probe_cleanup_removes_old_terminal_only(
        self, reset_probe_registry: ProbeRegistry
    ) -> None:
        import time

        agent = _new_agent("test-probe-cleanup")
        target_id = f"target_{agent.session_id[:8]}"

        probe_active = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_a",
            job_id="job_1",
            type="watch",
            pattern="module.func",
            config={},
        )
        reset_probe_registry.set_status(probe_active.id, "active")

        probe_old_stopped = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_b",
            job_id="job_2",
            type="trace",
            pattern="module.other",
            config={},
        )
        reset_probe_registry.set_status(probe_old_stopped.id, "active")
        reset_probe_registry.set_status(
            probe_old_stopped.id, "stopped", stopped_at=time.time() - 700
        )

        probe_recent_stopped = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_c",
            job_id="job_3",
            type="monitor",
            pattern=None,
            config={},
        )
        reset_probe_registry.set_status(probe_recent_stopped.id, "active")
        reset_probe_registry.set_status(probe_recent_stopped.id, "stopped")

        result = agent._execute_command(
            {"type": "probe", "action": "cleanup", "older_than_seconds": 600}
        )

        assert result["status"] == "success"
        assert result["data"]["removed"] == [probe_old_stopped.id]

        assert reset_probe_registry.get(probe_active.id) is not None
        assert reset_probe_registry.get(probe_old_stopped.id) is None
        assert reset_probe_registry.get(probe_recent_stopped.id) is not None

    def test_probe_cleanup_completed_only_maps_to_stopped(
        self, reset_probe_registry: ProbeRegistry
    ) -> None:
        import time

        agent = _new_agent("test-probe-cleanup-completed")
        target_id = f"target_{agent.session_id[:8]}"

        stopped_probe = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_a",
            job_id="job_1",
            type="watch",
            pattern="module.func",
            config={},
        )
        reset_probe_registry.set_status(stopped_probe.id, "active")
        reset_probe_registry.set_status(
            stopped_probe.id, "stopped", stopped_at=time.time() - 700
        )

        failed_probe = reset_probe_registry.create(
            target_id=target_id,
            client_session_id="client_b",
            job_id="job_2",
            type="trace",
            pattern="module.other",
            config={},
        )
        reset_probe_registry.set_status(failed_probe.id, "active")
        reset_probe_registry.set_status(
            failed_probe.id,
            "failed",
            stopped_at=time.time() - 700,
            error="bad",
        )

        result = agent._execute_command(
            {
                "type": "probe",
                "action": "cleanup",
                "older_than_seconds": 600,
                "completed_only": True,
            }
        )

        assert result["status"] == "success"
        assert result["data"]["removed"] == [stopped_probe.id]
        assert reset_probe_registry.get(stopped_probe.id) is None
        assert reset_probe_registry.get(failed_probe.id) is not None
