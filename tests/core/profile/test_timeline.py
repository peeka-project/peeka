import io
import json
import time

import pytest

from peeka.core.profile.models import ProfileConfig
from peeka.core.profile.models import ProfileSession
from peeka.core.profile.models import SampleRecord
from peeka.core.profile.models import StackRecord
from peeka.core.profile.processors import BuildTimelineProcessor
from peeka.core.profile.processors import ProcessedProfile
from peeka.core.profile.renderers import TimelineRenderer

def test_build_timeline_two_threads() -> None:
    base = time.time()
    session = ProfileSession(
        profile_id="test_timeline",
        backend="sampling",
        config=ProfileConfig(),
        samples=[
            SampleRecord(
                timestamp=base,
                thread_id=1,
                thread_name="MainThread",
                stack=[StackRecord(filename="f1.py", lineno=10, name="func1")],
            ),
            SampleRecord(
                timestamp=base + 0.1,
                thread_id=2,
                thread_name="WorkerThread",
                stack=[StackRecord(filename="f2.py", lineno=20, name="func2")],
            ),
        ],
    )

    processed = BuildTimelineProcessor().process(session)

    assert processed.timeline is not None
    assert len(processed.timeline) == 2

    lanes = sorted(processed.timeline, key=lambda item: item["thread_id"])

    assert lanes[0]["thread_id"] == 1
    assert lanes[1]["thread_id"] == 2
    for lane in lanes:
        assert "thread_id" in lane
        assert "events" in lane


def test_timeline_renderer_valid_json() -> None:
    base = time.time()
    session = ProfileSession(
        profile_id="test_timeline",
        backend="sampling",
        config=ProfileConfig(),
        samples=[
            SampleRecord(
                timestamp=base,
                thread_id=1,
                thread_name="MainThread",
                stack=[StackRecord(filename="f1.py", lineno=10, name="func1")],
            ),
        ],
    )

    processed: ProcessedProfile = BuildTimelineProcessor().process(session)

    output = io.StringIO()
    TimelineRenderer().render(processed, output)

    data = json.loads(output.getvalue())
    assert "traceEvents" in data
