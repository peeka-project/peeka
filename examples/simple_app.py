"""
Simple example application to demonstrate PeekA functionality
"""
import os
import random
import time


def reverse_string(input_string):
    """反转字符串"""
    return input_string[::-1]


def calculate_square(x):
    """Function to calculate square of a number."""
    if x < 0:
        raise ValueError("Cannot square negative numbers")
    return x * x


def process_data(data_list):
    """Function to process a list of data."""
    results = []
    for item in data_list:
        squared = calculate_square(item)
        results.append(squared)
    return results


def main():
    """Main function that simulates a long-running application."""
    print("Starting example application...")
    print("PID:", os.getpid())  # Print PID so we can attach to it

    while True:
        try:
            # Generate random data to process
            data = [random.randint(-5, 10) for _ in range(3)]
            print(f"Processing data: {data}")

            try:
                results = process_data(data)
                print(f"Results: {results}")
            except ValueError as e:
                print(f"Error processing data: {e}")

            time.sleep(2)  # Simulate work with delay

        except KeyboardInterrupt:
            print("\nShutting down...")
            break


if __name__ == "__main__":
    main()
