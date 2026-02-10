import sys
import time

import pytest


class MockAgent:
    def __init__(self):
        self._observations = []

    def _send_observation(self, observation):
        self._observations.append(observation)


class TestTraceCommand:
    @pytest.fixture
    def mock_agent(self):
        return MockAgent()

    @pytest.fixture
    def injector(self, mock_agent):
        from peeka.core.injector import DecoratorInjector

        return DecoratorInjector(mock_agent)

    @pytest.fixture
    def trace_command(self, mock_agent):
        from peeka.commands.trace import TraceCommand

        return TraceCommand(mock_agent)

    def test_trace_basic(self, injector, mock_agent):
        """Test basic trace functionality"""

        def helper_function(x):
            return x * 2

        def sample_function(a, b):
            result = helper_function(a)
            return result + b

        test_module = type(sys)("test_trace_module")
        test_module.sample_function = sample_function
        test_module.helper_function = helper_function
        sys.modules["test_trace_module"] = test_module

        try:
            watch_id = injector.inject_trace(
                "test_trace_module.sample_function", {"trace_depth": 3, "times": -1}
            )

            assert watch_id.startswith("trace_")
            result = test_module.sample_function(3, 5)
            assert result == 11

            # Should have one observation
            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]

            # Check observation structure
            assert obs["watch_id"] == watch_id
            assert obs["location"] == "AtExit"
            assert "call_tree" in obs
            assert "total_duration_ms" in obs
            assert "node_count" in obs

            # Check call tree structure
            call_tree = obs["call_tree"]
            assert len(call_tree) > 0
            root = call_tree[0]
            assert root["depth"] == 0
            assert "sample_function" in root["function"]
            assert "duration_ms" in root

        finally:
            del sys.modules["test_trace_module"]

    def test_trace_with_depth_limit(self, injector, mock_agent):
        """Test trace with depth limit"""

        def level3(x):
            return x + 1

        def level2(x):
            return level3(x) + 1

        def level1(x):
            return level2(x) + 1

        def root_function(x):
            return level1(x) + 1

        test_module = type(sys)("test_trace_depth")
        test_module.root_function = root_function
        test_module.level1 = level1
        test_module.level2 = level2
        test_module.level3 = level3
        sys.modules["test_trace_depth"] = test_module

        try:
            # Trace with depth 2 (should capture root + 2 levels)
            watch_id = injector.inject_trace(
                "test_trace_depth.root_function", {"trace_depth": 2, "times": 1}
            )

            result = test_module.root_function(10)
            assert result == 14

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]

            # Root node should be there
            assert len(obs["call_tree"]) > 0
            root = obs["call_tree"][0]
            assert root["depth"] == 0

        finally:
            del sys.modules["test_trace_depth"]

    def test_trace_with_condition(self, injector, mock_agent):
        """Test trace with condition expression"""

        def sample_function(x):
            time.sleep(0.001)  # Small delay to ensure cost > 0
            return x * 2

        test_module = type(sys)("test_trace_condition")
        test_module.sample_function = sample_function
        sys.modules["test_trace_condition"] = test_module

        try:
            # Only trace if cost > 0.5ms
            watch_id = injector.inject_trace(
                "test_trace_condition.sample_function",
                {"trace_depth": 2, "condition_express": "cost > 0.5"},
            )

            # This should be observed (with sleep)
            test_module.sample_function(5)
            assert len(mock_agent._observations) == 1

        finally:
            del sys.modules["test_trace_condition"]

    def test_trace_command_start(self, trace_command, mock_agent):
        """Test TraceCommand start action"""

        def sample_function(x):
            return x * 2

        test_module = type(sys)("test_trace_cmd")
        test_module.sample_function = sample_function
        sys.modules["test_trace_cmd"] = test_module

        try:
            params = {
                "action": "start",
                "pattern": "test_trace_cmd.sample_function",
                "depth": 3,
                "times": 1,
            }

            result = trace_command.execute(params)
            assert result["status"] == "success"
            assert "watch_id" in result
            assert result["pattern"] == "test_trace_cmd.sample_function"

            # Execute the function
            test_module.sample_function(10)

            # Should have observation
            assert len(mock_agent._observations) == 1

        finally:
            del sys.modules["test_trace_cmd"]

    def test_trace_command_invalid_pattern(self, trace_command):
        """Test TraceCommand with invalid pattern"""
        params = {
            "action": "start",
            "pattern": "nonexistent.module.function",
            "depth": 3,
        }

        result = trace_command.execute(params)
        assert result["status"] == "error"
        assert "Cannot find target" in result["error"]

    def test_trace_skip_builtin(self, injector, mock_agent):
        """Test trace with skip_builtin option"""

        def sample_function(items):
            # This will call len() which is a builtin
            return len(items)

        test_module = type(sys)("test_trace_builtin")
        test_module.sample_function = sample_function
        sys.modules["test_trace_builtin"] = test_module

        try:
            watch_id = injector.inject_trace(
                "test_trace_builtin.sample_function",
                {"trace_depth": 3, "skip_builtin": True},
            )

            result = test_module.sample_function([1, 2, 3])
            assert result == 3

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]

            # With skip_builtin=True, we shouldn't see len() in the call tree
            call_tree = obs["call_tree"]
            assert len(call_tree) > 0

        finally:
            del sys.modules["test_trace_builtin"]

    def test_trace_times_limit(self, injector, mock_agent):
        """Test trace with times limit"""

        def sample_function(x):
            return x + 1

        test_module = type(sys)("test_trace_times")
        test_module.sample_function = sample_function
        sys.modules["test_trace_times"] = test_module

        try:
            watch_id = injector.inject_trace(
                "test_trace_times.sample_function", {"trace_depth": 2, "times": 2}
            )

            # Call 5 times but only 2 should be observed
            for i in range(5):
                test_module.sample_function(i)

            assert len(mock_agent._observations) == 2

        finally:
            del sys.modules["test_trace_times"]


