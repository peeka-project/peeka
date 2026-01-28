#!/usr/bin/env python3
"""
Simple manual test script for local verification
Tests attach and watch across Python versions without pytest
"""

import sys
import time
from pathlib import Path
from typing import Any, Dict


class MockAgent:
    """Mock PeekaAgent for testing DecoratorInjector in isolation"""

    def __init__(self):
        self._observations = []

    def _send_observation(self, observation: Dict[str, Any]) -> None:
        """Store observation data"""
        self._observations.append(observation)


def test_attach_mechanism():
    """Test which attach mechanism is available"""
    print("\n" + "=" * 60)
    print("Test 1: Attach Mechanism Detection")
    print("=" * 60)

    print(f"Python version: {sys.version_info.major}.{sys.version_info.minor}")

    if hasattr(sys, "remote_exec"):
        print("✓ Using PEP 768 (sys.remote_exec)")
        return True
    else:
        print("→ Using GDB fallback")
        import shutil

        if shutil.which("gdb"):
            print("✓ GDB found:", shutil.which("gdb"))
            return True
        else:
            print("✗ GDB not found - install with: sudo apt-get install gdb")
            return False


def test_watch_basic():
    """Test basic watch functionality"""
    print("\n" + "=" * 60)
    print("Test 2: Basic Watch Command (simplified)")
    print("=" * 60)

    sys.path.insert(0, str(Path(__file__).parent.parent))

    from peeka.core.injector import DecoratorInjector

    mock_agent = MockAgent()
    injector = DecoratorInjector(mock_agent)

    def sample_function(x, y):
        return x + y

    test_module = type(sys)("manual_test_module")
    test_module.sample_function = sample_function
    sys.modules["manual_test_module"] = test_module

    try:
        watch_id = injector.inject(
            pattern="manual_test_module.sample_function",
            watch_config={"depth": 2, "times": 3, "condition_express": None},
        )

        if not watch_id:
            print("✗ Injection failed")
            return False

        print("✓ Function injection successful")

        sample_function(1, 2)
        sample_function(3, 4)
        sample_function(5, 6)

        time.sleep(0.2)

        injector.uninject(watch_id)

        print(f"✓ Watch completed and restored")
        return True

    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        if "manual_test_module" in sys.modules:
            del sys.modules["manual_test_module"]


def test_watch_condition():
    """Test watch with condition filtering"""
    print("\n" + "=" * 60)
    print("Test 3: Watch with Condition Filtering")
    print("=" * 60)

    sys.path.insert(0, str(Path(__file__).parent.parent))

    from peeka.core.injector import DecoratorInjector

    mock_agent = MockAgent()
    injector = DecoratorInjector(mock_agent)

    def sample_function(value):
        return value * 2

    test_module = type(sys)("cond_test_module")
    test_module.sample_function = sample_function
    sys.modules["cond_test_module"] = test_module

    try:
        watch_id = injector.inject(
            pattern="cond_test_module.sample_function",
            watch_config={
                "depth": 2,
                "times": -1,
                "condition_express": "params[0] > 50",
            },
        )

        if not watch_id:
            print("✗ Injection failed")
            return False

        print(f"✓ Watch with condition started: {watch_id}")

        test_module.sample_function(10)
        test_module.sample_function(30)
        test_module.sample_function(100)
        test_module.sample_function(5)

        time.sleep(0.2)

        injector.uninject(watch_id)

        if len(mock_agent._observations) == 1:
            print(
                f"✓ Condition filter working: {len(mock_agent._observations)} observation (only value>50)"
            )
            return True
        else:
            print(f"✗ Expected 1 observation, got {len(mock_agent._observations)}")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        if "cond_test_module" in sys.modules:
            del sys.modules["cond_test_module"]


def test_security():
    """Test that dangerous conditions are neutralized by simpleeval"""
    print("\n" + "=" * 60)
    print("Test 4: Security - Dangerous Code Blocked at Evaluation")
    print("=" * 60)

    sys.path.insert(0, str(Path(__file__).parent.parent))

    from peeka.core.injector import DecoratorInjector

    mock_agent = MockAgent()
    injector = DecoratorInjector(mock_agent)

    def sample_function(x):
        return x

    test_module = type(sys)("security_test")
    test_module.sample_function = sample_function
    sys.modules["security_test"] = test_module

    try:
        watch_id = injector.inject(
            pattern="security_test.sample_function",
            watch_config={"condition_express": "__import__('os').system('echo pwned')"},
        )

        sample_function(1)
        sample_function(2)

        time.sleep(0.2)

        injector.uninject(watch_id)

        if len(mock_agent._observations) == 0:
            print(f"✓ Dangerous condition blocked: no observations sent")
            return True
        else:
            print(f"✗ Expected 0 observations, got {len(mock_agent._observations)}")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        if "security_test" in sys.modules:
            del sys.modules["security_test"]


def main():
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║        Peeka Manual Compatibility Test Suite              ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print(
        f"\nPython {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

    results = []

    results.append(("Attach Mechanism", test_attach_mechanism()))
    results.append(("Basic Watch", test_watch_basic()))
    results.append(("Condition Filter", test_watch_condition()))
    results.append(("Security Block", test_security()))

    print("\n" + "=" * 60)
    print("Test Results Summary")
    print("=" * 60)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:<10} {name}")

    total = len(results)
    passed = sum(1 for _, p in results if p)

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
