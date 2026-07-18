# pyright: reportAny=false, reportUnusedCallResult=false, reportDeprecated=false, reportExplicitAny=false
"""Tests for concrete profile renderers."""

import json
from io import StringIO
from typing import Any
from typing import Dict
from typing import cast

import pytest

from peeka.core.profile.models import ProfileConfig
from peeka.core.profile.models import ProfileSession
from peeka.core.profile.models import ProfileSummary
from peeka.core.profile.models import SampleRecord
from peeka.core.profile.models import StackRecord
from peeka.core.profile.processors import ProcessedProfile
from peeka.core.profile.renderers import JsonRenderer
from peeka.core.profile.renderers import PerfettoRenderer
from peeka.core.profile.renderers import ProfileRenderer
from peeka.core.profile.renderers import SpeedscopeRenderer
from peeka.core.profile.renderers import TextRenderer


def make_session() -> ProfileSession:
    return ProfileSession(
        profile_id="profile-1",
        backend="sampling",
        config=ProfileConfig(interval_ms=50),
        started_at=100.0,
        ended_at=100.3,
        samples=[
            SampleRecord(
                timestamp=100.0,
                thread_id=11,
                thread_name="main",
                stack=[
                    StackRecord(filename="app.py", lineno=1, name="root", module="app"),
                    StackRecord(filename="app.py", lineno=2, name="leaf", module="app"),
                ],
            ),
            SampleRecord(
                timestamp=100.25,
                thread_id=11,
                thread_name="main",
                stack=[
                    StackRecord(filename="app.py", lineno=1, name="root", module="app"),
                    StackRecord(filename="worker.py", lineno=9, name="worker", module="worker"),
                ],
            ),
        ],
        summary=ProfileSummary(
            sample_count=2,
            duration_ms=300.0,
            start_time=100.0,
            top_functions=[{"name": "leaf", "own_pct": 75.0, "total_pct": 90.0}],
        ),
    )


def make_processed_profile() -> ProcessedProfile:
    session = make_session()
    return ProcessedProfile(
        profile_id=session.profile_id,
        backend=session.backend,
        session=session,
        top_list=[
            {
                "name": "leaf",
                "filename": "app.py",
                "line": 2,
                "own_pct": 75.0,
                "total_pct": 90.0,
                "own_time": 0.15,
                "total_time": 0.27,
                "own_count": 3,
                "total_count": 4,
            },
            {
                "name": "worker",
                "filename": "worker.py",
                "line": 9,
                "own_pct": 25.0,
                "total_pct": 25.0,
                "own_time": 0.05,
                "total_time": 0.05,
                "own_count": 1,
                "total_count": 1,
            },
        ],
    )


@pytest.mark.unit
class TestJsonRenderer:
    def test_render_basic_payload(self) -> None:
        renderer = JsonRenderer()
        output = StringIO()

        renderer.render(make_processed_profile(), output)

        payload = cast(Dict[str, Any], json.loads(output.getvalue()))
        assert payload["profile_id"] == "profile-1"
        assert payload["backend"] == "sampling"
        assert payload["started_at"] == 100.0
        assert payload["summary"]["sample_count"] == 2
        assert payload["top_list"][0]["name"] == "leaf"
        assert "samples" not in payload

    def test_render_includes_samples_when_requested(self) -> None:
        renderer = JsonRenderer(pretty=True, include_samples=True)
        output = StringIO()

        renderer.render(make_processed_profile(), output)

        payload = cast(Dict[str, Any], json.loads(output.getvalue()))
        assert payload["samples"][0]["thread_id"] == 11
        assert payload["samples"][0]["stack"][1]["name"] == "leaf"
        assert output.getvalue().startswith("{\n  ")


