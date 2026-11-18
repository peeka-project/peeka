"""Regression tests for trace hook dispatchers, concurrency, greenlet, and probe transparency."""

import asyncio
import sys
import types
from typing import Any, Dict, List

import pytest

from peeka.commands.monitor import MonitorCommand
from peeka.core.injector import DecoratorInjector
from peeka.core.instrumentation import trace as trace_mod
from peeka.core.instrumentation.trace_backends import _is_coroutine_yield_return
from peeka.core.runtime.compat import (
    BACKEND_SETTRACE,
    BACKEND_SYS_MONITORING,
    BACKEND_WRAPPER_ONLY,
)


class MockAgent:
    """Minimal injector agent capturing observations."""

    def __init__(self) -> None:
        self._observations: List[Dict[str, Any]] = []

    def _send_observation(self, observation: Dict[str, Any]) -> None:
        self._observations.append(observation)


@pytest.fixture(autouse=True)
def _reset_trace_state():
    """Ensure clean sys.gettrace and gevent cache around each test."""
    orig_trace = sys.gettrace()
    orig_cache = trace_mod._GEVENT_PATCHED_CACHE
    trace_mod._GEVENT_PATCHED_CACHE = None
    try:
        yield
    finally:
        sys.settrace(orig_trace)
        trace_mod._GEVENT_PATCHED_CACHE = orig_cache


def _occupy_all_monitoring_slots() -> List[int]:
    """Claim all free sys.monitoring tool IDs and return the ones we claimed."""
    claimed: List[int] = []
    for tool_id in range(6):
        if sys.monitoring.get_tool(tool_id) is None:
            sys.monitoring.use_tool_id(tool_id, f"test-slot-{tool_id}")
            claimed.append(tool_id)
    return claimed


def _free_monitoring_slots(claimed: List[int]) -> None:
    """Release sys.monitoring tool IDs claimed by _occupy_all_monitoring_slots."""
    for tool_id in claimed:
        try:
            sys.monitoring.set_events(tool_id, 0)
        except ValueError:
            pass
        try:
            sys.monitoring.free_tool_id(tool_id)
        except ValueError:
            pass


