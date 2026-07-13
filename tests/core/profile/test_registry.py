"""Tests for the profile session registry."""

import time
from collections.abc import Sequence

import pytest

from peeka.core.profile.models import ProfileConfig
from peeka.core.profile.models import SampleRecord
from peeka.core.profile.models import StackRecord
from peeka.core.profile.registry import ProfileRegistry


def make_sample(sequence: int) -> SampleRecord:
    return SampleRecord(
        timestamp=float(sequence),
        thread_id=sequence,
        thread_name="MainThread",
        stack=[
            StackRecord(
                filename="/tmp/app.py",
                lineno=sequence,
                name="worker",
                module="app",
            )
        ],
        lane="cpu",
    )


def set_time(monkeypatch: pytest.MonkeyPatch, value: Sequence[float]) -> None:
    monkeypatch.setattr(time, "time", lambda: value[0])


def test_start_stop_snapshot_and_list_sessions(monkeypatch: pytest.MonkeyPatch) -> None:
    current = [100.0]
    set_time(monkeypatch, current)

    registry = ProfileRegistry()
    config = ProfileConfig(backend="sampling", interval_ms=10, duration_ms=1000)

    profile_id = registry.start(config)
    registry.add_sample(profile_id, make_sample(1))

    snapshot = registry.snapshot(profile_id)
    snapshot.samples.append(make_sample(2))

    current[0] = 125.0
    stopped = registry.stop(profile_id)
    sessions = registry.list_sessions()
    stored = registry.get_session(profile_id)

    assert profile_id.startswith("prof_")
    assert stored is not None
    assert stored.status == "stopped"
    assert stopped.status == "stopped"
    assert stopped.ended_at == 125.0
    assert len(registry.snapshot(profile_id).samples) == 1
    assert len(sessions) == 1
    assert sessions[0].profile_id == profile_id
    assert sessions[0].status == "stopped"


def test_add_sample_drops_when_session_hits_max_samples(monkeypatch: pytest.MonkeyPatch) -> None:
    current = [1.0]
    set_time(monkeypatch, current)

    registry = ProfileRegistry()
    config = ProfileConfig(backend="sampling", interval_ms=10, max_samples=2)
    profile_id = registry.start(config)

    registry.add_sample(profile_id, make_sample(1))
    registry.add_sample(profile_id, make_sample(2))
    registry.add_sample(profile_id, make_sample(3))

    session = registry.get_session(profile_id)
    assert session is not None
    assert len(session.samples) == 2
    assert [sample.timestamp for sample in session.samples] == [1.0, 2.0]


def test_cleanup_removes_stopped_sessions_older_than_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    current = [1.0]
    set_time(monkeypatch, current)

    registry = ProfileRegistry(max_sessions=10)
    config = ProfileConfig(backend="sampling", interval_ms=10)

    current[0] = 1.0
    profile_a = registry.start(config)
    current[0] = 2.0
    _ = registry.stop(profile_a)

    current[0] = 3.0
    profile_b = registry.start(config)
    current[0] = 4.0
    _ = registry.stop(profile_b)

    current[0] = 5.0
    profile_c = registry.start(config)
    current[0] = 6.0
    _ = registry.stop(profile_c)

    current[0] = 20.0
    removed = registry.cleanup(older_than_secs=15.0)
    remaining = registry.list_sessions()

    assert removed == 2
    assert [session.profile_id for session in remaining] == [profile_c]


def test_stop_evicts_oldest_stopped_session_when_limit_exceeded(monkeypatch: pytest.MonkeyPatch) -> None:
    current = [1.0]
    set_time(monkeypatch, current)

    registry = ProfileRegistry(max_sessions=2)
    config = ProfileConfig(backend="sampling", interval_ms=10)

    current[0] = 1.0
    profile_a = registry.start(config)
    current[0] = 2.0
    _ = registry.stop(profile_a)

    current[0] = 3.0
    profile_b = registry.start(config)
    current[0] = 4.0
    _ = registry.stop(profile_b)

    current[0] = 5.0
    profile_c = registry.start(config)
    current[0] = 6.0
    _ = registry.stop(profile_c)

    remaining_ids = [session.profile_id for session in registry.list_sessions()]

    assert profile_a not in remaining_ids
    assert set(remaining_ids) == {profile_b, profile_c}


def test_cleanup_with_max_sessions_override_keeps_newest_stopped(monkeypatch: pytest.MonkeyPatch) -> None:
    current = [1.0]
    set_time(monkeypatch, current)

    registry = ProfileRegistry(max_sessions=10)
    config = ProfileConfig(backend="sampling", interval_ms=10)

    current[0] = 1.0
    profile_a = registry.start(config)
    current[0] = 2.0
    _ = registry.stop(profile_a)

    current[0] = 3.0
    profile_b = registry.start(config)
    current[0] = 4.0
    _ = registry.stop(profile_b)

    current[0] = 5.0
    profile_c = registry.start(config)
    current[0] = 6.0
    _ = registry.stop(profile_c)

    removed = registry.cleanup(max_sessions=2)
    remaining_ids = [session.profile_id for session in registry.list_sessions()]

    assert removed == 1
    assert profile_a not in remaining_ids
    assert set(remaining_ids) == {profile_b, profile_c}
