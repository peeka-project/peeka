import pytest
from peeka.core.profile.models import ProfileConfig, ProfileSession, SampleRecord, StackRecord
from peeka.core.profile.processors import BuildTimelineProcessor
from peeka.core.profile.renderers import TimelineRenderer
import io
import json

def test_build_timeline_processor_produces_lanes():
    session = ProfileSession(
        profile_id="test_timeline",
        backend="sampling",
        config=ProfileConfig(),
        samples=[
            SampleRecord(
                timestamp=0.0,
                thread_id=1,
                thread_name="MainThread",
                stack=[StackRecord(filename="f1.py", lineno=10, name="func1")],
            ),
            SampleRecord(
                timestamp=0.1,
                thread_id=2,
                thread_name="WorkerThread",
                stack=[StackRecord(filename="f2.py", lineno=20, name="func2")],
            ),
        ]
    )
    
    processor = BuildTimelineProcessor()
    processed = processor.process(session)
    
    assert processed.timeline is not None
    assert len(processed.timeline) == 2
    
    lanes = sorted(processed.timeline, key=lambda x: x["thread_id"])
    
    assert lanes[0]["thread_id"] == 1
    assert lanes[0]["thread_name"] == "MainThread"
    assert len(lanes[0]["events"]) == 1
    assert lanes[0]["events"][0]["name"] == "func1"
    
    assert lanes[1]["thread_id"] == 2
    assert lanes[1]["thread_name"] == "WorkerThread"
    assert len(lanes[1]["events"]) == 1
    assert lanes[1]["events"][0]["name"] == "func2"

def test_timeline_renderer_outputs_json():
    session = ProfileSession(
        profile_id="test_timeline",
        backend="sampling",
        config=ProfileConfig(),
        samples=[
            SampleRecord(
                timestamp=0.0,
                thread_id=1,
                thread_name="MainThread",
                stack=[StackRecord(filename="f1.py", lineno=10, name="func1")],
            )
        ]
    )
    
    processor = BuildTimelineProcessor()
    processed = processor.process(session)
    
    output = io.StringIO()
    renderer = TimelineRenderer()
    renderer.render(processed, output)
    
    result = json.loads(output.getvalue())
    assert "traceEvents" in result
    assert len(result["traceEvents"]) == 1
    assert result["traceEvents"][0]["name"] == "func1"
