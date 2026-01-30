"""Tests for stack command - call trace capture."""

import pytest
import sys
import threading
from unittest.mock import patch
from peeka.commands.stack import StackCommand
from peeka.core.injector import DecoratorInjector
from peeka.core.observer import ObservationManager


class MockAgent:
    """Mock agent for testing commands without full PeekaAgent setup."""

    def __init__(self):
        self._observations = []
        self._lock = threading.Lock()
        self.observer = ObservationManager()
        self.injector = DecoratorInjector(self)

    def _send_observation(self, obs):
        with self._lock:
            self._observations.append(obs)
        self.observer.add_observation(obs)


@pytest.fixture
def mock_agent():
    return MockAgent()


@pytest.fixture
def stack_cmd(mock_agent):
    return StackCommand(mock_agent)


@pytest.fixture
def test_module():
    """Create synthetic test module with nested call structure."""
    module = type(sys)("test_stack_module")

    def inner_function(x):
        return x * 2

    def middle_function(x):
        return module.inner_function(x)

    def outer_function(x):
        return module.middle_function(x)

    module.inner_function = inner_function
    module.middle_function = middle_function
    module.outer_function = outer_function

    sys.modules["test_stack_module"] = module
    yield module
    del sys.modules["test_stack_module"]


class TestStackCommand:
    """Test stack command - call trace capture."""

    def test_stack_start_captures_call_trace(self, stack_cmd, test_module):
        """Stack command should capture call stack at function entry."""
        params = {"action": "start", "pattern": "test_stack_module.inner_function"}
        result = stack_cmd.execute(params)

        assert result["status"] == "success"
        assert "watch_id" in result

        # Trigger function call
        test_module.outer_function(10)

        # Should have observation with stack trace
        observations = stack_cmd.agent._observations
        assert len(observations) > 0

        obs = observations[0]
        assert "stack" in obs
        assert isinstance(obs["stack"], list)
        assert len(obs["stack"]) > 0

        # Verify stack contains caller info
        stack_frames = obs["stack"]
        assert any(
            "outer_function" in frame.get("function", "") for frame in stack_frames
        )
        assert any(
            "middle_function" in frame.get("function", "") for frame in stack_frames
        )

    def test_stack_includes_frame_details(self, stack_cmd, test_module):
        """Stack frames should include filename, lineno, function, code_context."""
        params = {"action": "start", "pattern": "test_stack_module.inner_function"}
        stack_cmd.execute(params)

        test_module.inner_function(5)

        obs = stack_cmd.agent._observations[0]
        frame = obs["stack"][0]

        # Required fields from inspect.FrameInfo
        assert "filename" in frame
        assert "lineno" in frame
        assert "function" in frame
        assert "code_context" in frame or frame["code_context"] is None

    def test_stack_with_depth_limit(self, stack_cmd, test_module):
        """--depth flag should limit stack frame count."""
        params = {
            "action": "start",
            "pattern": "test_stack_module.inner_function",
            "depth": 2,
        }
        result = stack_cmd.execute(params)
        assert result["status"] == "success"

        test_module.outer_function(10)

        obs = stack_cmd.agent._observations[0]
        assert len(obs["stack"]) <= 2

    def test_stack_default_depth_ten(self, stack_cmd, test_module):
        """Default depth should be 10 frames."""
        params = {"action": "start", "pattern": "test_stack_module.inner_function"}
        stack_cmd.execute(params)

        # Create deep call stack (15 levels)
        def make_deep_call(depth):
            if depth == 0:
                return test_module.inner_function(1)
            return make_deep_call(depth - 1)

        make_deep_call(15)

        obs = stack_cmd.agent._observations[0]
        assert len(obs["stack"]) == 10  # Should be capped at default

    def test_stack_with_condition(self, stack_cmd, test_module):
        """--condition-express should filter when to capture stack."""
        params = {
            "action": "start",
            "pattern": "test_stack_module.inner_function",
            "condition": "params[0] > 5",
        }
        stack_cmd.execute(params)

        # Call with value that doesn't match condition
        test_module.inner_function(3)
        assert len(stack_cmd.agent._observations) == 0

        # Call with value that matches condition
        test_module.inner_function(10)
        assert len(stack_cmd.agent._observations) == 1
        assert "stack" in stack_cmd.agent._observations[0]

    def test_stack_respects_times_limit(self, stack_cmd, test_module):
        """--times flag should limit number of captures."""
        params = {
            "action": "start",
            "pattern": "test_stack_module.inner_function",
            "times": 3,
        }
        stack_cmd.execute(params)

        # Call function 5 times
        for i in range(5):
            test_module.inner_function(i)

        # Should only capture first 3
        assert len(stack_cmd.agent._observations) == 3

    def test_stack_stop_action(self, stack_cmd, test_module):
        """stop action should remove instrumentation."""
        # Start watching
        params_start = {
            "action": "start",
            "pattern": "test_stack_module.inner_function",
        }
        result = stack_cmd.execute(params_start)
        watch_id = result["watch_id"]

        # Stop watching
        params_stop = {"action": "stop", "watch_id": watch_id}
        result = stack_cmd.execute(params_stop)
        assert result["status"] == "success"

        # Function call should not be captured
        initial_count = len(stack_cmd.agent._observations)
        test_module.inner_function(5)
        assert len(stack_cmd.agent._observations) == initial_count

    def test_stack_status_action(self, stack_cmd, test_module):
        """status action should return active watches."""
        params_start = {
            "action": "start",
            "pattern": "test_stack_module.inner_function",
        }
        result = stack_cmd.execute(params_start)
        watch_id = result["watch_id"]

        params_status = {"action": "status"}
        result = stack_cmd.execute(params_status)

        assert result["status"] == "success"
        assert "watches" in result
        watch_ids = [w["watch_id"] for w in result["watches"]]
        assert watch_id in watch_ids

    def test_stack_invalid_pattern(self, stack_cmd):
        """Invalid pattern should return error."""
        params = {"action": "start", "pattern": "nonexistent.module.function"}
        result = stack_cmd.execute(params)
        assert result["status"] == "error"
        assert "error" in result

    def test_stack_missing_pattern(self, stack_cmd):
        """Missing pattern parameter should return error."""
        params = {"action": "start"}
        result = stack_cmd.execute(params)
        assert result["status"] == "error"
        assert "pattern" in result["error"].lower()

    def test_stack_invalid_depth(self, stack_cmd, test_module):
        """Negative depth should return error."""
        params = {
            "action": "start",
            "pattern": "test_stack_module.inner_function",
            "depth": -1,
        }
        result = stack_cmd.execute(params)
        assert result["status"] == "error"
        assert "depth" in result["error"].lower()

    def test_stack_captures_at_enter_only(self, stack_cmd, test_module):
        """Stack should be captured at AtEnter, not AtExit."""
        params = {"action": "start", "pattern": "test_stack_module.inner_function"}
        stack_cmd.execute(params)

        test_module.inner_function(5)

        # Should have exactly one observation (AtEnter only)
        observations = [
            obs
            for obs in stack_cmd.agent._observations
            if obs.get("location") == "AtEnter"
        ]
        assert len(observations) == 1

        exit_observations = [
            obs
            for obs in stack_cmd.agent._observations
            if obs.get("location") == "AtExit"
        ]
        # Exit observations should not have stack (or be empty)
        for obs in exit_observations:
            assert "stack" not in obs or len(obs["stack"]) == 0
