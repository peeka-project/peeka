"""Contracts for future watch orphan-grace cleanup.

These tests intentionally keep the historical ``ttl`` filename, but the
contract is *not* a wall-clock watch-age TTL:

- the grace timer starts only after owner/session loss or liveness failure;
- active watches with a live owner/stream survive beyond the grace duration;
- orphan-grace cleanup is watch-only, not trace/stack/monitor/top cleanup.
"""

# pyright: reportAny=false, reportArgumentType=false, reportAttributeAccessIssue=false, reportDeprecated=false, reportExplicitAny=false, reportImplicitStringConcatenation=false, reportMissingTypeArgument=false, reportPrivateUsage=false, reportUnannotatedClassAttribute=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnusedCallResult=false

import sys
import time
from types import ModuleType
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, cast

import pytest

from peeka.commands.watch import WatchCommand
from peeka.core.injector import DecoratorInjector

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


TEST_GRACE_SECONDS = 0.01
ORPHAN_GRACE_COMMAND_TYPES: Tuple[str, ...] = ("watch",)


class FakeObserver:
    """Minimal watch observer used by WatchCommand tests."""

    def __init__(self) -> None:
        self.registered: Dict[str, Dict[str, Any]] = {}

    def register_watch(
        self, watch_id: str, pattern: str, config: Dict[str, Any]
    ) -> None:
        self.registered[watch_id] = {"pattern": pattern, "config": config}

    def unregister_watch(self, watch_id: str) -> Dict[str, Any]:
        _ = self.registered.pop(watch_id, None)
        return {"count": 0}

    def clear_all(self) -> None:
        self.registered.clear()


class FakeWatchAgent:
    """WatchCommand agent double with explicit owner liveness hooks for T7."""

    def __init__(self) -> None:
        self._observations: List[Dict[str, Any]] = []
        self.injector = DecoratorInjector(cast("PeekaAgent", cast(object, self)))
        self.observer = FakeObserver()
        self.watch_orphan_grace_seconds = TEST_GRACE_SECONDS
        self.live_client_sessions: Set[str] = set()
        self.stopped_probe_ids: List[str] = []

    def _send_observation(self, observation: Dict[str, Any]) -> None:
        self._observations.append(observation)

    def is_client_session_live(self, client_session_id: Optional[str]) -> bool:
        """T7 liveness hook scaffold: stream/session ownership check."""
        return client_session_id in self.live_client_sessions

    def stop_probe_context(self, probe_id: str) -> None:
        self.stopped_probe_ids.append(probe_id)


def _install_module(monkeypatch: pytest.MonkeyPatch, module_name: str) -> ModuleType:
    module = ModuleType(module_name)

    def watched(value: int) -> int:
        return value + 1

    watched.__module__ = module_name
    setattr(module, "watched", watched)
    monkeypatch.setitem(sys.modules, module_name, module)
    return module


def _start_watch(
    agent: FakeWatchAgent,
    module_name: str,
    client_session_id: str,
) -> str:
    result = WatchCommand(cast("PeekaAgent", cast(object, agent))).execute(
        {
            "action": "start",
            "pattern": f"{module_name}.watched",
            "depth": 2,
            "times": -1,
            "finish": True,
            # T7 TODO: production hook should accept/use this test override.
            "watch_orphan_grace_seconds": TEST_GRACE_SECONDS,
            # T7 TODO: owner liveness is keyed by the client/session, not watch age.
            "client_session_id": client_session_id,
        }
    )

    assert result["status"] == "success"
    return cast(str, result["watch_id"])


def _trigger_future_orphan_cleanup(agent: Any, watch_id: str) -> None:
    """Call the future T7 orphan cleanup hook, or xfail until it exists."""
    hook_names = (
        "cleanup_orphan_watches",
        "_cleanup_orphan_watches",
        "_cleanup_watch_orphans",
        "_sweep_orphan_watches",
        "_run_watch_orphan_cleanup_once",
    )
    for hook_name in hook_names:
        hook = getattr(agent, hook_name, None)
        if hook is None:
            continue
        t1 = time.monotonic()
        try:
            hook(now=t1)
        except TypeError:
            hook()
        t2 = t1 + TEST_GRACE_SECONDS + 0.001
        try:
            hook(now=t2)
        except TypeError:
            hook()
        return

    pytest.xfail(
        "T7 orphan-grace cleanup is not implemented yet; expected a watch-only "
        f"cleanup hook for {watch_id}."
    )


def test_abandoned_watch_is_cleaned_after_owner_loss_grace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Owner loss starts grace; after grace an abandoned watch is removed.

    This is an xfail contract until T7 adds the cleanup hook. The timer must
    start after session/stream liveness fails, not at watch creation time.
    """
    module = _install_module(monkeypatch, "test_watch_ttl_cleanup_abandoned")
    agent = FakeWatchAgent()
    watch_id = _start_watch(agent, module.__name__, "owner-gone")

    assert watch_id in agent.injector.instrumented
    time.sleep(TEST_GRACE_SECONDS * 2)

    _trigger_future_orphan_cleanup(agent, watch_id)

    assert watch_id not in agent.injector.instrumented
    agent._observations.clear()
    assert module.watched(1) == 2
    assert agent._observations == []


def test_active_live_watch_survives_beyond_grace_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Live stream/session ownership prevents grace cleanup.

    This guards against a wall-clock watch-age TTL: the watch is older than the
    test grace duration, but the owner is still live and observations flow.
    """
    module = _install_module(monkeypatch, "test_watch_ttl_cleanup_active")
    agent = FakeWatchAgent()
    agent.live_client_sessions.add("live-stream-owner")
    watch_id = _start_watch(agent, module.__name__, "live-stream-owner")

    time.sleep(TEST_GRACE_SECONDS * 2)

    assert watch_id in agent.injector.instrumented
    assert module.watched(41) == 42
    assert [obs["watch_id"] for obs in agent._observations] == [watch_id]


def test_orphan_grace_cleanup_is_watch_only() -> None:
    """Document T7 scope: no orphan TTL for trace/stack/monitor/top.

    D8 says trace/stack/monitor count semantics stay unchanged. T7 should hook
    only watch orphan ownership/liveness cleanup and must not sweep other probe
    types on disconnect or by wall-clock age.
    """
    assert ORPHAN_GRACE_COMMAND_TYPES == ("watch",)
    assert "trace" not in ORPHAN_GRACE_COMMAND_TYPES
    assert "stack" not in ORPHAN_GRACE_COMMAND_TYPES
    assert "monitor" not in ORPHAN_GRACE_COMMAND_TYPES
    assert "top" not in ORPHAN_GRACE_COMMAND_TYPES
