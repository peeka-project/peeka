"""
Peeka Demo Application
Demonstrates Peeka capabilities
"""

import logging
import os
import sys
import time

# Set up loggers for logger command demo
logging.basicConfig(level=logging.WARNING, format="%(name)s [%(levelname)s] %(message)s")
logger = logging.getLogger("demo")
logger.setLevel(logging.INFO)
calc_logger = logging.getLogger("demo.calculator")
calc_logger.setLevel(logging.DEBUG)
perf_logger = logging.getLogger("demo.performance")
perf_logger.setLevel(logging.WARNING)

class Calculator:
    """Simple calculator for demonstration"""

    def __init__(self, name: str = "demo"):
        self.name = name
        self.history = []

    def add(self, a: int, b: int) -> int:
        """Add two numbers"""
        calc_logger.debug("add(%d, %d)", a, b)
        result = a + b
        self.history.append(("add", a, b, result))
        return result

    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers"""
        result = a * b
        self.history.append(("multiply", a, b, result))
        return result

    def power(self, base: int, exp: int) -> int:
        """Calculate power"""
        result = base**exp
        self.history.append(("power", base, exp, result))
        return result

    def divide(self, a: int, b: int) -> float:
        """Divide two numbers (may raise exception)"""
        if b == 0:
            calc_logger.error("Division by zero: %d / %d", a, b)
            raise ValueError("Division by zero")
        result = a / b
        self.history.append(("divide", a, b, result))
        return result

    def calculate(self, a: int, b: int) -> dict:
        """Compound calculation - good for trace demo.

        Calls multiple sub-methods with varying cost, then returns.
        Use: peeka-cli trace 'demo.Calculator.calculate' -n 2
        """
        calc_logger.info("calculate(%d, %d) started", a, b)
        sum_result = self.add(a, b)
        prod_result = self.multiply(a, b)
        if b != 0:
            div_result = self.divide(a, b)
        else:
            div_result = 0.0
        slow_val = slow_operation(sum_result)
        calc_logger.info("calculate(%d, %d) done", a, b)
        return {
            "sum": sum_result,
            "product": prod_result,
            "division": div_result,
            "slow": slow_val,
        }

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


def slow_operation(value: int) -> int:
    """Simulate slow operation for cost filtering demo"""
    import time

    perf_logger.warning("slow_operation started, value=%d", value)
    time.sleep(0.02)
    return value * 2


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
        fibonacci(8),
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
    print(f"当前进程 PID: {os.getpid()}")
    print()
    print("Try these Arthas-compatible watch commands:")
    print(f"  # Observe function entry (-b flag)")
    print(f"  peeka-cli attach {os.getpid()}")
    print(f"  peeka-cli watch 'demo.Calculator.add' -b")
    print()
    print(f"  # Observe only exceptions (-e flag)")
    print(f"  peeka-cli attach {os.getpid()}")
    print(f"  peeka-cli watch 'demo.Calculator.divide' -e")
    print()
    print(f"  # Filter by execution time (cost variable)")
    print(f"  peeka-cli attach {os.getpid()}")
    print(f"  peeka-cli watch 'demo.slow_operation' --condition 'cost > 15'")
    print()
    print(f"  # Observe entry and exit (-b -s flags)")
    print(f"  peeka-cli attach {os.getpid()}")
    print(f"  peeka-cli watch 'demo.Calculator.multiply' -b -s")
    print()
    print(f"  # Logger command - list/get/set log levels at runtime")
    print(f"  peeka-cli attach {os.getpid()}")
    print(f"  peeka-cli logger --action list")
    print(f"  peeka-cli logger --action set --logger demo.calculator --level WARNING")
    print()

    calc = Calculator("loop-calc")
    counter = 0

    try:
        while True:
            counter += 1

            result1 = calc.add(counter, counter * 2)
            result2 = calc.multiply(counter, 3)

            if counter % 5 == 0:
                result3 = calc.power(2, counter % 10)

            if counter % 7 == 0:
                try:
                    result4 = calc.divide(10, 0 if counter % 14 == 0 else 2)
                except ValueError as e:
                    pass

            if counter % 8 == 0:
                result5 = slow_operation(counter)

            if counter % 10 == 0:
                print(f"[{counter}] Operations performed: {len(calc.get_history())}")

            if counter % 3 == 0:
                calc.calculate(counter, counter + 1)

            logger.info("[iter %d] cycle complete", counter)

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
        "--mode",
        choices=["basic", "loop"],
        default="basic",
        help="Demo mode (default: basic)",
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

    if args.mode == "basic":
        demo_basic()
    elif args.mode == "loop":
        demo_loop()

    print()
    print("Demo complete!")
    print()
    print("To attach Peeka to a running process:")
    print("  $ peeka-cli attach <PID>")
    print()
    print("To watch function calls:")
    print("  $ peeka-cli watch 'demo.Calculator.add'")
    print()
    print("Arthas-compatible observation flags:")
    print("  -b, --before     Observe at function entry (AtEnter)")
    print("  -e, --exception  Observe only on exception (AtExceptionExit)")
    print("  -s, --success    Observe only on success (AtExit)")
    print("  -f, --finish     Observe on both success and exception (default)")
    print()
    print("Examples:")
    print("  $ peeka-cli watch 'demo.Calculator.add' -b")
    print("  $ peeka-cli watch 'demo.Calculator.divide' -e")
    print("  $ peeka-cli watch 'demo.slow_operation' --condition 'cost > 15'")
    print()


if __name__ == "__main__":
    main()
