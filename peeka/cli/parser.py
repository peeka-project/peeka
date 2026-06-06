"""Argparse parser construction for peeka-cli."""

import argparse

import peeka

from peeka.cli.parsers.attach import add_attach_parsers
from peeka.cli.parsers.clients import add_client_parsers
from peeka.cli.parsers.consumers import add_consumer_parsers
from peeka.cli.parsers.dx import add_dx_parsers
from peeka.cli.parsers.jobs import add_job_parsers
from peeka.cli.parsers.observe import add_observe_parsers
from peeka.cli.parsers.probes import add_probe_parsers
from peeka.cli.parsers.run import add_run_parser
from peeka.cli.parsers.runtime import add_runtime_parsers
from peeka.cli.parsers.targets import add_target_parsers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="peeka-cli",
        description="Peeka - Python Diagnostic Tool based on PEP 768",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
    Examples:
      peeka-cli attach 12345                  # Attach to process 12345
      peeka-cli watch "mymodule.func"         # Watch function calls (must attach first)
      peeka-cli stack "mod.func"              # Stack trace (must attach first)
      peeka-cli detach                        # Detach from current process
      peeka-cli reset                         # Reset all enhancements
      peeka-cli run myscript.py arg1 -- watch "module.function" --success  # Run script and watch function from start
        """,
    )

    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {peeka.__version__}"
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    add_attach_parsers(subparsers)
    add_observe_parsers(subparsers)
    add_runtime_parsers(subparsers)
    add_run_parser(subparsers)
    add_target_parsers(subparsers)
    add_client_parsers(subparsers)
    add_consumer_parsers(subparsers)
    add_dx_parsers(subparsers)
    add_job_parsers(subparsers)
    add_probe_parsers(subparsers)
    return parser
