"""Tests for monitor command - statistics collection."""

import asyncio
import functools
import inspect
import sys
import threading
import time
from types import ModuleType
from typing import Any, Callable, cast

import pytest

from peeka.commands.monitor import MonitorCommand
from peeka.core.runtime.compat import BACKEND_WRAPPER_ONLY


def _assert_no_inactive_peeka_wrappers(func: Any, live_wrappers: set) -> None:
    inner = getattr(func, "__wrapped__", None)
    if inner is None:
        return
    if inner in live_wrappers:
        return
    stale_next = getattr(inner, "__wrapped__", None)
    assert stale_next is None, (
        f"Inactive Peeka wrapper at depth 1: {func!r}.__wrapped__ = "
        f"{inner!r} (not live, but has __wrapped__ = {stale_next!r}). "
        f"Live wrappers: {live_wrappers}"
    )


class MockAgent:
    """Mock agent for testing commands without full PeekaAgent setup."""

    def __init__(self):
        self._observations = []
        self._lock = threading.Lock()
        self.injector: Any = None

    def _send_observation(self, obs):
        with self._lock:
            self._observations.append(obs)


@pytest.fixture
def mock_agent():
    return MockAgent()


@pytest.fixture
def monitor_cmd(mock_agent):
    cmd = MonitorCommand(mock_agent)
    yield cmd
    # Ensure any lingering monitor timer threads are stopped between tests.
    cmd.stop_active_resources(pattern=None, reason="test teardown")


@pytest.fixture
def test_module():
    """Create synthetic test module with functions."""
    module = type(sys)("test_monitor_module")

    def fast_function(x):
        return x * 2

    def slow_function(x):
        time.sleep(0.01)
        return x * 2

    def failing_function(x):
        if x < 0:
            raise ValueError("Negative input")
        return x * 2

    module.fast_function = fast_function
    module.slow_function = slow_function
    module.failing_function = failing_function

    sys.modules["test_monitor_module"] = module
    yield module
    del sys.modules["test_monitor_module"]


