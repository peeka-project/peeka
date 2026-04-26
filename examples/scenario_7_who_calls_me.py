#!/usr/bin/env python3
"""
Multi-Service System - Call Frequency Analysis Scenario

This example demonstrates call frequency analysis with multiple callers
invoking the same database method at different rates.

Pattern: Database.execute_query() called by 3 services at different frequencies
- UserRepository: ~1 Hz (steady, 1 query per call)
- OrderRepository: ~0.5 Hz (moderate, 1 query per call)
- ReportService: ~25 Hz aggregate (5 queries per report, reports at 5 Hz)

Peeka workflow:
  peeka-cli attach <PID>
  peeka-cli stack '__main__.Database.execute_query' -n 10
  peeka-cli watch '__main__.Database.execute_query' -n 20
  peeka-cli trace '__main__.ReportService.generate_daily_report' -d 3 -n 2
"""

import argparse
import os
import random
import threading
import time


class Database:
    """Database with single query method called by multiple services."""

    def __init__(self):
        """Initialize the database."""
        self.query_count = 0
        self.query_lock = threading.Lock()

    def execute_query(self, sql):
        """
        Execute SQL query.

        This is the TARGET METHOD - called by 3 services at different rates.

        Args:
            sql: SQL query string

        Returns:
            Query result dict
        """
        with self.query_lock:
            self.query_count += 1
            count = self.query_count

        # Simulate query execution
        time.sleep(random.uniform(0.001, 0.005))

        return {
            "query_count": count,
            "sql": sql,
            "rows": random.randint(1, 100),
        }


class UserRepository:
    """User repository - calls Database.execute_query() at ~1 Hz."""

    def __init__(self, db):
        """
        Initialize user repository.

        Args:
            db: Database instance
        """
        self.db = db
        self.users_fetched = 0

    def get_user(self, user_id):
        """
        Get user by ID (1 query per call).

        Args:
            user_id: User ID

        Returns:
            User dict
        """
        sql = f"SELECT * FROM users WHERE id = {user_id}"
        self.db.execute_query(sql)

        self.users_fetched += 1

        return {"user_id": user_id, "username": f"user_{user_id}"}

    def list_users(self, limit=10):
        """
        List users (1 query per call).

        Args:
            limit: Result limit
        """
        sql = f"SELECT * FROM users LIMIT {limit}"
        self.db.execute_query(sql)


class OrderRepository:
    """Order repository - calls Database.execute_query() at ~0.5 Hz."""

    def __init__(self, db):
        """
        Initialize order repository.

        Args:
            db: Database instance
        """
        self.db = db
        self.orders_fetched = 0

    def get_order(self, order_id):
        """
        Get order by ID (1 query per call).

        Args:
            order_id: Order ID

        Returns:
            Order dict
        """
        sql = f"SELECT * FROM orders WHERE id = {order_id}"
        self.db.execute_query(sql)

        self.orders_fetched += 1

        return {"order_id": order_id, "status": "completed"}

    def list_orders(self, user_id, limit=10):
        """
        List orders for user (1 query per call).

        Args:
            user_id: User ID
            limit: Result limit
        """
        sql = f"SELECT * FROM orders WHERE user_id = {user_id} LIMIT {limit}"
        self.db.execute_query(sql)


class ReportService:
    """Report service - calls Database.execute_query() at high frequency (~25 Hz)."""

    def __init__(self, db):
        """
        Initialize report service.

        Args:
            db: Database instance
        """
        self.db = db
        self.reports_generated = 0

    def generate_daily_report(self, date):
        """
        Generate daily report (5 queries per report).

        This method calls Database.execute_query() 5 times,
        achieving high aggregate frequency even with moderate call rate.

        Args:
            date: Report date

        Returns:
            Report dict
        """
        # Query 1: User count
        self.db.execute_query(f"SELECT COUNT(*) FROM users WHERE date = '{date}'")

        # Query 2: Order count
        self.db.execute_query(f"SELECT COUNT(*) FROM orders WHERE date = '{date}'")

        # Query 3: Revenue sum
        self.db.execute_query(f"SELECT SUM(amount) FROM orders WHERE date = '{date}'")

        # Query 4: Top products
        self.db.execute_query(
            f"SELECT product_id, COUNT(*) FROM orders WHERE date = '{date}' "
            f"GROUP BY product_id ORDER BY COUNT(*) DESC LIMIT 10"
        )

        # Query 5: User activity
        self.db.execute_query(
            f"SELECT user_id, COUNT(*) FROM activities WHERE date = '{date}' "
            f"GROUP BY user_id ORDER BY COUNT(*) DESC LIMIT 10"
        )

        self.reports_generated += 1

        return {
            "date": date,
            "report_id": self.reports_generated,
            "queries_executed": 5,
        }


