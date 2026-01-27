#!/usr/bin/env python3
"""
Simple manual test script for local verification
Tests attach and watch across Python versions without pytest
"""

import sys
import time
from pathlib import Path


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
    from peeka.core.observer import ObservationManager

    observer = ObservationManager()
    injector = DecoratorInjector(observer)

    def sample_function(x, y):
        return x + y

    test_module = type(sys)("manual_test_module")
    test_module.sample_function = sample_function
    sys.modules["manual_test_module"] = test_module

    try:
        success = injector.inject(
            pattern="manual_test_module.sample_function",
            depth=2,
            times=3,
            condition=None,
        )

        if not success:
            print("✗ Injection failed")
            return False

        print("✓ Function injection successful")

        sample_function(1, 2)
        sample_function(3, 4)
        sample_function(5, 6)

        time.sleep(0.2)

        injector.restore("manual_test_module.sample_function")

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
    from peeka.core.observer import ObservationManager

    observer = ObservationManager()
    injector = DecoratorInjector(observer)

    def sample_function(value):
        return value * 2

    test_module = type(sys)("cond_test_module")
    test_module.sample_function = sample_function
    sys.modules["cond_test_module"] = test_module

    try:
        success = injector.inject(
            pattern="cond_test_module.sample_function",
            depth=2,
            times=-1,
            condition="params[0] > 50",
        )

        if not success:
            print("✗ Injection failed")
            return False

        watch_id = injector.get_watch_id("cond_test_module.sample_function")
        print(f"✓ Watch with condition started: {watch_id}")

        sample_function(10)
        sample_function(30)
        sample_function(100)
        sample_function(5)

        time.sleep(0.2)

        stats = observer.get_watch_stats(watch_id)
        injector.restore("cond_test_module.sample_function")

        if stats and stats["count"] == 1:
            print(
                f"✓ Condition filter working: {stats['count']} observation (only value>50)"
            )
            return True
        else:
            print(f"✗ Expected 1 observation, got {stats['count'] if stats else 0}")
            return False

    except Exception as e:
        print(f"✗ Error: {e}")
        return False
    finally:
        if "cond_test_module" in sys.modules:
            del sys.modules["cond_test_module"]


def test_security():
    """Test that dangerous conditions are blocked"""
    print("\n" + "=" * 60)
    print("Test 4: Security - Block Dangerous Code")
    print("=" * 60)

    sys.path.insert(0, str(Path(__file__).parent.parent))

    from peeka.core.injector import DecoratorInjector
    from peeka.core.observer import ObservationManager

    observer = ObservationManager()
    injector = DecoratorInjector(observer)

    def sample_function(x):
        return x

    test_module = type(sys)("security_test")
    test_module.sample_function = sample_function
    sys.modules["security_test"] = test_module

    dangerous_conditions = [
        "__import__('os').system('echo pwned')",
        "eval('1+1')",
        "params.__class__",
    ]

    all_blocked = True
    try:
        for condition in dangerous_conditions:
            try:
                injector.inject(
                    pattern="security_test.sample_function", condition=condition
                )
                print(f"✗ Should block: {condition[:50]}")
                all_blocked = False
            except Exception as e:
                if "not permitted" in str(e).lower() or "name" in str(e).lower():
                    print(f"✓ Blocked: {condition[:50]}")
                else:
                    print(f"✗ Unexpected error for {condition[:50]}: {e}")
                    all_blocked = False

        return all_blocked

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
