import json

import pytest

from peeka.core.profile.models import ProfileConfig
from peeka.core.profile.models import ProfileSession
from peeka.core.profile.models import ProfileSummary
from peeka.core.profile.models import SampleRecord
from peeka.core.profile.models import StackRecord


def test_profile_session_round_trip() -> None:
    config = ProfileConfig(
        backend="sampling",
        interval_ms=25,
        duration_ms=1500,
        max_samples=5000,
    )
    session = ProfileSession(
        profile_id="profile_123",
        backend="sampling",
        config=config,
        status="running",
        samples=[
            SampleRecord(
                timestamp=1.25,
                thread_id=7,
                thread_name="MainThread",
                stack=[
                    StackRecord(
                        filename="/tmp/app.py",
                        lineno=42,
                        name="main",
                        module="app",
                    )
                ],
                lane="cpu",
            )
        ],
        summary=ProfileSummary(
            sample_count=1,
            duration_ms=10.0,
            start_time=1.0,
            top_functions=[{"name": "main", "count": 1}],
        ),
    )

    payload = session.to_dict()
    restored = ProfileSession.from_dict(payload)

    assert restored.to_dict() == payload
    assert json.loads(restored.to_json()) == payload


def test_profile_config_validation_mentions_interval_ms() -> None:
    with pytest.raises(ValueError, match="interval_ms"):
        _ = ProfileConfig(interval_ms=0)


def test_profile_config_validation_rejects_max_samples() -> None:
    with pytest.raises(ValueError, match="max_samples"):
        _ = ProfileConfig(max_samples=0)


def test_profile_session_validation_rejects_empty_profile_id() -> None:
    config = ProfileConfig()
    with pytest.raises(ValueError, match="profile_id"):
        _ = ProfileSession(profile_id="", backend="sampling", config=config)
