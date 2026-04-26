#!/usr/bin/env python3
"""
Data Processing - High CPU Usage Scenario

This example demonstrates inefficient data transformation with repeated
sorting operations causing high CPU usage.

Bug location: DataProcessor.transform_data()
- Performs redundant sorting operations on the same dataset
- O(n log n) sorting repeated 3 times without caching results
- Called once per batch in process_batch()

Peeka workflow:
  peeka-cli attach <PID>
  peeka-cli top '__main__.DataProcessor' -n 10
  peeka-cli trace '__main__.DataProcessor.process_batch' --depth 2 -n 3
  peeka-cli watch '__main__.DataProcessor.transform_data' -n 5
"""

import argparse
import os
import random
import time


class DataProcessor:
    """Data processor with CPU-intensive transformation bug."""

    def __init__(self, batch_size=300):
        """
        Initialize the data processor.

        Args:
            batch_size: Number of records per batch
        """
        self.batch_size = batch_size
        self.batches_processed = 0

    def generate_batch(self):
        """
        Generate a batch of sample data.

        Returns:
            List of data records
        """
        return [
            {
                "id": i,
                "value": random.uniform(0, 1000),
                "category": random.choice(["A", "B", "C", "D"]),
            }
            for i in range(self.batch_size)
        ]

    def transform_data(self, data):
        """
        Transform data with BUG in repeated sorting.

        BUG: Performs redundant sorting operations without caching:
        1. Initial sort for ordering
        2. Validation during transform (iterates sorted data)
        3. Refinement sort (sorts again for final output)

        This creates O(n²) behavior in the context of process_batch().

        Args:
            data: List of data records

        Returns:
            Transformed data list
        """
        # BUG: First sort - ordering by value
        sorted_data = sorted(data, key=lambda x: x["value"])

        # BUG: Redundant validation during transform
        # (iterates through sorted data, could cache but doesn't)
        validated = []
        for record in sorted_data:
            if record["value"] > 0:
                validated.append(
                    {
                        "id": record["id"],
                        "value": record["value"],
                        "category": record["category"],
                        "processed": True,
                    }
                )

        # BUG: Third sort - refinement (sorts again!)
        # This is completely redundant since validated preserves sorted order
        refined = sorted(validated, key=lambda x: x["value"])

        return refined

    def process_batch(self):
        """
        Process a batch of data.

        Generates data, transforms it, and returns batch info.

        Returns:
            Dict with batch processing info
        """
        self.batches_processed += 1

        batch = self.generate_batch()
        transformed = self.transform_data(batch)

        return {
            "batch_id": self.batches_processed,
            "records": len(transformed),
            "avg_value": sum(r["value"] for r in transformed) / len(transformed),
        }


def main():
    """Main entry point - continuous data processing loop."""
    parser = argparse.ArgumentParser(
        description="Data Processing - High CPU Usage Demonstration",
        epilog="Press Ctrl+C to stop the processor.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=300,
        help="Number of records per batch (default: 300)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=0.05,
        help="Sleep interval between batches in seconds (default: 0.05)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Data Processing - High CPU Usage Scenario")
    print("=" * 70)
    print()
    print(f"PID: {os.getpid()}")
    print()
    print("Bug: transform_data() performs redundant sorting operations")
    print("     - Sorts data 3 times without caching results")
    print("     - O(n log n) repeated in tight loop")
    print(f"     - Batch size: {args.batch_size} records")
    print()
    print("Running continuous data processing. Press Ctrl+C to stop.")
    print()

    processor = DataProcessor(batch_size=args.batch_size)

    try:
        while True:
            result = processor.process_batch()

            print(
                f"[Batch #{result['batch_id']}] "
                f"Records: {result['records']}, "
                f"Avg Value: {result['avg_value']:.2f}"
            )

            # Sleep to prevent extreme CPU saturation
            # (allows system to remain responsive for debugging)
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print()
        print("Stopped.")
        print(f"Total batches processed: {processor.batches_processed}")


if __name__ == "__main__":
    main()
