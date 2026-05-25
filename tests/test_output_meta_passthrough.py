"""Tests for OutputFormatter meta passthrough."""

import json

import pytest

from peeka.core.output import OutputFormatter


@pytest.mark.unit
class TestOutputMetaPassthrough:
    """JSONL meta passthrough tests."""

    def test_result_with_meta_promotes_meta_to_top_level(self, capsys):
        """Command response meta becomes top-level JSONL meta."""
        OutputFormatter.result(
            "trace",
            {
                "status": "success",
                "watch_id": "trace_1",
                "meta": {
                    "gevent_state": "patched",
                    "backend": "wrapper_only",
                    "greenlet_blind": False,
                    "degraded_reason": "degraded",
                },
            },
        )

        output = json.loads(capsys.readouterr().out)
        assert output["type"] == "result"
        assert output["data"]["watch_id"] == "trace_1"
        assert "meta" not in output["data"]
        assert output["meta"]["backend"] == "wrapper_only"

    def test_result_without_meta_stays_unchanged(self, capsys):
        """Results without meta keep the existing JSONL shape."""
        OutputFormatter.result("logger", {"status": "success", "items": 2})

        output = json.loads(capsys.readouterr().out)
        assert output == {
            "type": "result",
            "command": "logger",
            "data": {"status": "success", "items": 2},
        }

    def test_meta_does_not_override_record_fields(self, capsys):
        """Nested meta cannot override the JSONL record type."""
        OutputFormatter.result(
            "top",
            {
                "status": "success",
                "meta": {
                    "type": "wrong",
                    "backend": "frame_walk",
                },
            },
        )

        output = json.loads(capsys.readouterr().out)
        assert output["type"] == "result"
        assert output["meta"]["type"] == "wrong"

    def test_event_accepts_explicit_meta_kwarg(self, capsys):
        """Streaming start events can carry response metadata."""
        OutputFormatter.event(
            "trace_started",
            data={"trace_id": "trace_1"},
            meta={"gevent_state": "none"},
        )

        output = json.loads(capsys.readouterr().out)
        assert output["type"] == "event"
        assert output["meta"] == {"gevent_state": "none"}