class TestTraceIntegration:
    """Integration tests for trace functionality"""

    @pytest.fixture
    def mock_agent(self):
        return MockAgent()

    @pytest.fixture
    def injector(self, mock_agent):
        from peeka.core.injector import DecoratorInjector

        return DecoratorInjector(mock_agent)

    def test_trace_nested_calls(self, injector, mock_agent):
        """Test tracing nested function calls"""

        def validate(x):
            if x < 0:
                raise ValueError("Negative value")
            return True

        def compute(x):
            validate(x)
            return x * x

        def process(x):
            result = compute(x)
            return result + 10

        test_module = type(sys)("test_trace_nested")
        test_module.process = process
        test_module.compute = compute
        test_module.validate = validate
        sys.modules["test_trace_nested"] = test_module

        try:
            watch_id = injector.inject_trace(
                "test_trace_nested.process", {"trace_depth": 5, "skip_builtin": True}
            )

            result = test_module.process(5)
            assert result == 35

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]

            # Should have call tree
            assert "call_tree" in obs
            call_tree = obs["call_tree"]
            assert len(call_tree) > 0

            # Root should be process
            root = call_tree[0]
            assert "process" in root["function"]
            assert root["depth"] == 0
            assert root["duration_ms"] > 0

        finally:
            del sys.modules["test_trace_nested"]

    def test_trace_with_exception(self, injector, mock_agent):
        """Test trace when function raises exception"""

        def failing_function(x):
            if x < 0:
                raise ValueError("Negative value not allowed")
            return x * 2

        test_module = type(sys)("test_trace_exception")
        test_module.failing_function = failing_function
        sys.modules["test_trace_exception"] = test_module

        try:
            watch_id = injector.inject_trace(
                "test_trace_exception.failing_function", {"trace_depth": 2}
            )

            # This should raise an exception
            with pytest.raises(ValueError):
                test_module.failing_function(-5)

            # Should still have observation
            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]
            assert "call_tree" in obs

        finally:
            del sys.modules["test_trace_exception"]
