import argparse
import functools
import json
import sys
import time
from types import ModuleType
from unittest.mock import patch

import pytest

from peeka.cli.handlers import observe as observe_cli
from peeka.core.runtime.compat import BACKEND_WRAPPER_ONLY


class MockAgent:
    def __init__(self):
        self._observations = []
        self.injector = None  # Will be set by fixtures
        self.observer = MockObserver()

    def _send_observation(self, observation):
        self._observations.append(observation)


class MockObserver:
    def __init__(self):
        self._watches = {}

    def register_watch(self, watch_id, pattern, config):
        self._watches[watch_id] = {"pattern": pattern, "config": config}

    def unregister_watch(self, watch_id):
        return self._watches.pop(watch_id, {})

    def clear_all(self):
        self._watches.clear()

    def get_watch_stats(self, watch_id):
        return {}

    def get_all_stats(self):
        return {}


class MockTraceStreamingClient:
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
        if command.get("type") == "trace" and command.get("action") == "start":
            return {"status": "success", "watch_id": "trace_cli_123"}
        return {"status": "success"}

    def stream_observations(self):
        return iter(self.observations)

    def disconnect(self):
        self.connected = False


class MockClientSessionContext:
    def __enter__(self):
        return "trace_cli_session"

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


def _trace_cli_args(times):
    return argparse.Namespace(
        pattern="module.fn",
        times=times,
        condition_express=None,
        skip_builtin=True,
        min_duration=0,
        client=None,
    )


def test_trace_times_limit_cli_emits_exact_n_observations_from_local_count(
    monkeypatch, capsys
):
    observations = [
        {"watch_id": "trace_cli_123", "count": 5, "call_tree": []},
        {"watch_id": "trace_cli_123", "count": 6, "call_tree": []},
        {"watch_id": "trace_cli_123", "count": 7, "call_tree": []},
    ]
    streaming_clients = []

    def build_streaming_client(socket_path):
        client = MockTraceStreamingClient(socket_path, observations)
        streaming_clients.append(client)
        return client

    monkeypatch.setattr(
        observe_cli, "_check_agent_attached", lambda: ("/tmp/peeka_trace.sock", 1234)
    )
    monkeypatch.setattr(observe_cli, "StreamingAgentClient", build_streaming_client)
    monkeypatch.setattr(observe_cli, "ephemeral_client", lambda target_id: MockClientSessionContext())

    assert observe_cli.cmd_trace(_trace_cli_args(times=2)) == 0

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    emitted_observations = [
        record for record in records if record.get("watch_id") == "trace_cli_123"
    ]

    assert len(emitted_observations) == 2
    assert [record["count"] for record in emitted_observations] == [5, 6]
    assert streaming_clients[0].commands_sent[-1] == {
        "type": "trace",
        "action": "stop",
        "watch_id": "trace_cli_123",
    }


def test_trace_cli_disables_agent_times_gate(monkeypatch, capsys):
    """CLI trace start must send times=-1 so agent never stops production early."""
    streaming_clients = []

    def build_streaming_client(socket_path):
        client = MockTraceStreamingClient(socket_path, [])
        streaming_clients.append(client)
        return client

    monkeypatch.setattr(
        observe_cli, "_check_agent_attached", lambda: ("/tmp/peeka_trace.sock", 1234)
    )
    monkeypatch.setattr(observe_cli, "StreamingAgentClient", build_streaming_client)
    monkeypatch.setattr(observe_cli, "ephemeral_client", lambda target_id: MockClientSessionContext())

    observe_cli.cmd_trace(_trace_cli_args(times=2))

    start_commands = [
        cmd for cmd in streaming_clients[0].commands_sent
        if cmd.get("type") == "trace" and cmd.get("action") == "start"
    ]
    assert start_commands, "expected trace start command"
    agent_times = start_commands[0].get("times")
    assert agent_times == -1, (
        f"CLI trace must send times=-1 to agent (got {agent_times!r}); "
        "agent-side times gating must not limit production for CLI trace -n"
    )