@pytest.mark.unit
class TestConcurrentCoroutineTracerIsolation:
    """Concurrent coroutines must not corrupt sys.gettrace or exhaust monitoring slots."""

    @pytest.mark.parametrize("backend", [None, BACKEND_SETTRACE])
    def test_cancelled_coroutine_does_not_clobber_active_sibling_or_leak_tracer(
        self, monkeypatch: pytest.MonkeyPatch, backend: Any
    ) -> None:
        """Cancelling task A keeps task B tracing and restores sys.gettrace to None."""
        mod = types.ModuleType("test_conc_cancel_mod")

        def sibling_callee() -> int:
            return 7

        async def hold(gate: asyncio.Event, tag: str) -> str:
            await gate.wait()
            if tag == "B":
                sibling_callee()
            return tag

        sibling_callee.__module__ = mod.__name__
        hold.__module__ = mod.__name__
        mod.sibling_callee = sibling_callee  # type: ignore[attr-defined]
        mod.hold = hold  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, mod.__name__, mod)

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        injector.inject_trace(
            f"{mod.__name__}.hold", {}, force_backend=backend
        )

        async def run() -> None:
            gates = [asyncio.Event(), asyncio.Event()]
            task_a = asyncio.create_task(mod.hold(gates[0], "A"))
            task_b = asyncio.create_task(mod.hold(gates[1], "B"))
            await asyncio.sleep(0)

            task_a.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task_a

            if backend == BACKEND_SETTRACE or not hasattr(sys, "monitoring"):
                assert sys.gettrace() is not None

            gates[1].set()
            assert await task_b == "B"
            assert sys.gettrace() is None

        try:
            asyncio.run(run())
            assert sys.gettrace() is None
            assert len(agent._observations) == 1
            callees = [c["function"] for c in agent._observations[0]["call_tree"]]
            assert any("sibling_callee" in fn for fn in callees)
        finally:
            injector.uninject_all()

    def test_out_of_order_completion_keeps_remaining_task_isolated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Task finishing earlier must not detach tracer from still-running sibling."""
        mod = types.ModuleType("test_conc_ooo_mod")

        def callee_a() -> int:
            return 1

        def callee_b() -> int:
            return 2

        async def work(gate: asyncio.Event, which: str) -> str:
            await gate.wait()
            return str(callee_a() if which == "A" else callee_b())

        for fn in (callee_a, callee_b, work):
            fn.__module__ = mod.__name__
        mod.callee_a = callee_a  # type: ignore[attr-defined]
        mod.callee_b = callee_b  # type: ignore[attr-defined]
        mod.work = work  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, mod.__name__, mod)

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        injector.inject_trace(
            f"{mod.__name__}.work", {}, force_backend=BACKEND_SETTRACE
        )

        async def run() -> None:
            gate_a, gate_b = asyncio.Event(), asyncio.Event()
            task_a = asyncio.create_task(mod.work(gate_a, "A"))
            task_b = asyncio.create_task(mod.work(gate_b, "B"))
            await asyncio.sleep(0)

            gate_a.set()
            assert await task_a == "1"
            assert sys.gettrace() is not None

            gate_b.set()
            assert await task_b == "2"
            assert sys.gettrace() is None

        try:
            asyncio.run(run())
            assert len(agent._observations) == 2
            first_callees = [c["function"] for c in agent._observations[0]["call_tree"]]
            second_callees = [c["function"] for c in agent._observations[1]["call_tree"]]
            assert any("callee_a" in fn for fn in first_callees)
            assert not any("callee_b" in fn for fn in first_callees)
            assert any("callee_b" in fn for fn in second_callees)
            assert not any("callee_a" in fn for fn in second_callees)
        finally:
            injector.uninject_all()

    @pytest.mark.skipif(not hasattr(sys, "monitoring"), reason="requires sys.monitoring")
    def test_ten_concurrent_coroutines_share_single_monitoring_slot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """More than 6 concurrent tasks share 1 monitoring slot and never touch settrace."""
        mod = types.ModuleType("test_conc_ten_mod")

        def task_helper(idx: int) -> int:
            return idx + 1

        async def hold(gate: asyncio.Event, idx: int) -> int:
            await gate.wait()
            return task_helper(idx)

        task_helper.__module__ = mod.__name__
        hold.__module__ = mod.__name__
        mod.task_helper = task_helper  # type: ignore[attr-defined]
        mod.hold = hold  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, mod.__name__, mod)

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        injector.inject_trace(f"{mod.__name__}.hold", {})

        async def run() -> None:
            gates = [asyncio.Event() for _ in range(10)]
            tasks = [asyncio.create_task(mod.hold(g, idx)) for idx, g in enumerate(gates)]
            await asyncio.sleep(0)

            peeka_tools = [
                tid
                for tid in range(6)
                if sys.monitoring.get_tool(tid) == "peeka-trace"
            ]
            assert len(peeka_tools) == 1
            assert sys.gettrace() is None

            for gate in gates:
                gate.set()
            results = await asyncio.gather(*tasks)
            assert results == list(range(1, 11))
            assert sys.gettrace() is None
            remaining_tools = [
                tid
                for tid in range(6)
                if sys.monitoring.get_tool(tid) == "peeka-trace"
            ]
            assert remaining_tools == []

        try:
            asyncio.run(run())
            assert len(agent._observations) == 10
            for obs in agent._observations:
                assert any("task_helper" in c["function"] for c in obs["call_tree"])
        finally:
            injector.uninject_all()

    def test_legacy_39_yield_from_unwind_vs_suspension(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """On Python < 3.10, suspension precedes YIELD_FROM while unwind points at YIELD_FROM."""
        import dis

        synthetic_opname = list(dis.opname)
        load_const_op = dis.opmap["LOAD_CONST"]
        if "YIELD_FROM" in dis.opmap and dis.opmap["YIELD_FROM"] < 256:
            yield_from_op = dis.opmap["YIELD_FROM"]
        else:
            yield_from_op = 72
            synthetic_opname[yield_from_op] = "YIELD_FROM"
            monkeypatch.setattr(dis, "opname", synthetic_opname)

        fake_code = types.SimpleNamespace(
            co_code=bytes([load_const_op, 0, yield_from_op, 0])
        )
        monkeypatch.setattr(sys, "version_info", (3, 9, 25))

        suspended_frame = types.SimpleNamespace(
            f_code=fake_code, f_lasti=0
        )
        unwind_frame = types.SimpleNamespace(
            f_code=fake_code, f_lasti=2
        )
        assert _is_coroutine_yield_return(suspended_frame) is True
        assert _is_coroutine_yield_return(unwind_frame) is False


@pytest.mark.unit
class TestSharedHookDispatcherProtection:
    """Shared settrace dispatcher must forward to and restore pre-existing tracers."""

    def test_concurrent_coroutines_preserve_and_forward_existing_tracer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pre-existing user tracer still observes events during & after concurrent traces."""
        mod = types.ModuleType("test_existing_tracer_mod")
        observed_events: List[Any] = []

        def previous(frame: Any, event: str, _arg: Any) -> Any:
            if frame.f_code.co_filename == __file__ or event == "call":
                observed_events.append((event, frame.f_code.co_name))
            return previous

        def callee() -> int:
            return 42

        async def hold(gate: asyncio.Event) -> int:
            await gate.wait()
            return callee()

        callee.__module__ = mod.__name__
        hold.__module__ = mod.__name__
        mod.callee = callee  # type: ignore[attr-defined]
        mod.hold = hold  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, mod.__name__, mod)

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        injector.inject_trace(
            f"{mod.__name__}.hold", {}, force_backend=BACKEND_SETTRACE
        )

        async def run() -> None:
            sys.settrace(previous)
            gates = [asyncio.Event(), asyncio.Event()]
            task_a = asyncio.create_task(mod.hold(gates[0]))
            task_b = asyncio.create_task(mod.hold(gates[1]))
            await asyncio.sleep(0)

            task_a.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task_a

            gates[1].set()
            assert await task_b == 42
            assert sys.gettrace() is previous

        try:
            asyncio.run(run())
            assert ("call", "callee") in observed_events
            assert ("return", "callee") in observed_events
            assert ("line", "callee") in observed_events
        finally:
            sys.settrace(None)
            injector.uninject_all()

    @pytest.mark.skipif(not hasattr(sys, "monitoring"), reason="requires sys.monitoring")
    def test_slots_exhausted_without_gevent_falls_back_and_protects_tracer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without gevent, full monitoring slots fall back to settrace safely."""
        mod = types.ModuleType("test_slots_no_gevent_mod")
        seen_by_prev: List[str] = []

        def previous(frame: Any, event: str, _arg: Any) -> Any:
            if event == "call":
                seen_by_prev.append(frame.f_code.co_name)
            return previous

        def child() -> int:
            return 9

        def root() -> int:
            return child()

        child.__module__ = mod.__name__
        root.__module__ = mod.__name__
        mod.child = child  # type: ignore[attr-defined]
        mod.root = root  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, mod.__name__, mod)

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        injector.inject_trace(
            f"{mod.__name__}.root", {}, force_backend=BACKEND_SYS_MONITORING
        )

        claimed = _occupy_all_monitoring_slots()
        try:
            sys.settrace(previous)
            assert mod.root() == 9
            assert sys.gettrace() is previous
            assert "child" in seen_by_prev
            callees = [c["function"] for c in agent._observations[0]["call_tree"]]
            assert any("child" in fn for fn in callees)
        finally:
            sys.settrace(None)
            _free_monitoring_slots(claimed)
            injector.uninject_all()


@pytest.mark.unit
class TestGeventSlotExhaustionDowngrade:
    """When sys.monitoring slots are full under gevent, trace must safely downgrade."""

    @pytest.mark.skipif(not hasattr(sys, "monitoring"), reason="requires sys.monitoring")
    @pytest.mark.parametrize("backend", [None, BACKEND_SYS_MONITORING])
    def test_sync_monitoring_slots_full_under_gevent_downgrades_to_wrapper_only(
        self, monkeypatch: pytest.MonkeyPatch, backend: Any
    ) -> None:
        """Sync trace must never install sys.settrace when slots are exhausted under gevent."""
        fake_monkey = types.ModuleType("gevent.monkey")
        fake_monkey.is_module_patched = lambda _name: True  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "gevent.monkey", fake_monkey)

        mod = types.ModuleType("test_slots_gevent_sync_mod")

        def probe() -> bool:
            return sys.gettrace() is not None

        probe.__module__ = mod.__name__
        mod.probe = probe  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, mod.__name__, mod)

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        injector.inject_trace(
            f"{mod.__name__}.probe", {}, force_backend=backend
        )

        claimed = _occupy_all_monitoring_slots()
        try:
            assert mod.probe() is False
            assert sys.gettrace() is None
            obs = agent._observations[0]
            assert obs["call_tree"] == []
            trace_meta = obs["runtime_meta"]["trace"]
            assert trace_meta["downgraded"] is True
            assert trace_meta["effective_backend"] == BACKEND_WRAPPER_ONLY
            assert trace_meta["gevent_patched_now"] is True
        finally:
            _free_monitoring_slots(claimed)
            injector.uninject_all()

    @pytest.mark.skipif(not hasattr(sys, "monitoring"), reason="requires sys.monitoring")
    def test_async_monitoring_slots_full_under_gevent_downgrades_to_wrapper_only(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Async trace must never install sys.settrace when slots are exhausted under gevent."""
        fake_monkey = types.ModuleType("gevent.monkey")
        fake_monkey.is_module_patched = lambda _name: True  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "gevent.monkey", fake_monkey)

        mod = types.ModuleType("test_slots_gevent_async_mod")

        async def probe() -> bool:
            await asyncio.sleep(0)
            return sys.gettrace() is not None

        probe.__module__ = mod.__name__
        mod.probe = probe  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, mod.__name__, mod)

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        injector.inject_trace(
            f"{mod.__name__}.probe", {}, force_backend=BACKEND_SYS_MONITORING
        )

        claimed = _occupy_all_monitoring_slots()
        try:
            assert asyncio.run(mod.probe()) is False
            assert sys.gettrace() is None
            obs = agent._observations[0]
            assert obs["call_tree"] == []
            trace_meta = obs["runtime_meta"]["trace"]
            assert trace_meta["downgraded"] is True
            assert trace_meta["effective_backend"] == BACKEND_WRAPPER_ONLY
        finally:
            _free_monitoring_slots(claimed)
            injector.uninject_all()


