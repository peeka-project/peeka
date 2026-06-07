"""peeka-cli entry point and command dispatcher."""

import sys

from peeka.cli.parser import build_parser
from peeka.core.output import OutputFormatter
from peeka.core.output import configure_logging

configure_logging()


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

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
