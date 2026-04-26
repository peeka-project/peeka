#!/usr/bin/env python3
"""
Emergency Diagnostics - Inspect and Logger Scenario

This example demonstrates emergency runtime diagnostics with hidden state
inspection and logger level adjustment.

Bugs:
1. UserService._cache: Unbounded dict growth (every get_user adds entry)
2. UserService._retry_count: Integer that increments always (no reset)
3. PaymentGateway: Debug logs hidden at WARNING level by default

Peeka workflow:
  peeka-cli attach <PID>
  peeka-cli sc User
  peeka-cli sm get_user
  peeka-cli inspect '__main__.UserService' --attr _cache
  peeka-cli inspect '__main__.UserService' --attr _retry_count
  peeka-cli logger --action list
  peeka-cli logger --action set __main__ DEBUG
  peeka-cli watch '__main__.UserService.get_user' -n 5
"""

import argparse
import logging
import os
import random
import time


# Setup logging for logger command demonstration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


class AppConfig:
    """Application configuration."""

    def __init__(self):
        """Initialize app configuration."""
        self.feature_flags = {
            "cache_enabled": True,
            "retry_enabled": True,
            "debug_mode": False,
        }
        self.thresholds = {
            "max_retries": 3,
            "timeout_ms": 5000,
        }

    def get_flag(self, flag_name):
        """
        Get feature flag value.

        Args:
            flag_name: Flag name

        Returns:
            Flag value
        """
        return self.feature_flags.get(flag_name, False)


class UserService:
    """User service with hidden state bugs."""

    def __init__(self, config):
        """
        Initialize user service.

        Args:
            config: AppConfig instance
        """
        self.config = config
        self.logger = logging.getLogger(__name__)

        # BUG: Cache grows unbounded (no eviction)
        self._cache = {}

        # BUG: Retry count increments always (no reset)
        self._retry_count = 0

        self.users_fetched = 0

    def get_user(self, user_id):
        """
        Get user by ID with BUG - cache grows unbounded.

        BUG 1: _cache dict grows without cleanup (every call adds entry).
        BUG 2: _retry_count increments on every call (never resets).

        Args:
            user_id: User ID

        Returns:
            User dict
        """
        self.logger.debug(f"Fetching user {user_id}")

        # Check cache first
        if user_id in self._cache:
            self.logger.debug(f"Cache hit for user {user_id}")
            return self._cache[user_id]

        # BUG: Retry count increments always (should reset on success)
        self._retry_count += 1

        # Simulate database fetch
        time.sleep(random.uniform(0.005, 0.015))

        user = {
            "user_id": user_id,
            "username": f"user_{user_id}",
            "email": f"user_{user_id}@example.com",
            "created_at": time.time(),
        }

        # BUG: Cache grows unbounded (no LRU/TTL/max_size)
        self._cache[user_id] = user
        self.users_fetched += 1

        self.logger.info(f"Fetched user {user_id} (cache size: {len(self._cache)})")

        return user


class PaymentGateway:
    """Payment gateway with logger level demonstration."""

    def __init__(self):
        """Initialize payment gateway."""
        # Logger default is WARNING (debug logs hidden)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.WARNING)

        self.payments_processed = 0

    def process_payment(self, user_id, amount):
        """
        Process payment transaction.

        Args:
            user_id: User ID
            amount: Payment amount

        Returns:
            Transaction ID
        """
        # Debug logs hidden by default (need logger --action set)
        self.logger.debug(
            f"Processing payment for user {user_id}, amount ${amount:.2f}"
        )

        # Simulate payment processing
        time.sleep(random.uniform(0.01, 0.03))

        transaction_id = f"txn_{self.payments_processed + 1}"
        self.payments_processed += 1

        self.logger.warning(
            f"Payment processed: {transaction_id}, user={user_id}, amount=${amount:.2f}"
        )

        return transaction_id


def demo_mode():
    """Display demonstration instructions."""
    print("=" * 70)
    print("Emergency Diagnostics - Demo Mode")
    print("=" * 70)
    print()
    print(f"PID: {os.getpid()}")
    print()
    print("Available Peeka Commands:")
    print()
    print("1. Search classes:")
    print("   peeka-cli sc User")
    print()
    print("2. Search methods:")
    print("   peeka-cli sm get_user")
    print()
    print("3. Inspect hidden state:")
    print("   peeka-cli inspect '__main__.UserService' --attr _cache")
    print("   peeka-cli inspect '__main__.UserService' --attr _retry_count")
    print()
    print("4. List loggers:")
    print("   peeka-cli logger --action list")
    print()
    print("5. Set logger level (enable DEBUG logs):")
    print("   peeka-cli logger --action set __main__ DEBUG")
    print()
    print("6. Watch function calls:")
    print("   peeka-cli watch '__main__.UserService.get_user' -n 5")
    print()
    print("Press Ctrl+C to exit demo mode.")
    print()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        print("Exiting demo mode.")


def loop_mode(interval):
    """
    Run continuous service loop.

    Args:
        interval: Sleep interval between operations
    """
    print("=" * 70)
    print("Emergency Diagnostics - Loop Mode")
    print("=" * 70)
    print()
    print(f"PID: {os.getpid()}")
    print()
    print("Bugs:")
    print("  1. UserService._cache grows unbounded (no eviction)")
    print("  2. UserService._retry_count increments always (no reset)")
    print("  3. PaymentGateway debug logs hidden (WARNING level)")
    print()
    print("Running continuous service loop. Press Ctrl+C to stop.")
    print()

    config = AppConfig()
    user_service = UserService(config)
    payment_gateway = PaymentGateway()

    counter = 0

    try:
        while True:
            counter += 1

            # Fetch user (cache grows)
            user_id = random.randint(1, 100)
            user_service.get_user(user_id)

            # Process payment (debug logs hidden)
            amount = random.uniform(10, 500)
            payment_gateway.process_payment(user_id, amount)

            # Print stats every 10 iterations
            if counter % 10 == 0:
                print(
                    f"[Iteration {counter}] "
                    f"Cache size: {len(user_service._cache)}, "
                    f"Retry count: {user_service._retry_count}, "
                    f"Payments: {payment_gateway.payments_processed}"
                )

            time.sleep(interval)

    except KeyboardInterrupt:
        print()
        print("Stopped.")
        print(f"Total users fetched: {user_service.users_fetched}")
        print(f"Final cache size: {len(user_service._cache)}")
        print(f"Final retry count: {user_service._retry_count}")
        print(f"Total payments: {payment_gateway.payments_processed}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Emergency Diagnostics - Inspect and Logger Demonstration",
        epilog="Press Ctrl+C to stop.",
    )
    parser.add_argument(
        "--mode",
        choices=["demo", "loop"],
        default="demo",
        help="Run mode: demo (show commands) or loop (continuous execution)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.5,
        help="Sleep interval between operations in loop mode (default: 0.5)",
    )

    args = parser.parse_args()

    if args.mode == "demo":
        demo_mode()
    else:
        loop_mode(args.interval)


if __name__ == "__main__":
    main()
