#!/usr/bin/env python3
"""
Banking System - Deadlock Scenario

This example demonstrates a classic deadlock caused by lock acquisition
in inconsistent order across threads.

Bug location: TransferService.transfer()
- Locks accounts in call order (from_account → to_account)
- Two threads transferring in opposite directions create circular wait
- Thread A: locks account 1 → waits for account 2
- Thread B: locks account 2 → waits for account 1

Peeka workflow:
  peeka-cli attach <PID>
  peeka-cli thread --action list
  peeka-cli thread --action stacks
  peeka-cli stack '__main__.TransferService.transfer' -n 5

Main thread stays in heartbeat loop (never participates in deadlock).
"""

import argparse
import os
import random
import threading
import time


class BankAccount:
    """Bank account with balance and thread lock."""

    def __init__(self, account_id, initial_balance=1000):
        """
        Initialize a bank account.

        Args:
            account_id: Account identifier
            initial_balance: Starting balance
        """
        self.account_id = account_id
        self.balance = initial_balance
        self.lock = threading.Lock()

    def debit(self, amount):
        """
        Debit (subtract) amount from balance.

        Args:
            amount: Amount to debit
        """
        if self.balance >= amount:
            self.balance -= amount
            return True
        return False

    def credit(self, amount):
        """
        Credit (add) amount to balance.

        Args:
            amount: Amount to credit
        """
        self.balance += amount


class TransferService:
    """Transfer service with deadlock bug."""

    def __init__(self):
        """Initialize the transfer service."""
        self.transfers_completed = 0
        self.transfer_lock = threading.Lock()

    def transfer(self, from_account, to_account, amount):
        """
        Transfer money between accounts with BUG - lock order deadlock.

        BUG: Acquires locks in call order (from_account → to_account).
        When two threads transfer in opposite directions:
        - Thread A: locks account 1 → waits for account 2
        - Thread B: locks account 2 → waits for account 1
        Result: Circular wait = DEADLOCK

        Correct fix: Lock accounts in consistent order (by account_id).

        Args:
            from_account: Source account
            to_account: Destination account
            amount: Transfer amount

        Returns:
            True if transfer succeeded, False otherwise
        """
        # Randomized pre-transfer sleep to create deadlock window
        time.sleep(random.uniform(0.001, 0.005))

        # BUG: Lock acquisition in call order (inconsistent across threads)
        with from_account.lock:
            # Sleep between locks to increase deadlock probability
            time.sleep(random.uniform(0.01, 0.05))

            with to_account.lock:
                # Perform transfer
                if from_account.debit(amount):
                    to_account.credit(amount)

                    with self.transfer_lock:
                        self.transfers_completed += 1

                    print(
                        f"[Transfer #{self.transfers_completed}] "
                        f"{from_account.account_id} → {to_account.account_id}: "
                        f"${amount:.2f}"
                    )
                    return True

        return False


def worker_a_to_b(service, account_a, account_b, stop_event):
    """
    Worker thread: transfers from account A to account B.

    Args:
        service: TransferService instance
        account_a: Source account
        account_b: Destination account
        stop_event: Event to signal shutdown
    """
    while not stop_event.is_set():
        amount = random.uniform(10, 50)
        service.transfer(account_a, account_b, amount)
        time.sleep(random.uniform(0.1, 0.3))


def worker_b_to_a(service, account_a, account_b, stop_event):
    """
    Worker thread: transfers from account B to account A.

    Args:
        service: TransferService instance
        account_a: Target account
        account_b: Source account
        stop_event: Event to signal shutdown
    """
    while not stop_event.is_set():
        amount = random.uniform(10, 50)
        service.transfer(account_b, account_a, amount)
        time.sleep(random.uniform(0.1, 0.3))


def main():
    """Main entry point - starts worker threads and heartbeat loop."""
    parser = argparse.ArgumentParser(
        description="Banking System - Deadlock Demonstration",
        epilog="Press Ctrl+C to stop the system.",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Heartbeat interval in seconds (default: 1.0)",
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Banking System - Deadlock Scenario")
    print("=" * 70)
    print()
    print(f"PID: {os.getpid()}")
    print()
    print("Bug: transfer() locks accounts in call order")
    print("     - Thread A: locks account A → waits for account B")
    print("     - Thread B: locks account B → waits for account A")
    print("     - Result: Circular wait = DEADLOCK")
    print()
    print("Two worker threads transfer in opposite directions.")
    print("Main thread stays responsive (heartbeat only, no locking).")
    print()
    print("Running transfer service. Press Ctrl+C to stop.")
    print()

    # Create accounts
    account_a = BankAccount("Account-A", initial_balance=10000)
    account_b = BankAccount("Account-B", initial_balance=10000)

    # Create transfer service
    service = TransferService()

    # Create stop event for graceful shutdown
    stop_event = threading.Event()

    # Start worker threads
    thread_a_to_b = threading.Thread(
        target=worker_a_to_b,
        args=(service, account_a, account_b, stop_event),
        daemon=True,
        name="Worker-A→B",
    )

    thread_b_to_a = threading.Thread(
        target=worker_b_to_a,
        args=(service, account_a, account_b, stop_event),
        daemon=True,
        name="Worker-B→A",
    )

    thread_a_to_b.start()
    thread_b_to_a.start()

    print(f"Started worker threads: {thread_a_to_b.name}, {thread_b_to_a.name}")
    print()

    try:
        # Main thread: heartbeat loop only (never participates in locking)
        while True:
            time.sleep(args.interval)

    except KeyboardInterrupt:
        print()
        print("Stopping...")
        stop_event.set()

        # Wait for workers to finish
        thread_a_to_b.join(timeout=2.0)
        thread_b_to_a.join(timeout=2.0)

        print("Stopped.")
        print(f"Total transfers completed: {service.transfers_completed}")
        print(f"Final balances: A=${account_a.balance:.2f}, B=${account_b.balance:.2f}")


if __name__ == "__main__":
    main()
