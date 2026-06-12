"""Tests for watch CLI runtime metadata and limit semantics."""

# pyright: reportDeprecated=false, reportExplicitAny=false, reportAny=false

import subprocess
import sys
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

import pytest

from peeka.cli.handlers import observe
from peeka.cli.streaming import counted_limit
from peeka.core.output import OutputFormatter


def test_emit_watch_started_forwards_runtime_meta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """watch_started should expose runtime_meta as event metadata."""
    captured: Dict[str, Any] = {}

    def capture_event(
        event: str,
        data: Optional[Dict[str, Any]] = None,
        meta: Optional[Dict[str, Any]] = None,
        **_kwargs: Any,
    ) -> None:
        captured["event"] = event
        captured["data"] = data
        captured["meta"] = meta

    monkeypatch.setattr(OutputFormatter, "event", capture_event)

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

    observe._emit_watch_started(args, response, "watch_001")  # pyright: ignore[reportPrivateUsage]

    assert captured["event"] == "watch_started"
    assert captured["data"]["watch_id"] == "watch_001"
    assert captured["data"]["pattern"] == "pkg.mod.func"
    assert captured["data"]["target"] == {"is_coroutine_function": False}
    assert captured["meta"] == runtime_meta


@pytest.mark.parametrize(
    "limit, expected",
    [
        (-1, [False, False, False]),
        (0, [False, False, False]),
        (1, [True, True, True]),
        (2, [False, True, True]),
    ],
)
def test_counted_limit_uses_local_emitted_observation_count(
    limit: int,
    expected: List[bool],
) -> None:
    args = SimpleNamespace(times=limit)
    predicate = counted_limit("times")

    results = [predicate(args, {"count": index}) for index in range(3)]

    assert results == expected


def test_counted_limit_stops_after_n_emitted_observations() -> None:
    args = SimpleNamespace(times=2)
    predicate = counted_limit("times")

    assert predicate(args, {"count": 1}) is False
    assert predicate(args, {"count": 2}) is True
    assert predicate(args, {"count": 3}) is True


def test_watch_times_help_current_wording_mentions_print_observations() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "watch", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    help_text = result.stdout.lower()
    assert "-n, --times" in result.stdout
    assert "observations" in help_text
    assert "print" in help_text or "emit" in help_text


def test_watch_times_help_does_not_say_capture() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "watch", "--help"],
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    help_text = result.stdout.lower()
    # Old wording was "number of times to capture"; it must be gone after T8.
    assert "number of times to capture" not in help_text
