"""Target and deprecated session CLI handlers."""

import json
import sys
from pathlib import Path

from peeka.core.output import OutputFormatter
from peeka.core.targets import cleanup_stale_targets
from peeka.core.targets import detach_target
from peeka.core.targets import discover_targets
from peeka.core.targets import get_target


def cmd_target(args) -> int:
    if not args.target_action:
        OutputFormatter.error("target", error="Missing target subcommand")
        return 1

    try:
        if args.target_action == "list":
            return cmd_target_list(args)
        elif args.target_action == "current":
            return cmd_target_current(args)
        elif args.target_action == "status":
            return cmd_target_status(args)
        elif args.target_action == "inspect":
            return cmd_target_inspect(args)
        elif args.target_action == "cleanup":
            return cmd_target_cleanup(args)
        elif args.target_action == "detach":
            return cmd_target_detach(args)
        else:
            OutputFormatter.error(
                "target", error=f"Unknown target action: {args.target_action}"
            )
            return 1
    except Exception as e:
        OutputFormatter.error("target", error=str(e))
        return 1


def cmd_target_list(args) -> int:
    targets = discover_targets()

    if args.format == "json":
        for target in targets:
            OutputFormatter.event("target.discovered", data=target.to_dict())
        return 0
    else:
        if not targets:
            print("No targets found.", file=sys.stderr)
            return 0

        print(
            f"{'Target ID':<20} {'State':<10} {'PID':<10} {'Python':<15} {'Socket':<40}"
        )
        print("-" * 95)
        for target in targets:
            socket_short = Path(target.socket_path).name
            print(
                f"{target.target_id:<20} {target.state:<10} {target.pid:<10} {target.python_version:<15} {socket_short:<40}"
            )
        return 0


def cmd_target_current(args) -> int:
    targets = discover_targets()
    alive_targets = [t for t in targets if t.state == "alive"]

    if len(alive_targets) == 1:
        target = alive_targets[0]
        if args.format == "json":
            OutputFormatter.success("target.current", data=target.to_dict())
        else:
            print(
                f"Current target: {target.target_id} (PID {target.pid})",
                file=sys.stderr,
            )
        return 0
    elif len(alive_targets) == 0:
        if args.format == "json":
            OutputFormatter.error(
                "target.current",
                error="No alive targets found",
                error_code="TARGET_NOT_FOUND",
            )
        else:
            print("TARGET_NOT_FOUND: No alive targets found", file=sys.stderr)
        return 1
    else:
        if args.format == "json":
            OutputFormatter.error(
                "target.current",
                error=f"Multiple alive targets found: {len(alive_targets)}",
                error_code="TARGET_AMBIGUOUS",
                targets=[t.target_id for t in alive_targets],
            )
        else:
            print(
                f"TARGET_AMBIGUOUS: Multiple alive targets found ({len(alive_targets)}): "
                + ", ".join(t.target_id for t in alive_targets),
                file=sys.stderr,
            )
        return 2


def cmd_target_status(args) -> int:
    target = get_target(args.target)
    if target is None:
        if args.format == "json":
            OutputFormatter.error(
                "target.status",
                error=f"Target not found: {args.target}",
                error_code="TARGET_NOT_FOUND",
            )
        else:
            print(f"TARGET_NOT_FOUND: {args.target}", file=sys.stderr)
        return 1

    if args.format == "json":
        OutputFormatter.success("target.status", data=target.to_dict())
        return 0
    else:
        print(f"Target ID: {target.target_id}")
        print(f"State: {target.state}")
        print(f"PID: {target.pid}")
        print(f"Python Version: {target.python_version}")
        print(f"Peeka Version: {target.peeka_version}")
        print(f"Socket: {target.socket_path}")
        print(f"Agent Mode: {target.agent_mode}")
        print(f"Injection Mode: {target.injection_mode}")
        return 0


