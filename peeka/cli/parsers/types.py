"""Shared argparse type parsers for CLI commands."""

import argparse


def _parse_duration(duration_str: str) -> int:
    """Parse duration string into seconds.

    Supports:
        - Bare integers (interpreted as seconds)
        - Ns (N seconds)
        - Nm (N minutes)
        - Nh (N hours)

    Args:
        duration_str: Duration string to parse.

    Returns:
        Duration in seconds.

    Raises:
        argparse.ArgumentTypeError: If duration_str is invalid.
    """
    if not duration_str:
        raise argparse.ArgumentTypeError("Duration cannot be empty")

    duration_str = duration_str.strip()

    # Try bare integer
    try:
        seconds = int(duration_str)
        if seconds < 0:
            raise argparse.ArgumentTypeError("Duration must be non-negative")
        return seconds
    except ValueError:
        pass

    # Try unit-suffixed form
    if len(duration_str) < 2:
        raise argparse.ArgumentTypeError(f"Invalid duration format: {duration_str}")

    value_str = duration_str[:-1]
    unit = duration_str[-1].lower()

    try:
        value = int(value_str)
        if value < 0:
            raise argparse.ArgumentTypeError("Duration must be non-negative")
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid duration value: {value_str}")

    if unit == "s":
        return value
    elif unit == "m":
        return value * 60
    elif unit == "h":
        return value * 3600
    else:
        raise argparse.ArgumentTypeError(
            f"Invalid duration unit: {unit} (use s, m, or h)"
        )
