#!/usr/bin/env python3
"""
API Service - Intermittent Slow Query Scenario

This example demonstrates intermittent performance issues in database queries
where certain search patterns trigger inefficient nested loop execution.

Bug location: DatabaseSimulator.search_products()
- Fast path: Direct list comprehension (~5ms)
- Slow path: Nested loop with I/O simulation when query length > 10 chars
- Every 7th product search uses a long query, triggering the bug

Peeka workflow:
  peeka-cli attach <PID>
  peeka-cli monitor '__main__.DatabaseSimulator' --interval 2
  peeka-cli watch '__main__.DatabaseSimulator.search_products' --condition "cost > 200" -n 3
  peeka-cli trace '__main__.ApiService.handle_product_search' -n 2 --min-duration 10
"""

import argparse
import os
import random
import time


class DatabaseSimulator:
    """Database simulator with intermittent slow query pattern."""

    def __init__(self):
        """Initialize the database simulator."""
        self.query_count = 0
        self.product_catalog = [
            {"id": i, "name": f"Product {i}", "price": random.uniform(10, 1000)}
            for i in range(1, 101)
        ]
        self.user_profiles = {
            i: {"user_id": i, "name": f"User {i}", "email": f"user{i}@example.com"}
            for i in range(1, 51)
        }

    def query(self, query_type, params):
        """
        Generic query method with 90% fast / 10% slow pattern.

        Args:
            query_type: Type of query (user, product, order)
            params: Query parameters

        Returns:
            Query result
        """
        self.query_count += 1

        # 90% fast, 10% slow for generic queries
        if random.random() < 0.1:
            time.sleep(random.uniform(0.05, 0.15))

        return {"query_type": query_type, "params": params, "count": self.query_count}

    def search_products(self, query_str):
        """
        Search products with BUG in query processing.

        BUG: When query length > 10, uses inefficient nested loop
        with I/O simulation instead of direct filtering.

        Args:
            query_str: Search query string

        Returns:
            List of matching products
        """
        if len(query_str) > 10:
            # SLOW PATH: Inefficient nested loop simulation
            results = []
            for product in self.product_catalog:
                # Simulate complex search with nested operations
                for _ in range(100):
                    # Simulate I/O wait or complex comparison
                    time.sleep(0.01)
                    if query_str.lower() in product["name"].lower():
                        break
                if query_str.lower() in product["name"].lower():
                    results.append(product)
            return results
        else:
            # FAST PATH: Direct filtering
            return [
                p
                for p in self.product_catalog
                if query_str.lower() in p["name"].lower()
            ]

    def get_user_profile(self, user_id):
        """
        Get user profile (fast operation).

        Args:
            user_id: User ID

        Returns:
            User profile dict
        """
        time.sleep(random.uniform(0.001, 0.005))
        return self.user_profiles.get(user_id, {})


class ApiService:
    """API service simulator with multiple endpoint types."""

    def __init__(self):
        """Initialize the API service."""
        self.db = DatabaseSimulator()
        self.request_count = 0

    def handle_user_query(self, user_id):
        """
        Handle user profile query (fast path).

        Args:
            user_id: User ID
        """
        self.request_count += 1
        profile = self.db.get_user_profile(user_id)
        print(
            f"[User Query #{self.request_count}] User: {profile.get('name', 'Unknown')}"
        )

    def handle_product_search(self, query):
        """
        Handle product search query (intermittent slow path).

        Args:
            query: Search query string
        """
        self.request_count += 1
        start = time.time()
        results = self.db.search_products(query)
        duration = (time.time() - start) * 1000

        print(
            f"[Product Search #{self.request_count}] Query: '{query[:30]}...', "
            f"Results: {len(results)}, Duration: {duration:.1f}ms"
        )

    def handle_order_create(self, user_id, items):
        """
        Handle order creation (fast path).

        Args:
            user_id: User ID
            items: List of item IDs
        """
        self.request_count += 1

        # Simulate order processing
        time.sleep(random.uniform(0.005, 0.015))
        self.db.query("order_create", {"user_id": user_id, "items": items})

        print(
            f"[Order Create #{self.request_count}] User: {user_id}, Items: {len(items)}"
        )


def main():
    """Main entry point - continuous API request simulation."""
    parser = argparse.ArgumentParser(
        description="API Service - Intermittent Slow Query Demonstration",
        epilog="Press Ctrl+C to stop the service.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Sleep interval between requests in seconds (default: 1.0)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("API Service - Intermittent Slow Query Scenario")
    print("=" * 70)
    print()
    print(f"PID: {os.getpid()}")
    print()
    print("Bug: search_products() uses nested loop when query length > 10")
    print("     Slow path: ~1 second (nested loop with I/O simulation)")
    print("     Fast path: ~5ms (direct list comprehension)")
    print()
    print("Every 7th product search uses a long query, triggering the bug.")
    print()
    print("Running continuous API request simulation. Press Ctrl+C to stop.")
    print()

    service = ApiService()
    counter = 0

    short_queries = [
        "laptop",
        "phone",
        "tablet",
        "monitor",
        "keyboard",
        "mouse",
    ]

    try:
        while True:
            counter += 1

            # Cycle through different request types
            request_type = counter % 3

            if request_type == 0:
                # User query (fast)
                user_id = random.randint(1, 50)
                service.handle_user_query(user_id)

            elif request_type == 1:
                # Product search (intermittent slow)
                if counter % 7 == 0:
                    # Long query triggers the bug
                    query = "high performance laptop computer"
                else:
                    query = random.choice(short_queries)
                service.handle_product_search(query)

            else:
                # Order create (fast)
                user_id = random.randint(1, 50)
                items = [random.randint(1, 100) for _ in range(random.randint(1, 5))]
                service.handle_order_create(user_id, items)

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print()
        print("Stopped.")
        print(f"Total requests processed: {service.request_count}")


if __name__ == "__main__":
    main()