class TestMonitorCommand:
    """Test monitor command - statistics collection."""

    def _make_mixed_monitor_target(self, module_name):
        def monitored_function(value):
            return value + 10

        test_module = ModuleType(module_name)
        setattr(test_module, "monitored_function", monitored_function)
        sys.modules[module_name] = test_module
        return test_module, monitored_function

    def _call_monitored(self, test_module, value):
        monitored = cast(
            Callable[[int], int], getattr(test_module, "monitored_function")
        )
        return monitored(value)

    def _build_mixed_probe_tools(self):
        from peeka.core.injector import DecoratorInjector

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]
        agent.injector = injector
        monitor_cmd = MonitorCommand(agent)  # pyright: ignore[reportArgumentType]
        return agent, injector, monitor_cmd

    def _start_monitor(self, monitor_cmd, pattern):
        result = monitor_cmd.execute(
            {"action": "start", "pattern": pattern, "cycle": 60}
        )
        assert result["status"] == "success"
        return cast(str, result["watch_id"])

    def _assert_monitor_total(self, monitor_cmd, monitor_id, total):
        assert monitor_id is not None
        stats = monitor_cmd.manager.get_stats(monitor_id)
        assert stats is not None
        assert stats["total"] == total

    def _start_injector_probe(self, injector, pattern, probe_kind):
        if probe_kind == "watch":
            return injector.inject(pattern, {"depth": 2, "times": -1})
        return injector.inject_trace(
            pattern,
            {"trace_depth": 2, "times": -1},
            force_backend=BACKEND_WRAPPER_ONLY,
        )

    def _exercise_injector_probe_then_monitor_lifecycle(self, probe_kind):
        agent, injector, monitor_cmd = self._build_mixed_probe_tools()
        module_name = f"test_{probe_kind}_monitor_lifecycle_probe_first"
        test_module, true_original_function = self._make_mixed_monitor_target(
            module_name
        )
        pattern = f"{module_name}.monitored_function"
        probe_id = None
        monitor_id = None

        try:
            probe_id = self._start_injector_probe(injector, pattern, probe_kind)
            monitor_id = self._start_monitor(monitor_cmd, pattern)

            assert self._call_monitored(test_module, 1) == 11
            assert [obs["watch_id"] for obs in agent._observations] == [probe_id]
            self._assert_monitor_total(monitor_cmd, monitor_id, 1)

            agent._observations.clear()
            injector.uninject(probe_id)
            probe_id = None

            assert self._call_monitored(test_module, 2) == 12
            assert agent._observations == []
            self._assert_monitor_total(monitor_cmd, monitor_id, 2)

            result = monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            assert result["status"] == "success"
            assert result["final_stats"]["total"] == 2
            monitor_id = None

            assert self._call_monitored(test_module, 3) == 13
            assert agent._observations == []
            assert getattr(test_module, "monitored_function") is true_original_function
        finally:
            if probe_id in injector.instrumented:
                injector.uninject(probe_id)
            if monitor_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            injector.uninject_all()
            setattr(test_module, "monitored_function", true_original_function)
            del sys.modules[module_name]

    def _assert_monitor_chain_boundary(self, test_module, original_code):
        wrapped = getattr(test_module, "monitored_function")
        wrapped_any = cast(Any, wrapped)
        assert hasattr(wrapped_any, "__wrapped__")
        unwrapped = inspect.unwrap(wrapped)
        assert unwrapped.__code__ is original_code
        assert wrapped.__code__ is not original_code

    def _exercise_monitor_then_injector_probe_lifecycle(
        self, probe_kind, assert_chain=False
    ):
        agent, injector, monitor_cmd = self._build_mixed_probe_tools()
        module_name = f"test_{probe_kind}_monitor_lifecycle_monitor_first"
        test_module, true_original_function = self._make_mixed_monitor_target(
            module_name
        )
        pattern = f"{module_name}.monitored_function"
        monitor_id = None
        probe_id = None
        original_code = true_original_function.__code__

        try:
            monitor_id = self._start_monitor(monitor_cmd, pattern)
            if assert_chain:
                self._assert_monitor_chain_boundary(test_module, original_code)
            probe_id = self._start_injector_probe(injector, pattern, probe_kind)

            assert self._call_monitored(test_module, 1) == 11
            self._assert_monitor_total(monitor_cmd, monitor_id, 1)
            assert [obs["watch_id"] for obs in agent._observations] == [probe_id]

            agent._observations.clear()
            result = monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            assert result["status"] == "success"
            assert result["final_stats"]["total"] == 1
            monitor_id = None

            assert self._call_monitored(test_module, 2) == 12
            assert [obs["watch_id"] for obs in agent._observations] == [probe_id]

            agent._observations.clear()
            injector.uninject(probe_id)
            probe_id = None

            assert self._call_monitored(test_module, 3) == 13
            assert agent._observations == []
            assert getattr(test_module, "monitored_function") is true_original_function
        finally:
            if probe_id in injector.instrumented:
                injector.uninject(probe_id)
            if monitor_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            injector.uninject_all()
            setattr(test_module, "monitored_function", true_original_function)
            del sys.modules[module_name]

    def test_watch_monitor_lifecycle_watch_stops_first_keeps_monitor_active(self):
        self._exercise_injector_probe_then_monitor_lifecycle("watch")

    def test_watch_monitor_lifecycle_monitor_stops_first_keeps_watch_active(self):
        self._exercise_monitor_then_injector_probe_lifecycle("watch")

    def test_trace_monitor_lifecycle_trace_stops_first_keeps_monitor_active(self):
        self._exercise_injector_probe_then_monitor_lifecycle("trace")

    def test_trace_monitor_lifecycle_monitor_stops_first_keeps_trace_active(self):
        self._exercise_monitor_then_injector_probe_lifecycle("trace")

    def test_monitor_first_watch_layering(self):
        self._exercise_monitor_then_injector_probe_lifecycle(
            "watch", assert_chain=True
        )

    def test_monitor_first_trace_layering(self):
        self._exercise_monitor_then_injector_probe_lifecycle(
            "trace", assert_chain=True
        )

    def _exercise_same_function_multi_monitor_lifecycle(
        self, monitor_cmd, module_name, stop_first
    ):
        def monitored_function(value):
            return value + 10

        true_original_function = monitored_function
        test_module = ModuleType(module_name)
        setattr(test_module, "monitored_function", monitored_function)
        sys.modules[module_name] = test_module

        monitor_a = None
        monitor_b = None
        try:
            result_a = monitor_cmd.execute(
                {
                    "action": "start",
                    "pattern": f"{module_name}.monitored_function",
                    "cycle": 60,
                }
            )
            assert result_a["status"] == "success"
            monitor_a = result_a["watch_id"]

            result_b = monitor_cmd.execute(
                {
                    "action": "start",
                    "pattern": f"{module_name}.monitored_function",
                    "cycle": 60,
                }
            )
            assert result_b["status"] == "success"
            monitor_b = result_b["watch_id"]

            monitored = cast(
                Callable[[int], int], getattr(test_module, "monitored_function")
            )
            assert monitored(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_a)["total"] == 1
            assert monitor_cmd.manager.get_stats(monitor_b)["total"] == 1

            if stop_first == "a":
                stopped_first = monitor_a
                remaining_monitor = monitor_b
                final_monitor = monitor_b
            else:
                stopped_first = monitor_b
                remaining_monitor = monitor_a
                final_monitor = monitor_a

            stop_result = monitor_cmd.execute(
                {"action": "stop", "watch_id": stopped_first}
            )
            assert stop_result["status"] == "success"

            monitored = cast(
                Callable[[int], int], getattr(test_module, "monitored_function")
            )
            assert monitored(2) == 12
            assert monitor_cmd.manager.get_stats(remaining_monitor)["total"] == 2

            final_result = monitor_cmd.execute(
                {"action": "stop", "watch_id": final_monitor}
            )
            assert final_result["status"] == "success"
            assert final_result["final_stats"]["total"] == 2

            monitored = cast(
                Callable[[int], int], getattr(test_module, "monitored_function")
            )
            assert monitored(3) == 13
            assert getattr(test_module, "monitored_function") is true_original_function
        finally:
            for watch_id in (monitor_a, monitor_b):
                if watch_id in monitor_cmd._monitors:
                    monitor_cmd.execute({"action": "stop", "watch_id": watch_id})
            setattr(test_module, "monitored_function", true_original_function)
            del sys.modules[module_name]

    def test_same_function_multi_monitor_lifecycle_stop_a_then_b_keeps_b_active(
        self, monitor_cmd
    ):
        self._exercise_same_function_multi_monitor_lifecycle(
            monitor_cmd, "test_monitor_multi_monitor_ab", "a"
        )

    def test_same_function_multi_monitor_lifecycle_stop_b_then_a_keeps_a_active(
        self, monitor_cmd
    ):
        self._exercise_same_function_multi_monitor_lifecycle(
            monitor_cmd, "test_monitor_multi_monitor_ba", "b"
        )

    def test_same_function_multi_monitor_wrapped_chain(self, monitor_cmd):
        module_name = "test_monitor_multi_monitor_wrapped_chain"
        test_module, true_original_function = self._make_mixed_monitor_target(
            module_name
        )
        pattern = f"{module_name}.monitored_function"
        monitor_a_id = None
        monitor_b_id = None

        try:
            monitor_a_id = self._start_monitor(monitor_cmd, pattern)
            monitor_b_id = self._start_monitor(monitor_cmd, pattern)

            wrapped = cast(
                Callable[[int], int], getattr(test_module, "monitored_function")
            )
            wrapped_any = cast(Any, wrapped)
            monitor_a_wrapper = cast(Any, monitor_cmd._monitors[monitor_a_id]["wrapper"])
            monitor_b_wrapper = cast(Any, monitor_cmd._monitors[monitor_b_id]["wrapper"])

            assert hasattr(
                wrapped_any, "__wrapped__"
            ), "expected monitor wrapper metadata from @wraps"
            assert wrapped is monitor_b_wrapper
            assert wrapped_any.__wrapped__ is monitor_a_wrapper
            assert monitor_b_wrapper.__wrapped__ is monitor_a_wrapper
            assert monitor_a_wrapper.__wrapped__ is true_original_function
            assert inspect.unwrap(wrapped) is true_original_function

            assert self._call_monitored(test_module, 1) == 11
            self._assert_monitor_total(monitor_cmd, monitor_a_id, 1)
            self._assert_monitor_total(monitor_cmd, monitor_b_id, 1)

            stop_a = monitor_cmd.execute({"action": "stop", "watch_id": monitor_a_id})
            assert stop_a["status"] == "success"
            assert monitor_a_id not in monitor_cmd._monitors
            assert monitor_b_id in monitor_cmd._monitors

            wrapped = cast(
                Callable[[int], int], getattr(test_module, "monitored_function")
            )
            assert wrapped is monitor_cmd._monitors[monitor_b_id]["wrapper"]

            assert self._call_monitored(test_module, 2) == 12
            self._assert_monitor_total(monitor_cmd, monitor_b_id, 2)
            assert monitor_cmd.manager.get_stats(monitor_a_id) is None

            stop_b = monitor_cmd.execute({"action": "stop", "watch_id": monitor_b_id})
            assert stop_b["status"] == "success"
            assert getattr(test_module, "monitored_function") is true_original_function
            assert self._call_monitored(test_module, 3) == 13
        finally:
            for watch_id in (monitor_a_id, monitor_b_id):
                if watch_id in monitor_cmd._monitors:
                    monitor_cmd.execute({"action": "stop", "watch_id": watch_id})
            setattr(test_module, "monitored_function", true_original_function)
            del sys.modules[module_name]

    def test_injector_root_original_not_downgraded_on_monitor_stop(self):
        agent, injector, monitor_cmd = self._build_mixed_probe_tools()
        module_name = "test_monitor_root_original_not_downgraded"
        test_module, true_original_function = self._make_mixed_monitor_target(
            module_name
        )
        pattern = f"{module_name}.monitored_function"

        watch_id = None
        monitor_a_id = None
        trace_id = None

        try:
            watch_id = self._start_injector_probe(injector, pattern, "watch")
            watch_wrapper = cast(Any, injector.instrumented[watch_id]["wrapper"])

            monitor_a_id = self._start_monitor(monitor_cmd, pattern)

            trace_id = self._start_injector_probe(injector, pattern, "trace")

            stop_result = monitor_cmd.execute({"action": "stop", "watch_id": monitor_a_id})
            assert stop_result["status"] == "success"
            monitor_a_id = None

            assert injector.instrumented[trace_id]["root_original"] is true_original_function
            assert injector.instrumented[trace_id]["root_original"] is not watch_wrapper

            trace_wrapper = cast(Any, injector.instrumented[trace_id]["wrapper"])
            assert self._call_monitored(test_module, 1) == 11
            assert trace_wrapper is getattr(test_module, "monitored_function")
        finally:
            if trace_id in injector.instrumented:
                injector.uninject(trace_id)
            if watch_id in injector.instrumented:
                injector.uninject(watch_id)
            if monitor_a_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_a_id})
            injector.uninject_all()
            setattr(test_module, "monitored_function", true_original_function)
            assert getattr(test_module, "monitored_function") is true_original_function
            del sys.modules[module_name]

    def test_active_monitor_owned_root_original_not_stale_after_peer_stop(self):
        agent, injector, monitor_cmd = self._build_mixed_probe_tools()
        module_name = "test_monitor_owned_root_original_not_stale"
        test_module, true_original_function = self._make_mixed_monitor_target(
            module_name
        )
        pattern = f"{module_name}.monitored_function"

        monitor_a_id = None
        watch_id = None
        monitor_b_id = None

        try:
            monitor_a_id = self._start_monitor(monitor_cmd, pattern)
            monitor_a_wrapper = cast(Any, monitor_cmd._monitors[monitor_a_id]["wrapper"])

            watch_id = self._start_injector_probe(injector, pattern, "watch")

            monitor_b_id = self._start_monitor(monitor_cmd, pattern)

            stop_result = monitor_cmd.execute({"action": "stop", "watch_id": monitor_a_id})
            assert stop_result["status"] == "success"
            monitor_a_id = None

            assert monitor_cmd._monitors[monitor_b_id]["owned_root_original"] is true_original_function
            assert monitor_cmd._monitors[monitor_b_id]["owned_root_original"] is not monitor_a_wrapper

            assert self._call_monitored(test_module, 1) == 11
        finally:
            if watch_id in injector.instrumented:
                injector.uninject(watch_id)
            if monitor_b_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_b_id})
            if monitor_a_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_a_id})
            injector.uninject_all()
            setattr(test_module, "monitored_function", true_original_function)
            assert getattr(test_module, "monitored_function") is true_original_function
            del sys.modules[module_name]

    @pytest.mark.root_metadata
    def test_outer_monitor_restores_root_after_inner_monitor_and_lower_probe_stop(
        self, monitor_cmd
    ):
        agent, injector, monitor_cmd = self._build_mixed_probe_tools()
        module_name = "test_monitor_root_metadata_propagation_regression"
        test_module, true_original_function = self._make_mixed_monitor_target(
            module_name
        )
        pattern = f"{module_name}.monitored_function"
        probe_id = None
        monitor_a_id = None
        monitor_b_id = None

        try:
            probe_id = self._start_injector_probe(injector, pattern, "watch")
            monitor_a_id = self._start_monitor(monitor_cmd, pattern)
            monitor_b_id = self._start_monitor(monitor_cmd, pattern)

            watch_wrapper = cast(Any, injector.instrumented[probe_id]["wrapper"])
            monitor_a_wrapper = cast(Any, monitor_cmd._monitors[monitor_a_id]["wrapper"])
            monitor_b_wrapper = cast(Any, monitor_cmd._monitors[monitor_b_id]["wrapper"])

            assert getattr(test_module, "monitored_function") is monitor_b_wrapper
            assert monitor_b_wrapper is not monitor_a_wrapper
            assert monitor_a_wrapper is not watch_wrapper

            stop_a_result = monitor_cmd.execute({"action": "stop", "watch_id": monitor_a_id})
            assert stop_a_result["status"] == "success"

            injector.uninject(probe_id)
            probe_id = None

            stop_b_result = monitor_cmd.execute({"action": "stop", "watch_id": monitor_b_id})
            assert stop_b_result["status"] == "success"

            final_slot = getattr(test_module, "monitored_function")
            assert final_slot is true_original_function
            assert final_slot is not watch_wrapper
            assert final_slot is not monitor_a_wrapper
        finally:
            if probe_id in injector.instrumented:
                injector.uninject(probe_id)
            for watch_id in (monitor_a_id, monitor_b_id):
                if watch_id in monitor_cmd._monitors:
                    monitor_cmd.execute({"action": "stop", "watch_id": watch_id})
            setattr(test_module, "monitored_function", true_original_function)
            del sys.modules[module_name]

    def test_monitor_stop_after_middle_probe_stop_keeps_lower_live_wrapper_active(self):
        agent, injector, monitor_cmd = self._build_mixed_probe_tools()
        module_name = "test_monitor_stacked_lower_live_wrapper_active"
        test_module, true_original_function = self._make_mixed_monitor_target(
            module_name
        )
        pattern = f"{module_name}.monitored_function"

        watch_a_id = None
        watch_b_id = None
        monitor_id = None

        try:
            watch_a_id = self._start_injector_probe(injector, pattern, "watch")
            watch_a_wrapper = getattr(test_module, "monitored_function")
            assert watch_a_wrapper is not true_original_function

            watch_b_id = self._start_injector_probe(injector, pattern, "trace")
            watch_b_wrapper = getattr(test_module, "monitored_function")
            assert watch_b_wrapper is not watch_a_wrapper

            monitor_id = self._start_monitor(monitor_cmd, pattern)
            monitor_wrapper = getattr(test_module, "monitored_function")
            assert monitor_wrapper is not watch_b_wrapper

            assert self._call_monitored(test_module, 1) == 11
            assert [obs["watch_id"] for obs in agent._observations] == [watch_a_id, watch_b_id]

            agent._observations.clear()
            injector.uninject(watch_b_id)
            watch_b_id = None

            stop_result = monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            assert stop_result["status"] == "success"
            monitor_id = None

            assert getattr(test_module, "monitored_function") is watch_a_wrapper
            assert getattr(test_module, "monitored_function") is not true_original_function

            assert self._call_monitored(test_module, 2) == 12
            assert [obs["watch_id"] for obs in agent._observations] == [watch_a_id]
        finally:
            for probe_id in (watch_a_id, watch_b_id):
                if probe_id in injector.instrumented:
                    injector.uninject(probe_id)
            if monitor_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            injector.uninject_all()
            setattr(test_module, "monitored_function", true_original_function)
            del sys.modules[module_name]

    def test_monitor_start_collects_statistics(self, monitor_cmd, test_module):
        """Monitor should collect call statistics."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 1,
        }
        result = monitor_cmd.execute(params)

        assert result["status"] == "success"
        assert "watch_id" in result

        for i in range(5):
            test_module.fast_function(i)

        time.sleep(1.5)

        observations = monitor_cmd.agent._observations
        assert len(observations) > 0

        stats = observations[-1]
        assert "total" in stats
        assert stats["total"] >= 5
        assert "success" in stats
        assert "fail" in stats

    def test_monitor_tracks_success_count(self, monitor_cmd, test_module):
        """Monitor should track successful calls."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 1,
        }
        monitor_cmd.execute(params)

        for i in range(3):
            test_module.fast_function(i)

        time.sleep(1.5)

        stats = monitor_cmd.agent._observations[-1]
        assert stats["success"] == 3
        assert stats["fail"] == 0

    def test_monitor_tracks_failures(self, monitor_cmd, test_module):
        """Monitor should track failed calls."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.failing_function",
            "cycle": 1,
        }
        monitor_cmd.execute(params)

        for i in [-2, -1, 1, 2]:
            try:
                test_module.failing_function(i)
            except ValueError:
                pass

        time.sleep(1.5)

        stats = monitor_cmd.agent._observations[-1]
        assert stats["total"] == 4
        assert stats["success"] == 2
        assert stats["fail"] == 2

    def test_monitor_timing_statistics(self, monitor_cmd, test_module):
        """Monitor should track avg, min, max response time."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.slow_function",
            "cycle": 1,
        }
        monitor_cmd.execute(params)

        for i in range(3):
            test_module.slow_function(i)

        time.sleep(1.5)

        stats = monitor_cmd.agent._observations[-1]
        assert "rt_avg" in stats
        assert "rt_min" in stats
        assert "rt_max" in stats

        assert stats["rt_avg"] >= 10

    def test_monitor_periodic_output(self, monitor_cmd, test_module):
        """Monitor should output statistics at cycle intervals."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 1,
        }
        monitor_cmd.execute(params)

        test_module.fast_function(1)

        time.sleep(2.5)

        observations = monitor_cmd.agent._observations
        cycle_outputs = [obs for obs in observations if "cycle" in obs]
        assert len(cycle_outputs) >= 2

    def test_monitor_cycle_limit(self, monitor_cmd, test_module):
        """--cycles flag should limit number of output cycles."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 1,
            "cycles": 2,
        }
        monitor_cmd.execute(params)

        for i in range(10):
            test_module.fast_function(i)
            time.sleep(0.3)

        time.sleep(3)

        observations = monitor_cmd.agent._observations
        cycle_outputs = [obs for obs in observations if "cycle" in obs]
        assert len(cycle_outputs) == 2

    def test_monitor_stop_and_reset(self, monitor_cmd, test_module):
        """stop action should stop timer and output final statistics."""
        params_start = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 5,
        }
        result = monitor_cmd.execute(params_start)
        watch_id = result["watch_id"]

        for i in range(3):
            test_module.fast_function(i)

        time.sleep(0.5)

        params_stop = {"action": "stop", "watch_id": watch_id}
        result = monitor_cmd.execute(params_stop)

        assert result["status"] == "success"
        assert "final_stats" in result
        assert result["final_stats"]["total"] == 3

    def test_monitor_thread_safety(self, monitor_cmd, test_module):
        """Monitor should be thread-safe for concurrent calls."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 2,
        }
        monitor_cmd.execute(params)

        def make_calls():
            for i in range(10):
                test_module.fast_function(i)

        threads = [threading.Thread(target=make_calls) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        time.sleep(2.5)

        stats = monitor_cmd.agent._observations[-1]
        assert stats["total"] == 50

    def test_monitor_lightweight_wrapper(self, monitor_cmd, test_module):
        """Monitor should NOT capture full params (lightweight)."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 1,
        }
        monitor_cmd.execute(params)

        large_data = {"key": "x" * 10000}
        try:
            test_module.fast_function(large_data)
        except TypeError:
            pass

        time.sleep(1.5)

        observations = monitor_cmd.agent._observations
        for obs in observations:
            assert "params" not in obs or obs["params"] is None

    def test_monitor_no_thread_leaks(self, monitor_cmd, test_module):
        """Stopping monitor should clean up timer thread."""
        initial_thread_count = threading.active_count()

        params_start = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 1,
        }
        result = monitor_cmd.execute(params_start)
        watch_id = result["watch_id"]

        time.sleep(0.5)

        assert threading.active_count() > initial_thread_count

        params_stop = {"action": "stop", "watch_id": watch_id}
        monitor_cmd.execute(params_stop)

        time.sleep(0.5)

        assert threading.active_count() == initial_thread_count

    def test_monitor_status_action(self, monitor_cmd, test_module):
        """status action should return active monitors."""
        params_start = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 5,
        }
        result = monitor_cmd.execute(params_start)
        watch_id = result["watch_id"]

        params_status = {"action": "status"}
        result = monitor_cmd.execute(params_status)

        assert result["status"] == "success"
        assert "monitors" in result
        assert watch_id in result["monitors"]

    def test_monitor_uses_agent_injector_target_resolution(self, test_module):
        """Monitor should reuse agent target resolution for script aliases."""

        class RedirectingInjector:
            def _resolve_target(self, pattern):
                if pattern == "demo_alias.fast_function":
                    return (
                        test_module.fast_function,
                        test_module,
                        "fast_function",
                    )
                return None

        agent = MockAgent()
        agent.injector = RedirectingInjector()  # pyright: ignore[reportAttributeAccessIssue]
        monitor_cmd = MonitorCommand(agent)  # pyright: ignore[reportArgumentType]

        result = monitor_cmd.execute(
            {
                "action": "start",
                "pattern": "demo_alias.fast_function",
                "cycle": 0.05,
            }
        )

        assert result["status"] == "success"
        watch_id = result["watch_id"]

        try:
            assert test_module.fast_function(21) == 42
            time.sleep(0.15)

            observations = agent._observations
            assert observations
            assert observations[-1]["total"] >= 1
        finally:
            monitor_cmd.execute({"action": "stop", "watch_id": watch_id})

    def test_monitor_invalid_pattern(self, monitor_cmd):
        """Invalid pattern should return error."""
        params = {
            "action": "start",
            "pattern": "nonexistent.module.function",
            "cycle": 1,
        }
        result = monitor_cmd.execute(params)

        assert result["status"] == "error"
        assert "error" in result

    def test_monitor_start_exposes_canonical_monitor_id(self, monitor_cmd, test_module):
        """Monitor start must include canonical monitor_id in response."""
        result = monitor_cmd.execute(
            {"action": "start", "pattern": "test_monitor_module.fast_function", "cycle": 60}
        )
        assert result["status"] == "success"
        assert "monitor_id" in result, "monitor_id must be present in start response"
        assert result["monitor_id"] == result["watch_id"]
        monitor_cmd.execute({"action": "stop", "watch_id": result["watch_id"]})

    def test_monitor_wrapper_exposes_wrapped_metadata(self, monitor_cmd, test_module):
        """Monitor wrapper must preserve wrapped-function metadata for restore logic."""
        original_fn = test_module.fast_function

        result = monitor_cmd.execute(
            {"action": "start", "pattern": "test_monitor_module.fast_function", "cycle": 60}
        )
        assert result["status"] == "success"
        watch_id = result["watch_id"]

        try:
            wrapper = test_module.fast_function
            assert wrapper is not original_fn
            assert hasattr(wrapper, "__wrapped__")
            assert wrapper.__wrapped__ is original_fn
            assert wrapper.__name__ == original_fn.__name__
        finally:
            monitor_cmd.execute({"action": "stop", "watch_id": watch_id})

        assert test_module.fast_function is original_fn

    def test_monitor_stop_accepts_monitor_id_canonical(self, monitor_cmd, test_module):
        """Monitor stop must accept canonical monitor_id parameter."""
        start = monitor_cmd.execute(
            {"action": "start", "pattern": "test_monitor_module.fast_function", "cycle": 60}
        )
        assert start["status"] == "success"
        watch_id = start["watch_id"]
        result = monitor_cmd.execute({"action": "stop", "monitor_id": watch_id})
        assert result["status"] == "success", (
            f"stop with monitor_id should succeed, got: {result}"
        )

    def test_monitor_stop_legacy_watch_id_still_works(self, monitor_cmd, test_module):
        """Monitor stop must still accept legacy watch_id parameter."""
        start = monitor_cmd.execute(
            {"action": "start", "pattern": "test_monitor_module.fast_function", "cycle": 60}
        )
        assert start["status"] == "success"
        watch_id = start["watch_id"]
        result = monitor_cmd.execute({"action": "stop", "watch_id": watch_id})
        assert result["status"] == "success"

    def test_monitor_status_single_exposes_monitor_id(self, monitor_cmd, test_module):
        """Monitor status for single monitor must include monitor_id in response."""
        start = monitor_cmd.execute(
            {"action": "start", "pattern": "test_monitor_module.fast_function", "cycle": 60}
        )
        watch_id = start["watch_id"]
        result = monitor_cmd.execute({"action": "status", "watch_id": watch_id})
        assert result["status"] == "success"
        assert "monitor_id" in result, "status response must include monitor_id"
        assert result["monitor_id"] == watch_id
        monitor_cmd.execute({"action": "stop", "watch_id": watch_id})

    def test_monitor_observation_includes_monitor_id(self, monitor_cmd, test_module):
        """Observations emitted by monitor must include monitor_id alongside watch_id."""
        result = monitor_cmd.execute(
            {
                "action": "start",
                "pattern": "test_monitor_module.fast_function",
                "cycle": 0.05,
                "cycles": 1,
            }
        )
        watch_id = result["watch_id"]
        test_module.fast_function(1)
        time.sleep(0.2)
        observations = [obs for obs in monitor_cmd.agent._observations if "cycle" in obs]
        assert observations, "expected at least one cycle observation"
        obs = observations[0]
        assert "monitor_id" in obs, "observation must include monitor_id"
        assert obs["monitor_id"] == obs["watch_id"]
        monitor_cmd.execute({"action": "stop", "watch_id": watch_id})

    def test_monitor_stop_restores_alias_bindings(self, test_module):
        """Monitor stop must restore alias bindings that were patched at start."""
        import sys as _sys

        def target_fn(x):
            return x + 1

        mod_primary = type(_sys)("test_monitor_alias_primary")
        mod_primary.target_fn = target_fn
        mod_alias = type(_sys)("test_monitor_alias_secondary")
        mod_alias.target_fn = target_fn
        _sys.modules["test_monitor_alias_primary"] = mod_primary
        _sys.modules["test_monitor_alias_secondary"] = mod_alias

        agent = MockAgent()
        from peeka.core.injector import DecoratorInjector
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]
        agent.injector = injector
        monitor_cmd = MonitorCommand(agent)  # pyright: ignore[reportArgumentType]

        try:
            result = monitor_cmd.execute(
                {
                    "action": "start",
                    "pattern": "test_monitor_alias_primary.target_fn",
                    "cycle": 60,
                }
            )
            assert result["status"] == "success"
            watch_id = result["watch_id"]
            wrapper = mod_primary.target_fn

            mod_alias.target_fn = wrapper

            stop_result = monitor_cmd.execute({"action": "stop", "watch_id": watch_id})
            assert stop_result["status"] == "success"

            assert mod_primary.target_fn is target_fn, (
                "primary slot must be restored to original after monitor stop"
            )
            assert mod_alias.target_fn is target_fn, (
                "alias slot must be restored to original after monitor stop"
            )
        finally:
            for mod_name in ("test_monitor_alias_primary", "test_monitor_alias_secondary"):
                _sys.modules.pop(mod_name, None)

    def test_monitor_alias_restore_uses_computed_replacement(self, test_module):
        """Regression: alias restore must use the same computed replacement as canonical.

        Scenario: a watch probe is injected first, then a monitor wraps the watch
        wrapper. The watch probe is uninjected (gone from instrumented) before monitor
        stops. canonical restore walks __wrapped__ to reach target_fn (the inner
        original). Alias restore still uses monitor_info['original'] = watch_wrapper
        (the now-removed injector wrapper). This leaves canonical and alias pointing
        to different objects.
        """
        import sys as _sys

        def target_fn(x):
            return x + 1

        mod_primary = type(_sys)("test_monitor_alias_replacement_primary")
        mod_primary.target_fn = target_fn
        mod_alias = type(_sys)("test_monitor_alias_replacement_alias")
        mod_alias.target_fn = target_fn
        _sys.modules["test_monitor_alias_replacement_primary"] = mod_primary
        _sys.modules["test_monitor_alias_replacement_alias"] = mod_alias

        agent = MockAgent()
        from peeka.core.injector import DecoratorInjector
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]
        agent.injector = injector
        monitor_cmd = MonitorCommand(agent)  # pyright: ignore[reportArgumentType]

        try:
            watch_probe_id = injector.inject(
                "test_monitor_alias_replacement_primary.target_fn",
                {"depth": 1, "times": -1},
            )
            watch_wrapper = mod_primary.target_fn
            assert watch_wrapper is not target_fn
            assert getattr(watch_wrapper, "__wrapped__", None) is target_fn

            result = monitor_cmd.execute(
                {
                    "action": "start",
                    "pattern": "test_monitor_alias_replacement_primary.target_fn",
                    "cycle": 60,
                }
            )
            assert result["status"] == "success"
            watch_id = result["watch_id"]
            monitor_wrapper = mod_primary.target_fn
            assert monitor_wrapper is not watch_wrapper

            mod_alias.target_fn = monitor_wrapper

            injector.uninject(watch_probe_id)

            stop_result = monitor_cmd.execute({"action": "stop", "watch_id": watch_id})
            assert stop_result["status"] == "success"

            canonical_fn = mod_primary.target_fn
            alias_fn = mod_alias.target_fn

            assert canonical_fn is alias_fn, (
                "canonical and alias slots must point to the same object after monitor stop; "
                f"got canonical={canonical_fn!r}, alias={alias_fn!r}. "
                "Alias restore must use the same computed replacement as canonical restore."
            )
        finally:
            for mod_name in ("test_monitor_alias_replacement_primary", "test_monitor_alias_replacement_alias"):
                _sys.modules.pop(mod_name, None)


