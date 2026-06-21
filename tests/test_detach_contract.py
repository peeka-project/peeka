"""
Contract tests for DetachCommand resource cleanup.

# regression: c03971e
"""

import sys
import threading
from types import ModuleType
from typing import Any, Dict, List, cast

import pytest

from peeka.commands.detach import DetachCommand
from peeka.commands.monitor import MonitorCommand
from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand
from peeka.commands.top import TopCommand


class _ContractAgent:
    def __init__(self) -> None:
        from peeka.core.injector import DecoratorInjector
        from peeka.core.observer import ObservationManager

        self.attached_pid: int = 12345
        self.observer = ObservationManager()
        self.injector = DecoratorInjector(cast(Any, self))
        self.command_handlers: Dict[str, Any] = {}
        self._stop_calls: int = 0
        self._observations: List[Any] = []

    def _send_observation(self, observation: Any) -> None:
        self._observations.append(observation)

    def list_tracked_probe_types(self) -> List[str]:
        return []

    def stop(self) -> None:
        self._stop_calls += 1


@pytest.mark.integration
class TestDetachContractCleanup:
    # regression: c03971e

    def test_monitor_thread_joined_on_detach(self) -> None:
        """Detach stops the periodic timer thread of an active monitor."""
        mod_name = "test_dc_contract_thread_joined"

        def target_fn(x: int) -> int:
            return x + 1

        module = ModuleType(mod_name)
        setattr(module, "target_fn", target_fn)
        sys.modules[mod_name] = module

        try:
            agent = _ContractAgent()
            monitor_cmd = MonitorCommand(cast(Any, agent))
            agent.command_handlers["monitor"] = monitor_cmd

            result = monitor_cmd.execute(
                {"action": "start", "pattern": f"{mod_name}.target_fn", "cycle": 60}
            )
            assert result["status"] == "success", f"monitor start failed: {result}"
            watch_id: str = result["watch_id"]

            with monitor_cmd._lock:
                timer_thread: threading.Thread = monitor_cmd._monitors[watch_id]["timer_thread"]

            assert timer_thread is not None
            assert timer_thread.is_alive(), "Timer thread must be alive before detach"

            detach_result = DetachCommand(cast(Any, agent)).execute({})
            assert detach_result["status"] == "success", f"detach failed: {detach_result}"

            timer_thread.join(timeout=0.5)

            assert not timer_thread.is_alive(), "Timer thread must not be alive after detach"
            assert monitor_cmd._monitors == {}, "_monitors must be empty after detach"
        finally:
            sys.modules.pop(mod_name, None)

    def test_monitor_wrapper_restored_on_detach(self) -> None:
        """Detach restores the original function in the module attribute slot."""
        mod_name = "test_dc_contract_wrapper_restored"

        def target_fn(x: int) -> int:
            return x + 1

        original_fn = target_fn
        module = ModuleType(mod_name)
        setattr(module, "target_fn", target_fn)
        sys.modules[mod_name] = module

        try:
            agent = _ContractAgent()
            monitor_cmd = MonitorCommand(cast(Any, agent))
            agent.command_handlers["monitor"] = monitor_cmd

            result = monitor_cmd.execute(
                {"action": "start", "pattern": f"{mod_name}.target_fn", "cycle": 60}
            )
            assert result["status"] == "success"

            assert getattr(module, "target_fn") is not original_fn, (
                "Monitor wrapper must replace original in module slot"
            )

            detach_result = DetachCommand(cast(Any, agent)).execute({})
            assert detach_result["status"] == "success"

            assert getattr(module, "target_fn") is original_fn, (
                "Original function must be restored in module slot after detach"
            )
        finally:
            sys.modules.pop(mod_name, None)

    def test_top_sampling_thread_joined_on_detach(self) -> None:
        """Detach stops and clears the top sampling thread and its internal state."""
        agent = _ContractAgent()
        top_cmd = TopCommand(cast(Any, agent))
        agent.command_handlers["top"] = top_cmd

        result = top_cmd.execute({"action": "start", "interval": 0.01})
        assert result["status"] == "success", f"top start failed: {result}"

        with top_cmd._lock:
            sampling_thread = top_cmd._sampling_thread

        assert sampling_thread is not None
        assert sampling_thread.is_alive(), "Sampling thread must be alive before detach"

        try:
            detach_result = DetachCommand(cast(Any, agent)).execute({})
            assert detach_result["status"] == "success", f"detach failed: {detach_result}"

            sampling_thread.join(timeout=0.5)

            assert not sampling_thread.is_alive(), (
                "Sampling thread must not be alive after detach"
            )
            with top_cmd._lock:
                assert top_cmd._sampling_thread is None, (
                    "_sampling_thread must be None after detach"
                )
                assert top_cmd._top_id is None, "_top_id must be None after detach"
        finally:
            with top_cmd._lock:
                still_alive = (
                    top_cmd._sampling_thread is not None
                    and top_cmd._sampling_thread.is_alive()
                )
            if still_alive:
                top_cmd.execute({"action": "stop"})

    def test_multiple_monitors_all_stopped_on_detach(self) -> None:
        """Detach stops every active monitor and restores all wrapped functions."""
        mod_name_a = "test_dc_contract_multi_a"
        mod_name_b = "test_dc_contract_multi_b"

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

        try:
            agent = _ContractAgent()
            monitor_cmd = MonitorCommand(cast(Any, agent))
            agent.command_handlers["monitor"] = monitor_cmd

            res_a = monitor_cmd.execute(
                {"action": "start", "pattern": f"{mod_name_a}.fn_a", "cycle": 60}
            )
            res_b = monitor_cmd.execute(
                {"action": "start", "pattern": f"{mod_name_b}.fn_b", "cycle": 60}
            )
            assert res_a["status"] == "success"
            assert res_b["status"] == "success"

            watch_id_a: str = res_a["watch_id"]
            watch_id_b: str = res_b["watch_id"]

            with monitor_cmd._lock:
                thread_a: threading.Thread = monitor_cmd._monitors[watch_id_a]["timer_thread"]
                thread_b: threading.Thread = monitor_cmd._monitors[watch_id_b]["timer_thread"]

            assert thread_a.is_alive(), "Monitor A thread must be alive before detach"
            assert thread_b.is_alive(), "Monitor B thread must be alive before detach"
            assert getattr(module_a, "fn_a") is not original_a, "Monitor A wrapper must be installed"
            assert getattr(module_b, "fn_b") is not original_b, "Monitor B wrapper must be installed"

            detach_result = DetachCommand(cast(Any, agent)).execute({})
            assert detach_result["status"] == "success"

            thread_a.join(timeout=0.5)
            thread_b.join(timeout=0.5)

            assert not thread_a.is_alive(), "Monitor A timer thread must be stopped after detach"
            assert not thread_b.is_alive(), "Monitor B timer thread must be stopped after detach"
            assert monitor_cmd._monitors == {}, "All monitors must be removed from _monitors"
            assert getattr(module_a, "fn_a") is original_a, "fn_a must be restored to original after detach"
            assert getattr(module_b, "fn_b") is original_b, "fn_b must be restored to original after detach"
        finally:
            sys.modules.pop(mod_name_a, None)
            sys.modules.pop(mod_name_b, None)

    def test_detach_safe_with_no_handler_instantiated(self) -> None:
        """Detach succeeds for an agent that has no command_handlers attribute."""

        class _BareAgent:
            attached_pid: int = 99999

            def __init__(self) -> None:
                from peeka.core.injector import DecoratorInjector
                from peeka.core.observer import ObservationManager

                self.injector = DecoratorInjector(cast(Any, self))
                self.observer = ObservationManager()

            def _send_observation(self, observation: Any) -> None:
                pass

            def stop(self) -> None:
                pass

        agent = _BareAgent()
        assert not hasattr(agent, "command_handlers"), (
            "_BareAgent must not have command_handlers for this test to be valid"
        )

        result = DetachCommand(cast(Any, agent)).execute({})
        assert result["status"] == "success", (
            f"detach must succeed when command_handlers is absent: {result}"
        )
        assert result["pid"] == 99999

    def test_detach_with_empty_command_handlers_succeeds(self) -> None:
        """Detach succeeds when command_handlers is present but has no monitor or top keys."""
        agent = _ContractAgent()

        result = DetachCommand(cast(Any, agent)).execute({})

        assert result["status"] == "success", (
            f"detach must succeed with empty command_handlers dict: {result}"
        )
        assert agent._stop_calls == 1, (
            f"agent.stop() must be called exactly once: {agent._stop_calls}"
        )

    def test_detach_cleanup_failure_continues_structural_teardown(self) -> None:
        """A handler's stop_active_resources raising must not abort agent.stop()."""

        class _FailingHandler(ResourceOwningCommand):
            is_resource_owner = True
            cleanup_scope = CleanupScope.DETACH_ONLY

            def execute(self, params: Any) -> Dict[str, Any]:
                return {"status": "success"}

            def stop_active_resources(self, pattern: Any, reason: Any) -> Dict[str, Any]:
                raise RuntimeError("simulated cleanup failure")

            def list_active_resources(self) -> Dict[str, Any]:
                return {"active": []}

        agent = _ContractAgent()
        agent.command_handlers["monitor"] = _FailingHandler()

        result = DetachCommand(cast(Any, agent)).execute({})

        assert result["status"] == "success", (
            f"detach must succeed even when a handler raises during cleanup: {result}"
        )
        assert agent._stop_calls == 1, (
            f"agent.stop() must still be called after handler failure: {agent._stop_calls}"
        )

    def test_detach_idempotent_on_already_stopped_resources(self) -> None:
        """Second detach on an already-cleaned agent returns success without crashing."""
        mod_name = "test_dc_contract_idempotent"

        def target_fn(x: int) -> int:
            return x + 1

        module = ModuleType(mod_name)
        setattr(module, "target_fn", target_fn)
        sys.modules[mod_name] = module

        try:
            agent = _ContractAgent()
            monitor_cmd = MonitorCommand(cast(Any, agent))
            agent.command_handlers["monitor"] = monitor_cmd

            start_result = monitor_cmd.execute(
                {"action": "start", "pattern": f"{mod_name}.target_fn", "cycle": 60}
            )
            assert start_result["status"] == "success", (
                f"monitor start must succeed: {start_result}"
            )

            first_result = DetachCommand(cast(Any, agent)).execute({})
            assert first_result["status"] == "success", (
                f"first detach must succeed: {first_result}"
            )
            assert agent._stop_calls == 1

            second_result = DetachCommand(cast(Any, agent)).execute({})
            assert second_result["status"] == "success", (
                f"second detach must succeed without crash: {second_result}"
            )
        finally:
            sys.modules.pop(mod_name, None)
