#!/usr/bin/env python3
"""
Minimal compatibility test - tests core mechanisms only
No pytest required, no full integration, just core functionality
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_python_version():
    """Show Python version and attach mechanism"""
    print("\n" + "=" * 60)
    print("Python Version & Attach Mechanism")
    print("=" * 60)
    print(
        f"Python: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )

    if hasattr(sys, "remote_exec"):
        print("✓ PEP 768 available (sys.remote_exec)")
        mechanism = "PEP 768"
    else:
        import shutil

        if shutil.which("gdb"):
            print("✓ GDB fallback available")
            mechanism = "GDB fallback"
        else:
            print("✗ No attach mechanism (GDB not found)")
            mechanism = "None"

    return mechanism != "None"


def test_imports():
    """Test that core modules can be imported"""
    print("\n" + "=" * 60)
    print("Core Module Imports")
    print("=" * 60)

    try:
        from peeka.core.attach import ProcessAttacher

        print("✓ peeka.core.attach")

        from peeka.core.agent import PeekaAgent

        print("✓ peeka.core.agent")

        from peeka.core.injector import DecoratorInjector

        print("✓ peeka.core.injector")

        from peeka.core.observer import ObservationManager

        print("✓ peeka.core.observer")

        from peeka.core.safeeval.simpleeval import SimpleEval

        print("✓ peeka.core.safeeval")

        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_safeeval_security():
    """Test that simpleeval blocks dangerous code"""
    print("\n" + "=" * 60)
    print("Security: simpleeval Blocks Dangerous Code")
    print("=" * 60)

    from peeka.core.safeeval.simpleeval import SimpleEval

    evaluator = SimpleEval()

    dangerous = [
        ("__import__('os')", "import blocking"),
        ("eval('1+1')", "eval blocking"),
        ("compile('x=1', '<string>', 'exec')", "compile blocking"),
    ]

    all_blocked = True
    for expr, desc in dangerous:
        try:
            evaluator.eval(expr)
            print(f"✗ {desc} FAILED - should have blocked: {expr}")
            all_blocked = False
        except Exception:
            print(f"✓ {desc}")

    return all_blocked


def test_safeeval_allows_safe():
    """Test that simpleeval allows safe expressions"""
    print("\n" + "=" * 60)
    print("Security: simpleeval Allows Safe Code")
    print("=" * 60)

    from peeka.core.safeeval.simpleeval import SimpleEval

    evaluator = SimpleEval()
    evaluator.names = {"x": 10, "y": 20}

    safe = [
        ("x + y", 30),
        ("x > 5", True),
        ("x * 2", 20),
    ]

    all_passed = True
    for expr, expected in safe:
        try:
            result = evaluator.eval(expr)
            if result == expected:
                print(f"✓ {expr} = {result}")
            else:
                print(f"✗ {expr} = {result} (expected {expected})")
                all_passed = False
        except Exception as e:
            print(f"✗ {expr} raised exception: {e}")
            all_passed = False

    return all_passed


def main():
    print("\n╔════════════════════════════════════════════════════════════╗")
    print("║     Peeka Minimal Compatibility Test (Python 3.9-3.14)    ║")
    print("╚════════════════════════════════════════════════════════════╝")

    results = [
        ("Python Version", test_python_version()),
        ("Core Imports", test_imports()),
        ("Security Blocking", test_safeeval_security()),
        ("Safe Expressions", test_safeeval_allows_safe()),
    ]

    print("\n" + "=" * 60)
    print("Test Results")
    print("=" * 60)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{status:<10} {name}")

    total = len(results)
    passed_count = sum(1 for _, p in results if p)

    print(f"\nTotal: {passed_count}/{total} tests passed")

    if passed_count == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed_count} test(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
