#!/usr/bin/env python3
"""
Eventlet-monkey-patched target process for Peeka attach testing.

This example intentionally patches socket/threading/time before Peeka attaches.
It is useful for reproducing the class of failures where an injected agent
accidentally depends on target-process Python threading/socket primitives.

Run:
  python examples/eventlet_attach_target.py

Then, from another shell:
  peeka-cli attach <PID>
  peeka-cli watch 'index.handler' -n 5
  peeka-cli watch '__main__.RequestService.handle_request' -n 5
  peeka-cli patch-status --pid <PID>

Install eventlet when needed:
  python -m pip install eventlet
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from dataclasses import dataclass
from typing import Any, Dict

try:
    import eventlet
except ImportError:
    print(
        "This example requires eventlet. Install it with: python -m pip install eventlet",
        file=sys.stderr,
    )
    raise SystemExit(1)

eventlet.monkey_patch()

import time  # noqa: E402

# Make the target path look like a common serverless entrypoint.
# Peeka can watch this function as `index.handler`.
sys.modules.setdefault("index", sys.modules[__name__])


@dataclass
class RequestStats:
    total: int = 0
    slow: int = 0
    errors: int = 0


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """Serverless-style handler called by eventlet greenlets."""
    request_id = int(event["request_id"])
    user_id = int(event["user_id"])

    # Cooperative eventlet sleep keeps the hub active while the process runs.
    eventlet.sleep(random.uniform(0.005, 0.025))

    slow_path = request_id % 9 == 0
    if slow_path:
        eventlet.sleep(random.uniform(0.12, 0.24))

    if request_id % 37 == 0:
        raise RuntimeError(f"simulated intermittent failure request_id={request_id}")

    return {
        "request_id": request_id,
        "user_id": user_id,
        "slow_path": slow_path,
        "message": f"hello user {user_id}",
    }


class RequestService:
    """Small eventlet service that repeatedly calls the watched handler."""

    def __init__(self) -> None:
        self.stats = RequestStats()

    def handle_request(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Wrap `handler` so Peeka can watch either function."""
        self.stats.total += 1
        try:
            result = handler(event)
        except Exception:
            self.stats.errors += 1
            raise

        if result.get("slow_path"):
            self.stats.slow += 1
        return result


def run_traffic(interval: float, duration: float) -> None:
    service = RequestService()
    pool = eventlet.GreenPool(32)
    request_id = 0
    started = time.monotonic()

    while True:
        request_id += 1
        event = {
            "request_id": request_id,
            "user_id": random.randint(1000, 9999),
            "path": "/api/profile",
        }
        pool.spawn(_handle_safely, service, event)

        if request_id % 25 == 0:
            print(
                "traffic "
                f"requests={service.stats.total} "
                f"slow={service.stats.slow} "
                f"errors={service.stats.errors} "
                f"greenlets={len(pool)}",
                flush=True,
            )

        if duration > 0 and time.monotonic() - started >= duration:
            break
        eventlet.sleep(interval)

    pool.waitall(timeout=5)


def _handle_safely(service: RequestService, event: Dict[str, Any]) -> None:
    try:
        service.handle_request(event)
    except RuntimeError as exc:
        print(f"request error: {exc}", flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an eventlet-monkey-patched process for Peeka attach testing."
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.05,
        help="Seconds between spawned requests (default: 0.05)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0,
        help="Seconds to run; 0 means forever (default: 0)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("Peeka eventlet attach target")
    print("=" * 70)
    print(f"PID: {os.getpid()}")
    print(f"socket patched: {eventlet.patcher.is_monkey_patched('socket')}")
    print(f"threading patched: {eventlet.patcher.is_monkey_patched('threading')}")
    print()
    print("Try:")
    print(f"  peeka-cli attach {os.getpid()}")
    print("  peeka-cli watch 'index.handler' -n 5")
    print("  peeka-cli watch '__main__.RequestService.handle_request' -n 5")
    print(f"  peeka-cli patch-status --pid {os.getpid()}")
    print()
    print("This process keeps the eventlet hub active. Press Ctrl+C to stop.")
    print()
    print(f"EVENTLET_TARGET_READY pid={os.getpid()}")
    print()

    try:
        run_traffic(args.interval, args.duration)
    except KeyboardInterrupt:
        print()
        print("Stopped.")


if __name__ == "__main__":
    main()
