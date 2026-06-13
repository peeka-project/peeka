"""Tests for stack command - call trace capture."""

import argparse
import json
import sys
import threading

import pytest

from peeka.cli.handlers import observe as observe_cli
from peeka.commands.stack import StackCommand
from peeka.core.injector import DecoratorInjector
from peeka.core.observer import ObservationManager


class MockAgent:
    """Mock agent for testing commands without full PeekaAgent setup."""

    def __init__(self):
        self._observations = []
        self._lock = threading.Lock()
        self.observer = ObservationManager()
        self.injector = DecoratorInjector(self)  # pyright: ignore[reportArgumentType]

    def _send_observation(self, obs):
        with self._lock:
            self._observations.append(obs)
        self.observer.add_observation(obs)


class MockStackStreamingClient:
    def __init__(self, socket_path, observations):
        self.socket_path = socket_path
        self.observations = observations
        self.commands_sent = []
        self.connected = False

    def connect(self):
        self.connected = True
        return {"status": "success"}

    def send_command(self, command):
        self.commands_sent.append(command)
        if command.get("type") == "stack" and command.get("action") == "start":
            return {"status": "success", "stack_id": "stack_cli_123"}
        return {"status": "success"}

    def stream_observations(self):
        return iter(self.observations)

    def disconnect(self):
        self.connected = False


class MockClientSessionContext:
    def __enter__(self):
        return "stack_cli_session"

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def _stack_cli_args(times):
    return argparse.Namespace(
        pattern="module.fn",
        depth=3,
        times=times,
        condition_express=None,
    )


def test_stack_times_limit_cli_emits_exact_n_observations_from_local_count(
    monkeypatch, capsys
):
    observations = [
        {"stack_id": "stack_cli_123", "count": 5, "stack": []},
        {"stack_id": "stack_cli_123", "count": 6, "stack": []},
        {"stack_id": "stack_cli_123", "count": 7, "stack": []},
    ]
    streaming_clients = []

    def build_streaming_client(socket_path):
        client = MockStackStreamingClient(socket_path, observations)
        streaming_clients.append(client)
        return client

    monkeypatch.setattr(
        observe_cli, "_check_agent_attached", lambda: ("/tmp/peeka_stack.sock", 1234)
    )
    monkeypatch.setattr(observe_cli, "StreamingAgentClient", build_streaming_client)
    monkeypatch.setattr(
        observe_cli, "ephemeral_client", lambda target_id: MockClientSessionContext()
    )

    assert observe_cli.cmd_stack(_stack_cli_args(times=2)) == 0

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    emitted_observations = [
        record for record in records if record.get("stack_id") == "stack_cli_123"
    ]

    assert len(emitted_observations) == 2
    assert [record["count"] for record in emitted_observations] == [5, 6]
    assert streaming_clients[0].commands_sent[-2:] == [
        {"type": "stack", "action": "stop", "stack_id": "stack_cli_123"},
        {"type": "reset", "action": "reset", "pattern": "module.fn"},
    ]


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
        """--condition should filter when to capture stack."""
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


class TestStackWrapperGroupLifecycle:
    """T2: stack probes must participate in shared wrapper-group lifecycle."""

    @pytest.fixture
    def target_module(self):
        mod = type(sys)("test_stack_wg_module")

        def fn(x):
            return x * 3

        mod.fn = fn
        sys.modules["test_stack_wg_module"] = mod
        yield mod, fn
        sys.modules.pop("test_stack_wg_module", None)

    def test_stack_probe_gets_wrapper_group_key_despite_stack_depth(self, target_module):
        """Stack probe injected with stack_depth must receive wrapper_group_key metadata."""
        from peeka.core.injector import DecoratorInjector

        class _Agent:
            def __init__(self):
                self._observations = []

            def _send_observation(self, obs):
                self._observations.append(obs)

        agent = _Agent()
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]

        watch_id = injector.inject(
            "test_stack_wg_module.fn",
            {"depth": 2, "before": True, "stack_depth": 5},
        )
        info = injector.instrumented.get(watch_id, {})
        assert "wrapper_group_key" in info, (
            f"stack probe must have wrapper_group_key but instrumented[{watch_id}]={info}"
        )
        assert "root_original" in info
        injector.uninject(watch_id)

    def test_stack_watch_mixed_stop_stack_first_restores_original(self, target_module):
        """Stop stack before watch: callable must stay as watch wrapper, not be lost."""
        from peeka.core.injector import DecoratorInjector

        class _Agent:
            def __init__(self):
                self._observations = []

            def _send_observation(self, obs):
                self._observations.append(obs)

        mod, original_fn = target_module

        agent = _Agent()
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]

        watch_id = injector.inject("test_stack_wg_module.fn", {"depth": 2})
        stack_id = injector.inject(
            "test_stack_wg_module.fn",
            {"depth": 2, "before": True, "stack_depth": 5},
        )

        injector.uninject(stack_id)
        assert mod.fn is not original_fn, (
            "watch wrapper must still be active after stack is stopped"
        )

        injector.uninject(watch_id)
        assert mod.fn is original_fn, (
            "original function must be restored after both probes stopped"
        )

    def test_stack_watch_mixed_stop_watch_first_restores_original(self, target_module):
        """Stop watch before stack: callable must stay as stack wrapper, not be lost."""
        from peeka.core.injector import DecoratorInjector

        class _Agent:
            def __init__(self):
                self._observations = []

            def _send_observation(self, obs):
                self._observations.append(obs)

        mod, original_fn = target_module

        agent = _Agent()
        injector = DecoratorInjector(agent)  # pyright: ignore[reportArgumentType]

        watch_id = injector.inject("test_stack_wg_module.fn", {"depth": 2})
        stack_id = injector.inject(
            "test_stack_wg_module.fn",
            {"depth": 2, "before": True, "stack_depth": 5},
        )

        injector.uninject(watch_id)
        assert mod.fn is not original_fn, (
            "stack wrapper must still be active after watch is stopped"
        )

        injector.uninject(stack_id)
        assert mod.fn is original_fn, (
            "original function must be restored after both probes stopped"
        )
