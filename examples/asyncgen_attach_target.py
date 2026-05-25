#!/usr/bin/env python3
"""
Async generator target process for Peeka attach testing.

This example demonstrates async generator workloads with Execution Profile
emission when watching async generators via peeka. The async generator yields
items with sleep between yields, allowing observation of yield points and
performance metrics.

Run:
  python examples/asyncgen_attach_target.py

Then, from another shell:
  peeka-cli attach <PID>
  peeka-cli watch 'asyncgen_attach_target.stream_items' -n 1

The watch command will capture Execution Profile emissions on terminal states
(normal completion, aclose, or exception), showing:
  - mode: "async_generator"
  - yields: number of items yielded
  - wall_cost: total wall-clock time
  - cpu_cost: CPU time
  - context_switches: number of context switches
  - termination: "exhausted", "closed", or "errored"
"""

import asyncio
import os
from typing import AsyncGenerator


async def stream_items() -> AsyncGenerator[int, None]:
    """
    Async generator that yields items with sleep between yields.

    Yields:
        Sequential integers from 0 to 99.
    """
    for i in range(100):
        yield i
        await asyncio.sleep(0.5)


async def consumer() -> None:
    """Consume items from the async generator."""
    count = 0
    async for item in stream_items():
        count += 1
        if count % 5 == 0:
            print(f"Consumed {count} items", flush=True)
    print(f"Finished consuming {count} items", flush=True)


async def main() -> None:
    """Main async entry point."""
    print(f"PID: {os.getpid()}", flush=True)
    print(f"ASYNCGEN_TARGET_READY pid={os.getpid()}", flush=True)
    print("Starting async generator consumer...", flush=True)

    try:
        await consumer()
    except KeyboardInterrupt:
        print("Interrupted.", flush=True)


def main_sync() -> None:
    """Synchronous entry point that runs asyncio.run()."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
