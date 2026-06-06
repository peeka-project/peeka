"""CLI package helpers."""


def main() -> int:
    """Run the peeka CLI entry point."""
    from peeka.cli.main import main as run_main

    return run_main()
