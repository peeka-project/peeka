"""
Peeka Demo Application
Demonstrates Peeka capabilities
"""

import sys
import time


class Calculator:
    """Simple calculator for demonstration"""

    def __init__(self, name: str = "demo"):
        self.name = name
        self.history = []

    def add(self, a: int, b: int) -> int:
        """Add two numbers"""
        result = a + b
        self.history.append(('add', a, b, result))
        return result

    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers"""
        result = a * b
        self.history.append(('multiply', a, b, result))
        return result

    def power(self, base: int, exp: int) -> int:
        """Calculate power"""
        result = base ** exp
        self.history.append(('power', base, exp, result))
        return result

    def get_history(self) -> list:
        """Get calculation history"""
        return self.history.copy()


def factorial(n: int) -> int:
    """Calculate factorial"""
    if n <= 1:
        return 1
    return n * factorial(n - 1)


def fibonacci(n: int) -> int:
    """Calculate nth Fibonacci number"""
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


def demo_basic():
    """Basic demonstration"""
    print("=" * 60)
    print("Peeka Demo - Basic Operations")
    print("=" * 60)
    print()

    calc = Calculator("demo-calc")

    print("Performing calculations...")
    results = [
        calc.add(10, 20),
        calc.multiply(5, 7),
        calc.power(2, 8),
        factorial(5),
        fibonacci(8)
    ]

    print(f"Results: {results}")
    print(f"History: {calc.get_history()}")
    print()


def demo_loop():
    """Continuous loop demonstration"""
    print("=" * 60)
    print("Peeka Demo - Continuous Loop")
    print("=" * 60)
    print()
    print("Running continuous loop. Press Ctrl+C to stop.")
    print("You can attach Peeka to this process while it runs.")
    print(f"Process PID: {sys.argv[0] if len(sys.argv) > 1 else 'N/A'}")
    print()

    calc = Calculator("loop-calc")
    counter = 0

    try:
        while True:
            counter += 1

            # Perform various operations
            result1 = calc.add(counter, counter * 2)
            result2 = calc.multiply(counter, 3)

            if counter % 5 == 0:
                result3 = calc.power(2, counter % 10)

            if counter % 10 == 0:
                print(f"[{counter}] Operations performed: {len(calc.get_history())}")

            time.sleep(0.5)

    except KeyboardInterrupt:
        print()
        print("Stopped.")
        print(f"Total operations: {len(calc.get_history())}")


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Peeka Demo Application")
    parser.add_argument(
        '--mode',
        choices=['basic', 'loop'],
        default='basic',
        help='Demo mode (default: basic)'
    )

    args = parser.parse_args()

    print()
    print("╔════════════════════════════════════════════════════════════╗")
    print("║                  Peeka Demo Application                 ║")
    print("╚════════════════════════════════════════════════════════════╝")
    print()
    print(f"Process ID: {sys.argv[0] if hasattr(sys, 'argv') else 'N/A'}")
    print(f"Python Version: {sys.version}")
    print()

    if args.mode == 'basic':
        demo_basic()
    elif args.mode == 'loop':
        demo_loop()

    print()
    print("Demo complete!")
    print()
    print("To attach Peeka to a running process:")
    print("  $ Peeka attach <PID>")
    print()
    print("To watch function calls:")
    print("  $ Peeka watch <PID> 'demo.Calculator.add'")
    print()


if __name__ == '__main__':
    main()
