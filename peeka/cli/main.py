"""peeka-cli entry point and command dispatcher."""

import sys
from typing import Callable, Dict

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
from peeka.cli.parser import build_parser
from peeka.core.output import OutputFormatter
from peeka.core.output import configure_logging

configure_logging()

CommandHandler = Callable[[object], int]

_COMMAND_HANDLERS: Dict[str, CommandHandler] = {
    "attach": attach.cmd_attach,
    "detach": attach.cmd_detach,
    "watch": observe.cmd_watch,
    "trace": observe.cmd_trace,
    "stack": observe.cmd_stack,
    "logger": runtime.cmd_logger,
    "monitor": observe.cmd_monitor,
    "sc": runtime.cmd_sc,
    "sm": runtime.cmd_sm,
    "memory": runtime.cmd_memory,
    "inspect": runtime.cmd_vmtool,
    "reset": runtime.cmd_reset,
    "thread": runtime.cmd_thread,
    "patch-status": runtime.cmd_patch_status,
    "top": observe.cmd_top,
    "run": run.cmd_run,
    "target": targets.cmd_target,
    "session": targets.cmd_session,
    "client": clients.cmd_client,
    "consumer": consumers.cmd_consumer,
    "dx": dx.cmd_dx,
    "job": jobs.cmd_job,
    "probe": probes.cmd_probe,
}


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    handler = _COMMAND_HANDLERS.get(args.command)
    if handler is None:
        OutputFormatter.error("peeka", error=f"Unknown command: {args.command}")
        return 1

    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\n", file=sys.stderr)
        return 130
    except Exception as exc:
        OutputFormatter.error("peeka", error=str(exc))
        return 1


if __name__ == "__main__":
    sys.exit(main())
