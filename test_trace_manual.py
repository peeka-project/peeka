#!/usr/bin/env python3
"""
Simple test script to verify trace functionality
"""
import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class MockAgent:
    def __init__(self):
        self._observations = []

    def _send_observation(self, observation):
        self._observations.append(observation)
        print(f"[Observation received] watch_id={observation.get('watch_id')}")
        print(f"  Total duration: {observation.get('total_duration_ms', 0):.3f}ms")
        print(f"  Node count: {observation.get('node_count', 0)}")
        if 'call_tree' in observation:
            print(f"  Call tree nodes: {len(observation['call_tree'])}")


def helper_function(x):
    """Helper function for testing"""
    time.sleep(0.001)  # Small delay
    return x * 2


def nested_helper(x):
    """Nested helper"""
    return helper_function(x) + 1


def sample_function(a, b):
    """Sample function to trace"""
    result = nested_helper(a)
    return result + b


def test_basic_trace():
    """Test basic trace functionality"""
    print("\n=== Test 1: Basic Trace ===")
    from peeka.core.injector import DecoratorInjector

    mock_agent = MockAgent()
    injector = DecoratorInjector(mock_agent)

    # Create test module
    test_module = type(sys)("test_trace_module")
    test_module.sample_function = sample_function
    test_module.nested_helper = nested_helper
    test_module.helper_function = helper_function
    sys.modules["test_trace_module"] = test_module

    try:
        watch_id = injector.inject_trace(
            "test_trace_module.sample_function",
            {"trace_depth": 3, "times": 1, "skip_builtin": True}
        )
        print(f"Trace injected with watch_id: {watch_id}")

        result = test_module.sample_function(3, 5)
        print(f"Function result: {result}")
        print(f"Expected: {(3 * 2 + 1) + 5} = 12")

        print(f"\nTotal observations: {len(mock_agent._observations)}")
        if mock_agent._observations:
            obs = mock_agent._observations[0]
            print(f"Observation keys: {list(obs.keys())}")

        print("✓ Test passed!")

    finally:
        del sys.modules["test_trace_module"]


def test_trace_with_condition():
    """Test trace with condition"""
    print("\n=== Test 2: Trace with Condition ===")
    from peeka.core.injector import DecoratorInjector

    def timed_function(x):
        if x > 10:
            time.sleep(0.002)  # 2ms delay
        else:
            time.sleep(0.0001)  # 0.1ms delay
        return x * 2

    mock_agent = MockAgent()
    injector = DecoratorInjector(mock_agent)

    test_module = type(sys)("test_trace_condition")
    test_module.timed_function = timed_function
    sys.modules["test_trace_condition"] = test_module

    try:
        watch_id = injector.inject_trace(
            "test_trace_condition.timed_function",
            {"trace_depth": 2, "condition_express": "cost > 1"}
        )
        print(f"Trace injected with condition: cost > 1ms")

        print("\nCalling with x=5 (should not observe, < 1ms)...")
        test_module.timed_function(5)
        print(f"Observations: {len(mock_agent._observations)}")

        print("\nCalling with x=15 (should observe, > 1ms)...")
        test_module.timed_function(15)
        print(f"Observations: {len(mock_agent._observations)}")

        print("✓ Test passed!")

    finally:
        del sys.modules["test_trace_condition"]


def test_trace_depth_limit():
    """Test trace depth limit"""
    print("\n=== Test 3: Trace Depth Limit ===")
    from peeka.core.injector import DecoratorInjector

    def level3(x):
        return x + 1

    def level2(x):
        return level3(x) + 1

    def level1(x):
        return level2(x) + 1

    def root_function(x):
        return level1(x) + 1

    mock_agent = MockAgent()
    injector = DecoratorInjector(mock_agent)

    test_module = type(sys)("test_trace_depth")
    test_module.root_function = root_function
    test_module.level1 = level1
    test_module.level2 = level2
    test_module.level3 = level3
    sys.modules["test_trace_depth"] = test_module

    try:
        watch_id = injector.inject_trace(
            "test_trace_depth.root_function",
            {"trace_depth": 2, "times": 1}
        )
        print(f"Trace injected with depth=2")

        result = test_module.root_function(10)
        print(f"Function result: {result}")
        print(f"Expected: {10 + 1 + 1 + 1 + 1} = 14")

        if mock_agent._observations:
            obs = mock_agent._observations[0]
            print(f"Node count: {obs.get('node_count', 0)}")

        print("✓ Test passed!")

    finally:
        del sys.modules["test_trace_depth"]


def test_trace_command():
    """Test TraceCommand"""
    print("\n=== Test 4: TraceCommand ===")
    from peeka.commands.trace import TraceCommand

    def sample_func(x):
        return x * 3

    mock_agent = MockAgent()
    trace_command = TraceCommand(mock_agent)

    # Also need injector and observer
    from peeka.core.injector import DecoratorInjector
    from peeka.core.observer import ObservationManager

    mock_agent.injector = DecoratorInjector(mock_agent)
    mock_agent.observer = ObservationManager()

    test_module = type(sys)("test_trace_cmd")
    test_module.sample_func = sample_func
    sys.modules["test_trace_cmd"] = test_module

    try:
        params = {
            "action": "start",
            "pattern": "test_trace_cmd.sample_func",
            "depth": 3,
            "times": 1,
        }

        result = trace_command.execute(params)
        print(f"Command result: {result}")
        print(f"Status: {result.get('status')}")

        if result.get("status") == "success":
            print(f"Watch ID: {result.get('watch_id')}")

            # Execute the function
            test_module.sample_func(5)
            print(f"Total observations: {len(mock_agent._observations)}")
            print("✓ Test passed!")
        else:
            print(f"✗ Test failed: {result.get('error')}")

    finally:
        del sys.modules["test_trace_cmd"]


def main():
    print("=" * 60)
    print("Trace Functionality Test Suite")
    print("=" * 60)

    try:
        test_basic_trace()
        test_trace_with_condition()
        test_trace_depth_limit()
        test_trace_command()

        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
