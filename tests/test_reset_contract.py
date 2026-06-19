"""
Contract tests for ResetCommand monitor resource cleanup.

# regression: c03971e
"""

import sys
import threading
from types import ModuleType
from typing import Any, Dict, List, cast

import pytest

from peeka.commands.monitor import MonitorCommand
from peeka.commands.reset import ResetCommand
from peeka.commands.top import TopCommand


class _ContractAgent:
    def __init__(self) -> None:
        from peeka.core.injector import DecoratorInjector
        from peeka.core.observer import ObservationManager

        self.attached_pid: int = 12345
        self.observer = ObservationManager()
        self.injector = DecoratorInjector(cast(Any, self))
        self.command_handlers: Dict[str, Any] = {}
        self._observations: List[Any] = []

    def _send_observation(self, observation: Any) -> None:
        self._observations.append(observation)

    def stop(self) -> None:
        pass


@pytest.mark.integration
class TestResetContractCleanup:
    # regression: c03971e

    def test_reset_pattern_stops_matching_monitor_only(self) -> None:
        """Reset with pattern stops matched monitor; unmatched monitor remains active and wrapped."""
        mod_name_a = "test_rc_pat_match"
        mod_name_b = "test_rc_pat_unmatched"

        def fn_a(x: int) -> int:
            return x + 1

        def fn_b(x: int) -> int:
            return x * 2

        original_a = fn_a
        original_b = fn_b

        module_a = ModuleType(mod_name_a)
        setattr(module_a, "fn_a", fn_a)
        module_b = ModuleType(mod_name_b)
        setattr(module_b, "fn_b", fn_b)
        sys.modules[mod_name_a] = module_a
        sys.modules[mod_name_b] = module_b

        agent = _ContractAgent()
        monitor_cmd = MonitorCommand(cast(Any, agent))
        agent.command_handlers["monitor"] = monitor_cmd

        watch_id_a = ""
        watch_id_b = ""

        try:
            res_a = monitor_cmd.execute(
                {"action": "start", "pattern": f"{mod_name_a}.fn_a", "cycle": 60}
            )
            assert res_a["status"] == "success", f"monitor A start failed: {res_a}"
            watch_id_a = res_a["watch_id"]

            res_b = monitor_cmd.execute(
                {"action": "start", "pattern": f"{mod_name_b}.fn_b", "cycle": 60}
            )
            assert res_b["status"] == "success", f"monitor B start failed: {res_b}"
            watch_id_b = res_b["watch_id"]

            with monitor_cmd._lock:
                thread_a: threading.Thread = monitor_cmd._monitors[watch_id_a]["timer_thread"]
                thread_b: threading.Thread = monitor_cmd._monitors[watch_id_b]["timer_thread"]

            assert thread_a.is_alive(), "Monitor A timer thread must be alive before reset"
            assert thread_b.is_alive(), "Monitor B timer thread must be alive before reset"
            assert getattr(module_a, "fn_a") is not original_a, (
                "Monitor A wrapper must be installed before reset"
            )
            assert getattr(module_b, "fn_b") is not original_b, (
                "Monitor B wrapper must be installed before reset"
            )

            reset_result = ResetCommand(cast(Any, agent)).execute(
                {"action": "reset", "pattern": f"{mod_name_a}.*"}
            )
            assert reset_result["status"] == "success", f"reset failed: {reset_result}"

            # _stop_monitor joins with timeout=2 inside the lock; the thread exits
            # stop_event.wait without re-acquiring _lock, so no deadlock.
            thread_a.join(timeout=0.5)

            assert not thread_a.is_alive(), (
                "Matched monitor A timer thread must be stopped after pattern reset"
            )
            assert getattr(module_a, "fn_a") is original_a, (
                "fn_a must be restored to original after pattern reset"
            )
            assert watch_id_a not in monitor_cmd._monitors, (
                "Matched monitor A must be removed from _monitors after reset"
            )

            assert thread_b.is_alive(), (
                "Unmatched monitor B timer thread must remain alive after pattern reset"
            )
            assert getattr(module_b, "fn_b") is not original_b, (
                "fn_b wrapper must remain installed for unmatched monitor B"
            )
            assert watch_id_b in monitor_cmd._monitors, (
                "Unmatched monitor B must remain in _monitors after pattern reset"
            )

        finally:
            if watch_id_b and watch_id_b in monitor_cmd._monitors:
                monitor_cmd.execute({"action": "stop", "watch_id": watch_id_b})
            sys.modules.pop(mod_name_a, None)
            sys.modules.pop(mod_name_b, None)

    def test_reset_does_not_clear_observer_registrations(self) -> None:
        """Reset removes injected wrappers but leaves observer registration state intact."""
        mod_name = "test_rc_observer_preserve"

        def target_fn() -> str:
            return "original"

        original_fn = target_fn

        module = ModuleType(mod_name)
        setattr(module, "target_fn", target_fn)
        sys.modules[mod_name] = module

        try:
            agent = _ContractAgent()

            watch_id = agent.injector.inject(
                f"{mod_name}.target_fn",
                {"depth": 2, "command": "watch"},
            )
            agent.observer.register_watch(
                watch_id,
                f"{mod_name}.target_fn",
                {"command": "watch"},
            )

            assert getattr(module, "target_fn") is not original_fn, (
                "Injector wrapper must replace original in module slot before reset"
            )
            assert agent.observer.get_all_stats()["active_watches"] == 1, (
                "Observer must have 1 active watch before reset"
            )

            reset_result = ResetCommand(cast(Any, agent)).execute({"action": "reset"})
            assert reset_result["status"] == "success", f"reset failed: {reset_result}"
            assert reset_result["count"] == 1

            assert getattr(module, "target_fn") is original_fn, (
                "Original function must be restored in module slot after reset"
            )
            assert agent.injector.instrumented == {}, (
                "Injector instrumented dict must be empty after reset"
            )

            assert agent.observer.get_all_stats()["active_watches"] == 1, (
                "Observer active_watches must remain intact after reset"
            )
            assert agent.observer.get_watch_stats(watch_id) is not None, (
                "Observer watch stats must remain present after reset"
            )

        finally:
            sys.modules.pop(mod_name, None)

    def test_reset_all_stops_all_monitors(self) -> None:
        """Reset all stops every active monitor and restores all wrapped functions."""
        mod_name_a = "test_rc_all_mod_a"
        mod_name_b = "test_rc_all_mod_b"

        def fn_a(x: int) -> int:
            return x + 1

        def fn_b(x: int) -> int:
            return x * 2

        original_a = fn_a
        original_b = fn_b

        module_a = ModuleType(mod_name_a)
        setattr(module_a, "fn_a", fn_a)
        module_b = ModuleType(mod_name_b)
        setattr(module_b, "fn_b", fn_b)
        sys.modules[mod_name_a] = module_a
        sys.modules[mod_name_b] = module_b

        agent = _ContractAgent()
        monitor_cmd = MonitorCommand(cast(Any, agent))
        agent.command_handlers["monitor"] = monitor_cmd

        try:
            res_a = monitor_cmd.execute(
                {"action": "start", "pattern": f"{mod_name_a}.fn_a", "cycle": 60}
            )
            assert res_a["status"] == "success", f"monitor A start failed: {res_a}"
            watch_id_a: str = res_a["watch_id"]

            res_b = monitor_cmd.execute(
                {"action": "start", "pattern": f"{mod_name_b}.fn_b", "cycle": 60}
            )
            assert res_b["status"] == "success", f"monitor B start failed: {res_b}"
            watch_id_b: str = res_b["watch_id"]

            with monitor_cmd._lock:
                thread_a: threading.Thread = monitor_cmd._monitors[watch_id_a]["timer_thread"]
                thread_b: threading.Thread = monitor_cmd._monitors[watch_id_b]["timer_thread"]

            assert thread_a.is_alive(), "Monitor A must be alive before reset all"
            assert thread_b.is_alive(), "Monitor B must be alive before reset all"
            assert getattr(module_a, "fn_a") is not original_a, (
                "Monitor A wrapper must be installed before reset all"
            )
            assert getattr(module_b, "fn_b") is not original_b, (
                "Monitor B wrapper must be installed before reset all"
            )

            reset_result = ResetCommand(cast(Any, agent)).execute({"action": "reset"})
            assert reset_result["status"] == "success", f"reset all failed: {reset_result}"

            thread_a.join(timeout=0.5)
            thread_b.join(timeout=0.5)

            assert not thread_a.is_alive(), (
                "Monitor A timer thread must be stopped after reset all"
            )
            assert not thread_b.is_alive(), (
                "Monitor B timer thread must be stopped after reset all"
            )
            assert monitor_cmd._monitors == {}, (
                "All monitors must be removed from _monitors after reset all"
            )
            assert getattr(module_a, "fn_a") is original_a, (
                "fn_a must be restored to original after reset all"
            )
            assert getattr(module_b, "fn_b") is original_b, (
                "fn_b must be restored to original after reset all"
            )

        finally:
            for wid in list(monitor_cmd._monitors.keys()):
                monitor_cmd.execute({"action": "stop", "watch_id": wid})
            sys.modules.pop(mod_name_a, None)
            sys.modules.pop(mod_name_b, None)

    def test_reset_does_not_stop_top_sampler(self) -> None:
        """Critical negative contract: generic reset must NOT stop the top sampler.

        reset routes cleanup through stop_resource_owners_for_reset which only
        touches the 'monitor' handler — top is intentionally excluded at the
        lifecycle helper level.  This test makes that decision executable.
        """
        agent = _ContractAgent()
        top_cmd = TopCommand(cast(Any, agent))
        agent.command_handlers["top"] = top_cmd

        try:
            start_result = top_cmd.execute({"action": "start", "interval": 0.01})
            assert start_result["status"] == "success", f"top start failed: {start_result}"

            with top_cmd._lock:
                sampling_thread = top_cmd._sampling_thread
                top_id_before = top_cmd._top_id

            assert sampling_thread is not None, "Sampling thread must exist after start"
            assert sampling_thread.is_alive(), "Sampling thread must be alive after start"
            assert top_id_before is not None, "_top_id must be set after start"

            reset_result = ResetCommand(cast(Any, agent)).execute({"action": "reset"})
            assert reset_result["status"] == "success", f"reset failed: {reset_result}"

            # Negative contract: top sampler must NOT be stopped by generic reset
            assert sampling_thread.is_alive(), (
                "Top sampling thread must remain alive after generic reset — "
                "reset must not manage top lifecycle"
            )
            with top_cmd._lock:
                assert top_cmd._top_id is not None, (
                    "_top_id must remain set after generic reset"
                )

        finally:
            top_cmd.execute({"action": "stop"})

    def test_reset_idempotent_second_call_succeeds(self) -> None:
        """Reset twice on fresh agent with no active monitors must succeed both calls."""
        agent = _ContractAgent()

        first = ResetCommand(cast(Any, agent)).execute({"action": "reset"})
        assert first["status"] == "success", f"first reset failed: {first}"

        second = ResetCommand(cast(Any, agent)).execute({"action": "reset"})
        assert second["status"] == "success", f"second reset failed: {second}"

    def test_reset_with_no_monitor_handler_succeeds(self) -> None:
        """Reset with empty command_handlers (no 'monitor' key) must succeed without crash."""
        agent = _ContractAgent()

        result = ResetCommand(cast(Any, agent)).execute({"action": "reset"})
        assert result["status"] == "success", (
            f"reset without monitor handler failed: {result}"
        )
