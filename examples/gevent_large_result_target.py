#!/usr/bin/env python3
"""
Gevent-monkey-patched target that returns large objects from its handler.

Used for performance regression tests that reproduce the CPU spike scenario
where tracing a function returning large data causes high serialization overhead.

Run:
  python examples/gevent_large_result_target.py

Then, from another shell:
  peeka-cli attach <PID>
  peeka-cli trace 'index.handler' -n 5

Install gevent when needed:
  python -m pip install gevent
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from typing import Any, Dict

try:
    from gevent import monkey
except ImportError:
    print(
        "This example requires gevent. Install it with: python -m pip install gevent",
        file=sys.stderr,
    )
    raise SystemExit(1)

monkey.patch_all()

import gevent  # noqa: E402
import time  # noqa: E402
from gevent.pool import Pool  # noqa: E402

# Make the target path look like a common serverless entrypoint.
# Peeka can trace this function as `index.handler`.
sys.modules.setdefault("index", sys.modules[__name__])


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    request_id = int(event["request_id"])
    gevent.sleep(random.uniform(0.001, 0.005))  # faster interval, higher call rate
    # Return a large object to reproduce the CPU spike scenario
    return {
        "request_id": request_id,
        "payload": [{"key": f"item_{i}", "value": "x" * 100} for i in range(500)],
    }


def run_traffic(interval: float, duration: float) -> None:
    pool = Pool(32)
    request_id = 0
    started = time.monotonic()

    while True:
        request_id += 1
        event = {"request_id": request_id}
        pool.spawn(_handle_safely, event)

        if request_id % 50 == 0:
            print(
                f"traffic requests={request_id} greenlets={len(pool)}",
                flush=True,
            )

        if duration > 0 and time.monotonic() - started >= duration:
            break
        gevent.sleep(interval)

    pool.join(timeout=5)


def _handle_safely(event: Dict[str, Any]) -> None:
    try:
        handler(event)
    except Exception as exc:
        print(f"request error: {exc}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a gevent target returning large objects for Peeka perf testing."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.01,
        help="Seconds between spawned requests (default: 0.01)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0,
        help="Seconds to run; 0 means forever (default: 0)",
    )
    args = parser.parse_args()

    print(f"GEVENT_LARGE_RESULT_READY pid={os.getpid()}", flush=True)

    try:
        run_traffic(args.interval, args.duration)
    except KeyboardInterrupt:
        print()
        print("Stopped.")


if __name__ == "__main__":
    main()