def worker_users(user_repo, stop_event):
    """
    Worker thread for user repository (~1 Hz).

    Args:
        user_repo: UserRepository instance
        stop_event: Event to signal shutdown
    """
    while not stop_event.is_set():
        user_id = random.randint(1, 1000)
        user_repo.get_user(user_id)
        time.sleep(1.0)


def worker_orders(order_repo, stop_event):
    """
    Worker thread for order repository (~0.5 Hz).

    Args:
        order_repo: OrderRepository instance
        stop_event: Event to signal shutdown
    """
    while not stop_event.is_set():
        order_id = random.randint(1, 1000)
        order_repo.get_order(order_id)
        time.sleep(2.0)


def worker_reports(report_service, stop_event):
    """
    Worker thread for report service (~5 Hz for reports, ~25 Hz for queries).

    Each report generation calls Database.execute_query() 5 times,
    resulting in high aggregate query frequency.

    Args:
        report_service: ReportService instance
        stop_event: Event to signal shutdown
    """
    while not stop_event.is_set():
        date = time.strftime("%Y-%m-%d")
        report_service.generate_daily_report(date)
        time.sleep(0.2)


def main():
    """Main entry point - starts worker threads and heartbeat loop."""
    parser = argparse.ArgumentParser(
        description="Multi-Service System - Call Frequency Analysis",
        epilog="Press Ctrl+C to stop the system.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Stats reporting interval in seconds (default: 5.0)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Multi-Service System - Call Frequency Analysis")
    print("=" * 70)
    print()
    print(f"PID: {os.getpid()}")
    print()
    print("Pattern: Database.execute_query() called by 3 services")
    print("  - UserRepository: ~1 Hz (1 query per call)")
    print("  - OrderRepository: ~0.5 Hz (1 query per call)")
    print("  - ReportService: ~25 Hz aggregate (5 queries per report)")
    print()
    print("Use stack command to identify which service is calling most frequently.")
    print()
    print("Running multi-service system. Press Ctrl+C to stop.")
    print()

    # Create database and repositories
    db = Database()
    user_repo = UserRepository(db)
    order_repo = OrderRepository(db)
    report_service = ReportService(db)

    # Create stop event for graceful shutdown
    stop_event = threading.Event()

    # Start worker threads
    thread_users = threading.Thread(
        target=worker_users,
        args=(user_repo, stop_event),
        daemon=True,
        name="Worker-Users",
    )

    thread_orders = threading.Thread(
        target=worker_orders,
        args=(order_repo, stop_event),
        daemon=True,
        name="Worker-Orders",
    )

    thread_reports = threading.Thread(
        target=worker_reports,
        args=(report_service, stop_event),
        daemon=True,
        name="Worker-Reports",
    )

    thread_users.start()
    thread_orders.start()
    thread_reports.start()

    print(
        f"Started worker threads: {thread_users.name}, "
        f"{thread_orders.name}, {thread_reports.name}"
    )
    print()

    last_stats_time = time.time()
    last_query_count = 0

    try:
        # Main thread: heartbeat loop with periodic stats
        while True:
            time.sleep(1.0)

            # Print stats at specified interval
            elapsed = time.time() - last_stats_time
            if elapsed >= args.interval:
                current_count = db.query_count
                queries_per_sec = (current_count - last_query_count) / elapsed

                print(
                    f"[Stats] "
                    f"Total queries: {current_count}, "
                    f"Rate: {queries_per_sec:.1f} queries/sec, "
                    f"Users: {user_repo.users_fetched}, "
                    f"Orders: {order_repo.orders_fetched}, "
                    f"Reports: {report_service.reports_generated}"
                )

                last_stats_time = time.time()
                last_query_count = current_count

    except KeyboardInterrupt:
        print()
        print("Stopping...")
        stop_event.set()

        # Wait for workers to finish
        thread_users.join(timeout=2.0)
        thread_orders.join(timeout=2.0)
        thread_reports.join(timeout=2.0)

        print("Stopped.")
        print(f"Total queries executed: {db.query_count}")


if __name__ == "__main__":
    main()