@pytest.mark.unit
class TestGreenletSameThreadIsolation:
    """Greenlets sharing an OS thread must never misattribute calls across greenlets."""

    @pytest.mark.parametrize("backend", [BACKEND_SETTRACE, BACKEND_SYS_MONITORING])
    def test_simulated_greenlet_switch_excludes_other_greenlet_calls(
        self, monkeypatch: pytest.MonkeyPatch, backend: Any
    ) -> None:
        """Calls executed while switched to another greenlet are excluded from call_tree."""
        if backend == BACKEND_SYS_MONITORING and not hasattr(sys, "monitoring"):
            pytest.skip("requires sys.monitoring")

        g_main = object()
        g_worker = object()
        current_holder = [g_worker]

        fake_greenlet = types.ModuleType("greenlet")
        fake_greenlet.getcurrent = lambda: current_holder[0]  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "greenlet", fake_greenlet)

        mod = types.ModuleType("test_sim_greenlet_mod")

        def worker_callee() -> int:
            return 10

        def unrelated() -> int:
            return 20

        def root() -> int:
            worker_callee()
            current_holder[0] = g_main
            unrelated()
            current_holder[0] = g_worker
            return 42

        for fn in (worker_callee, unrelated, root):
            fn.__module__ = mod.__name__
        mod.worker_callee = worker_callee  # type: ignore[attr-defined]
        mod.unrelated = unrelated  # type: ignore[attr-defined]
        mod.root = root  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, mod.__name__, mod)

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        injector.inject_trace(f"{mod.__name__}.root", {}, force_backend=backend)

        try:
            assert mod.root() == 42
            callees = [c["function"] for c in agent._observations[0]["call_tree"]]
            assert any("worker_callee" in fn for fn in callees)
            assert not any("unrelated" in fn for fn in callees)
        finally:
            injector.uninject_all()

    @pytest.mark.parametrize("backend", [BACKEND_SETTRACE, BACKEND_SYS_MONITORING])
    def test_real_greenlet_switch_isolation(
        self, monkeypatch: pytest.MonkeyPatch, backend: Any
    ) -> None:
        """Real greenlet switches on the same OS thread stay isolated per greenlet."""
        if backend == BACKEND_SYS_MONITORING and not hasattr(sys, "monitoring"):
            pytest.skip("requires sys.monitoring")
        greenlet_mod = pytest.importorskip("greenlet")

        mod = types.ModuleType("test_real_greenlet_mod")

        def g_callee() -> int:
            return 3

        def g2_callee() -> int:
            return 5

        def unrelated() -> int:
            return 17

        def root() -> int:
            g_callee()
            greenlet_mod.getcurrent().parent.switch()
            return 42

        def other() -> int:
            g2_callee()
            greenlet_mod.getcurrent().parent.switch()
            return 99

        for fn in (g_callee, g2_callee, unrelated, root, other):
            fn.__module__ = mod.__name__
        mod.g_callee = g_callee  # type: ignore[attr-defined]
        mod.g2_callee = g2_callee  # type: ignore[attr-defined]
        mod.unrelated = unrelated  # type: ignore[attr-defined]
        mod.root = root  # type: ignore[attr-defined]
        mod.other = other  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, mod.__name__, mod)

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        root_id = injector.inject_trace(
            f"{mod.__name__}.root", {}, force_backend=backend
        )
        other_id = injector.inject_trace(
            f"{mod.__name__}.other", {}, force_backend=backend
        )

        try:
            g1 = greenlet_mod.greenlet(mod.root)
            g2 = greenlet_mod.greenlet(mod.other)
            g1.switch()
            unrelated()
            g2.switch()
            assert g1.switch() == 42
            assert g2.switch() == 99

            obs_by_id = {
                obs["watch_id"]: [c["function"] for c in obs["call_tree"]]
                for obs in agent._observations
            }
            root_callees = obs_by_id[root_id]
            other_callees = obs_by_id[other_id]

            assert any("g_callee" in fn for fn in root_callees)
            assert not any("unrelated" in fn for fn in root_callees)
            assert not any("g2_callee" in fn for fn in root_callees)

            assert any("g2_callee" in fn for fn in other_callees)
            assert not any("unrelated" in fn for fn in other_callees)
            assert not any("g_callee" in fn for fn in other_callees)
        finally:
            injector.uninject_all()


