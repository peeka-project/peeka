#!/usr/bin/env python3
import os
import time


class Calculator:
    def _validate(self, a: int, b: int) -> None:
        if not isinstance(a, int) or not isinstance(b, int):
            raise TypeError("Expected int operands")

    def add(self, a: int, b: int) -> int:
        self._validate(a, b)
        return a + b

    def multiply(self, a: int, b: int) -> int:
        return a * b


def main():
    pid_file = os.environ.get("PEEKA_TEST_PID_FILE", "/tmp/peeka_e2e_target.pid")
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))

    ready_file = os.environ.get("PEEKA_TEST_READY_FILE", "/tmp/peeka_e2e_target.ready")
    open(ready_file, "w").close()

    calc = Calculator()
    counter = 0

    while counter < 10000:
        calc.add(counter, counter + 1)
        calc.multiply(counter, 2)
        counter += 1
        time.sleep(0.1)


if __name__ == "__main__":
    main()
