"""Tests for reset command - restore enhanced methods to original state."""

import sys

import pytest


class MockAgent:
    """Mock agent for testing commands without full PeekaAgent setup."""

    def __init__(self):
        self._observations = []

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
            watch_id_1 = injector.inject("test_no_match.func1", {"depth": 2})
            watch_id_2 = injector.inject("test_no_match.func2", {"depth": 2})

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
            watch_id = injector.inject("test_cmd_reset.func1", {"depth": 2})

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
            watch_id_2 = injector.inject("mod2_cmd.func2", {"depth": 2})

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
            watch_id_1 = injector1.inject("test_isolation_mod.func", {"depth": 2})
            watch_id_2 = injector2.inject("test_isolation_mod.func", {"depth": 2})

            response1 = injector1.reset()
            assert response1["count"] == 1
            assert len(injector1.instrumented) == 0

            assert len(injector2.instrumented) == 1
            response2 = injector2.list_enhanced()
            assert response2["total"] == 1

        finally:
            del sys.modules["test_isolation_mod"]
