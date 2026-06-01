# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportPrivateLocalImportUsage=false, reportUnusedParameter=false

import re
import threading
from typing import Dict
from typing import List
from typing import Optional

import pytest

from peeka.core import probes
from peeka.core.probes import PROBE_SCHEMA_VERSION
from peeka.core.probes import ObservationEvent
from peeka.core.probes import ProbeContext
from peeka.core.probes import ProbeRegistry
from peeka.core.probes import ProbeRun
from peeka.core.probes import ProbeStatus
from peeka.core.probes import next_valid_actions


EXPECTED_ACTIONS: Dict[ProbeStatus, List[str]] = {
    "created": ["inspect"],
    "active": ["pause", "stop", "inspect"],
    "paused": ["resume", "stop", "inspect"],
    "stopped": ["inspect"],
    "failed": ["inspect", "cleanup"],
}


def _create_probe(registry: ProbeRegistry) -> ProbeRun:
    return registry.create(
        target_id="target_alpha",
        client_session_id="client_bravo",
        job_id="job_cafe1234",
        type="watch",
        pattern="pkg.fn",
        config={"limit": 5},
    )


class TestProbeRegistry:
    def test_lifecycle(self, monkeypatch: pytest.MonkeyPatch) -> None:
        registry = ProbeRegistry()
        timestamps = iter([100.0, 110.0, 120.0])

        monkeypatch.setattr(probes.time, "time", lambda: next(timestamps))

        probe = _create_probe(registry)

        assert probe.id.startswith("prb_")
        assert len(probe.id) == 12
        assert probe.created_at == 100.0
        assert probe.updated_at == 100.0
        assert probe.started_at is None
        assert probe.stopped_at is None

        assert registry.set_status(probe.id, "active") is True
        assert probe.status == "active"
        assert probe.started_at == 110.0
        assert probe.updated_at == 110.0

        assert registry.set_status(probe.id, "stopped") is True
        assert probe.status == "stopped"
        assert probe.stopped_at == 120.0
        assert probe.updated_at == 120.0

    def test_illegal_transition_rejected(self) -> None:
        registry = ProbeRegistry()
        probe = _create_probe(registry)

        assert registry.set_status(probe.id, "stopped") is False
        assert probe.status == "created"
        assert probe.started_at is None
        assert probe.stopped_at is None

    def test_ring_buffer(self) -> None:
        registry = ProbeRegistry()
        probe = _create_probe(registry)

        for index in range(150):
            _ = registry.record_event(probe.id, {"index": index})

        events = registry.get_recent_events(probe.id)

        assert len(events) == 100
        assert events[0].sequence == 50
        assert events[0].payload == {"index": 50}
        assert events[-1].sequence == 149

    def test_event_id_format(self) -> None:
        registry = ProbeRegistry()
        probe = _create_probe(registry)

        event = registry.record_event(probe.id, {"kind": "sample"})

        assert event is not None
        assert re.fullmatch(r"evt_[0-9a-f]{6}_0", event.event_id) is not None
        assert event.event_id == "evt_{}_0".format(probe.id[-6:])

    def test_event_sequence_monotonic(self) -> None:
        registry = ProbeRegistry()
        probe = _create_probe(registry)

        events = [registry.record_event(probe.id, {"index": index}) for index in range(3)]

        assert [event.sequence for event in events if event is not None] == [0, 1, 2]

    def test_summary_monotonic(self) -> None:
        registry = ProbeRegistry()
        probe = _create_probe(registry)

        _ = registry.record_event(probe.id, {"index": 1})
        _ = registry.record_event(probe.id, {"index": 2})
        _ = registry.update_summary(probe.id, event_count_delta=3, last_event_at=456.0)

        assert probe.event_count == 5
        assert probe.last_event_at == 456.0
        assert probe.summary["event_count"] == 5
        assert probe.summary["last_event_at"] == 456.0

    def test_cleanup_removes_old_terminal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        registry = ProbeRegistry()
        probe = _create_probe(registry)
        probe.status = "stopped"
        probe.stopped_at = 100.0

        monkeypatch.setattr(probes.time, "time", lambda: 1000.0)

        removed_ids = registry.cleanup(older_than_seconds=600)

        assert removed_ids == [probe.id]
        assert registry.get(probe.id) is None

    def test_cleanup_preserves_active(self, monkeypatch: pytest.MonkeyPatch) -> None:
        registry = ProbeRegistry()
        probe = _create_probe(registry)
        probe.status = "active"
        probe.started_at = 100.0

        monkeypatch.setattr(probes.time, "time", lambda: 1000.0)

        removed_ids = registry.cleanup(older_than_seconds=1)

        assert removed_ids == []
        assert registry.get(probe.id) is probe

    def test_cleanup_filters_by_target_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        registry = ProbeRegistry()
        target_probe = _create_probe(registry)
        other_probe = registry.create(
            target_id="target_other",
            client_session_id="client_delta",
            job_id="job_bead1234",
            type="trace",
            pattern="pkg.other",
            config={},
        )

        target_probe.status = "stopped"
        target_probe.stopped_at = 100.0
        other_probe.status = "stopped"
        other_probe.stopped_at = 100.0

        monkeypatch.setattr(probes.time, "time", lambda: 1000.0)

        removed_ids = registry.cleanup(older_than_seconds=600, target_id="target_alpha")

        assert removed_ids == [target_probe.id]
        assert registry.get(target_probe.id) is None
        assert registry.get(other_probe.id) is other_probe

    def test_next_valid_actions(self) -> None:
        for status, expected_actions in EXPECTED_ACTIONS.items():
            assert next_valid_actions(status) == expected_actions

        probe = ProbeRun(
            id="prb_deadbeef",
            target_id="target_alpha",
            client_session_id="client_bravo",
            job_id="job_cafe1234",
            type="watch",
            pattern="pkg.fn",
            config={"limit": 1},
            status="failed",
            created_at=10.0,
            updated_at=12.0,
            started_at=11.0,
            stopped_at=12.0,
            last_event_at=12.0,
            event_count=2,
            last_error={"code": "BOOM", "message": "bad"},
            summary={"event_count": 2},
            schema_version=PROBE_SCHEMA_VERSION,
        )

        serialized = probe.to_dict()

        assert serialized["id"] == "prb_deadbeef"
        assert serialized["probe_id"] == "prb_deadbeef"
        assert probe.probe_id == "prb_deadbeef"
        assert serialized["updated_at"] == 12.0
        assert serialized["last_error"] == {"code": "BOOM", "message": "bad"}
        assert serialized["next_valid_actions"] == ["inspect", "cleanup"]
        assert serialized["schema_version"] == PROBE_SCHEMA_VERSION

    def test_updated_at_advances_on_status_change_and_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = ProbeRegistry()
        timestamps = iter([100.0, 110.0, 120.0])

        monkeypatch.setattr(probes.time, "time", lambda: next(timestamps))

        probe = _create_probe(registry)

        assert probe.updated_at == 100.0
        assert registry.set_status(probe.id, "active") is True
        assert probe.updated_at == 110.0

        event = registry.record_event(probe.id, {"kind": "sample"})

        assert event is not None
        assert probe.updated_at == 120.0

    def test_summary_includes_last_error_on_failure(self) -> None:
        registry = ProbeRegistry()
        probe = _create_probe(registry)

        assert registry.set_status(probe.id, "active") is True
        assert registry.set_status(
            probe.id,
            "failed",
            error="kaput",
        ) is True

        assert probe.last_error == {"code": "", "message": "kaput"}
        assert probe.summary["last_error"] == "kaput"

    def test_thread_safe(self) -> None:
        registry = ProbeRegistry()
        created_probe_ids: List[str] = []
        created_probe_ids_lock = threading.Lock()

        def worker(thread_index: int) -> None:
            probe = registry.create(
                target_id="target_{}".format(thread_index),
                client_session_id="client_{}".format(thread_index),
                job_id="job_{:04d}".format(thread_index),
                type="watch",
                pattern="pkg.fn",
                config={"thread": thread_index},
            )
            with created_probe_ids_lock:
                created_probe_ids.append(probe.id)

            for event_index in range(100):
                event = registry.record_event(probe.id, {"thread": thread_index, "event": event_index})
                assert isinstance(event, ObservationEvent)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(10)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(created_probe_ids) == 10
        assert len(set(created_probe_ids)) == 10
        assert len(registry.list()) == 10

        for probe_id in created_probe_ids:
            probe = registry.get(probe_id)
            assert probe is not None
            assert probe.event_count == 100
            assert probe.summary["event_count"] == 100
            recent_events = registry.get_recent_events(probe_id)
            assert len(recent_events) == 100
            assert [event.sequence for event in recent_events] == list(range(100))


