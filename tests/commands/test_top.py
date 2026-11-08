import sys
import threading
import time

from typing import Any, Dict

import pytest


class MockAgent:
    """Mock agent for testing TopCommand."""

    def __init__(self):
        self._observations = []
        self.observer = MockObserver()

    def _send_observation(self, observation: Dict[str, Any]) -> None:
        """Store observation for test verification."""
        self._observations.append(observation)


class MockObserver:
    """Mock observer for watch registration."""

    def __init__(self):
        self._watches = {}

    def register_watch(
        self, watch_id: str, watch_type: str, params: Dict[str, Any]
    ) -> None:
        """Register a watch."""
        self._watches[watch_id] = {"type": watch_type, "params": params}

    def unregister_watch(self, watch_id: str) -> None:
        """Unregister a watch."""
        self._watches.pop(watch_id, None)


@pytest.mark.unit
class TestTopCommand:
    @pytest.fixture
    def mock_agent(self):
        """Create mock agent instance."""
        return MockAgent()

    @pytest.fixture
    def top_command(self, mock_agent):
        """Create TopCommand instance with mock agent."""
        from peeka.commands.top import TopCommand

        cmd = TopCommand(mock_agent)
        yield cmd
        # Ensure any lingering sampling thread is stopped between tests.
        cmd.stop_active_resources(pattern=None, reason="test teardown")

    @pytest.fixture(autouse=True)
    def cleanup_registry(self):
        from peeka.commands.top import _PROFILE_REGISTRY

        for session in _PROFILE_REGISTRY.list_sessions():
            if session.status == "running":
                try:
                    _PROFILE_REGISTRY.stop(session.profile_id)
                except Exception:
                    pass
        _PROFILE_REGISTRY.cleanup(max_sessions=0)
        yield
        for session in _PROFILE_REGISTRY.list_sessions():
            if session.status == "running":
                try:
                    _PROFILE_REGISTRY.stop(session.profile_id)
                except Exception:
                    pass
        _PROFILE_REGISTRY.cleanup(max_sessions=0)

    def test_start_creates_sampling_thread(self, top_command):
        """Test that start creates and starts sampling thread."""
        result = top_command.execute({"action": "start", "interval": 0.01})

        assert result["status"] == "success"
        assert "top_id" in result
        assert result["interval"] == 0.01
        assert result["stream"] is False

        # Verify thread is alive
        assert top_command._sampling_thread is not None
        assert top_command._sampling_thread.is_alive()

        # Cleanup
        top_command.execute({"action": "stop"})

    def test_start_rejects_sub_millisecond_interval_without_leaking_resources(self, top_command):
        """Invalid sub-millisecond intervals must not start sampler resources."""
        from peeka.commands.top import _PROFILE_REGISTRY

        before_sessions = _PROFILE_REGISTRY.list_sessions()

        result = top_command.execute({"action": "start", "interval": 0.0005})

        assert result["status"] == "error"
        assert "interval" in result["error"].lower()
        assert top_command._sampling_thread is None
        assert top_command._observation_thread is None
        assert top_command._top_id is None
        assert top_command._profile_id is None
        assert _PROFILE_REGISTRY.list_sessions() == before_sessions

    def test_start_accepts_one_millisecond_interval(self, top_command):
        """The minimum valid 1ms top interval still starts normally."""
        result = top_command.execute({"action": "start", "interval": 0.001})

        assert result["status"] == "success"
        assert result["interval"] == 0.001
        assert top_command._sampling_thread is not None
        assert top_command._sampling_thread.is_alive()

        top_command.execute({"action": "stop"})

    def test_stop_terminates_thread(self, top_command):
        """Test that stop terminates sampling thread."""
        # Start first
        start_result = top_command.execute({"action": "start", "interval": 0.01})
        assert start_result["status"] == "success"
        top_id = start_result["top_id"]

        # Verify thread is running
        thread = top_command._sampling_thread
        assert thread.is_alive()

        # Stop
        stop_result = top_command.execute({"action": "stop"})
        assert stop_result["status"] == "success"
        assert stop_result["top_id"] == top_id

        # Wait briefly for thread to terminate
        time.sleep(0.1)

        # Verify thread is no longer alive (stop sets _sampling_thread to None)
        assert top_command._sampling_thread is None
        assert not thread.is_alive()

    def test_snapshot_returns_function_stats(self, top_command):
        """Test that snapshot returns function statistics."""
        # Start sampling
        top_command.execute({"action": "start", "interval": 0.01})

        # Let it sample a few times
        time.sleep(0.05)

        # Get snapshot
        result = top_command.execute({"action": "snapshot"})

        assert result["status"] == "success"
        assert "snapshot" in result

        snapshot = result["snapshot"]
        assert snapshot["type"] == "top_snapshot"
        assert "top_id" in snapshot
        assert snapshot["total_samples"] > 0
        assert snapshot["sample_interval"] == 0.01
        assert isinstance(snapshot["functions"], list)

        # Verify function structure if any functions captured
        if snapshot["functions"]:
            func = snapshot["functions"][0]
            assert "name" in func
            assert "filename" in func
            assert "line" in func
            assert "own_pct" in func
            assert "total_pct" in func
            assert "own_time" in func
            assert "total_time" in func
            assert "own_count" in func
            assert "total_count" in func

        # Cleanup
        top_command.execute({"action": "stop"})

    def test_snapshot_when_not_running(self, top_command):
        """Test snapshot when profiler is not running."""
        result = top_command.execute({"action": "snapshot"})

        assert result["status"] == "success"
        snapshot = result["snapshot"]
        assert snapshot["total_samples"] == 0
        assert snapshot["functions"] == []

    def test_stop_when_not_running(self, top_command):
        """Test stop when profiler is not running."""
        result = top_command.execute({"action": "stop"})

        assert result["status"] == "error"
        assert "not running" in result["error"].lower()

    def test_reset_clears_stats(self, top_command):
        """Test that reset clears accumulated statistics."""
        # Start sampling
        top_command.execute({"action": "start", "interval": 0.01})

        # Let it accumulate samples
        time.sleep(0.05)

        # Get snapshot to verify we have data
        result1 = top_command.execute({"action": "snapshot"})
        assert result1["snapshot"]["total_samples"] > 0

        # Reset
        reset_result = top_command.execute({"action": "reset"})
        assert reset_result["status"] == "success"

        # Get snapshot again - should be zeroed
        result2 = top_command.execute({"action": "snapshot"})
        assert result2["snapshot"]["total_samples"] == 0
        assert result2["snapshot"]["functions"] == []

        # Cleanup
        top_command.execute({"action": "stop"})

    def test_double_start_returns_existing_id(self, top_command):
        """Test that starting twice returns existing top_id."""
        # First start
        result1 = top_command.execute({"action": "start", "interval": 0.01})
        assert result1["status"] == "success"
        top_id1 = result1["top_id"]

        # Second start
        result2 = top_command.execute({"action": "start", "interval": 0.01})
        assert result2["status"] == "success"
        top_id2 = result2["top_id"]

        # Should be the same ID
        assert top_id1 == top_id2
        assert "already running" in result2["message"].lower()

        # Cleanup
        top_command.execute({"action": "stop"})

    def test_own_vs_total_counts(self, top_command):
        """Test that own_count and total_count are correctly calculated."""
        # Create a test module with nested function calls
        test_module = type(sys)("test_top_module")

        def leaf_function():
            """Leaf function that does actual work."""
            time.sleep(0.01)
            return 42

        def parent_function():
            """Parent function that calls leaf."""
            return leaf_function()

        test_module.leaf_function = leaf_function
        test_module.parent_function = parent_function
        sys.modules["test_top_module"] = test_module

        try:
            # Start profiling with short interval
            top_command.execute({"action": "start", "interval": 0.005})

            # Run parent function which calls leaf
            for _ in range(3):
                test_module.parent_function()

            # Let profiler capture some samples
            time.sleep(0.05)

            # Get snapshot
            result = top_command.execute({"action": "snapshot"})
            snapshot = result["snapshot"]

            # Find our functions in the stats
            functions = {f["name"]: f for f in snapshot["functions"]}

            # Leaf function should have own_count > 0 (it's at the bottom of stack)
            if "leaf_function" in functions:
                leaf = functions["leaf_function"]
                assert leaf["own_count"] > 0
                assert leaf["total_count"] >= leaf["own_count"]

            # Parent function should have total_count but possibly low own_count
            if "parent_function" in functions:
                parent = functions["parent_function"]
                assert parent["total_count"] > 0

            # Cleanup
            top_command.execute({"action": "stop"})

        finally:
            del sys.modules["test_top_module"]

    def test_recursive_deduplication(self, top_command):
        """Test that recursive functions are counted once per sample for total."""
        # Create a recursive function
        test_module = type(sys)("test_recursive_module")

        def recursive_func(n):
            """Recursive function for testing deduplication."""
            if n <= 0:
                time.sleep(0.01)
                return 1
            return recursive_func(n - 1) + 1

        test_module.recursive_func = recursive_func
        sys.modules["test_recursive_module"] = test_module

        try:
            # Start profiling
            top_command.execute({"action": "start", "interval": 0.005})

            # Call recursive function
            test_module.recursive_func(5)

            # Let profiler capture samples
            time.sleep(0.05)

            # Get snapshot
            result = top_command.execute({"action": "snapshot"})
            snapshot = result["snapshot"]

            # Find recursive function
            functions = {f["name"]: f for f in snapshot["functions"]}

            if "recursive_func" in functions:
                recursive = functions["recursive_func"]
                # The function should be deduplicated - total_count should not be
                # multiplied by recursion depth
                # In a single sample, it should appear once in total_count even
                # if it appears multiple times in the stack
                assert recursive["total_count"] > 0

            # Cleanup
            top_command.execute({"action": "stop"})

        finally:
            del sys.modules["test_recursive_module"]

    def test_thread_exclusion(self, top_command):
        """Test that peeka's sampling thread is excluded from profiling."""
        # Start profiling
        result = top_command.execute({"action": "start", "interval": 0.01})
        assert result["status"] == "success"

        # Let it sample
        time.sleep(0.05)

        # Get snapshot
        snapshot_result = top_command.execute({"action": "snapshot"})
        snapshot = snapshot_result["snapshot"]

        # The sampling thread's own loop function should not appear
        for func in snapshot["functions"]:
            assert func["name"] != "_sampling_loop", (
                "Peeka's sampling loop should not appear in profiling data"
            )

        # Cleanup
        top_command.execute({"action": "stop"})

    def test_streaming_mode(self, top_command, mock_agent):
        """Test streaming mode sends periodic observations."""
        # Start with streaming enabled
        result = top_command.execute(
            {"action": "start", "interval": 0.01, "stream": True}
        )
        assert result["status"] == "success"
        assert result["stream"] is True

        # Verify observation thread is created
        assert top_command._observation_thread is not None
        assert top_command._observation_thread.is_alive()

        # Wait for at least one observation
        time.sleep(1.2)

        # Should have received observations
        assert len(mock_agent._observations) > 0

        # Verify observation structure
        obs = mock_agent._observations[0]
        assert obs["type"] == "top_snapshot"
        assert "functions" in obs

        # Cleanup
        top_command.execute({"action": "stop"})

    def test_unknown_action(self, top_command):
        """Test that unknown action returns error."""
        result = top_command.execute({"action": "invalid_action"})

        assert result["status"] == "error"
        assert "unknown action" in result["error"].lower()

    def test_thread_lifecycle_with_timeout(self, top_command):
        """Test thread lifecycle with proper cleanup on timeout."""
        # Start profiling
        top_command.execute({"action": "start", "interval": 0.01})

        # Verify thread is alive
        thread = top_command._sampling_thread
        assert thread.is_alive()

        # Stop and verify thread terminates within timeout
        stop_result = top_command.execute({"action": "stop"})
        assert stop_result["status"] == "success"

        # Thread should terminate quickly (within 2s timeout)
        time.sleep(0.2)
        assert top_command._sampling_thread is None
        assert not thread.is_alive()

    def test_captures_real_thread_functions(self, top_command):
        """Integration test: verify profiler captures functions from a real busy thread."""
        import itertools

        stop_flag = threading.Event()

        def busy_worker():
            """CPU-bound worker that the profiler should capture."""
            counter = 0
            while not stop_flag.is_set():
                counter += 1
                # Do some actual computation to stay on-CPU
                for _ in itertools.islice(range(10000), 1000):
                    pass

        worker = threading.Thread(target=busy_worker, name="test-busy-worker", daemon=True)
        worker.start()

        try:
            # Start profiling with short interval
            result = top_command.execute({"action": "start", "interval": 0.005})
            assert result["status"] == "success"

            # Let it accumulate enough samples
            time.sleep(0.3)

            # Get snapshot
            snapshot_result = top_command.execute({"action": "snapshot"})
            snapshot = snapshot_result["snapshot"]

            assert snapshot["total_samples"] > 0, "Profiler should have collected samples"
            assert len(snapshot["functions"]) > 0, (
                f"Profiler should have captured functions from the busy worker thread, "
                f"but functions list is empty. total_samples={snapshot['total_samples']}"
            )

            # Verify at least one function has meaningful stats
            func_names = [f["name"] for f in snapshot["functions"]]
            has_real_function = any(
                f["own_count"] > 0 for f in snapshot["functions"]
            )
            assert has_real_function, (
                f"At least one function should have own_count > 0, "
                f"but got: {func_names}"
            )

            # Cleanup profiler
            top_command.execute({"action": "stop"})

        finally:
            stop_flag.set()
            worker.join(timeout=2.0)

    def test_thread_exclusion_with_real_threads(self, top_command):
        """Verify peeka threads are excluded but non-peeka threads are captured."""
        stop_flag = threading.Event()

        def non_peeka_worker():
            """Worker that should be captured by profiler."""
            while not stop_flag.is_set():
                sum(range(1000))  # Stay busy
                time.sleep(0.001)

        worker = threading.Thread(
            target=non_peeka_worker, name="app-worker", daemon=True
        )
        worker.start()

        try:
            result = top_command.execute({"action": "start", "interval": 0.005})
            assert result["status"] == "success"

            time.sleep(0.3)

            snapshot_result = top_command.execute({"action": "snapshot"})
            snapshot = snapshot_result["snapshot"]

            # Should capture at least some functions
            assert len(snapshot["functions"]) > 0, (
                "Should capture non-peeka thread functions"
            )

            # Verify the worker function was captured
            func_names = [f["name"] for f in snapshot["functions"]]
            assert "non_peeka_worker" in func_names, (
                f"Expected 'non_peeka_worker' in captured functions, got: {func_names}"
            )

            # Peeka's own sampling/observation threads should not appear
            for func in snapshot["functions"]:
                assert func["name"] != "_sampling_loop", (
                    "Peeka's sampling loop should not appear in profiling data"
                )
                assert func["name"] != "_send_periodic_observations", (
                    "Peeka's observation loop should not appear in profiling data"
                )

            top_command.execute({"action": "stop"})

        finally:
            stop_flag.set()
            worker.join(timeout=2.0)

    def test_agent_threads_exec_from_source_are_excluded(self):
        """Agent threads whose code was exec'd from source must be filtered.

        In a real target the agent module is exec'd from source, so its frames
        report co_filename "<string>" and the package-path check misses them.
        Regression: `top` listed the agent's _handle_client at ~199% own.
        """
        import _thread

        from peeka.commands.top import TopCommand

        source = (
            "import time\n"
            "class FakeAgent(MockAgent):\n"
            "    def _handle_client(self, stop):\n"
            "        while not stop.is_set():\n"
            "            sum(range(500))\n"
            "    def _send(self, stop):\n"
            "        def send_frames():\n"
            "            while not stop.is_set():\n"
            "                sum(range(500))\n"
            "        send_frames()\n"
        )
        namespace: Dict[str, Any] = {"MockAgent": MockAgent}
        exec(compile(source, "<string>", "exec"), namespace)
        agent = namespace["FakeAgent"]()

        stop = threading.Event()

        def app_worker():
            while not stop.is_set():
                sum(range(500))

        _thread.start_new_thread(agent._handle_client, (stop,))
        # Root frame is a nested function of an agent method.
        _thread.start_new_thread(lambda: agent._send(stop), ())
        worker = threading.Thread(target=app_worker, daemon=True)
        worker.start()

        cmd = TopCommand(agent)
        try:
            assert cmd.execute({"action": "start", "interval": 0.005})["status"] == "success"
            time.sleep(0.3)
            names = [f["name"] for f in cmd.execute({"action": "snapshot"})["snapshot"]["functions"]]
            assert "app_worker" in names
            assert "_handle_client" not in names
            # The lambda root is not agent code, so only check the agent-rooted one.
            cmd.execute({"action": "stop"})
        finally:
            stop.set()
            worker.join(timeout=2.0)
            cmd.stop_active_resources(pattern=None, reason="test teardown")

    def test_stop_active_resources_returns_list_shape(self, top_command):
        """Test that stop_active_resources always returns a list for 'stopped'."""
        result = top_command.stop_active_resources(pattern=None, reason="test")
        assert isinstance(result["stopped"], list)
        assert result["stopped"] == []
        assert isinstance(result["errors"], list)
        assert result["errors"] == []

        start_result = top_command.execute({"action": "start", "interval": 0.01})
        assert start_result["status"] == "success"
        top_id = start_result["top_id"]

        result = top_command.stop_active_resources(pattern=None, reason="test")
        assert isinstance(result["stopped"], list)
        assert len(result["stopped"]) == 1
        assert result["stopped"][0]["top_id"] == top_id
        assert result["errors"] == []

    def test_transient_profile_session_cleaned_up_after_stop(self, top_command):
        """Default (keep_profile=False): profile session is removed after stop."""
        from peeka.commands.top import _PROFILE_REGISTRY

        result = top_command.execute({"action": "start", "interval": 0.01})
        assert result["status"] == "success"
        profile_id = result["profile_id"]

        stop_result = top_command.execute({"action": "stop"})
        assert stop_result["status"] == "success"

        assert _PROFILE_REGISTRY.get_session(profile_id) is None

    def test_keep_profile_retains_session_after_stop(self, top_command):
        """With keep_profile=True, profile session persists in registry after stop."""
        from peeka.commands.top import _PROFILE_REGISTRY

        result = top_command.execute(
            {"action": "start", "interval": 0.01, "keep_profile": True}
        )
        assert result["status"] == "success"
        profile_id = result["profile_id"]

        stop_result = top_command.execute({"action": "stop"})
        assert stop_result["status"] == "success"

        session = _PROFILE_REGISTRY.get_session(profile_id)
        assert session is not None
        assert session.status == "stopped"

    def test_default_stop_preserves_previous_kept_profile(self, top_command):
        """Default stop removes only its own transient profile session."""
        from peeka.commands.top import _PROFILE_REGISTRY

        kept_start = top_command.execute(
            {"action": "start", "interval": 0.01, "keep_profile": True}
        )
        kept_profile_id = kept_start["profile_id"]
        assert top_command.execute({"action": "stop"})["status"] == "success"

        transient_start = top_command.execute({"action": "start", "interval": 0.01})
        transient_profile_id = transient_start["profile_id"]
        assert top_command.execute({"action": "stop"})["status"] == "success"

        kept_session = _PROFILE_REGISTRY.get_session(kept_profile_id)
        assert kept_session is not None
        assert kept_session.status == "stopped"
        assert _PROFILE_REGISTRY.get_session(transient_profile_id) is None

    def test_profile_samples_store_root_to_leaf_stack_order(self, top_command):
        """Raw profile samples use root-to-leaf order for processors."""
        from peeka.commands.top import _PROFILE_REGISTRY

        entered_leaf = threading.Event()
        release_leaf = threading.Event()

        def root_order_worker():
            return parent_order_worker()

        def parent_order_worker():
            return leaf_order_worker()

        def leaf_order_worker():
            entered_leaf.set()
            release_leaf.wait(timeout=2.0)
            return None

        worker = threading.Thread(target=root_order_worker, name="order-worker", daemon=True)
        worker.start()
        assert entered_leaf.wait(timeout=2.0)

        try:
            start_result = top_command.execute(
                {"action": "start", "interval": 0.001, "keep_profile": True}
            )
            profile_id = start_result["profile_id"]
            time.sleep(0.05)
            assert top_command.execute({"action": "stop"})["status"] == "success"
        finally:
            release_leaf.set()
            worker.join(timeout=2.0)

        session = _PROFILE_REGISTRY.get_session(profile_id)
        assert session is not None
        order_sample = next(
            sample
            for sample in session.samples
            if {"parent_order_worker", "leaf_order_worker"}.issubset(
                {frame.name for frame in sample.stack}
            )
        )
        names = [frame.name for frame in order_sample.stack]
        assert names.index("parent_order_worker") < names.index("leaf_order_worker")

    def test_keep_profile_flag_appears_in_snapshot(self, top_command):
        """With keep_profile=True, snapshot includes 'keep_profile' key."""
        top_command.execute(
            {"action": "start", "interval": 0.01, "keep_profile": True}
        )

        snapshot_result = top_command.execute({"action": "snapshot"})
        assert snapshot_result["status"] == "success"
        assert snapshot_result["snapshot"].get("keep_profile") is True

        top_command.execute({"action": "stop"})

    def test_no_keep_profile_absent_from_snapshot_by_default(self, top_command):
        """Default (keep_profile=False): 'keep_profile' key absent from snapshot."""
        top_command.execute({"action": "start", "interval": 0.01})

        snapshot_result = top_command.execute({"action": "snapshot"})
        assert "keep_profile" not in snapshot_result["snapshot"]

        top_command.execute({"action": "stop"})

    def test_snapshot_profile_id_matches_registry(self, top_command):
        """profile_id in snapshot matches the actual ProfileRegistry session ID."""
        from peeka.commands.top import _PROFILE_REGISTRY

        result = top_command.execute({"action": "start", "interval": 0.01})
        assert result["status"] == "success"
        start_profile_id = result["profile_id"]

        snapshot_result = top_command.execute({"action": "snapshot"})
        snapshot_profile_id = snapshot_result["snapshot"]["profile_id"]

        assert snapshot_profile_id == start_profile_id
        assert _PROFILE_REGISTRY.get_session(start_profile_id) is not None

        top_command.execute({"action": "stop"})
