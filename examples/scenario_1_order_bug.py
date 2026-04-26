#!/usr/bin/env python3
"""
E-commerce Order System - Order Amount Calculation Bug Scenario

This example demonstrates a classic bug in order total calculation where
discount is multiplied instead of being properly applied as a percentage reduction.

Bug location: OrderProcessor.calculate_total()
- Buggy code: total = subtotal * order.discount (multiplies by 20 instead of * 0.20)
- Every 5th order has discount=20, triggering the bug
"""

import argparse
import os
import time


class Order:
    """Represents an e-commerce order with items and optional discount."""

    def __init__(self, order_id, items, discount=0):
        """
        Initialize an order.

        Args:
            order_id: Unique order identifier
            items: List of (price, quantity) tuples
            discount: Discount percentage (0-100), defaults to 0
        """
        self.order_id = order_id
        self.items = items
        self.discount = discount

    def get_subtotal(self):
        """Calculate subtotal before discount."""
        return sum(price * quantity for price, quantity in self.items)


class OrderProcessor:
    """Processes orders and calculates totals with a bug in discount calculation."""

    def __init__(self):
        """Initialize the order processor."""
        self.orders_processed = 0

    def create_order(self, order_id, items, discount=0):
        """
        Create an order.

        Args:
            order_id: Unique order identifier
            items: List of (price, quantity) tuples
            discount: Discount percentage (0-100)

        Returns:
            Order instance
        """
        return Order(order_id, items, discount)

    def calculate_total(self, order):
        """
        Calculate order total with BUG in discount application.

        BUG: Multiplies subtotal by discount instead of applying percentage reduction.
        Should be: total = subtotal * (1 - order.discount / 100)
        Actual: total = subtotal * order.discount

        Args:
            order: Order instance

        Returns:
            Calculated total (buggy)
        """
        subtotal = order.get_subtotal()
        if order.discount > 0:
            # BUG: This multiplies by discount value instead of applying discount percentage
            total = subtotal * order.discount
        else:
            total = subtotal
        return total

    def process_order(self, order):
        """
        Process an order and print details.

        Args:
            order: Order instance
        """
        self.orders_processed += 1
        subtotal = order.get_subtotal()
        total = self.calculate_total(order)

        print(
            f"[Order #{order.order_id}] Subtotal: ${subtotal:.2f}, "
            f"Discount: {order.discount}%, Total: ${total:.2f}"
        )


def generate_sample_items():
    """Generate sample items for an order."""
    return [
        (19.99, 1),  # Item 1: $19.99 x 1
        (29.99, 1),  # Item 2: $29.99 x 1
        (29.99, 1),  # Item 3: $29.99 x 1
    ]


def main():
    """Main entry point - continuous order processing loop."""
    parser = argparse.ArgumentParser(
        description="E-commerce Order System - Bug Demonstration",
        epilog="Press Ctrl+C to stop the order processing loop.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Sleep interval between orders in seconds (default: 2.0)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("E-commerce Order System - Bug Scenario")
    print("=" * 70)
    print()
    print(f"PID: {os.getpid()}")
    print()
    print("Bug: Order total calculation multiplies by discount instead of")
    print("     applying it as a percentage reduction.")
    print()
    print("Every 5th order has a 20% discount, triggering the bug:")
    print("  - Buggy: $79.97 * 20 = $1,599.40")
    print("  - Correct: $79.97 * (1 - 20/100) = $63.98")
    print()
    print("Running continuous order processing. Press Ctrl+C to stop.")
    print()

    processor = OrderProcessor()
    counter = 0

    try:
        while True:
            counter += 1

            # Every 5th order has a 20% discount (triggers the bug)
            items = generate_sample_items()
            discount = 20 if counter % 5 == 0 else 0

            order = processor.create_order(counter, items, discount)
            processor.process_order(order)

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print()
        print("Stopped.")
        print(f"Total orders processed: {processor.orders_processed}")


if __name__ == "__main__":
    main()