class TestProbeContext:
    def test_context_normal_exit(self) -> None:
        registry = ProbeRegistry()
        
        with ProbeContext(
            registry,
            target_id="target_alpha",
            client_session_id="client_bravo",
            job_id="job_cafe1234",
            type="watch",
            pattern="pkg.fn",
            config={"limit": 5},
        ) as ctx:
            assert ctx.probe_id is not None
            assert ctx.probe is not None
            assert ctx.probe.status == "active"
            
            ctx.record_event({"index": 0})
            ctx.record_event({"index": 1})
            ctx.record_event({"index": 2})
        
        probe = registry.get(ctx.probe_id)
        assert probe is not None
        assert probe.status == "stopped"
        assert probe.event_count == 3
        assert probe.stopped_at is not None

    def test_context_exception_marks_failed(self) -> None:
        registry = ProbeRegistry()
        probe_id: Optional[str] = None
        
        try:
            with ProbeContext(
                registry,
                target_id="target_alpha",
                client_session_id="client_bravo",
                job_id="job_cafe1234",
                type="watch",
                pattern="pkg.fn",
            ) as ctx:
                probe_id = ctx.probe_id
                raise ValueError("test error message")
        except ValueError:
            pass
        
        assert probe_id is not None
        probe = registry.get(probe_id)
        assert probe is not None
        assert probe.status == "failed"
        assert probe.last_error == {
            "code": "COMMAND_EXECUTION_ERROR",
            "message": "test error message",
        }
        assert probe.summary["last_error"] == "test error message"

    def test_context_exception_does_not_suppress(self) -> None:
        registry = ProbeRegistry()
        
        with pytest.raises(RuntimeError, match="boom"):
            with ProbeContext(
                registry,
                target_id="target_alpha",
                client_session_id="client_bravo",
                job_id="job_cafe1234",
                type="watch",
                pattern="pkg.fn",
            ):
                raise RuntimeError("boom")

    def test_record_event_returns_event(self) -> None:
        registry = ProbeRegistry()
        
        with ProbeContext(
            registry,
            target_id="target_alpha",
            client_session_id="client_bravo",
            job_id="job_cafe1234",
            type="watch",
            pattern="pkg.fn",
        ) as ctx:
            event1 = ctx.record_event({"kind": "sample_1"})
            event2 = ctx.record_event({"kind": "sample_2"})
            event3 = ctx.record_event({"kind": "sample_3"})
        
        assert event1 is not None
        assert event1.probe_id == ctx.probe_id
        assert event1.sequence == 0
        assert event1.payload == {"kind": "sample_1"}
        
        assert event2 is not None
        assert event2.sequence == 1
        
        assert event3 is not None
        assert event3.sequence == 2

    def test_should_stop_when_externally_stopped(self) -> None:
        registry = ProbeRegistry()
        
        with ProbeContext(
            registry,
            target_id="target_alpha",
            client_session_id="client_bravo",
            job_id="job_cafe1234",
            type="watch",
            pattern="pkg.fn",
        ) as ctx:
            assert ctx.probe_id is not None
            assert ctx.should_stop() is False
            
            registry.set_status(ctx.probe_id, "stopped")
            
            assert ctx.should_stop() is True

    def test_double_enter_creates_new_probe(self) -> None:
        registry = ProbeRegistry()
        
        with ProbeContext(
            registry,
            target_id="target_alpha",
            client_session_id="client_bravo",
            job_id="job_1",
            type="watch",
            pattern="pkg.fn",
        ) as ctx1:
            probe_id_1 = ctx1.probe_id
            assert probe_id_1 is not None
        
        with ProbeContext(
            registry,
            target_id="target_alpha",
            client_session_id="client_bravo",
            job_id="job_2",
            type="trace",
            pattern="pkg.other",
        ) as ctx2:
            probe_id_2 = ctx2.probe_id
            assert probe_id_2 is not None
        
        assert probe_id_1 != probe_id_2
        
        probe1 = registry.get(probe_id_1)
        probe2 = registry.get(probe_id_2)
        
        assert probe1 is not None
        assert probe1.type == "watch"
        assert probe1.job_id == "job_1"
        
        assert probe2 is not None
        assert probe2.type == "trace"
        assert probe2.job_id == "job_2"
