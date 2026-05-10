#!/usr/bin/env python3
"""
Asyncio target process for Peeka attach testing.

This example demonstrates asyncio workloads with bounded coroutines,
producer/consumer patterns, and mixed sync/async operations.

Run:
  python examples/asyncio_attach_target.py --duration 0

Then, from another shell:
  peeka-cli attach <PID>
  peeka-cli watch 'handle_request' -n 5
  peeka-cli watch '__main__.AsyncRequestService.process' -n 5
  peeka-cli watch '__main__.async_compute' -n 5
"""

import argparse
import asyncio
import os
import signal
import sys
from pathlib import Path
from typing import Any, Dict, Optional

# Module-level stop event for SIGTERM handling
stop_event: Optional[asyncio.Event] = None


def sync_compute(x: int, y: int) -> int:
    """Synchronous computation function."""
    return x + y


async def async_compute(x: int, y: int) -> int:
    """Async computation that awaits sync_compute indirectly."""
    await asyncio.sleep(0.001)
    result = sync_compute(x, y)
    await asyncio.sleep(0.001)
    return result


# Module-level alias for async_compute
compute_alias = async_compute


async def handle_request(request_id: int) -> Dict[str, Any]:
    """Async handler with bounded sleep checkpoints."""
    await asyncio.sleep(0.002)
    result = {
        "request_id": request_id,
        "status": "success",
        "data": f"request_{request_id}",
    }
    await asyncio.sleep(0.001)
    return result


class AsyncRequestService:
    """Service class with async process method."""

    def __init__(self) -> None:
        self.processed_count = 0

    async def process(self, request_id: int) -> Dict[str, Any]:
        """Process a request asynchronously."""
        await asyncio.sleep(0.001)
        self.processed_count += 1
        result = {
            "request_id": request_id,
            "service_processed": self.processed_count,
            "message": f"processed by service",
        }
        await asyncio.sleep(0.001)
        return result


async def producer(queue: asyncio.Queue, count: int) -> None:
    """Producer coroutine that feeds items into queue."""
    for i in range(count):
        await asyncio.sleep(0.05)
        await queue.put({"item_id": i, "data": f"item_{i}"})


async def consumer(queue: asyncio.Queue, consumer_id: int) -> None:
    """Consumer coroutine that drains items from queue."""
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=1.0)
            await asyncio.sleep(0.01)
            queue.task_done()
        except asyncio.TimeoutError:
            break


async def main(
    duration: float, queue_size: int, workers: int
) -> None:
    """Main async entry point."""
    global stop_event
    stop_event = asyncio.Event()

    # Set up SIGTERM handler
    loop = asyncio.get_event_loop()
    loop.add_signal_handler(signal.SIGTERM, stop_event.set)

    # Create service and queue
    service = AsyncRequestService()
    queue: asyncio.Queue = asyncio.Queue(maxsize=queue_size)

    # Create consumer tasks
    consumer_tasks = [
        asyncio.create_task(consumer(queue, i)) for i in range(workers)
    ]

    # Create producer task
    producer_task = asyncio.create_task(producer(queue, 1000))

    request_id = 0
    start_time = asyncio.get_event_loop().time()

    try:
        while True:
            # Check if we should stop
            if duration > 0:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed >= duration:
                    break

            # Check for SIGTERM
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=1.0)
                break
            except asyncio.TimeoutError:
                pass

            # Dispatch workloads every 1 second
            await asyncio.sleep(1.0)

            # Dispatch handle_request
            await handle_request(request_id)

            # Dispatch AsyncRequestService.process
            await service.process(request_id)

            # Dispatch async_compute
            await async_compute(request_id, request_id + 1)

            # Dispatch compute_alias
            await compute_alias(request_id, request_id + 1)

            request_id += 1

    except asyncio.CancelledError:
        pass
    finally:
        # Cancel all tasks
        producer_task.cancel()
        for task in consumer_tasks:
            task.cancel()

        # Wait for cancellation with timeout
        all_tasks = [producer_task] + consumer_tasks
        try:
            await asyncio.wait_for(
                asyncio.wait(all_tasks),
                timeout=5.0,
            )
        except asyncio.TimeoutError:
            pass


def main_sync() -> None:
    """Synchronous entry point that runs asyncio.run()."""
    # Print ready marker
    print(f"ASYNCIO_TARGET_READY pid={os.getpid()}", flush=True)

    # Write ready file if env var is set
    ready_file = os.environ.get("PEEKA_TEST_READY_FILE")
    if ready_file:
        Path(ready_file).write_text(str(os.getpid()))

    # Parse arguments
    parser = argparse.ArgumentParser(
        description="Asyncio target process for Peeka attach testing"
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=0,
        help="Duration in seconds (0 = run until SIGTERM)",
    )
    parser.add_argument(
        "--queue-size", type=int, default=10, help="Queue size for producer/consumer"
    )
    parser.add_argument(
        "--workers", type=int, default=2, help="Number of consumer workers"
    )

    args = parser.parse_args()

    # Run asyncio main
    asyncio.run(main(args.duration, args.queue_size, args.workers))


if __name__ == "__main__":
    main_sync()
