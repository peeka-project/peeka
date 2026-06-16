"""Tests for reset command - restore enhanced methods to original state."""

import sys
from typing import Any

import pytest


class MockAgent:
    """Mock agent for testing commands without full PeekaAgent setup."""

    def __init__(self):
        self._observations = []
        from peeka.core.observer import ObservationManager

        self.observer = ObservationManager()

    def _send_observation(self, observation):
        self._observations.append(observation)


class TestResetCommand:
    """Test suite for reset command functionality."""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent for testing."""
        return MockAgent()

    @pytest.fixture
    def injector(self, mock_agent):
        """Create a DecoratorInjector instance for testing."""
        from peeka.core.injector import DecoratorInjector

        return DecoratorInjector(mock_agent)

    @pytest.fixture
    def reset_cmd(self, mock_agent):
        """Create a ResetCommand instance for testing."""
        from peeka.commands.reset import ResetCommand

        return ResetCommand(mock_agent)

    def test_reset_all(self, injector, mock_agent):
        """Test resetting all enhancements."""

        def func_a():
            return "a"

        def func_b():
            return "b"

        test_module = type(sys)("test_module_reset_all")
        test_module.func_a = func_a
        test_module.func_b = func_b
        sys.modules["test_module_reset_all"] = test_module

        try:
            watch_id_1 = injector.inject("test_module_reset_all.func_a", {"depth": 2})
            watch_id_2 = injector.inject("test_module_reset_all.func_b", {"depth": 2})

            assert len(injector.instrumented) == 2

            response = injector.reset()

            assert response["status"] == "success"
            assert response["action"] == "reset"
            assert response["count"] == 2
            assert len(response["affected"]) == 2

            affected_ids = [a["watch_id"] for a in response["affected"]]
            assert watch_id_1 in affected_ids
            assert watch_id_2 in affected_ids

            assert len(injector.instrumented) == 0

        finally:
            del sys.modules["test_module_reset_all"]

    def test_reset_with_pattern(self, injector, mock_agent):
        """Test resetting with pattern matching."""

        def func1():
            return 1

        def func2():
            return 2

        def func3():
            return 3

        mod1 = type(sys)("mod1")
        mod1.func1 = func1
        mod1.func2 = func2
        sys.modules["mod1"] = mod1

        mod2 = type(sys)("mod2")
        mod2.func3 = func3
        sys.modules["mod2"] = mod2

        try:
            watch_id_1 = injector.inject("mod1.func1", {"depth": 2})
            watch_id_2 = injector.inject("mod1.func2", {"depth": 2})
            watch_id_3 = injector.inject("mod2.func3", {"depth": 2})

            assert len(injector.instrumented) == 3

            response = injector.reset("mod1.*")

            assert response["status"] == "success"
            assert response["action"] == "reset"
            assert response["count"] == 2
            assert len(response["affected"]) == 2

            affected_ids = [a["watch_id"] for a in response["affected"]]
            assert watch_id_1 in affected_ids
            assert watch_id_2 in affected_ids
            assert watch_id_3 not in affected_ids

            assert len(injector.instrumented) == 1
            assert watch_id_3 in injector.instrumented

        finally:
            del sys.modules["mod1"]
            del sys.modules["mod2"]

    def test_reset_with_exact_pattern(self, injector, mock_agent):
        """Test resetting with exact pattern match."""

        def func1():
            return 1

        def func2():
            return 2

        test_module = type(sys)("test_exact_pattern")
        test_module.func1 = func1
        test_module.func2 = func2
        sys.modules["test_exact_pattern"] = test_module

        try:
            watch_id_1 = injector.inject("test_exact_pattern.func1", {"depth": 2})
            watch_id_2 = injector.inject("test_exact_pattern.func2", {"depth": 2})

            assert len(injector.instrumented) == 2

            response = injector.reset("test_exact_pattern.func1")

            assert response["status"] == "success"
            assert response["count"] == 1
            assert len(response["affected"]) == 1

            assert response["affected"][0]["watch_id"] == watch_id_1
            assert len(injector.instrumented) == 1
            assert watch_id_2 in injector.instrumented

        finally:
            del sys.modules["test_exact_pattern"]

    def test_reset_no_match(self, injector, mock_agent):
        """Test reset with pattern that matches nothing."""

        def func1():
            return 1

        def func2():
            return 2

        test_module = type(sys)("test_no_match")
        test_module.func1 = func1
        test_module.func2 = func2
        sys.modules["test_no_match"] = test_module

        try:
            injector.inject("test_no_match.func1", {"depth": 2})
            injector.inject("test_no_match.func2", {"depth": 2})

            assert len(injector.instrumented) == 2

            response = injector.reset("nonexistent.*")

            assert response["status"] == "success"
            assert response["action"] == "reset"
            assert response["count"] == 0
            assert len(response["affected"]) == 0

            assert len(injector.instrumented) == 2

        finally:
            del sys.modules["test_no_match"]

    def test_list_enhanced(self, injector, mock_agent):
        """Test listing current enhancements."""

        def func1():
            return 1

        def func2():
            return 2

        test_module = type(sys)("test_list_enhanced")
        test_module.func1 = func1
        test_module.func2 = func2
        sys.modules["test_list_enhanced"] = test_module

        try:
            watch_id_1 = injector.inject(
                "test_list_enhanced.func1",
                {"depth": 2, "command": "watch"},
            )
            watch_id_2 = injector.inject(
                "test_list_enhanced.func2",
                {"depth": 2, "command": "stack"},
            )

            response = injector.list_enhanced()

            assert response["status"] == "success"
            assert response["action"] == "list"
            assert response["total"] == 2
            assert len(response["enhanced"]) == 2

            enhanced_dict = {e["watch_id"]: e for e in response["enhanced"]}
            assert watch_id_1 in enhanced_dict
            assert watch_id_2 in enhanced_dict

            assert enhanced_dict[watch_id_1]["pattern"] == "test_list_enhanced.func1"
            assert enhanced_dict[watch_id_1]["command"] == "watch"
            assert enhanced_dict[watch_id_2]["pattern"] == "test_list_enhanced.func2"
            assert enhanced_dict[watch_id_2]["command"] == "stack"

            assert "count" in enhanced_dict[watch_id_1]
            assert "count" in enhanced_dict[watch_id_2]

        finally:
            del sys.modules["test_list_enhanced"]

    def test_list_empty(self, injector, mock_agent):
        """Test listing when no enhancements."""
        response = injector.list_enhanced()

        assert response["status"] == "success"
        assert response["action"] == "list"
        assert response["total"] == 0
        assert len(response["enhanced"]) == 0

    def test_reset_already_empty(self, injector, mock_agent):
        """Test reset when nothing to reset."""
        response = injector.reset()

        assert response["status"] == "success"
        assert response["action"] == "reset"
        assert response["count"] == 0
        assert len(response["affected"]) == 0

    def test_reset_command_execute_reset_action(self, reset_cmd, mock_agent):
        """Test ResetCommand.execute() with reset action."""

        def func1():
            return 1

        test_module = type(sys)("test_cmd_reset")
        test_module.func1 = func1
        sys.modules["test_cmd_reset"] = test_module

        try:
            from peeka.core.injector import DecoratorInjector

            injector = DecoratorInjector(mock_agent)
            injector.inject("test_cmd_reset.func1", {"depth": 2})

            reset_cmd.agent.injector = injector

            response = reset_cmd.execute({"action": "reset"})

            assert response["status"] == "success"
            assert response["action"] == "reset"
            assert response["count"] == 1
            assert len(response["affected"]) == 1

        finally:
            del sys.modules["test_cmd_reset"]

    def test_reset_command_execute_list_action(self, reset_cmd, mock_agent):
        """Test ResetCommand.execute() with list action."""

        def func1():
            return 1

        test_module = type(sys)("test_cmd_list")
        test_module.func1 = func1
        sys.modules["test_cmd_list"] = test_module

        try:
            from peeka.core.injector import DecoratorInjector

            injector = DecoratorInjector(mock_agent)
            watch_id = injector.inject("test_cmd_list.func1", {"depth": 2})

            reset_cmd.agent.injector = injector

            response = reset_cmd.execute({"action": "list"})

            assert response["status"] == "success"
            assert response["action"] == "list"
            assert response["total"] == 1
            assert len(response["enhanced"]) == 1
            assert response["enhanced"][0]["watch_id"] == watch_id

        finally:
            del sys.modules["test_cmd_list"]

    def test_reset_command_execute_with_pattern(self, reset_cmd, mock_agent):
        """Test ResetCommand.execute() with pattern parameter."""

        def func1():
            return 1

        def func2():
            return 2

        mod1 = type(sys)("mod1_cmd")
        mod1.func1 = func1
        sys.modules["mod1_cmd"] = mod1

        mod2 = type(sys)("mod2_cmd")
        mod2.func2 = func2
        sys.modules["mod2_cmd"] = mod2

        try:
            from peeka.core.injector import DecoratorInjector

            injector = DecoratorInjector(mock_agent)
            watch_id_1 = injector.inject("mod1_cmd.func1", {"depth": 2})
            injector.inject("mod2_cmd.func2", {"depth": 2})

            reset_cmd.agent.injector = injector

            response = reset_cmd.execute({"action": "reset", "pattern": "mod1_cmd.*"})

            assert response["status"] == "success"
            assert response["count"] == 1
            assert response["affected"][0]["watch_id"] == watch_id_1

        finally:
            del sys.modules["mod1_cmd"]
            del sys.modules["mod2_cmd"]

    def test_reset_command_execute_invalid_action(self, reset_cmd):
        """Test ResetCommand.execute() with invalid action."""
        response = reset_cmd.execute({"action": "invalid"})

        assert response["status"] == "error"
        assert "Unknown action" in response["error"]

    def test_reset_command_execute_exception_handling(self, reset_cmd, mock_agent):
        """Test ResetCommand.execute() handles exceptions gracefully."""

        class BrokenInjector:
            def reset(self, pattern):
                raise RuntimeError("Injector error")

        reset_cmd.agent.injector = BrokenInjector()

        response = reset_cmd.execute({"action": "reset"})

        assert response["status"] == "error"
        assert "Injector error" in response["error"]

    def test_wildcard_patterns(self, injector):
        """Test various wildcard pattern matching scenarios."""
        funcs = {}
        for i in range(3):
            test_module = type(sys)(f"service_v{i}")
            test_module.query = lambda: None
            test_module.update = lambda: None
            sys.modules[f"service_v{i}"] = test_module
            funcs[f"service_v{i}"] = test_module

        try:
            watch_ids = []
            watch_ids.append(injector.inject("service_v0.query", {"depth": 2}))
            watch_ids.append(injector.inject("service_v0.update", {"depth": 2}))
            watch_ids.append(injector.inject("service_v1.query", {"depth": 2}))
            watch_ids.append(injector.inject("service_v2.update", {"depth": 2}))

            assert len(injector.instrumented) == 4

            response = injector.reset("service_v0.*")
            assert response["count"] == 2
            assert len(injector.instrumented) == 2

            injector.reset()
            assert len(injector.instrumented) == 0

            watch_ids = []
            watch_ids.append(injector.inject("service_v0.query", {"depth": 2}))
            watch_ids.append(injector.inject("service_v0.update", {"depth": 2}))
            watch_ids.append(injector.inject("service_v1.query", {"depth": 2}))
            watch_ids.append(injector.inject("service_v2.update", {"depth": 2}))

            response = injector.reset("*.query")
            assert response["count"] == 2

        finally:
            for i in range(3):
                if f"service_v{i}" in sys.modules:
                    del sys.modules[f"service_v{i}"]

    def test_pattern_matching_question_mark(self, injector):
        """Test ? wildcard pattern matching."""

        def func():
            return None

        for char in ["a", "b", "c"]:
            mod = type(sys)(f"mod_{char}")
            mod.func = func
            sys.modules[f"mod_{char}"] = mod

        try:
            watch_ids = []
            watch_ids.append(injector.inject("mod_a.func", {"depth": 2}))
            watch_ids.append(injector.inject("mod_b.func", {"depth": 2}))
            watch_ids.append(injector.inject("mod_c.func", {"depth": 2}))

            response = injector.reset("mod_?.func")
            assert response["count"] == 3

        finally:
            for char in ["a", "b", "c"]:
                if f"mod_{char}" in sys.modules:
                    del sys.modules[f"mod_{char}"]

    def test_list_enhanced_with_call_count(self, injector, mock_agent):
        """Test list_enhanced shows call count correctly."""

        def func():
            return 42

        test_module = type(sys)("test_call_count")
        test_module.func = func
        sys.modules["test_call_count"] = test_module

        try:
            watch_id = injector.inject("test_call_count.func", {"depth": 2})

            for _ in range(5):
                test_module.func()

            response = injector.list_enhanced()

            assert response["total"] == 1
            enhanced_item = response["enhanced"][0]
            assert enhanced_item["watch_id"] == watch_id
            assert enhanced_item["count"] == 5

        finally:
            del sys.modules["test_call_count"]

    def test_reset_preserves_isolation(self, mock_agent):
        """Test that reset operations on different injectors are isolated."""
        from peeka.core.injector import DecoratorInjector

        injector1 = DecoratorInjector(mock_agent)
        injector2 = DecoratorInjector(mock_agent)

        def func():
            return None

        mod1 = type(sys)("test_isolation_mod")
        mod1.func = func
        sys.modules["test_isolation_mod"] = mod1

        try:
            injector1.inject("test_isolation_mod.func", {"depth": 2})
            injector2.inject("test_isolation_mod.func", {"depth": 2})

            response1 = injector1.reset()
            assert response1["count"] == 1
            assert len(injector1.instrumented) == 0

            assert len(injector2.instrumented) == 1
            response2 = injector2.list_enhanced()
            assert response2["total"] == 1

        finally:
            del sys.modules["test_isolation_mod"]

    def test_reset_preserves_stream_observers_after_restore(self, mock_agent):
        """Reset restores functions but leaves stream observer registrations intact."""
        from peeka.commands.reset import ResetCommand
        from peeka.core.injector import DecoratorInjector

        def func():
            return "original"

        test_module = type(sys)("test_reset_stream_observer")
        test_module.func = func
        sys.modules["test_reset_stream_observer"] = test_module

        try:
            injector = DecoratorInjector(mock_agent)
            mock_agent.injector = injector
            watch_id = injector.inject(
                "test_reset_stream_observer.func",
                {"depth": 2, "command": "watch"},
            )
            mock_agent.observer.register_watch(
                watch_id,
                "test_reset_stream_observer.func",
                {"command": "watch"},
            )

            assert test_module.func is not func
            assert mock_agent.observer.get_all_stats()["active_watches"] == 1

            response = ResetCommand(mock_agent).execute({"action": "reset"})

            assert response["status"] == "success"
            assert response["count"] == 1
            assert test_module.func is func
            assert injector.instrumented == {}
            assert mock_agent.observer.get_all_stats()["active_watches"] == 1
            assert mock_agent.observer.get_watch_stats(watch_id) is not None

        finally:
            del sys.modules["test_reset_stream_observer"]


class TestResetMonitorInteraction:
    """T3: reset must stop and restore active monitor wrappers."""

    @pytest.fixture
    def mod_and_fn(self):
        def target(x):
            return x + 5

        mod = type(sys)("test_reset_monitor_mod")
        mod.target = target
        sys.modules["test_reset_monitor_mod"] = mod
        yield mod, target
        sys.modules.pop("test_reset_monitor_mod", None)

    def _make_agent_with_monitor(self, mod, fn_name):
        from peeka.commands.monitor import MonitorCommand
        from peeka.core.injector import DecoratorInjector
        from peeka.commands.reset import ResetCommand
        from peeka.core.observer import ObservationManager

        class _Agent:
            injector: Any
            monitor_cmd: Any

            def __init__(self):
                self._observations = []
                self.observer = ObservationManager()
                self.injector = None
                self.monitor_cmd = None

            def _send_observation(self, obs):
                self._observations.append(obs)

        agent = _Agent()
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]
        agent.injector = injector
        monitor_cmd = MonitorCommand(agent)  # pyright: ignore[reportArgumentType]
        agent.monitor_cmd = monitor_cmd
        reset_cmd = ResetCommand(agent)  # pyright: ignore[reportArgumentType]
        return agent, injector, monitor_cmd, reset_cmd

    def test_reset_monitor_all_stops_monitor_and_restores_callable(self, mod_and_fn):
        """reset-all must stop active monitor, restore callable, and clear monitor state."""
        mod, original_fn = mod_and_fn
        agent, injector, monitor_cmd, reset_cmd = self._make_agent_with_monitor(
            mod, "target"
        )

        start = monitor_cmd.execute(
            {"action": "start", "pattern": "test_reset_monitor_mod.target", "cycle": 60}
        )
        assert start["status"] == "success"
        watch_id = start["watch_id"]
        assert mod.target is not original_fn, "monitor should wrap the callable"

        setattr(reset_cmd.agent, "monitor_cmd", monitor_cmd)
        response = reset_cmd.execute({"action": "reset"})

        assert response["status"] == "success"
        assert mod.target is original_fn, (
            "reset must restore callable to original after stopping monitor"
        )
        assert watch_id not in monitor_cmd._monitors, (
            "reset must remove monitor from _monitors"
        )

    def test_reset_stops_monitor_first_watch_second(self, mod_and_fn):
        """reset must stop the monitor before restoring the watch wrapper."""
        mod, original_fn = mod_and_fn
        agent, injector, monitor_cmd, reset_cmd = self._make_agent_with_monitor(
            mod, "target"
        )
        call_order = []

        original_monitor_execute = monitor_cmd.execute
        original_injector_reset = injector.reset

        def recording_monitor_execute(params):
            if params.get("action") == "stop":
                call_order.append("monitor")
            return original_monitor_execute(params)

        def recording_injector_reset(pattern=None):
            call_order.append("watch")
            return original_injector_reset(pattern)

        monitor_cmd.execute = recording_monitor_execute  # type: ignore[assignment]
        injector.reset = recording_injector_reset  # type: ignore[assignment]

        start = original_monitor_execute(
            {"action": "start", "pattern": "test_reset_monitor_mod.target", "cycle": 60}
        )
        assert start["status"] == "success"
        watch_id = start["watch_id"]

        injected_watch_id = injector.inject(
            "test_reset_monitor_mod.target", {"depth": 2}
        )

        assert mod.target is not original_fn, "watch wrapper should sit above monitor"
        assert mod.target(1) == 6
        stats = monitor_cmd.manager.get_stats(watch_id)
        assert stats is not None
        assert stats["total"] == 1
        assert watch_id in monitor_cmd._monitors
        assert injected_watch_id in injector.instrumented

        response = reset_cmd.execute({"action": "reset"})

        assert response["status"] == "success"
        assert call_order == ["monitor", "watch"]
        assert mod.target is original_fn
        assert watch_id not in monitor_cmd._monitors
        assert injected_watch_id not in injector.instrumented
        assert monitor_cmd.manager.get_stats(watch_id) is None

    def test_reset_preserves_user_decorator_after_monitor_stop(self, mod_and_fn):
        """reset must restore the user decorator object, not the raw function."""
        from functools import wraps

        mod, raw_fn = mod_and_fn
        calls = []

        def record_calls(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                calls.append((args, kwargs))
                return fn(*args, **kwargs)

            return wrapper

        decorated_fn = record_calls(raw_fn)
        mod.target = decorated_fn

        agent, injector, monitor_cmd, reset_cmd = self._make_agent_with_monitor(
            mod, "target"
        )

        start = monitor_cmd.execute(
            {"action": "start", "pattern": "test_reset_monitor_mod.target", "cycle": 60}
        )
        assert start["status"] == "success"
        assert mod.target is not decorated_fn

        response = reset_cmd.execute({"action": "reset"})

        assert response["status"] == "success"
        assert mod.target is decorated_fn
        assert mod.target is not raw_fn
        assert mod.target(7) == 12
        assert calls == [((7,), {})]

    def test_reset_monitor_pattern_stops_matching_monitor_only(self, mod_and_fn):
        """reset pattern must stop only monitors whose pattern matches."""
        mod, original_fn = mod_and_fn

        def other_fn(x):
            return x * 2

        mod2 = type(sys)("test_reset_monitor_mod2")
        mod2.other_fn = other_fn
        sys.modules["test_reset_monitor_mod2"] = mod2

        try:
            agent, injector, monitor_cmd, reset_cmd = self._make_agent_with_monitor(
                mod, "target"
            )

            start1 = monitor_cmd.execute(
                {"action": "start", "pattern": "test_reset_monitor_mod.target", "cycle": 60}
            )
            start2 = monitor_cmd.execute(
                {"action": "start", "pattern": "test_reset_monitor_mod2.other_fn", "cycle": 60}
            )
            assert start1["status"] == "success"
            assert start2["status"] == "success"
            wid1 = start1["watch_id"]
            wid2 = start2["watch_id"]

            setattr(reset_cmd.agent, "monitor_cmd", monitor_cmd)
            response = reset_cmd.execute(
                {"action": "reset", "pattern": "test_reset_monitor_mod.target"}
            )

            assert response["status"] == "success"
            assert mod.target is original_fn, "matched monitor callable must be restored"
            assert wid1 not in monitor_cmd._monitors, "matched monitor must be removed"
            assert wid2 in monitor_cmd._monitors, "unmatched monitor must remain active"

            monitor_cmd.execute({"action": "stop", "watch_id": wid2})
        finally:
            sys.modules.pop("test_reset_monitor_mod2", None)


    def test_reset_resolves_monitor_via_command_handlers(self, mod_and_fn):
        """Regression: reset must find the monitor handler through real agent command_handlers.

        Real PeekaAgent stores handlers in self.command_handlers and exposes
        _get_handler(); it never has agent.monitor_cmd. Current ResetCommand
        only checks getattr(self.agent, 'monitor_cmd', None), so on a real
        agent monitor wrappers are never cleaned up.
        """
        from peeka.commands.monitor import MonitorCommand
        from peeka.core.injector import DecoratorInjector
        from peeka.commands.reset import ResetCommand
        from peeka.core.observer import ObservationManager

        mod, original_fn = mod_and_fn

        class _RealishAgent:
            injector: Any
            monitor_cmd: Any

            def __init__(self):
                self._observations = []
                self.observer = ObservationManager()
                self.command_handlers = {}
                self.injector = None
                self.monitor_cmd = None

            def _send_observation(self, obs):
                self._observations.append(obs)

            def _get_handler(self, cmd_type):
                handler = self.command_handlers.get(cmd_type)
                if handler is not None:
                    return handler
                if cmd_type == "monitor":
                    handler = MonitorCommand(self)  # pyright: ignore[reportArgumentType]
                    self.command_handlers[cmd_type] = handler
                    return handler
                return None

        agent = _RealishAgent()
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]
        agent.injector = injector
        monitor_cmd = agent._get_handler("monitor")
        assert monitor_cmd is not None
        reset_cmd = ResetCommand(agent)  # pyright: ignore[reportArgumentType]

        start = monitor_cmd.execute(
            {"action": "start", "pattern": "test_reset_monitor_mod.target", "cycle": 60}
        )
        assert start["status"] == "success"
        watch_id = start["watch_id"]
        assert mod.target is not original_fn

        response = reset_cmd.execute({"action": "reset"})
        assert response["status"] == "success"

        assert mod.target is original_fn, (
            "reset must restore the callable — monitor handler must be resolved "
            "via command_handlers/_get_handler, not just agent.monitor_cmd"
        )
        assert watch_id not in monitor_cmd._monitors, (
            "reset must remove the monitor from _monitors via real handler lookup"
        )


class TestResetLifecycleRegression:
    """Regression tests for reset lifecycle gaps (Task 4 — probe-lifecycle-fix)."""

    def _make_handler_agent(self):
        from peeka.commands.monitor import MonitorCommand
        from peeka.commands.reset import ResetCommand
        from peeka.core.injector import DecoratorInjector
        from peeka.core.observer import ObservationManager
        from typing import Any

        class _HandlerAgent:
            injector: Any
            monitor_cmd: Any

            def __init__(self):
                self._observations = []
                self.observer = ObservationManager()
                self.command_handlers: dict = {}
                self.injector = None
                self.monitor_cmd = None

            def _send_observation(self, obs):
                self._observations.append(obs)

            def _get_handler(self, cmd_type):
                handler = self.command_handlers.get(cmd_type)
                if handler is not None:
                    return handler
                if cmd_type == "monitor":
                    handler = MonitorCommand(self)  # pyright: ignore[reportArgumentType]
                    self.command_handlers[cmd_type] = handler
                    return handler
                return None

        agent = _HandlerAgent()
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]
        agent.injector = injector
        monitor_cmd = agent._get_handler("monitor")
        reset_cmd = ResetCommand(agent)  # pyright: ignore[reportArgumentType]
        return agent, injector, monitor_cmd, reset_cmd

    def test_reset_removes_monitor_in_real_handler_registry(self):
        """After reset, _monitors must be empty when monitor is stored via command_handlers.

        Regression: reset must resolve MonitorCommand through _get_handler /
        command_handlers, not only agent.monitor_cmd, so that active monitors
        registered in that real-handler registry are stopped and removed.
        """

        def target(x):
            return x + 1

        mod = type(sys)("test_rlr_handler_registry")
        mod.target = target
        sys.modules["test_rlr_handler_registry"] = mod

        try:
            agent, injector, monitor_cmd, reset_cmd = self._make_handler_agent()

            start = monitor_cmd.execute(
                {"action": "start", "pattern": "test_rlr_handler_registry.target", "cycle": 60}
            )
            assert start["status"] == "success"
            watch_id = start["watch_id"]

            assert watch_id in monitor_cmd._monitors

            response = reset_cmd.execute({"action": "reset"})

            assert response["status"] == "success"
            assert monitor_cmd._monitors == {}, (
                "reset must empty _monitors when handler is resolved via command_handlers"
            )
        finally:
            sys.modules.pop("test_rlr_handler_registry", None)

    def test_reset_mixed_probes_leaves_no_active_wrapper(self):
        """After reset, the canonical slot must be the pre-Peeka original even when
        watch, trace, and monitor probes were all active on the same target.
        """

        def target(x):
            return x * 2

        mod = type(sys)("test_rlr_mixed_probes")
        mod.target = target
        sys.modules["test_rlr_mixed_probes"] = mod

        try:
            agent, injector, monitor_cmd, reset_cmd = self._make_handler_agent()

            mon_start = monitor_cmd.execute(
                {"action": "start", "pattern": "test_rlr_mixed_probes.target", "cycle": 60}
            )
            assert mon_start["status"] == "success"

            watch_id = injector.inject(
                "test_rlr_mixed_probes.target", {"depth": 2, "command": "watch"}
            )

            trace_id = injector.inject_trace(
                "test_rlr_mixed_probes.target", {"depth": 2}
            )

            assert mod.target is not target

            response = reset_cmd.execute({"action": "reset"})

            assert response["status"] == "success"
            assert mod.target is target, (
                "reset must restore canonical slot to original even with "
                "watch + trace + monitor all active"
            )
            assert watch_id not in injector.instrumented
            assert trace_id not in injector.instrumented
            assert monitor_cmd._monitors == {}
        finally:
            sys.modules.pop("test_rlr_mixed_probes", None)

    def test_reset_restores_aliases(self):
        """reset must restore module-level aliases back to the original callable.

        When inject() discovers an alias in another module and replaces it with
        the wrapper, reset() must undo that alias replacement so the alias slot
        points at the original function again.
        """

        def handler(event):
            return event

        primary_mod = type(sys)("test_rlr_alias_primary")
        primary_mod.handler = handler
        alias_mod = type(sys)("test_rlr_alias_secondary")
        alias_mod.handler = handler
        sys.modules["test_rlr_alias_primary"] = primary_mod
        sys.modules["test_rlr_alias_secondary"] = alias_mod

        try:
            from peeka.commands.reset import ResetCommand
            from peeka.core.injector import DecoratorInjector
            from peeka.core.observer import ObservationManager

            class _Agent:
                def __init__(self):
                    self._observations = []
                    self.observer = ObservationManager()

                def _send_observation(self, obs):
                    self._observations.append(obs)

            agent = _Agent()
            injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]
            agent.injector = injector  # type: ignore[attr-defined]

            watch_id = injector.inject("test_rlr_alias_primary.handler", {"depth": 2})

            assert primary_mod.handler is not handler
            assert alias_mod.handler is not handler
            assert primary_mod.handler is alias_mod.handler

            response = ResetCommand(agent).execute({"action": "reset"})  # pyright: ignore[reportArgumentType]

            assert response["status"] == "success"
            assert primary_mod.handler is handler, "canonical slot must be restored"
            assert alias_mod.handler is handler, "alias slot must also be restored"
            assert watch_id not in injector.instrumented
        finally:
            sys.modules.pop("test_rlr_alias_primary", None)
            sys.modules.pop("test_rlr_alias_secondary", None)

    def test_reset_after_monitor_stop_restores_original(self):
        """reset after an explicit monitor stop must still restore the callable.

        If a monitor is started and then manually stopped before reset is called,
        reset must leave the canonical slot as the original function (not a
        stale wrapper) and must not error on an already-empty _monitors dict.
        """

        def target(x):
            return x - 1

        mod = type(sys)("test_rlr_after_stop")
        mod.target = target
        sys.modules["test_rlr_after_stop"] = mod

        try:
            agent, injector, monitor_cmd, reset_cmd = self._make_handler_agent()

            start = monitor_cmd.execute(
                {"action": "start", "pattern": "test_rlr_after_stop.target", "cycle": 60}
            )
            assert start["status"] == "success"
            watch_id = start["watch_id"]

            stop = monitor_cmd.execute({"action": "stop", "watch_id": watch_id})
            assert stop["status"] == "success"
            assert watch_id not in monitor_cmd._monitors
            assert mod.target is target

            injected_id = injector.inject(
                "test_rlr_after_stop.target", {"depth": 2, "command": "watch"}
            )
            assert mod.target is not target

            response = reset_cmd.execute({"action": "reset"})

            assert response["status"] == "success", f"reset failed: {response}"
            assert mod.target is target, (
                "reset must restore canonical even when monitor was already stopped"
            )
            assert injected_id not in injector.instrumented
            assert monitor_cmd._monitors == {}
        finally:
            sys.modules.pop("test_rlr_after_stop", None)

    def test_reset_with_pattern_only_affects_matching(self):
        """reset with a specific pattern must only affect probes that match.

        Probes on a non-matching target (different module) must remain active
        and their canonical slots must remain wrapped after the partial reset.
        """

        def fn_a(x):
            return x

        def fn_b(x):
            return x + 10

        mod_a = type(sys)("test_rlr_pattern_a")
        mod_a.fn = fn_a
        mod_b = type(sys)("test_rlr_pattern_b")
        mod_b.fn = fn_b
        sys.modules["test_rlr_pattern_a"] = mod_a
        sys.modules["test_rlr_pattern_b"] = mod_b

        try:
            agent, injector, monitor_cmd, reset_cmd = self._make_handler_agent()

            # Start monitors on both targets
            start_a = monitor_cmd.execute(
                {"action": "start", "pattern": "test_rlr_pattern_a.fn", "cycle": 60}
            )
            start_b = monitor_cmd.execute(
                {"action": "start", "pattern": "test_rlr_pattern_b.fn", "cycle": 60}
            )
            assert start_a["status"] == "success"
            assert start_b["status"] == "success"
            wid_a = start_a["watch_id"]
            wid_b = start_b["watch_id"]

            watch_a = injector.inject("test_rlr_pattern_a.fn", {"depth": 2})
            watch_b = injector.inject("test_rlr_pattern_b.fn", {"depth": 2})

            response = reset_cmd.execute(
                {"action": "reset", "pattern": "test_rlr_pattern_a.*"}
            )

            assert response["status"] == "success"

            assert mod_a.fn is fn_a, "canonical for pattern_a must be restored"
            assert wid_a not in monitor_cmd._monitors, "monitor_a must be removed"
            assert watch_a not in injector.instrumented, "watch_a must be removed"

            assert mod_b.fn is not fn_b, "canonical for pattern_b must remain wrapped"
            assert wid_b in monitor_cmd._monitors, "monitor_b must still be active"
            assert watch_b in injector.instrumented, "watch_b must still be active"

            monitor_cmd.execute({"action": "stop", "watch_id": wid_b})
            injector.uninject(watch_b)
        finally:
            sys.modules.pop("test_rlr_pattern_a", None)
            sys.modules.pop("test_rlr_pattern_b", None)


class TestResetListMonitorRegression:
    """Regression tests for reset --list including active monitors (T3 fix).

    Verifies that _list_enhanced() merges MonitorCommand._monitors entries
    into the list response so consumers can see active monitors alongside
    injector entries.
    """

    def _make_agent_with_mock_monitor(self, monitors=None):
        """Create a minimal agent with a mock MonitorCommand in command_handlers."""
        import threading

        from peeka.commands.reset import ResetCommand
        from peeka.core.injector import DecoratorInjector
        from peeka.core.observer import ObservationManager

        class _MockMonitorCmd:
            def __init__(self, monitors_dict):
                self._lock = threading.Lock()
                self._monitors = monitors_dict if monitors_dict is not None else {}

        class _Agent:
            def __init__(self):
                self._observations = []
                self.observer = ObservationManager()
                self.command_handlers = {}
                self.injector = None

            def _send_observation(self, obs):
                self._observations.append(obs)

        agent = _Agent()
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]
        agent.injector = injector
        mock_monitor = _MockMonitorCmd(monitors)
        agent.command_handlers["monitor"] = mock_monitor
        reset_cmd = ResetCommand(agent)  # pyright: ignore[reportArgumentType]
        return agent, injector, mock_monitor, reset_cmd

    def test_reset_list_includes_active_monitor(self):
        """reset --list must include active monitor entries alongside injector entries.

        Regression for T3: _list_enhanced() must merge MonitorCommand._monitors
        entries into the list response so TUI/CLI consumers can see active monitors.
        """
        agent, injector, mock_monitor, reset_cmd = self._make_agent_with_mock_monitor(
            monitors={
                "monitor_abc123": {
                    "pattern": "mymodule.*",
                    "cycle": 1.0,
                    "cycles": 5,
                    "cycle_count": 2,
                }
            }
        )

        response = reset_cmd.execute({"action": "list"})

        assert response["status"] == "success"
        enhanced = response["enhanced"]
        assert response["total"] == len(enhanced)

        monitor_entries = [e for e in enhanced if e.get("command") == "monitor"]
        assert len(monitor_entries) >= 1, "reset --list must include active monitor entries"

        monitor_entry = next(
            (e for e in monitor_entries if e.get("monitor_id") == "monitor_abc123"),
            None,
        )
        assert monitor_entry is not None, (
            "monitor_abc123 must appear in reset --list enhanced entries"
        )
        assert monitor_entry["monitor_id"] == "monitor_abc123"
        assert monitor_entry["command"] == "monitor"

    def test_reset_list_no_monitors_works(self):
        """reset --list must work correctly when no monitors are active.

        Regression: must not raise or error when monitor handler exists but
        has empty _monitors dict — should return only injector entries.
        """
        agent, injector, mock_monitor, reset_cmd = self._make_agent_with_mock_monitor(
            monitors={}
        )

        response = reset_cmd.execute({"action": "list"})

        assert response["status"] == "success"
        assert response["action"] == "list"
        assert response["total"] == 0
        assert len(response["enhanced"]) == 0
