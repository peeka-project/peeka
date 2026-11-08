"""Stop-order / reset / detach matrix for stacked probes on one callable.

Every combination of watch (W), stack (S), trace (T) and monitor (M) probes is
started on the same target (with a module alias, optionally behind a
``functools.wraps`` user decorator), then stopped in every order. After each
stop the target and alias are called and the test asserts:

* active probes still observe, stopped probes do not;
* canonical slot and alias stay identical;
* no stopped Peeka wrapper remains on the execution path;
* calls never block (stale wrappers used to hold the injector lock while
  calling into the next wrapper, deadlocking the caller).

After the last stop the canonical slot and alias must be the exact original
callable and all registries must be empty.
"""

import functools
import itertools
import sys
import threading
from types import ModuleType
from typing import Any, Callable, Dict, List, Tuple

import pytest

from peeka.commands.monitor import MonitorCommand
from peeka.core.injector import DecoratorInjector
from peeka.core.instrumentation.registry import wrapper_call_target
from peeka.core.runtime.compat import BACKEND_WRAPPER_ONLY

CALL_DEADLINE_SECONDS = 5.0

COMBOS = [
    "WW",
    "TT",
    "WT",
    "TW",
    "WTW",
    "TWT",
    "MM",
    "MW",
    "WM",
    "MT",
    "MS",
    "WMT",
    "MWM",
    "TMW",
    "SMW",
    "TMT",
    "WMTM",
    "WTMW",
]

Probe = Tuple[str, str]  # ("inj" | "mon", probe id)


class _Agent:
    def __init__(self) -> None:
        self._observations: List[Dict[str, Any]] = []
        self._lock = threading.Lock()
        self.injector: Any = None

    def _send_observation(self, obs: Dict[str, Any]) -> None:
        with self._lock:
            self._observations.append(obs)


class _Harness:
    """One target module + alias module + injector + monitor command."""

    _counter = itertools.count()

    def __init__(self, decorated: bool) -> None:
        n = next(self._counter)
        self.module_name = f"_stop_order_target_{n}"
        self.alias_module_name = f"_stop_order_alias_{n}"
        self.pattern = f"{self.module_name}.target"

        def raw(x: int) -> int:
            return x + 1

        if decorated:

            @functools.wraps(raw)
            def original(x: int) -> int:
                return raw(x)

        else:
            original = raw

        self.original: Callable[[int], int] = original
        self.module = ModuleType(self.module_name)
        setattr(self.module, "target", original)
        self.alias_module = ModuleType(self.alias_module_name)
        setattr(self.alias_module, "alias_target", original)
        sys.modules[self.module_name] = self.module
        sys.modules[self.alias_module_name] = self.alias_module

        self.agent = _Agent()
        self.injector = DecoratorInjector(self.agent)  # pyright: ignore[reportArgumentType]
        self.agent.injector = self.injector
        self.monitor_cmd = MonitorCommand(self.agent)  # pyright: ignore[reportArgumentType]
        self.all_wrapper_ids: set = set()

    def close(self) -> None:
        self.monitor_cmd.stop_active_resources(pattern=None, reason="test teardown")
        # A deadlocked call (the failure this module guards against) keeps the
        # injector lock forever; don't let teardown hang the whole session.
        if self.injector._lock.acquire(timeout=1):
            self.injector._lock.release()
            self.injector.uninject_all()
        sys.modules.pop(self.module_name, None)
        sys.modules.pop(self.alias_module_name, None)

    # -- probes -----------------------------------------------------------

    def start(self, kind: str) -> Probe:
        if kind == "W":
            probe: Probe = ("inj", self.injector.inject(self.pattern, {"depth": 1, "times": -1}))
        elif kind == "S":
            probe = (
                "inj",
                self.injector.inject(
                    self.pattern, {"depth": 1, "times": -1, "stack": True, "command": "stack"}
                ),
            )
        elif kind == "T":
            probe = (
                "inj",
                self.injector.inject_trace(
                    self.pattern, {"times": -1}, force_backend=BACKEND_WRAPPER_ONLY
                ),
            )
        else:
            result = self.monitor_cmd.execute(
                {"action": "start", "pattern": self.pattern, "cycle": 3600}
            )
            assert result["status"] == "success", result
            probe = ("mon", result["watch_id"])
        self.all_wrapper_ids |= {id(w) for w in self.live_wrappers()}
        return probe

    def stop(self, probe: Probe) -> None:
        if probe[0] == "inj":
            self.injector.uninject(probe[1])
        else:
            result = self.monitor_cmd.execute({"action": "stop", "watch_id": probe[1]})
            assert result["status"] == "success", result

    def live_wrappers(self) -> List[Any]:
        wrappers = [info["wrapper"] for info in self.injector.instrumented.values()]
        wrappers += [info["wrapper"] for info in self.monitor_cmd._monitors.values()]
        return wrappers

    def monitor_total(self, monitor_id: str) -> int:
        stats = self.monitor_cmd.manager.get_stats(monitor_id) or {}
        return int(stats.get("total", 0))

    # -- assertions -------------------------------------------------------

    def call_with_deadline(self, func: Callable[[int], int]) -> int:
        outcome: Dict[str, Any] = {}

        def run() -> None:
            try:
                outcome["value"] = func(1)
            except BaseException as exc:  # pragma: no cover - surfaced below
                outcome["error"] = exc

        worker = threading.Thread(target=run, daemon=True)
        worker.start()
        worker.join(CALL_DEADLINE_SECONDS)
        assert not worker.is_alive(), "call to instrumented target blocked (deadlock)"
        if "error" in outcome:
            raise outcome["error"]
        return outcome["value"]

    def execution_path(self) -> List[Any]:
        path = []
        current: Any = getattr(self.module, "target")
        for _ in range(32):
            path.append(current)
            if current is self.original:
                break
            nxt = wrapper_call_target(current)
            if nxt is None:
                break
            current = nxt
        return path

    def assert_routing(self, active: List[Probe], stopped: List[Probe], where: str) -> None:
        canonical = getattr(self.module, "target")
        alias = getattr(self.alias_module, "alias_target")
        assert canonical is alias, f"{where}: canonical and alias diverge"

        path = self.execution_path()
        assert path[-1] is self.original, f"{where}: execution path does not reach original"
        live_ids = {id(w) for w in self.live_wrappers()}
        stale = [w for w in path if id(w) in self.all_wrapper_ids and id(w) not in live_ids]
        assert not stale, f"{where}: stopped Peeka wrapper still on execution path"

        for label, func in (("canonical", canonical), ("alias", alias)):
            self.agent._observations.clear()
            before = {p[1]: self.monitor_total(p[1]) for p in active if p[0] == "mon"}
            assert self.call_with_deadline(func) == 2
            seen = {obs.get("watch_id") for obs in self.agent._observations}
            for probe in active:
                if probe[0] == "inj":
                    assert probe[1] in seen, f"{where} [{label}]: active {probe[1]} did not observe"
                else:
                    assert self.monitor_total(probe[1]) == before[probe[1]] + 1, (
                        f"{where} [{label}]: active monitor {probe[1]} not updated"
                    )
            for probe in stopped:
                if probe[0] == "inj":
                    assert probe[1] not in seen, f"{where} [{label}]: stopped {probe[1]} observed"

    def assert_fully_restored(self, where: str) -> None:
        assert getattr(self.module, "target") is self.original, f"{where}: canonical not restored"
        assert getattr(self.alias_module, "alias_target") is self.original, (
            f"{where}: alias not restored"
        )
        assert self.injector.instrumented == {}, f"{where}: injector probes left"
        assert self.monitor_cmd._monitors == {}, f"{where}: monitors left"