def test_trace_cli_filtered_count_ignores_unrelated_frames(monkeypatch, capsys):
    """Regression: trace -n must count only frames for the active trace stream.

    stream_counted_limit filters by watch_id, so an unrelated observation
    (different watch_id) or LOG frame must not count toward the limit.
    """
    active_id = "trace_cli_123"
    unrelated_obs = {"watch_id": "watch_other_999", "count": 1, "data": "unrelated"}
    log_frame = {"type": "log", "level": "INFO", "msg": "background log"}
    active_obs_1 = {"watch_id": active_id, "count": 5, "call_tree": []}
    active_obs_2 = {"watch_id": active_id, "count": 6, "call_tree": []}

    observations = [unrelated_obs, log_frame, active_obs_1, active_obs_2]

    streaming_clients = []

    def build_streaming_client(socket_path):
        client = MockTraceStreamingClient(socket_path, observations)
        streaming_clients.append(client)
        return client

    monkeypatch.setattr(
        observe_cli, "_check_agent_attached", lambda: ("/tmp/peeka_trace.sock", 1234)
    )
    monkeypatch.setattr(observe_cli, "StreamingAgentClient", build_streaming_client)
    monkeypatch.setattr(
        observe_cli, "ephemeral_client", lambda target_id: MockClientSessionContext()
    )

    assert observe_cli.cmd_trace(_trace_cli_args(times=2)) == 0

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    active_records = [r for r in records if r.get("watch_id") == active_id]
    assert len(active_records) == 2, (
        f"Expected 2 active trace records, got {len(active_records)}; "
        "unrelated frames must not count toward the local -n limit"
    )
    assert [r["count"] for r in active_records] == [5, 6]


