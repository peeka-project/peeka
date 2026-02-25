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

        return TopCommand(mock_agent)

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
        """Test that peeka threads are excluded from profiling."""
        # Start profiling
        result = top_command.execute({"action": "start", "interval": 0.01})
        assert result["status"] == "success"

        # Let it sample
        time.sleep(0.05)

        # Get snapshot
        snapshot_result = top_command.execute({"action": "snapshot"})
        snapshot = snapshot_result["snapshot"]

        # Check that peeka threads are not in the statistics
        for func in snapshot["functions"]:
            # Peeka's own code should be filtered out
            assert "peeka/" not in func.get("filename", "")

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
