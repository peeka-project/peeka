"""Tests for monitor command - statistics collection."""

import inspect
import sys
import threading
import time
from types import ModuleType
from typing import Any, Callable, cast

import pytest

from peeka.commands.monitor import MonitorCommand
from peeka.core.runtime.compat import BACKEND_WRAPPER_ONLY


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
    return MonitorCommand(mock_agent)


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
        unwrapped = inspect.unwrap(
            wrapped, stop=lambda f: not hasattr(f, "__wrapped__")
        )
        assert unwrapped is wrapped
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