def cmd_target_inspect(args) -> int:
    target = get_target(args.target)
    if target is None:
        if args.format == "json":
            OutputFormatter.error(
                "target.inspect",
                error=f"Target not found: {args.target}",
                error_code="TARGET_NOT_FOUND",
            )
        else:
            print(f"TARGET_NOT_FOUND: {args.target}", file=sys.stderr)
        return 1

    if args.format == "json":
        OutputFormatter.success("target.inspect", data=target.to_dict())
        return 0
    else:
        print(f"Target ID: {target.target_id}")
        print(f"State: {target.state}")
        print(f"PID: {target.pid}")
        print(f"Python Version: {target.python_version}")
        print(f"Peeka Version: {target.peeka_version}")
        print(f"Socket: {target.socket_path}")
        print(f"Agent Mode: {target.agent_mode}")
        print(f"Injection Mode: {target.injection_mode}")
        print(f"Created At: {target.created_at}")
        print(f"Last Seen At: {target.last_seen_at}")
        print(f"Runtime: {json.dumps(target.runtime, indent=2)}")
        print(f"Capabilities: {json.dumps(target.capabilities, indent=2)}")
        print(f"Next Valid Actions: {', '.join(target.next_valid_actions)}")
        return 0


def cmd_target_cleanup(args) -> int:
    result = cleanup_stale_targets(
        dry_run=args.dry_run, target_id=getattr(args, "target", None)
    )

    if args.format == "json":
        OutputFormatter.success("target.cleanup", data=result)
        return 0
    else:
        removed_count = len(result.get("removed", []))
        skipped_count = len(result.get("skipped", []))
        error_count = len(result.get("errors", []))

        if args.dry_run:
            print(
                f"Dry run: Would remove {removed_count} stale target(s)",
                file=sys.stderr,
            )
        else:
            print(f"Removed {removed_count} stale target(s)", file=sys.stderr)

        if skipped_count > 0:
            print(f"Skipped {skipped_count} target(s)", file=sys.stderr)

        if error_count > 0:
            print(f"Errors: {error_count}", file=sys.stderr)
            for error in result.get("errors", []):
                print(
                    f"  {error.get('target_id')}: {error.get('message')}",
                    file=sys.stderr,
                )

        return 0


def cmd_target_detach(args) -> int:
    result = detach_target(args.target, force=args.force)

    if not result.get("ok"):
        error_code = result.get("error_code", "TRANSPORT_ERROR")
        message = result.get("message", "Detach failed")

        if args.format == "json":
            OutputFormatter.error("target.detach", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)

        if error_code == "UNSUPPORTED_CAPABILITY" and not args.force:
            return 2
        return 1

    if args.format == "json":
        OutputFormatter.success("target.detach", data=result)
        return 0
    else:
        print(
            f"Successfully detached from target {result.get('target_id')}",
            file=sys.stderr,
        )
        if result.get("errors"):
            print("Warning: Some cleanup errors occurred:", file=sys.stderr)
            for error in result.get("errors", []):
                print(f"  {error.get('path')}: {error.get('message')}", file=sys.stderr)
        return 0


def cmd_session(args) -> int:
    if not args.session_action:
        OutputFormatter.error("session", error="Missing session subcommand")
        return 1

    try:
        if args.session_action == "list":
            return cmd_session_list(args)
        elif args.session_action == "status":
            return cmd_session_status(args)
        elif args.session_action == "detach":
            return cmd_session_detach(args)
        else:
            OutputFormatter.error(
                "session", error=f"Unknown session action: {args.session_action}"
            )
            return 1
    except Exception as e:
        OutputFormatter.error("session", error=str(e))
        return 1


def cmd_session_list(args) -> int:
    print(
        "[deprecated] 'peeka-cli session <X>' is deprecated; use 'peeka-cli target <X>'",
        file=sys.stderr,
    )
    return cmd_target_list(args)


def cmd_session_status(args) -> int:
    print(
        "[deprecated] 'peeka-cli session <X>' is deprecated; use 'peeka-cli target <X>'",
        file=sys.stderr,
    )
    return cmd_target_status(args)


def cmd_session_detach(args) -> int:
    print(
        "[deprecated] 'peeka-cli session <X>' is deprecated; use 'peeka-cli target <X>'",
        file=sys.stderr,
    )
    return cmd_target_detach(args)