@pytest.mark.unit
class TestTextRenderer:
    def test_render_summary_and_table(self) -> None:
        renderer = TextRenderer()
        output = StringIO()

        renderer.render(make_processed_profile(), output)

        rendered = output.getvalue()
        assert "Profile: profile-1" in rendered
        assert "Backend: sampling" in rendered
        assert "Duration: 300.00 ms" in rendered
        assert "Samples: 2" in rendered
        assert "function" in rendered
        assert "leaf (app.py:2)" in rendered
        assert "worker (worker.py:9)" in rendered
        assert "75.00%" in rendered
        assert "own_count" in rendered


@pytest.mark.unit
class TestSpeedscopeRenderer:
    def test_render_valid_speedscope_payload(self) -> None:
        renderer = SpeedscopeRenderer()
        output = StringIO()

        renderer.render(make_processed_profile(), output)

        payload = cast(Dict[str, Any], json.loads(output.getvalue()))
        assert payload["$schema"] == "https://www.speedscope.app/file-format-schema.json"
        assert payload["activeProfileIndex"] == 0
        assert payload["exporter"] == "peeka"
        assert payload["shared"]["frames"][0]["name"] == "root"
        assert len(payload["shared"]["frames"]) == 3
        assert payload["profiles"][0]["type"] == "sampled"
        assert payload["profiles"][0]["unit"] == "milliseconds"
        assert payload["profiles"][0]["samples"] == [[0, 1], [0, 2]]
        assert payload["profiles"][0]["weights"] == [250.0, 50.0]
        assert payload["profiles"][0]["endValue"] == 300.0

    def test_render_multithread_speedscope_uses_per_thread_weights(self) -> None:
        session = ProfileSession(
            profile_id="profile-multi",
            backend="sampling",
            config=ProfileConfig(interval_ms=100),
            started_at=100.0,
            ended_at=100.2,
            samples=[
                SampleRecord(
                    timestamp=100.0,
                    thread_id=1,
                    thread_name="main",
                    stack=[StackRecord(filename="app.py", lineno=1, name="main")],
                ),
                SampleRecord(
                    timestamp=100.001,
                    thread_id=2,
                    thread_name="worker",
                    stack=[StackRecord(filename="worker.py", lineno=1, name="worker")],
                ),
                SampleRecord(
                    timestamp=100.1,
                    thread_id=1,
                    thread_name="main",
                    stack=[StackRecord(filename="app.py", lineno=2, name="main_next")],
                ),
                SampleRecord(
                    timestamp=100.101,
                    thread_id=2,
                    thread_name="worker",
                    stack=[StackRecord(filename="worker.py", lineno=2, name="worker_next")],
                ),
            ],
        )
        processed = ProcessedProfile(
            profile_id=session.profile_id,
            backend=session.backend,
            session=session,
        )
        output = StringIO()

        SpeedscopeRenderer().render(processed, output)

        payload = cast(Dict[str, Any], json.loads(output.getvalue()))
        profiles = payload["profiles"]
        assert len(profiles) == 2
        assert [profile["name"] for profile in profiles] == [
            "profile-multi [main]",
            "profile-multi [worker]",
        ]
        assert profiles[0]["weights"] == pytest.approx([100.0, 100.0])
        assert profiles[1]["weights"] == pytest.approx([100.0, 100.0])
        assert profiles[0]["endValue"] == pytest.approx(200.0)
        assert profiles[1]["endValue"] == pytest.approx(200.0)


@pytest.mark.unit
class TestPerfettoRenderer:
    def test_render_trace_events(self) -> None:
        renderer = PerfettoRenderer()
        output = StringIO()

        renderer.render(make_processed_profile(), output)

        payload = cast(Dict[str, Any], json.loads(output.getvalue()))
        assert len(payload["traceEvents"]) == 2
        first = payload["traceEvents"][0]
        assert first["name"] == "leaf"
        assert first["ph"] == "i"
        assert first["ts"] == 100000000.0
        assert first["tid"] == 11
        assert first["pid"] == 0


def test_profile_renderer_is_abstract() -> None:
    with pytest.raises(TypeError):
        _ = ProfileRenderer()  # pyright: ignore[reportAbstractUsage]
