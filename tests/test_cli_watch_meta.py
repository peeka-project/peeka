"""Tests for watch CLI runtime metadata passthrough."""

from types import SimpleNamespace

from peeka.cli.handlers import observe


def test_emit_watch_started_forwards_runtime_meta(monkeypatch):
    """watch_started should expose runtime_meta as event metadata."""
    captured = {}

    def capture_event(event, data=None, meta=None, **kwargs):
        captured["event"] = event
        captured["data"] = data
        captured["meta"] = meta

    monkeypatch.setattr(observe.OutputFormatter, "event", capture_event)

    args = SimpleNamespace(pattern="pkg.mod.func")
    runtime_meta = {
        "gevent_state": "patched",
        "backend": "wrapper_only",
        "greenlet_blind": False,
    }
    response = {
        "runtime_meta": runtime_meta,
        "target": {"is_coroutine_function": False},
    }

    observe._emit_watch_started(args, response, "watch_001")

    assert captured["event"] == "watch_started"
    assert captured["data"]["watch_id"] == "watch_001"
    assert captured["data"]["pattern"] == "pkg.mod.func"
    assert captured["data"]["target"] == {"is_coroutine_function": False}
    assert captured["meta"] == runtime_meta