class TestTraceCommand:
    @pytest.fixture
    def mock_agent(self):
        return MockAgent()

    @pytest.fixture
    def injector(self, mock_agent):
        from peeka.core.injector import DecoratorInjector

        injector = DecoratorInjector(mock_agent)
        mock_agent.injector = injector  # Wire up the injector
        return injector

    @pytest.fixture
    def trace_command(self, mock_agent, injector):
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
                "test_trace_module.sample_function", {"times": -1}
            )

            assert watch_id.startswith("trace_")
            result = test_module.sample_function(3, 5)
            assert result == 11

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]

            assert obs["watch_id"] == watch_id
            assert obs["location"] == "AtExit"
            assert "call_tree" in obs
            assert "total_duration_ms" in obs
            assert "node_count" in obs
            assert "self_time_ms" in obs
            assert "callee_count" in obs

            call_tree = obs["call_tree"]
            assert isinstance(call_tree, list)
            assert len(call_tree) >= 1
            callee = call_tree[0]
            assert "helper_function" in callee["function"]
            assert "." in callee["function"]
            assert "count" in callee and callee["count"] >= 1
            assert "total_ms" in callee

        finally:
            del sys.modules["test_trace_module"]

    def test_trace_direct_callee_semantics(self, injector, mock_agent):

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
            _ = injector.inject_trace(
                "test_trace_depth.root_function", {"times": 1}
            )

            result = test_module.root_function(10)
            assert result == 14

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]

            call_tree = obs["call_tree"]
            assert isinstance(call_tree, list)
            assert len(call_tree) == 1
            callee = call_tree[0]
            assert "level1" in callee["function"]
            assert "." in callee["function"]

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
            _ = injector.inject_trace(
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
            _ = injector.inject_trace(
                "test_trace_builtin.sample_function",
                {"skip_builtin": True},
            )

            result = test_module.sample_function([1, 2, 3])
            assert result == 3

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]

            call_tree = obs["call_tree"]
            assert len(call_tree) == 0

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
            _ = injector.inject_trace(
                "test_trace_times.sample_function", {"trace_depth": 2, "times": 2}
            )

            # Call 5 times but only 2 should be observed
            for i in range(5):
                test_module.sample_function(i)

            assert len(mock_agent._observations) == 2

        finally:
            del sys.modules["test_trace_times"]

    def test_trace_trace_same_function_independent_stop(self, injector, mock_agent):
        """Stopping one same-function trace keeps the other trace active."""

        def stacked_function(value):
            return value + 10

        test_module = ModuleType("test_trace_trace_stacking")
        setattr(test_module, "stacked_function", stacked_function)
        sys.modules["test_trace_trace_stacking"] = test_module

        try:
            trace_a = injector.inject_trace(
                "test_trace_trace_stacking.stacked_function",
                {"trace_depth": 2, "times": -1},
                force_backend=BACKEND_WRAPPER_ONLY,
            )
            trace_b = injector.inject_trace(
                "test_trace_trace_stacking.stacked_function",
                {"trace_depth": 2, "times": -1},
                force_backend=BACKEND_WRAPPER_ONLY,
            )

            assert test_module.stacked_function(1) == 11
            assert {obs["watch_id"] for obs in mock_agent._observations} == {
                trace_a,
                trace_b,
            }

            mock_agent._observations.clear()
            injector.uninject(trace_a)

            assert trace_a not in injector.instrumented
            assert trace_b in injector.instrumented
            assert test_module.stacked_function(2) == 12
            assert [obs["watch_id"] for obs in mock_agent._observations] == [trace_b]

            mock_agent._observations.clear()
            injector.uninject(trace_b)
            assert test_module.stacked_function(3) == 13
            assert mock_agent._observations == []
            assert test_module.stacked_function is stacked_function
        finally:
            injector.uninject_all()
            del sys.modules["test_trace_trace_stacking"]

    def test_trace_uninject_restores_user_decorated_callable_boundary(
        self, injector, mock_agent
    ):
        """Trace uninject restores the pre-Peeka decorated callable boundary."""

        def user_decorator(func):
            @functools.wraps(func)
            def wrapper(value):
                return func(value) + 1

            return wrapper

        @user_decorator
        def traced_function(value):
            return value * 10

        decorated_function = traced_function
        raw_function = getattr(traced_function, "__wrapped__")

        test_module = ModuleType("test_trace_user_decorator_boundary")
        setattr(test_module, "traced_function", decorated_function)
        sys.modules["test_trace_user_decorator_boundary"] = test_module

        try:
            trace_id = injector.inject_trace(
                "test_trace_user_decorator_boundary.traced_function",
                {"trace_depth": 2, "times": -1},
                force_backend=BACKEND_WRAPPER_ONLY,
            )

            assert test_module.traced_function is not decorated_function
            assert test_module.traced_function(2) == 21
            assert [obs["watch_id"] for obs in mock_agent._observations] == [trace_id]

            mock_agent._observations.clear()
            injector.uninject(trace_id)

            assert test_module.traced_function is decorated_function
            assert test_module.traced_function is not raw_function
            assert getattr(test_module.traced_function, "__wrapped__") is raw_function
            assert test_module.traced_function(3) == 31
            assert mock_agent._observations == []
        finally:
            injector.uninject_all()
            del sys.modules["test_trace_user_decorator_boundary"]

    def test_watch_then_trace_same_function_independent_stop(self, injector, mock_agent):
        """Stopping a trace layered over a watch leaves the watch active."""

        def mixed_function(value):
            return value * 2

        test_module = ModuleType("test_watch_then_trace_lifecycle")
        setattr(test_module, "mixed_function", mixed_function)
        sys.modules["test_watch_then_trace_lifecycle"] = test_module

        try:
            watch_id = injector.inject(
                "test_watch_then_trace_lifecycle.mixed_function",
                {"depth": 2, "times": -1},
            )
            trace_id = injector.inject_trace(
                "test_watch_then_trace_lifecycle.mixed_function",
                {"trace_depth": 2, "times": -1},
                force_backend=BACKEND_WRAPPER_ONLY,
            )

            assert test_module.mixed_function(4) == 8
            assert {obs["watch_id"] for obs in mock_agent._observations} == {
                watch_id,
                trace_id,
            }

            mock_agent._observations.clear()
            injector.uninject(trace_id)

            assert trace_id not in injector.instrumented
            assert watch_id in injector.instrumented
            assert test_module.mixed_function(5) == 10
            assert [obs["watch_id"] for obs in mock_agent._observations] == [watch_id]

            mock_agent._observations.clear()
            injector.uninject(watch_id)
            assert test_module.mixed_function(6) == 12
            assert mock_agent._observations == []
            assert test_module.mixed_function is mixed_function
        finally:
            injector.uninject_all()
            del sys.modules["test_watch_then_trace_lifecycle"]

    def test_trace_then_watch_same_function_independent_stop(self, injector, mock_agent):
        """Stopping a watch layered over a trace leaves the trace active."""

        def mixed_function(value):
            return value - 1

        test_module = ModuleType("test_trace_then_watch_lifecycle")
        setattr(test_module, "mixed_function", mixed_function)
        sys.modules["test_trace_then_watch_lifecycle"] = test_module

        try:
            trace_id = injector.inject_trace(
                "test_trace_then_watch_lifecycle.mixed_function",
                {"trace_depth": 2, "times": -1},
                force_backend=BACKEND_WRAPPER_ONLY,
            )
            watch_id = injector.inject(
                "test_trace_then_watch_lifecycle.mixed_function",
                {"depth": 2, "times": -1},
            )

            assert test_module.mixed_function(7) == 6
            assert {obs["watch_id"] for obs in mock_agent._observations} == {
                trace_id,
                watch_id,
            }

            mock_agent._observations.clear()
            injector.uninject(watch_id)

            assert watch_id not in injector.instrumented
            assert trace_id in injector.instrumented
            assert test_module.mixed_function(8) == 7
            assert [obs["watch_id"] for obs in mock_agent._observations] == [trace_id]

            mock_agent._observations.clear()
            injector.uninject(trace_id)
            assert test_module.mixed_function(9) == 8
            assert mock_agent._observations == []
            assert test_module.mixed_function is mixed_function
        finally:
            injector.uninject_all()
            del sys.modules["test_trace_then_watch_lifecycle"]

    def test_stop_middle_mixed_probe_keeps_remaining_probe_emitting(
        self, injector, mock_agent
    ):
        """Stopping the lower mixed probe does not orphan the active upper probe."""

        def mixed_function(value):
            return value * value

        test_module = ModuleType("test_mixed_stop_middle_lifecycle")
        setattr(test_module, "mixed_function", mixed_function)
        sys.modules["test_mixed_stop_middle_lifecycle"] = test_module

        try:
            trace_id = injector.inject_trace(
                "test_mixed_stop_middle_lifecycle.mixed_function",
                {"trace_depth": 2, "times": -1},
                force_backend=BACKEND_WRAPPER_ONLY,
            )
            watch_id = injector.inject(
                "test_mixed_stop_middle_lifecycle.mixed_function",
                {"depth": 2, "times": -1},
            )

            assert test_module.mixed_function(3) == 9
            assert {obs["watch_id"] for obs in mock_agent._observations} == {
                trace_id,
                watch_id,
            }

            mock_agent._observations.clear()
            injector.uninject(trace_id)

            assert trace_id not in injector.instrumented
            assert watch_id in injector.instrumented
            assert test_module.mixed_function(4) == 16
            assert [obs["watch_id"] for obs in mock_agent._observations] == [watch_id]

            mock_agent._observations.clear()
            injector.uninject(watch_id)
            assert test_module.mixed_function(5) == 25
            assert mock_agent._observations == []
            assert test_module.mixed_function is mixed_function
        finally:
            injector.uninject_all()
            del sys.modules["test_mixed_stop_middle_lifecycle"]

    def test_trace_updates_alias_on_inject(self, injector, mock_agent):
        """inject_trace must update module-level aliases, just as inject() does.

        Regression (V-INJECTOR-TRACE-ALIASES): inject_trace() never calls
        _find_module_aliases() or _replace_aliases(), so module-level aliases
        that cache the original function are never redirected to the trace
        wrapper.  This test asserts the correct post-inject state and MUST
        FAIL until the bug is fixed.
        """

        def handler(x):
            return x * 2

        app_module = type(sys)("test_trace_alias_inject")
        app_module.handler = handler
        wrapper_module = type(sys)("test_trace_alias_inject_wrapper")
        wrapper_module.handler = handler
        sys.modules["test_trace_alias_inject"] = app_module
        sys.modules["test_trace_alias_inject_wrapper"] = wrapper_module

        try:
            injector.inject_trace(
                "test_trace_alias_inject.handler",
                {"trace_depth": 2, "times": -1},
                force_backend=BACKEND_WRAPPER_ONLY,
            )
            trace_wrapper = app_module.handler
            assert trace_wrapper is not handler, "canonical must be the trace wrapper"
            assert wrapper_module.handler is trace_wrapper, (
                "alias must be updated to the trace wrapper by inject_trace()"
            )
        finally:
            injector.uninject_all()
            sys.modules.pop("test_trace_alias_inject", None)
            sys.modules.pop("test_trace_alias_inject_wrapper", None)

    def test_trace_restores_alias_on_stop(self, injector, mock_agent):
        """After inject_trace + uninject, aliases must be restored to original.

        Regression (V-INJECTOR-TRACE-ALIASES): because inject_trace() never
        stores alias metadata, _restore_watch_aliases() has nothing to restore
        on uninject.  The intermediate assertion (alias == trace wrapper during
        active trace) proves the bug and MUST FAIL until fixed.
        """

        def handler(x):
            return x * 2

        app_module = type(sys)("test_trace_alias_restore")
        app_module.handler = handler
        wrapper_module = type(sys)("test_trace_alias_restore_wrapper")
        wrapper_module.handler = handler
        sys.modules["test_trace_alias_restore"] = app_module
        sys.modules["test_trace_alias_restore_wrapper"] = wrapper_module

        try:
            assert wrapper_module.handler is handler, "pre-inject: alias is original"

            trace_id = injector.inject_trace(
                "test_trace_alias_restore.handler",
                {"trace_depth": 2, "times": -1},
                force_backend=BACKEND_WRAPPER_ONLY,
            )
            trace_wrapper = app_module.handler
            assert trace_wrapper is not handler, "canonical replaced by trace wrapper"

            assert wrapper_module.handler is trace_wrapper, (
                "during active trace alias must point to the trace wrapper"
            )

            injector.uninject(trace_id)

            assert app_module.handler is handler, "canonical restored after uninject"
            assert wrapper_module.handler is handler, "alias restored after uninject"
        finally:
            injector.uninject_all()
            sys.modules.pop("test_trace_alias_restore", None)
            sys.modules.pop("test_trace_alias_restore_wrapper", None)

    def test_alias_points_to_live_wrapper_after_stop(self, injector, mock_agent):
        """After watch+trace stacking, stopping trace must leave alias on live watch wrapper.

        inject(watch) correctly updates the alias to the watch wrapper.
        When inject_trace() is layered on top, the alias should advance to the
        trace wrapper.  After uninject(trace) the alias should revert to the
        still-live watch wrapper.

        Regression: inject_trace() never updates the alias, so the alias stays
        on the watch wrapper throughout.  The assertion that alias == trace
        wrapper during active trace MUST FAIL.
        """

        def handler(x):
            return x * 2

        app_module = type(sys)("test_trace_alias_live")
        app_module.handler = handler
        wrapper_module = type(sys)("test_trace_alias_live_wrapper")
        wrapper_module.handler = handler
        sys.modules["test_trace_alias_live"] = app_module
        sys.modules["test_trace_alias_live_wrapper"] = wrapper_module

        try:
            watch_id = injector.inject(
                "test_trace_alias_live.handler", {"depth": 2, "times": -1}
            )
            watch_wrapper = app_module.handler
            assert wrapper_module.handler is watch_wrapper, (
                "inject() must have updated the alias to the watch wrapper"
            )

            trace_id = injector.inject_trace(
                "test_trace_alias_live.handler",
                {"trace_depth": 2, "times": -1},
                force_backend=BACKEND_WRAPPER_ONLY,
            )
            trace_wrapper = app_module.handler
            assert trace_wrapper is not watch_wrapper, "trace wrapped the watch wrapper"

            assert wrapper_module.handler is trace_wrapper, (
                "alias must advance to the outermost trace wrapper"
            )

            injector.uninject(trace_id)

            assert app_module.handler is watch_wrapper
            assert wrapper_module.handler is watch_wrapper, (
                "alias must revert to the live watch wrapper after trace stop"
            )
        finally:
            injector.uninject_all()
            sys.modules.pop("test_trace_alias_live", None)
            sys.modules.pop("test_trace_alias_live_wrapper", None)


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
            _ = injector.inject_trace(
                "test_trace_nested.process", {"skip_builtin": True}
            )

            result = test_module.process(5)
            assert result == 35

            assert len(mock_agent._observations) == 1
            obs = mock_agent._observations[0]

            assert "call_tree" in obs
            call_tree = obs["call_tree"]
            assert len(call_tree) >= 1

            func_names = [c["function"] for c in call_tree]
            assert any("compute" in f for f in func_names)
            assert not any("validate" in f for f in func_names)
            assert not any("process" in f for f in func_names)

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
            _ = injector.inject_trace(
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


@pytest.mark.skipif(
    sys.version_info < (3, 12),
    reason="sys.monitoring requires Python 3.12+",
)
class TestMonitoringCallbackLazyFormatting:

    def test_format_not_called_when_depth_exceeded(self):
        import peeka.core.instrumentation.trace_backends as _mod
        from peeka.core.instrumentation.trace_backends import (
            InjectorTraceBackendsMixin,
            _format_trace_function,
        )

        called_for = []

        def _recording_format(code, frame=None):
            called_for.append(code.co_name)
            return _format_trace_function(code, frame)

        class _B(InjectorTraceBackendsMixin):
            pass

        backend = _B()

        def grandcallee():
            return 42

        def callee():
            return grandcallee()

        def target():
            return callee()

        with patch.object(_mod, "_format_trace_function", side_effect=_recording_format):
            backend._trace_with_monitoring(target, (), {}, skip_builtin=False, min_duration=0.0)

        assert "target" in called_for
        assert "callee" in called_for
        assert "grandcallee" not in called_for

    def test_format_not_called_for_stdlib_with_skip_builtin(self):
        import peeka.core.instrumentation.trace_backends as _mod
        from peeka.core.instrumentation.trace_backends import (
            InjectorTraceBackendsMixin,
            _format_trace_function,
        )

        called_for = []

        def _recording_format(code, frame=None):
            called_for.append(code.co_filename)
            return _format_trace_function(code, frame)

        class _B(InjectorTraceBackendsMixin):
            pass

        backend = _B()

        def target():
            return json.dumps({"x": 1})

        with patch.object(_mod, "_format_trace_function", side_effect=_recording_format):
            backend._trace_with_monitoring(target, (), {}, skip_builtin=True, min_duration=0.0)

        assert any("test_trace" in f for f in called_for)
        stdlib_calls = [f for f in called_for if "json" in f.lower() or f.startswith("<")]
        assert stdlib_calls == []
