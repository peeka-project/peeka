# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportPrivateLocalImportUsage=false, reportUnusedParameter=false

import re
import threading
from typing import Dict
from typing import List

import pytest

from peeka.core import probes
from peeka.core.probes import PROBE_SCHEMA_VERSION
from peeka.core.probes import ObservationEvent
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
        assert probe.started_at is None
        assert probe.stopped_at is None

        assert registry.set_status(probe.id, "active") is True
        assert probe.status == "active"
        assert probe.started_at == 110.0

        assert registry.set_status(probe.id, "stopped") is True
        assert probe.status == "stopped"
        assert probe.stopped_at == 120.0

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

        removed_count = registry.cleanup(older_than_seconds=600)

        assert removed_count == 1
        assert registry.get(probe.id) is None

    def test_cleanup_preserves_active(self, monkeypatch: pytest.MonkeyPatch) -> None:
        registry = ProbeRegistry()
        probe = _create_probe(registry)
        probe.status = "active"
        probe.started_at = 100.0

        monkeypatch.setattr(probes.time, "time", lambda: 1000.0)

        removed_count = registry.cleanup(older_than_seconds=1)

        assert removed_count == 0
        assert registry.get(probe.id) is probe

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
            started_at=11.0,
            stopped_at=12.0,
            last_event_at=12.0,
            event_count=2,
            last_error={"code": "BOOM", "message": "bad"},
            summary={"event_count": 2},
            schema_version=PROBE_SCHEMA_VERSION,
        )

        serialized = probe.to_dict()

        assert serialized["next_valid_actions"] == ["inspect", "cleanup"]
        assert serialized["schema_version"] == PROBE_SCHEMA_VERSION

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
