#!/usr/bin/env python3
"""
Cache System - Memory Leak Scenario

This example demonstrates a memory leak caused by unbounded cache growth
without eviction policy (no LRU, no TTL, no max size limit).

Bug location: CacheManager.add()
- Cache dict grows without bounds
- No eviction mechanism (LRU/TTL/max_size)
- Memory grows steadily at ~100KB/sec with default settings

Peeka workflow:
  peeka-cli attach <PID>
  peeka-cli memory --action start
  peeka-cli memory --action top -n 10
  peeka-cli memory --action snapshot
  (wait 10-30 seconds)
  peeka-cli memory --action snapshot
  peeka-cli memory --action diff

Note: Do NOT import tracemalloc - Peeka injects it at runtime.
"""

import argparse
import os
import random
import time


class CacheManager:
    """Cache manager with unbounded growth bug."""

    def __init__(self):
        """Initialize the cache manager."""
        self.cache = {}
        self.hits = 0
        self.misses = 0

    def add(self, key, value):
        """
        Add entry to cache with BUG - no eviction.

        BUG: Cache grows unbounded without any eviction policy.
        Should implement LRU, TTL, or max_size limit, but doesn't.

        Args:
            key: Cache key
            value: Cache value
        """
        # BUG: Always adds, never evicts
        self.cache[key] = value

    def get(self, key):
        """
        Get entry from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        if key in self.cache:
            self.hits += 1
            return self.cache[key]
        else:
            self.misses += 1
            return None

    def size(self):
        """
        Get current cache size.

        Returns:
            Number of entries in cache
        """
        return len(self.cache)

    def stats(self):
        """
        Get cache statistics.

        Returns:
            Dict with cache stats
        """
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0

        return {
            "size": self.size(),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate,
        }


class RequestHandler:
    """Request handler that stores responses in cache."""

    def __init__(self, cache_manager):
        """
        Initialize the request handler.

        Args:
            cache_manager: CacheManager instance
        """
        self.cache = cache_manager
        self.requests_handled = 0

    def handle_request(self, request_id):
        """
        Handle request and store response in cache.

        This is where the memory leak manifests - every request
        adds a new cache entry without cleanup.

        Args:
            request_id: Request identifier
        """
        self.requests_handled += 1

        # Generate cache key
        cache_key = f"request_{request_id}"

        # Check cache first
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        # Simulate processing and generate response
        # Response size ~1KB per entry
        response = {
            "request_id": request_id,
            "timestamp": time.time(),
            "data": "x" * 1000,  # ~1KB payload
            "metadata": {
                "user_id": random.randint(1, 1000),
                "session_id": f"session_{random.randint(1, 100)}",
            },
        }

        # Store in cache (BUG: grows unbounded)
        self.cache.add(cache_key, response)

        return response


def main():
    """Main entry point - continuous request handling loop."""
    parser = argparse.ArgumentParser(
        description="Cache System - Memory Leak Demonstration",
        epilog="Press Ctrl+C to stop the handler.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=0,
        help="Run duration in seconds (0 = infinite, default: 0)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.1,
        help="Sleep interval between request batches in seconds (default: 0.1)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Cache System - Memory Leak Scenario")
    print("=" * 70)
    print()
    print(f"PID: {os.getpid()}")
    print()
    print("Bug: Cache grows unbounded without eviction policy")
    print("     - No LRU, no TTL, no max_size limit")
    print("     - ~1KB per entry * 100 entries/cycle = ~100KB/sec")
    print()
    print("Memory growth is steady and observable with peeka memory command.")
    print()
    print("Running continuous request handling. Press Ctrl+C to stop.")
    print()

    cache_manager = CacheManager()
    handler = RequestHandler(cache_manager)

    start_time = time.time()
    cycle = 0

    try:
        while True:
            cycle += 1

            # Process batch of requests (100 per cycle)
            for i in range(100):
                request_id = cycle * 100 + i
                handler.handle_request(request_id)

            # Print stats every cycle
            stats = cache_manager.stats()
            elapsed = time.time() - start_time

            print(
                f"[Cycle #{cycle}] "
                f"Requests: {handler.requests_handled}, "
                f"Cache Size: {stats['size']}, "
                f"Hit Rate: {stats['hit_rate']:.1f}%, "
                f"Elapsed: {elapsed:.1f}s"
            )

            # Check duration limit
            if args.duration > 0 and elapsed >= args.duration:
                break

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print()
        print("Stopped.")
        print(f"Total requests handled: {handler.requests_handled}")
        print(f"Final cache size: {cache_manager.size()}")


if __name__ == "__main__":
    main()