@pytest.mark.parametrize("decorated", [False, True], ids=["plain", "user_decorated"])
@pytest.mark.parametrize("combo", COMBOS)
def test_every_stop_order_keeps_routing_and_restores_original(combo: str, decorated: bool) -> None:
    for order in itertools.permutations(range(len(combo))):
        harness = _Harness(decorated)
        try:
            probes = [harness.start(kind) for kind in combo]
            harness.assert_routing(probes, [], f"{combo} started")
            active = list(probes)
            stopped: List[Probe] = []
            for step, idx in enumerate(order):
                harness.stop(probes[idx])
                active.remove(probes[idx])
                stopped.append(probes[idx])
                where = f"{combo} order={order} step={step} (stopped {combo[idx]}#{idx})"
                if active:
                    harness.assert_routing(active, stopped, where)
            harness.assert_fully_restored(f"{combo} order={order}")
        finally:
            harness.close()


@pytest.mark.parametrize("mode", ["reset", "detach"])
@pytest.mark.parametrize("decorated", [False, True], ids=["plain", "user_decorated"])
@pytest.mark.parametrize("combo", COMBOS)
def test_reset_and_detach_restore_original(combo: str, decorated: bool, mode: str) -> None:
    """Mirror ResetCommand / shutdown order: monitors first, then injector."""
    harness = _Harness(decorated)
    try:
        for kind in combo:
            harness.start(kind)
        if mode == "reset":
            harness.monitor_cmd.stop_active_resources(pattern=harness.pattern, reason="reset")
            harness.injector.reset(harness.pattern)
        else:
            harness.monitor_cmd.stop_active_resources(pattern=None, reason="detach")
            harness.injector.uninject_all()
        harness.assert_fully_restored(f"{combo} {mode}")
        assert harness.call_with_deadline(getattr(harness.module, "target")) == 2
    finally:
        harness.close()


def test_trace_times_limit_over_watch_does_not_deadlock() -> None:
    """A trace that reached its -n limit must not call inner wrappers under the lock."""
    harness = _Harness(decorated=False)
    try:
        watch_id = harness.injector.inject(harness.pattern, {"depth": 1, "times": -1})
        harness.injector.inject_trace(
            harness.pattern, {"times": 1}, force_backend=BACKEND_WRAPPER_ONLY
        )
        target = getattr(harness.module, "target")
        assert harness.call_with_deadline(target) == 2
        harness.agent._observations.clear()
        assert harness.call_with_deadline(target) == 2
        assert [obs["watch_id"] for obs in harness.agent._observations] == [watch_id]
    finally:
        harness.close()
