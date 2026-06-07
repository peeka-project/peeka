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

    from peeka.cli.handlers import attach
    from peeka.cli.handlers import clients
    from peeka.cli.handlers import consumers
    from peeka.cli.handlers import dx
    from peeka.cli.handlers import jobs
    from peeka.cli.handlers import observe
    from peeka.cli.handlers import probes
    from peeka.cli.handlers import run
    from peeka.cli.handlers import runtime
    from peeka.cli.handlers import targets

    subparsers.choices["attach"].set_defaults(handler=attach.cmd_attach)
    subparsers.choices["detach"].set_defaults(handler=attach.cmd_detach)
    subparsers.choices["watch"].set_defaults(handler=observe.cmd_watch)
    subparsers.choices["trace"].set_defaults(handler=observe.cmd_trace)
    subparsers.choices["stack"].set_defaults(handler=observe.cmd_stack)
    subparsers.choices["logger"].set_defaults(handler=runtime.cmd_logger)
    subparsers.choices["monitor"].set_defaults(handler=observe.cmd_monitor)
    subparsers.choices["sc"].set_defaults(handler=runtime.cmd_sc)
    subparsers.choices["sm"].set_defaults(handler=runtime.cmd_sm)
    subparsers.choices["memory"].set_defaults(handler=runtime.cmd_memory)
    subparsers.choices["inspect"].set_defaults(handler=runtime.cmd_vmtool)
    subparsers.choices["reset"].set_defaults(handler=runtime.cmd_reset)
    subparsers.choices["thread"].set_defaults(handler=runtime.cmd_thread)
    subparsers.choices["patch-status"].set_defaults(handler=runtime.cmd_patch_status)
    subparsers.choices["top"].set_defaults(handler=observe.cmd_top)
    subparsers.choices["run"].set_defaults(handler=run.cmd_run)
    subparsers.choices["target"].set_defaults(handler=targets.cmd_target)
    subparsers.choices["session"].set_defaults(handler=targets.cmd_session)
    subparsers.choices["client"].set_defaults(handler=clients.cmd_client)
    subparsers.choices["consumer"].set_defaults(handler=consumers.cmd_consumer)
    subparsers.choices["dx"].set_defaults(handler=dx.cmd_dx)
    subparsers.choices["job"].set_defaults(handler=jobs.cmd_job)
    subparsers.choices["probe"].set_defaults(handler=probes.cmd_probe)

    return parser