class TestMonitorUserDecoratorPreservation:
    """Regression tests for preserving user decorators around monitor stop."""

    def _build_monitor_cmd(self):
        agent = MockAgent()
        monitor_cmd = MonitorCommand(agent)  # pyright: ignore[reportArgumentType]
        return agent, monitor_cmd

    def _register_module(self, module_name, fn):
        module = ModuleType(module_name)
        setattr(module, "fn", fn)
        sys.modules[module_name] = module
        return module

    def _cleanup_module(self, module_name):
        sys.modules.pop(module_name, None)

    def test_lru_cache_preserved_after_monitor_stop(self):
        """Monitor stop must preserve functools.lru_cache wrapper identity."""
        agent, monitor_cmd = self._build_monitor_cmd()
        module_name = "test_monitor_user_decorator_lru_cache"
        raw_calls = []

        def raw_fn(value):
            raw_calls.append(value)
            return value * 2

        decorated_fn = functools.lru_cache(maxsize=None)(raw_fn)
        module = self._register_module(module_name, decorated_fn)

        try:
            start = monitor_cmd.execute(
                {"action": "start", "pattern": f"{module_name}.fn", "cycle": 60}
            )
            assert start["status"] == "success"
            watch_id = start["watch_id"]

            try:
                assert module.fn(7) == 14
            finally:
                monitor_cmd.execute({"action": "stop", "watch_id": watch_id})

            assert module.fn is decorated_fn
            assert module.fn is not raw_fn

            before_hits = decorated_fn.cache_info().hits
            assert module.fn(7) == 14
            assert decorated_fn.cache_info().hits == before_hits + 1
            assert raw_calls == [7]
        finally:
            self._cleanup_module(module_name)

    def test_custom_decorator_preserved_after_monitor_stop(self):
        """Monitor stop must preserve a custom wrapped decorator."""
        agent, monitor_cmd = self._build_monitor_cmd()
        module_name = "test_monitor_user_decorator_custom"
        decorator_calls = []

        def custom_decorator(fn):
            @functools.wraps(fn)
            def wrapper(value):
                decorator_calls.append(("custom", value))
                return fn(value)

            return wrapper

        def raw_fn(value):
            return value + 3

        decorated_fn = custom_decorator(raw_fn)
        module = self._register_module(module_name, decorated_fn)

        try:
            start = monitor_cmd.execute(
                {"action": "start", "pattern": f"{module_name}.fn", "cycle": 60}
            )
            assert start["status"] == "success"
            watch_id = start["watch_id"]

            try:
                assert module.fn(4) == 7
            finally:
                monitor_cmd.execute({"action": "stop", "watch_id": watch_id})

            assert module.fn is decorated_fn
            assert module.fn is not raw_fn

            decorator_calls.clear()
            assert module.fn(5) == 8
            assert decorator_calls == [("custom", 5)]
        finally:
            self._cleanup_module(module_name)

    def test_stacked_user_decorators_preserved_after_monitor_stop(self):
        """Monitor stop must preserve stacked user decorators."""
        agent, monitor_cmd = self._build_monitor_cmd()
        module_name = "test_monitor_user_decorator_stacked"
        outer_calls = []
        inner_calls = []

        def outer_decorator(fn):
            @functools.wraps(fn)
            def wrapper(value):
                outer_calls.append(("outer", value))
                return fn(value)

            return wrapper

        def inner_decorator(fn):
            @functools.wraps(fn)
            def wrapper(value):
                inner_calls.append(("inner", value))
                return fn(value)

            return wrapper

        def raw_fn(value):
            return value * 5

        decorated_fn = outer_decorator(inner_decorator(raw_fn))
        module = self._register_module(module_name, decorated_fn)

        try:
            start = monitor_cmd.execute(
                {"action": "start", "pattern": f"{module_name}.fn", "cycle": 60}
            )
            assert start["status"] == "success"
            watch_id = start["watch_id"]

            try:
                assert module.fn(2) == 10
            finally:
                monitor_cmd.execute({"action": "stop", "watch_id": watch_id})

            assert module.fn is decorated_fn
            assert module.fn is not raw_fn

            outer_calls.clear()
            inner_calls.clear()
            assert module.fn(6) == 30
            assert outer_calls == [("outer", 6)]
            assert inner_calls == [("inner", 6)]
        finally:
            self._cleanup_module(module_name)

    def test_async_user_decorator_preserved_after_monitor_stop(self):
        """Monitor stop must preserve async user decorators and awaitability."""
        agent, monitor_cmd = self._build_monitor_cmd()
        module_name = "test_monitor_user_decorator_async"
        decorator_calls = []

        def async_decorator(fn):
            @functools.wraps(fn)
            async def wrapper(value):
                decorator_calls.append(("async", value))
                return await fn(value)

            return wrapper

        async def raw_fn(value):
            return value * 4

        decorated_fn = async_decorator(raw_fn)
        module = self._register_module(module_name, decorated_fn)

        try:
            start = monitor_cmd.execute(
                {"action": "start", "pattern": f"{module_name}.fn", "cycle": 60}
            )
            assert start["status"] == "success"
            watch_id = start["watch_id"]

            try:
                assert asyncio.run(module.fn(3)) == 12
            finally:
                monitor_cmd.execute({"action": "stop", "watch_id": watch_id})

            assert module.fn is decorated_fn
            assert module.fn is not raw_fn

            decorator_calls.clear()
            assert asyncio.run(module.fn(5)) == 20
            assert decorator_calls == [("async", 5)]
        finally:
            self._cleanup_module(module_name)

    def test_alias_restore_preserves_user_decorator(self):
        """Monitor stop must restore aliases to the decorated callable."""
        agent, monitor_cmd = self._build_monitor_cmd()
        module_name = "test_monitor_user_decorator_alias"
        decorator_calls = []

        def custom_decorator(fn):
            @functools.wraps(fn)
            def wrapper(value):
                decorator_calls.append(value)
                return fn(value)

            return wrapper

        def raw_fn(value):
            return value + 1

        decorated_fn = custom_decorator(raw_fn)
        module = self._register_module(module_name, decorated_fn)
        setattr(module, "alias_fn", module.fn)

        try:
            start = monitor_cmd.execute(
                {"action": "start", "pattern": f"{module_name}.fn", "cycle": 60}
            )
            assert start["status"] == "success"
            watch_id = start["watch_id"]

            try:
                assert module.fn(3) == 4
            finally:
                monitor_cmd.execute({"action": "stop", "watch_id": watch_id})

            assert module.fn is decorated_fn
            assert module.alias_fn is decorated_fn
            assert module.fn is not raw_fn
            assert module.alias_fn is not raw_fn

            decorator_calls.clear()
            assert module.alias_fn(4) == 5
            assert decorator_calls == [4]
        finally:
            self._cleanup_module(module_name)

    def test_peeka_monitors_stacked_still_restore_correctly(self):
        """Two stacked monitors should leave the remaining one active after stop."""
        agent, monitor_cmd = self._build_monitor_cmd()
        module_name = "test_monitor_user_decorator_peeka_stack"

        def raw_fn(value):
            return value + 1

        module = self._register_module(module_name, raw_fn)

        try:
            first = monitor_cmd.execute(
                {"action": "start", "pattern": f"{module_name}.fn", "cycle": 0.05}
            )
            second = monitor_cmd.execute(
                {"action": "start", "pattern": f"{module_name}.fn", "cycle": 0.05}
            )
            assert first["status"] == "success"
            assert second["status"] == "success"
            first_id = first["watch_id"]
            second_id = second["watch_id"]

            try:
                assert module.fn(1) == 2
                time.sleep(0.2)
                assert {obs["watch_id"] for obs in agent._observations} >= {
                    first_id,
                    second_id,
                }

                agent._observations.clear()
                monitor_cmd.execute({"action": "stop", "watch_id": first_id})

                assert module.fn(2) == 3
                time.sleep(0.2)
                assert any(obs["watch_id"] == second_id for obs in agent._observations)
                assert all(obs["watch_id"] != first_id for obs in agent._observations)
            finally:
                monitor_cmd.execute({"action": "stop", "watch_id": second_id})
        finally:
            self._cleanup_module(module_name)

    def test_monitor_start_stop_restores_decorated_callable(self):
        """Regression: monitor stop must restore decorated wrapper identity, not raw inner."""
        agent, monitor_cmd = self._build_monitor_cmd()
        module_name = "test_monitor_start_stop_restores_decorated_callable"
        call_log = []

        def log_calls(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                call_log.append(args)
                return fn(*args, **kwargs)

            return wrapper

        def raw_fn(value):
            return value * 3

        decorated_fn = log_calls(raw_fn)
        module = self._register_module(module_name, decorated_fn)
        watch_id = None

        try:
            start = monitor_cmd.execute(
                {"action": "start", "pattern": f"{module_name}.fn", "cycle": 60}
            )
            assert start["status"] == "success"
            watch_id = start["watch_id"]

            assert module.fn(2) == 6
            monitor_cmd.execute({"action": "stop", "watch_id": watch_id})
            watch_id = None

            assert getattr(module, "fn") is decorated_fn, (
                "monitor stop must restore decorated wrapper, not bypass it"
            )
            assert getattr(module, "fn") is not raw_fn, (
                "raw inner function must not be exposed as canonical after monitor stop"
            )
            call_log.clear()
            assert module.fn(4) == 12
            assert call_log == [(4,)], "decorator behavior must be intact after monitor stop"
        finally:
            if watch_id is not None and watch_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": watch_id})
            self._cleanup_module(module_name)

    def test_watch_trace_mixed_with_decorated_callable(self):
        """Regression: after watch+trace both stop on user-decorated callable, decorated wrapper must be canonical."""
        from peeka.core.injector import DecoratorInjector

        module_name = "test_watch_trace_mixed_with_decorated_callable"
        call_log = []

        def tracking_decorator(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                call_log.append(("tracked",) + args)
                return fn(*args, **kwargs)

            return wrapper

        def raw_fn(value):
            return value + 7

        decorated_fn = tracking_decorator(raw_fn)
        module = ModuleType(module_name)
        setattr(module, "fn", decorated_fn)
        sys.modules[module_name] = module

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]
        agent.injector = injector
        watch_id = None
        trace_id = None

        try:
            pattern = f"{module_name}.fn"
            watch_id = injector.inject(pattern, {"depth": 2, "times": -1})
            trace_id = injector.inject_trace(
                pattern,
                {"trace_depth": 2, "times": -1},
                force_backend=BACKEND_WRAPPER_ONLY,
            )

            injector.uninject(watch_id)
            watch_id = None

            trace_wrapper = injector.instrumented[trace_id]["wrapper"]
            assert getattr(module, "fn") is trace_wrapper, (
                "canonical must route through active trace wrapper after watch stop"
            )

            injector.uninject(trace_id)
            trace_id = None

            assert getattr(module, "fn") is decorated_fn, (
                "trace stop must restore decorated wrapper, not bypass it"
            )
            assert getattr(module, "fn") is not raw_fn, (
                "raw inner function must not be exposed as canonical after all probes stop"
            )
            call_log.clear()
            assert module.fn(3) == 10
            assert call_log == [("tracked", 3)], (
                "decorator behavior must be intact after all probes stop"
            )
        finally:
            if watch_id is not None and watch_id in injector.instrumented:
                injector.uninject(watch_id)
            if trace_id is not None and trace_id in injector.instrumented:
                injector.uninject(trace_id)
            injector.uninject_all()
            setattr(module, "fn", decorated_fn)
            sys.modules.pop(module_name, None)

    def test_reset_with_decorated_callable_restores_decorated(self):
        """Regression: ResetCommand must restore decorated callable, not inner raw function."""
        from peeka.commands.reset import ResetCommand
        from peeka.core.injector import DecoratorInjector

        module_name = "test_reset_with_decorated_callable_restores_decorated"
        call_log = []

        def audit_decorator(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                call_log.append(("audit",) + args)
                return fn(*args, **kwargs)

            return wrapper

        def raw_fn(value):
            return value * 2

        decorated_fn = audit_decorator(raw_fn)
        module = self._register_module(module_name, decorated_fn)

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]
        agent.injector = injector
        monitor_cmd = MonitorCommand(agent)  # pyright: ignore[reportArgumentType]
        agent.monitor_cmd = monitor_cmd  # type: ignore[attr-defined]
        agent.command_handlers = {"monitor": monitor_cmd}  # type: ignore[attr-defined]
        reset_cmd = ResetCommand(agent)  # pyright: ignore[reportArgumentType]

        try:
            pattern = f"{module_name}.fn"
            start = monitor_cmd.execute(
                {"action": "start", "pattern": pattern, "cycle": 60}
            )
            assert start["status"] == "success"

            assert module.fn(5) == 10
            reset_result = reset_cmd.execute({"action": "reset", "pattern": pattern})
            assert reset_result["status"] == "success"

            assert getattr(module, "fn") is decorated_fn, (
                "reset must restore decorated wrapper, not bypass it"
            )
            assert getattr(module, "fn") is not raw_fn, (
                "raw inner function must not be exposed as canonical after reset"
            )
            call_log.clear()
            assert module.fn(3) == 6
            assert call_log == [("audit", 3)], (
                "decorator behavior must be intact after reset"
            )
        finally:
            self._cleanup_module(module_name)

    def test_user_decorator_preserved_after_multiple_stops(self):
        """Regression: decorated callable must survive multiple sequential monitor stops."""
        agent, monitor_cmd = self._build_monitor_cmd()
        module_name = "test_user_decorator_preserved_after_multiple_stops"
        call_log = []

        def counting_decorator(fn):
            @functools.wraps(fn)
            def wrapper(*args, **kwargs):
                call_log.append(args)
                return fn(*args, **kwargs)

            return wrapper

        def raw_fn(value):
            return value + 1

        decorated_fn = counting_decorator(raw_fn)
        module = self._register_module(module_name, decorated_fn)
        monitor_a_id = None
        monitor_b_id = None
        monitor_c_id = None

        try:
            pattern = f"{module_name}.fn"

            start_a = monitor_cmd.execute(
                {"action": "start", "pattern": pattern, "cycle": 60}
            )
            assert start_a["status"] == "success"
            monitor_a_id = start_a["watch_id"]

            start_b = monitor_cmd.execute(
                {"action": "start", "pattern": pattern, "cycle": 60}
            )
            assert start_b["status"] == "success"
            monitor_b_id = start_b["watch_id"]

            start_c = monitor_cmd.execute(
                {"action": "start", "pattern": pattern, "cycle": 60}
            )
            assert start_c["status"] == "success"
            monitor_c_id = start_c["watch_id"]

            assert module.fn(1) == 2

            monitor_cmd.execute({"action": "stop", "watch_id": monitor_a_id})
            monitor_a_id = None
            assert module.fn(2) == 3

            monitor_cmd.execute({"action": "stop", "watch_id": monitor_b_id})
            monitor_b_id = None
            assert module.fn(3) == 4

            monitor_cmd.execute({"action": "stop", "watch_id": monitor_c_id})
            monitor_c_id = None

            assert getattr(module, "fn") is decorated_fn, (
                "decorated callable must be restored after all monitors stop"
            )
            assert getattr(module, "fn") is not raw_fn, (
                "raw inner function must not be exposed as canonical after all monitors stop"
            )
            call_log.clear()
            assert module.fn(5) == 6
            assert call_log == [(5,)], "decorator behavior must be intact after all stops"
        finally:
            for mid in (monitor_a_id, monitor_b_id, monitor_c_id):
                if mid is not None and mid in monitor_cmd._monitors:
                    monitor_cmd.execute({"action": "stop", "watch_id": mid})
            self._cleanup_module(module_name)


class TestStopOrderMatrix:
    def _build_tools(self):
        from peeka.core.injector import DecoratorInjector

        agent = MockAgent()
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]
        agent.injector = injector
        monitor_cmd = MonitorCommand(agent)  # pyright: ignore[reportArgumentType]
        return agent, injector, monitor_cmd

    def _make_target(self, module_name: str):
        def target_fn(value: int) -> int:
            return value + 10

        mod = ModuleType(module_name)
        setattr(mod, "target_fn", target_fn)
        sys.modules[module_name] = mod
        return mod, target_fn

    def _start_watch(self, injector, pattern: str) -> str:
        return injector.inject(pattern, {"depth": 2, "times": -1})

    def _start_trace(self, injector, pattern: str) -> str:
        return injector.inject_trace(
            pattern, {"trace_depth": 2, "times": -1}, force_backend=BACKEND_WRAPPER_ONLY
        )

    def _start_stack(self, injector, pattern: str) -> str:
        return injector.inject(pattern, {"depth": 2, "times": -1, "stack_depth": 3})

    def _start_monitor(self, monitor_cmd, pattern: str) -> str:
        result = monitor_cmd.execute({"action": "start", "pattern": pattern, "cycle": 60})
        assert result["status"] == "success"
        return cast(str, result["watch_id"])

    def _stop_monitor(self, monitor_cmd, monitor_id: str) -> None:
        result = monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
        assert result["status"] == "success"

    def _live_wrappers(self, injector, monitor_cmd) -> set:
        inj = {info["wrapper"] for info in injector.instrumented.values()}
        mon = {info["wrapper"] for info in monitor_cmd._monitors.values()}
        return inj | mon

    def _assert_final_stop(self, mod, original, injector, monitor_cmd) -> None:
        assert not injector.instrumented, (
            f"injector still has entries: {list(injector.instrumented)}"
        )
        assert not monitor_cmd._monitors, (
            f"monitor_cmd still has entries: {list(monitor_cmd._monitors)}"
        )
        assert getattr(mod, "target_fn") is original, (
            f"canonical not restored: got {getattr(mod, 'target_fn')!r}"
        )
        _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), set())

    def test_stop_order_monitor_monitor_stop_a_then_b(self) -> None:
        agent, injector, monitor_cmd = self._build_tools()
        module_name = "test_stop_order_mon_mon_ab"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        monitor_a = monitor_b = None
        try:
            monitor_a = self._start_monitor(monitor_cmd, pattern)
            monitor_b = self._start_monitor(monitor_cmd, pattern)

            assert mod.target_fn(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_a)["total"] == 1
            assert monitor_cmd.manager.get_stats(monitor_b)["total"] == 1

            self._stop_monitor(monitor_cmd, monitor_a)
            monitor_a = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert monitor_cmd.manager.get_stats(monitor_b) is not None

            assert mod.target_fn(2) == 12
            assert monitor_cmd.manager.get_stats(monitor_b)["total"] == 2

            self._stop_monitor(monitor_cmd, monitor_b)
            monitor_b = None

            self._assert_final_stop(mod, original, injector, monitor_cmd)
            assert mod.target_fn(3) == 13
        finally:
            for mid in (monitor_a, monitor_b):
                if mid and mid in monitor_cmd._monitors:
                    monitor_cmd.execute({"action": "stop", "watch_id": mid})
            sys.modules.pop(module_name, None)

    def test_stop_order_monitor_monitor_stop_b_then_a(self) -> None:
        agent, injector, monitor_cmd = self._build_tools()
        module_name = "test_stop_order_mon_mon_ba"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        monitor_a = monitor_b = None
        try:
            monitor_a = self._start_monitor(monitor_cmd, pattern)
            monitor_b = self._start_monitor(monitor_cmd, pattern)

            assert mod.target_fn(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_a)["total"] == 1
            assert monitor_cmd.manager.get_stats(monitor_b)["total"] == 1

            self._stop_monitor(monitor_cmd, monitor_b)
            monitor_b = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert monitor_cmd.manager.get_stats(monitor_a) is not None

            assert mod.target_fn(2) == 12
            assert monitor_cmd.manager.get_stats(monitor_a)["total"] == 2

            self._stop_monitor(monitor_cmd, monitor_a)
            monitor_a = None

            self._assert_final_stop(mod, original, injector, monitor_cmd)
            assert mod.target_fn(3) == 13
        finally:
            for mid in (monitor_a, monitor_b):
                if mid and mid in monitor_cmd._monitors:
                    monitor_cmd.execute({"action": "stop", "watch_id": mid})
            sys.modules.pop(module_name, None)

    def test_stop_order_monitor_watch_stop_monitor_then_watch(self) -> None:
        agent, injector, monitor_cmd = self._build_tools()
        module_name = "test_stop_order_mon_watch_mw"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        monitor_id = watch_id = None
        try:
            monitor_id = self._start_monitor(monitor_cmd, pattern)
            watch_id = self._start_watch(injector, pattern)

            assert mod.target_fn(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_id)["total"] == 1
            assert [o["watch_id"] for o in agent._observations] == [watch_id]

            agent._observations.clear()
            self._stop_monitor(monitor_cmd, monitor_id)
            monitor_id = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert not monitor_cmd._monitors

            assert mod.target_fn(2) == 12
            assert [o["watch_id"] for o in agent._observations] == [watch_id]

            agent._observations.clear()
            injector.uninject(watch_id)
            watch_id = None

            self._assert_final_stop(mod, original, injector, monitor_cmd)
            assert mod.target_fn(3) == 13
        finally:
            if watch_id and watch_id in injector.instrumented:
                injector.uninject(watch_id)
            if monitor_id and monitor_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            sys.modules.pop(module_name, None)

    def test_stop_order_monitor_watch_stop_watch_then_monitor(self) -> None:
        agent, injector, monitor_cmd = self._build_tools()
        module_name = "test_stop_order_mon_watch_wm"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        monitor_id = watch_id = None
        try:
            monitor_id = self._start_monitor(monitor_cmd, pattern)
            watch_id = self._start_watch(injector, pattern)

            assert mod.target_fn(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_id)["total"] == 1
            assert [o["watch_id"] for o in agent._observations] == [watch_id]

            agent._observations.clear()
            injector.uninject(watch_id)
            watch_id = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert not injector.instrumented

            assert mod.target_fn(2) == 12
            assert agent._observations == []
            assert monitor_cmd.manager.get_stats(monitor_id)["total"] == 2

            self._stop_monitor(monitor_cmd, monitor_id)
            monitor_id = None

            self._assert_final_stop(mod, original, injector, monitor_cmd)
            assert mod.target_fn(3) == 13
        finally:
            if watch_id and watch_id in injector.instrumented:
                injector.uninject(watch_id)
            if monitor_id and monitor_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            sys.modules.pop(module_name, None)

    def test_stop_order_monitor_trace_stop_monitor_then_trace(self) -> None:
        agent, injector, monitor_cmd = self._build_tools()
        module_name = "test_stop_order_mon_trace_mt"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        monitor_id = trace_id = None
        try:
            monitor_id = self._start_monitor(monitor_cmd, pattern)
            trace_id = self._start_trace(injector, pattern)

            assert mod.target_fn(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_id)["total"] == 1
            assert [o["watch_id"] for o in agent._observations] == [trace_id]

            agent._observations.clear()
            self._stop_monitor(monitor_cmd, monitor_id)
            monitor_id = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert not monitor_cmd._monitors

            assert mod.target_fn(2) == 12
            assert [o["watch_id"] for o in agent._observations] == [trace_id]

            agent._observations.clear()
            injector.uninject(trace_id)
            trace_id = None

            self._assert_final_stop(mod, original, injector, monitor_cmd)
            assert mod.target_fn(3) == 13
        finally:
            if trace_id and trace_id in injector.instrumented:
                injector.uninject(trace_id)
            if monitor_id and monitor_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            sys.modules.pop(module_name, None)

    def test_stop_order_monitor_trace_stop_trace_then_monitor(self) -> None:
        agent, injector, monitor_cmd = self._build_tools()
        module_name = "test_stop_order_mon_trace_tm"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        monitor_id = trace_id = None
        try:
            monitor_id = self._start_monitor(monitor_cmd, pattern)
            trace_id = self._start_trace(injector, pattern)

            assert mod.target_fn(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_id)["total"] == 1
            assert [o["watch_id"] for o in agent._observations] == [trace_id]

            agent._observations.clear()
            injector.uninject(trace_id)
            trace_id = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert not injector.instrumented

            assert mod.target_fn(2) == 12
            assert agent._observations == []
            assert monitor_cmd.manager.get_stats(monitor_id)["total"] == 2

            self._stop_monitor(monitor_cmd, monitor_id)
            monitor_id = None

            self._assert_final_stop(mod, original, injector, monitor_cmd)
            assert mod.target_fn(3) == 13
        finally:
            if trace_id and trace_id in injector.instrumented:
                injector.uninject(trace_id)
            if monitor_id and monitor_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            sys.modules.pop(module_name, None)

    def test_stop_order_monitor_stack_stop_monitor_then_stack(self) -> None:
        agent, injector, monitor_cmd = self._build_tools()
        module_name = "test_stop_order_mon_stack_ms"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        monitor_id = stack_id = None
        try:
            monitor_id = self._start_monitor(monitor_cmd, pattern)
            stack_id = self._start_stack(injector, pattern)

            assert mod.target_fn(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_id)["total"] == 1
            assert [o["watch_id"] for o in agent._observations] == [stack_id]

            agent._observations.clear()
            self._stop_monitor(monitor_cmd, monitor_id)
            monitor_id = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert not monitor_cmd._monitors

            assert mod.target_fn(2) == 12
            assert [o["watch_id"] for o in agent._observations] == [stack_id]

            agent._observations.clear()
            injector.uninject(stack_id)
            stack_id = None

            self._assert_final_stop(mod, original, injector, monitor_cmd)
            assert mod.target_fn(3) == 13
        finally:
            if stack_id and stack_id in injector.instrumented:
                injector.uninject(stack_id)
            if monitor_id and monitor_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            sys.modules.pop(module_name, None)

    def test_stop_order_stack_above_monitor(self) -> None:
        agent, injector, monitor_cmd = self._build_tools()
        module_name = "test_stop_order_stack_above_mon"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        monitor_id = stack_id = None
        try:
            monitor_id = self._start_monitor(monitor_cmd, pattern)
            monitor_wrapper = getattr(mod, "target_fn")
            assert monitor_wrapper is not original

            stack_id = self._start_stack(injector, pattern)
            assert getattr(mod, "target_fn") is not monitor_wrapper

            assert mod.target_fn(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_id)["total"] == 1
            assert [o["watch_id"] for o in agent._observations] == [stack_id]

            agent._observations.clear()
            injector.uninject(stack_id)
            stack_id = None

            assert not injector.instrumented
            assert getattr(mod, "target_fn") is monitor_wrapper
            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)

            assert mod.target_fn(2) == 12
            assert agent._observations == []
            assert monitor_cmd.manager.get_stats(monitor_id)["total"] == 2

            self._stop_monitor(monitor_cmd, monitor_id)
            monitor_id = None

            self._assert_final_stop(mod, original, injector, monitor_cmd)
            assert mod.target_fn(3) == 13
        finally:
            if stack_id and stack_id in injector.instrumented:
                injector.uninject(stack_id)
            if monitor_id and monitor_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            sys.modules.pop(module_name, None)

    def test_stop_order_watch_monitor_trace_forward(self) -> None:
        agent, injector, monitor_cmd = self._build_tools()
        module_name = "test_stop_order_watch_mon_trace_fwd"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        watch_id = monitor_id = trace_id = None
        try:
            watch_id = self._start_watch(injector, pattern)
            monitor_id = self._start_monitor(monitor_cmd, pattern)
            trace_id = self._start_trace(injector, pattern)

            assert mod.target_fn(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_id)["total"] == 1
            assert {o["watch_id"] for o in agent._observations} == {watch_id, trace_id}

            agent._observations.clear()
            injector.uninject(watch_id)
            watch_id = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert watch_id not in injector.instrumented

            assert mod.target_fn(2) == 12
            assert monitor_cmd.manager.get_stats(monitor_id)["total"] == 2
            assert {o["watch_id"] for o in agent._observations} == {trace_id}

            agent._observations.clear()
            self._stop_monitor(monitor_cmd, monitor_id)
            monitor_id = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert not monitor_cmd._monitors

            assert mod.target_fn(3) == 13
            assert {o["watch_id"] for o in agent._observations} == {trace_id}

            agent._observations.clear()
            injector.uninject(trace_id)
            trace_id = None

            self._assert_final_stop(mod, original, injector, monitor_cmd)
            assert mod.target_fn(4) == 14
        finally:
            if watch_id and watch_id in injector.instrumented:
                injector.uninject(watch_id)
            if trace_id and trace_id in injector.instrumented:
                injector.uninject(trace_id)
            if monitor_id and monitor_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            injector.uninject_all()
            sys.modules.pop(module_name, None)

    def test_stop_order_watch_monitor_trace_reverse(self) -> None:
        agent, injector, monitor_cmd = self._build_tools()
        module_name = "test_stop_order_watch_mon_trace_rev"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        watch_id = monitor_id = trace_id = None
        try:
            watch_id = self._start_watch(injector, pattern)
            monitor_id = self._start_monitor(monitor_cmd, pattern)
            trace_id = self._start_trace(injector, pattern)

            assert mod.target_fn(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_id)["total"] == 1
            assert {o["watch_id"] for o in agent._observations} == {watch_id, trace_id}

            agent._observations.clear()
            injector.uninject(trace_id)
            trace_id = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)

            assert mod.target_fn(2) == 12
            assert {o["watch_id"] for o in agent._observations} == {watch_id}

            agent._observations.clear()
            self._stop_monitor(monitor_cmd, monitor_id)
            monitor_id = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert not monitor_cmd._monitors

            assert mod.target_fn(3) == 13
            assert {o["watch_id"] for o in agent._observations} == {watch_id}

            agent._observations.clear()
            injector.uninject(watch_id)
            watch_id = None

            self._assert_final_stop(mod, original, injector, monitor_cmd)
            assert mod.target_fn(4) == 14
        finally:
            if watch_id and watch_id in injector.instrumented:
                injector.uninject(watch_id)
            if trace_id and trace_id in injector.instrumented:
                injector.uninject(trace_id)
            if monitor_id and monitor_id in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": monitor_id})
            injector.uninject_all()
            sys.modules.pop(module_name, None)

    def test_stop_order_monitor_watch_monitor(self) -> None:
        agent, injector, monitor_cmd = self._build_tools()
        module_name = "test_stop_order_mon_watch_mon"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        monitor_a = watch_id = monitor_b = None
        try:
            monitor_a = self._start_monitor(monitor_cmd, pattern)
            watch_id = self._start_watch(injector, pattern)
            monitor_b = self._start_monitor(monitor_cmd, pattern)

            assert mod.target_fn(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_a)["total"] == 1
            assert monitor_cmd.manager.get_stats(monitor_b)["total"] == 1
            assert [o["watch_id"] for o in agent._observations] == [watch_id]

            agent._observations.clear()
            self._stop_monitor(monitor_cmd, monitor_b)
            monitor_b = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)

            assert mod.target_fn(2) == 12
            assert monitor_cmd.manager.get_stats(monitor_a)["total"] == 2
            assert [o["watch_id"] for o in agent._observations] == [watch_id]

            agent._observations.clear()
            injector.uninject(watch_id)
            watch_id = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert not injector.instrumented

            assert mod.target_fn(3) == 13
            assert agent._observations == []
            assert monitor_cmd.manager.get_stats(monitor_a)["total"] == 3

            self._stop_monitor(monitor_cmd, monitor_a)
            monitor_a = None

            self._assert_final_stop(mod, original, injector, monitor_cmd)
            assert mod.target_fn(4) == 14
        finally:
            if watch_id and watch_id in injector.instrumented:
                injector.uninject(watch_id)
            for mid in (monitor_a, monitor_b):
                if mid and mid in monitor_cmd._monitors:
                    monitor_cmd.execute({"action": "stop", "watch_id": mid})
            injector.uninject_all()
            sys.modules.pop(module_name, None)

    def test_stop_order_watch_monitor_trace_monitor(self) -> None:
        agent, injector, monitor_cmd = self._build_tools()
        module_name = "test_stop_order_watch_mon_trace_mon"
        mod, original = self._make_target(module_name)
        pattern = f"{module_name}.target_fn"
        watch_id = monitor_a = trace_id = monitor_b = None
        try:
            watch_id = self._start_watch(injector, pattern)
            monitor_a = self._start_monitor(monitor_cmd, pattern)
            trace_id = self._start_trace(injector, pattern)
            monitor_b = self._start_monitor(monitor_cmd, pattern)

            assert mod.target_fn(1) == 11
            assert monitor_cmd.manager.get_stats(monitor_a)["total"] == 1
            assert monitor_cmd.manager.get_stats(monitor_b)["total"] == 1
            assert {o["watch_id"] for o in agent._observations} == {watch_id, trace_id}

            agent._observations.clear()
            self._stop_monitor(monitor_cmd, monitor_b)
            monitor_b = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)

            assert mod.target_fn(2) == 12
            assert monitor_cmd.manager.get_stats(monitor_a)["total"] == 2
            assert {o["watch_id"] for o in agent._observations} == {watch_id, trace_id}

            agent._observations.clear()
            injector.uninject(trace_id)
            trace_id = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)

            assert mod.target_fn(3) == 13
            assert {o["watch_id"] for o in agent._observations} == {watch_id}
            assert monitor_cmd.manager.get_stats(monitor_a)["total"] == 3

            agent._observations.clear()
            self._stop_monitor(monitor_cmd, monitor_a)
            monitor_a = None

            live = self._live_wrappers(injector, monitor_cmd)
            _assert_no_inactive_peeka_wrappers(getattr(mod, "target_fn"), live)
            assert not monitor_cmd._monitors

            assert mod.target_fn(4) == 14
            assert {o["watch_id"] for o in agent._observations} == {watch_id}

            agent._observations.clear()
            injector.uninject(watch_id)
            watch_id = None

            self._assert_final_stop(mod, original, injector, monitor_cmd)
            assert mod.target_fn(5) == 15
        finally:
            if watch_id and watch_id in injector.instrumented:
                injector.uninject(watch_id)
            if trace_id and trace_id in injector.instrumented:
                injector.uninject(trace_id)
            for mid in (monitor_a, monitor_b):
                if mid and mid in monitor_cmd._monitors:
                    monitor_cmd.execute({"action": "stop", "watch_id": mid})
            injector.uninject_all()
            sys.modules.pop(module_name, None)