def _build_exec_module(
    monkeypatch: pytest.MonkeyPatch, name: str, source: str
) -> types.ModuleType:
    """Create a module with top-level functions defined in its own globals."""
    mod = types.ModuleType(name)
    mod.__file__ = f"/{name}.py"
    exec(compile(source, mod.__file__, "exec"), mod.__dict__)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


@pytest.mark.unit
class TestParentChildProbeTransparency:
    """Simultaneous parent & child probes must show business callees, not Peeka wrappers."""

    @pytest.mark.parametrize("backend", [BACKEND_SETTRACE, BACKEND_SYS_MONITORING])
    def test_parent_and_child_both_traced_show_business_callees(
        self, monkeypatch: pytest.MonkeyPatch, backend: Any
    ) -> None:
        """Parent's call_tree records child business function rather than trace wrapper."""
        if backend == BACKEND_SYS_MONITORING and not hasattr(sys, "monitoring"):
            pytest.skip("requires sys.monitoring")

        mod = _build_exec_module(
            monkeypatch,
            "test_parent_child_trace_mod",
            (
                "def grandchild(x):\n"
                "    return x + 1\n"
                "def child(x):\n"
                "    return grandchild(x) * 2\n"
                "def parent(x):\n"
                "    return child(x) + 10\n"
            ),
        )

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        parent_id = injector.inject_trace(
            f"{mod.__name__}.parent", {}, force_backend=backend
        )
        child_id = injector.inject_trace(
            f"{mod.__name__}.child", {}, force_backend=backend
        )

        try:
            assert mod.parent(5) == 22
            obs_by_id = {
                obs["watch_id"]: [c["function"] for c in obs["call_tree"]]
                for obs in agent._observations
            }
            assert obs_by_id[parent_id] == [f"{mod.__name__}.child"]
            assert obs_by_id[child_id] == [f"{mod.__name__}.grandchild"]
        finally:
            injector.uninject_all()

    @pytest.mark.parametrize("backend", [BACKEND_SETTRACE, BACKEND_SYS_MONITORING])
    def test_parent_traced_child_watched_with_condition_skips_watch_overhead(
        self, monkeypatch: pytest.MonkeyPatch, backend: Any
    ) -> None:
        """Child watch wrapper and its SimpleEval condition overhead stay transparent."""
        if backend == BACKEND_SYS_MONITORING and not hasattr(sys, "monitoring"):
            pytest.skip("requires sys.monitoring")

        mod = _build_exec_module(
            monkeypatch,
            "test_parent_trace_child_watch_mod",
            (
                "def grandchild(x):\n"
                "    return x + 1\n"
                "def child(x):\n"
                "    return grandchild(x)\n"
                "def parent(x):\n"
                "    return child(x)\n"
            ),
        )

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        trace_id = injector.inject_trace(
            f"{mod.__name__}.parent",
            {"skip_builtin": False},
            force_backend=backend,
        )
        watch_id = injector.inject(
            f"{mod.__name__}.child",
            {"condition_express": "params[0] > 0"},
        )

        try:
            assert mod.parent(5) == 6
            obs_by_id = {obs["watch_id"]: obs for obs in agent._observations}
            assert watch_id in obs_by_id
            parent_callees = [c["function"] for c in obs_by_id[trace_id]["call_tree"]]
            assert parent_callees == [f"{mod.__name__}.child"]
        finally:
            injector.uninject_all()

    @pytest.mark.parametrize("backend", [BACKEND_SETTRACE, BACKEND_SYS_MONITORING])
    def test_parent_traced_child_monitored_shows_business_callee(
        self, monkeypatch: pytest.MonkeyPatch, backend: Any
    ) -> None:
        """Child MonitorCommand wrapper stays transparent in parent trace call_tree."""
        if backend == BACKEND_SYS_MONITORING and not hasattr(sys, "monitoring"):
            pytest.skip("requires sys.monitoring")

        mod = _build_exec_module(
            monkeypatch,
            "test_parent_trace_child_monitor_mod",
            (
                "def child(x):\n"
                "    return x * 3\n"
                "def parent(x):\n"
                "    return child(x) + 1\n"
            ),
        )

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        agent.injector = injector  # type: ignore[attr-defined]
        monitor_cmd = MonitorCommand(agent)  # type: ignore[arg-type]

        mon_res = monitor_cmd.execute(
            {"action": "start", "pattern": f"{mod.__name__}.child", "cycle": 60}
        )
        assert mon_res["status"] == "success"
        trace_id = injector.inject_trace(
            f"{mod.__name__}.parent", {}, force_backend=backend
        )

        try:
            assert mod.parent(4) == 13
            obs_by_id = {obs["watch_id"]: obs for obs in agent._observations}
            parent_callees = [c["function"] for c in obs_by_id[trace_id]["call_tree"]]
            assert parent_callees == [f"{mod.__name__}.child"]
        finally:
            monitor_cmd.stop_active_resources(None, "test_cleanup")
            injector.uninject_all()

    @pytest.mark.parametrize("backend", [BACKEND_SETTRACE, BACKEND_SYS_MONITORING])
    def test_stacked_watch_and_trace_on_parent_with_traced_child(
        self, monkeypatch: pytest.MonkeyPatch, backend: Any
    ) -> None:
        """Stacked watch+trace on parent still records child business function only."""
        if backend == BACKEND_SYS_MONITORING and not hasattr(sys, "monitoring"):
            pytest.skip("requires sys.monitoring")

        mod = _build_exec_module(
            monkeypatch,
            "test_stacked_parent_child_mod",
            (
                "def grandchild(x):\n"
                "    return x + 1\n"
                "def child(x):\n"
                "    return grandchild(x) * 2\n"
                "def parent(x):\n"
                "    return child(x) + 10\n"
            ),
        )

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        parent_watch_id = injector.inject(f"{mod.__name__}.parent", {})
        parent_trace_id = injector.inject_trace(
            f"{mod.__name__}.parent", {}, force_backend=backend
        )
        child_trace_id = injector.inject_trace(
            f"{mod.__name__}.child", {}, force_backend=backend
        )

        try:
            assert mod.parent(5) == 22
            obs_by_id = {obs["watch_id"]: obs for obs in agent._observations}
            assert parent_watch_id in obs_by_id
            assert [c["function"] for c in obs_by_id[parent_trace_id]["call_tree"]] == [
                f"{mod.__name__}.child"
            ]
            assert [c["function"] for c in obs_by_id[child_trace_id]["call_tree"]] == [
                f"{mod.__name__}.grandchild"
            ]
        finally:
            injector.uninject_all()

    @pytest.mark.parametrize("backend", [BACKEND_SETTRACE, BACKEND_SYS_MONITORING])
    def test_async_parent_and_child_both_traced_show_business_callees(
        self, monkeypatch: pytest.MonkeyPatch, backend: Any
    ) -> None:
        """Async parent traced alongside async child records child business coroutine."""
        if backend == BACKEND_SYS_MONITORING and not hasattr(sys, "monitoring"):
            pytest.skip("requires sys.monitoring")

        mod = _build_exec_module(
            monkeypatch,
            "test_async_parent_child_mod",
            (
                "import asyncio\n"
                "async def grandchild(x):\n"
                "    await asyncio.sleep(0.01)\n"
                "    return x + 1\n"
                "async def child(x):\n"
                "    return await grandchild(x) * 2\n"
                "async def parent(x):\n"
                "    return await child(x) + 10\n"
            ),
        )

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # type: ignore[arg-type]
        parent_trace_id = injector.inject_trace(
            f"{mod.__name__}.parent", {}, force_backend=backend
        )
        child_trace_id = injector.inject_trace(
            f"{mod.__name__}.child", {}, force_backend=backend
        )

        try:
            assert asyncio.run(mod.parent(5)) == 22
            obs_by_id = {obs["watch_id"]: obs for obs in agent._observations}
            assert [c["function"] for c in obs_by_id[parent_trace_id]["call_tree"]] == [
                f"{mod.__name__}.child"
            ]
            assert [c["function"] for c in obs_by_id[child_trace_id]["call_tree"]] == [
                f"{mod.__name__}.grandchild"
            ]
        finally:
            injector.uninject_all()

    @pytest.mark.parametrize("backend", [BACKEND_SETTRACE, BACKEND_SYS_MONITORING])
    def test_async_parent_records_watched_child(self, monkeypatch, backend):
        if backend == BACKEND_SYS_MONITORING and not hasattr(sys, "monitoring"):
            pytest.skip("requires sys.monitoring")

        mod = _build_exec_module(
            monkeypatch,
            "test_trace_async_watched_child",
            "async def child(): return 3\nasync def parent(): return await child()\n",
        )
        agent = MockAgent()
        injector = DecoratorInjector(agent)
        try:
            child_id = injector.inject(f"{mod.__name__}.child", {})
            parent_id = injector.inject_trace(f"{mod.__name__}.parent", {}, force_backend=backend)
            assert asyncio.run(mod.parent()) == 3
            observations = {obs["watch_id"]: obs for obs in agent._observations}
            assert observations[child_id]["returnObj"] == 3
            assert [node["function"] for node in observations[parent_id]["call_tree"]] == [
                f"{mod.__name__}.child"
            ]
        finally:
            injector.uninject_all()
