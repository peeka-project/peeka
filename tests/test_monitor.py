"""Tests for monitor command - statistics collection."""

import pytest
import sys
import time
import threading
from peeka.commands.monitor import MonitorCommand


class MockAgent:
    """Mock agent for testing commands without full PeekaAgent setup."""

    def __init__(self):
        self._observations = []
        self._lock = threading.Lock()

    def _send_observation(self, obs):
        with self._lock:
            self._observations.append(obs)


@pytest.fixture
def mock_agent():
    return MockAgent()


@pytest.fixture
def monitor_cmd(mock_agent):
    return MonitorCommand(mock_agent)


@pytest.fixture
def test_module():
    """Create synthetic test module with functions."""
    module = type(sys)("test_monitor_module")

    def fast_function(x):
        return x * 2

    def slow_function(x):
        time.sleep(0.01)
        return x * 2

    def failing_function(x):
        if x < 0:
            raise ValueError("Negative input")
        return x * 2

    module.fast_function = fast_function
    module.slow_function = slow_function
    module.failing_function = failing_function

    sys.modules["test_monitor_module"] = module
    yield module
    del sys.modules["test_monitor_module"]


class TestMonitorCommand:
    """Test monitor command - statistics collection."""

    def test_monitor_start_collects_statistics(self, monitor_cmd, test_module):
        """Monitor should collect call statistics."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 1,
        }
        result = monitor_cmd.execute(params)

        assert result["status"] == "success"
        assert "watch_id" in result

        for i in range(5):
            test_module.fast_function(i)

        time.sleep(1.5)

        observations = monitor_cmd.agent._observations
        assert len(observations) > 0

        stats = observations[-1]
        assert "total" in stats
        assert stats["total"] >= 5
        assert "success" in stats
        assert "fail" in stats

    def test_monitor_tracks_success_count(self, monitor_cmd, test_module):
        """Monitor should track successful calls."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 1,
        }
        monitor_cmd.execute(params)

        for i in range(3):
            test_module.fast_function(i)

        time.sleep(1.5)

        stats = monitor_cmd.agent._observations[-1]
        assert stats["success"] == 3
        assert stats["fail"] == 0

    def test_monitor_tracks_failures(self, monitor_cmd, test_module):
        """Monitor should track failed calls."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.failing_function",
            "cycle": 1,
        }
        monitor_cmd.execute(params)

        for i in [-2, -1, 1, 2]:
            try:
                test_module.failing_function(i)
            except ValueError:
                pass

        time.sleep(1.5)

        stats = monitor_cmd.agent._observations[-1]
        assert stats["total"] == 4
        assert stats["success"] == 2
        assert stats["fail"] == 2

    def test_monitor_timing_statistics(self, monitor_cmd, test_module):
        """Monitor should track avg, min, max response time."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.slow_function",
            "cycle": 1,
        }
        monitor_cmd.execute(params)

        for i in range(3):
            test_module.slow_function(i)

        time.sleep(1.5)

        stats = monitor_cmd.agent._observations[-1]
        assert "rt_avg" in stats
        assert "rt_min" in stats
        assert "rt_max" in stats

        assert stats["rt_avg"] >= 10

    def test_monitor_periodic_output(self, monitor_cmd, test_module):
        """Monitor should output statistics at cycle intervals."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 1,
        }
        monitor_cmd.execute(params)

        test_module.fast_function(1)

        time.sleep(2.5)

        observations = monitor_cmd.agent._observations
        cycle_outputs = [obs for obs in observations if "cycle" in obs]
        assert len(cycle_outputs) >= 2

    def test_monitor_cycle_limit(self, monitor_cmd, test_module):
        """--cycles flag should limit number of output cycles."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 1,
            "cycles": 2,
        }
        monitor_cmd.execute(params)

        for i in range(10):
            test_module.fast_function(i)
            time.sleep(0.3)

        time.sleep(3)

        observations = monitor_cmd.agent._observations
        cycle_outputs = [obs for obs in observations if "cycle" in obs]
        assert len(cycle_outputs) == 2

    def test_monitor_stop_and_reset(self, monitor_cmd, test_module):
        """stop action should stop timer and output final statistics."""
        params_start = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 5,
        }
        result = monitor_cmd.execute(params_start)
        watch_id = result["watch_id"]

        for i in range(3):
            test_module.fast_function(i)

        time.sleep(0.5)

        params_stop = {"action": "stop", "watch_id": watch_id}
        result = monitor_cmd.execute(params_stop)

        assert result["status"] == "success"
        assert "final_stats" in result
        assert result["final_stats"]["total"] == 3

    def test_monitor_thread_safety(self, monitor_cmd, test_module):
        """Monitor should be thread-safe for concurrent calls."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 2,
        }
        monitor_cmd.execute(params)

        def make_calls():
            for i in range(10):
                test_module.fast_function(i)

        threads = [threading.Thread(target=make_calls) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        time.sleep(2.5)

        stats = monitor_cmd.agent._observations[-1]
        assert stats["total"] == 50

    def test_monitor_lightweight_wrapper(self, monitor_cmd, test_module):
        """Monitor should NOT capture full params (lightweight)."""
        params = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 1,
        }
        monitor_cmd.execute(params)

        large_data = {"key": "x" * 10000}
        try:
            test_module.fast_function(large_data)
        except TypeError:
            pass

        time.sleep(1.5)

        observations = monitor_cmd.agent._observations
        for obs in observations:
            assert "params" not in obs or obs["params"] is None

    def test_monitor_no_thread_leaks(self, monitor_cmd, test_module):
        """Stopping monitor should clean up timer thread."""
        initial_thread_count = threading.active_count()

        params_start = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 1,
        }
        result = monitor_cmd.execute(params_start)
        watch_id = result["watch_id"]

        time.sleep(0.5)

        assert threading.active_count() > initial_thread_count

        params_stop = {"action": "stop", "watch_id": watch_id}
        monitor_cmd.execute(params_stop)

        time.sleep(0.5)

        assert threading.active_count() == initial_thread_count

    def test_monitor_status_action(self, monitor_cmd, test_module):
        """status action should return active monitors."""
        params_start = {
            "action": "start",
            "pattern": "test_monitor_module.fast_function",
            "cycle": 5,
        }
        result = monitor_cmd.execute(params_start)
        watch_id = result["watch_id"]

        params_status = {"action": "status"}
        result = monitor_cmd.execute(params_status)

        assert result["status"] == "success"
        assert "monitors" in result
        assert watch_id in result["monitors"]

    def test_monitor_invalid_pattern(self, monitor_cmd):
        """Invalid pattern should return error."""
        params = {
            "action": "start",
            "pattern": "nonexistent.module.function",
            "cycle": 1,
        }
        result = monitor_cmd.execute(params)

        assert result["status"] == "error"
        assert "error" in result
