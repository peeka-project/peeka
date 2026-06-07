"""Result consumer CLI handlers."""

import json
import sys
from typing import Any, Dict

from peeka.cli.command_runner import run_command
from peeka.cli.responses import response_error_message as _response_error_message
from peeka.core.output import OutputFormatter


def cmd_consumer(args) -> int:
    if not args.consumer_action:
        OutputFormatter.error("consumer", error="Missing consumer subcommand")
        return 1

    try:
        if args.consumer_action == "create":
            return cmd_consumer_create(args)
        elif args.consumer_action == "list":
            return cmd_consumer_list(args)
        elif args.consumer_action == "status":
            return cmd_consumer_status(args)
        elif args.consumer_action == "drain":
            return cmd_consumer_drain(args)
        elif args.consumer_action == "close":
            return cmd_consumer_close(args)
        elif args.consumer_action == "cleanup":
            return cmd_consumer_cleanup(args)
        else:
            OutputFormatter.error(
                "consumer", error=f"Unknown consumer action: {args.consumer_action}"
            )
            return 1
    except Exception as e:
        OutputFormatter.error("consumer", error=str(e))
        return 1


def cmd_consumer_create(args) -> int:
    return run_command(
        args,
        "consumer.create",
        build_command=_build_consumer_create_command,
        render_success=_render_consumer_create_success,
        render_error=_render_consumer_create_error,
        error_exit_codes={"CLIENT_NOT_FOUND": 2, "UNSUPPORTED_CAPABILITY": 2},
    )


def cmd_consumer_list(args) -> int:
    return run_command(
        args,
        "consumer.list",
        build_command=_build_consumer_list_command,
        render_success=_render_consumer_list_success,
        render_error=_render_consumer_list_error,
    )


def cmd_consumer_status(args) -> int:
    return run_command(
        args,
        "consumer.status",
        build_command=_build_consumer_status_command,
        render_success=_render_consumer_status_success,
        render_error=_render_consumer_status_error,
        error_exit_codes={"CONSUMER_NOT_FOUND": 2},
    )


def cmd_consumer_drain(args) -> int:
    return run_command(
        args,
        "consumer.drain",
        build_command=_build_consumer_drain_command,
        render_success=_render_consumer_drain_success,
        render_error=_render_consumer_drain_error,
        error_exit_codes={
            "CONSUMER_NOT_FOUND": 2,
            "CONSUMER_CLOSED": 2,
            "CONSUMER_DRAIN_TIMEOUT": 2,
        },
    )


def cmd_consumer_close(args) -> int:
    return run_command(
        args,
        "consumer.close",
        build_command=_build_consumer_close_command,
        render_success=_render_consumer_close_success,
        render_error=_render_consumer_close_error,
        error_exit_codes={"CONSUMER_NOT_FOUND": 2},
    )


def cmd_consumer_cleanup(args) -> int:
    return run_command(
        args,
        "consumer.cleanup",
        build_command=_build_consumer_cleanup_command,
        render_success=_render_consumer_cleanup_success,
        render_error=_render_consumer_cleanup_error,
    )


def _build_consumer_create_command(args) -> Dict[str, Any]:
    return {
        "type": "consumer",
        "action": "create",
        "target_id": args.target,
        "source": args.source,
        "scope_type": args.scope_type,
        "scope_id": args.scope_id,
        "client_session_id": args.client,
        "max_buffer_size": args.max_buffer_size,
        "backpressure_policy": args.backpressure_policy,
    }


def _build_consumer_list_command(args) -> Dict[str, Any]:
    return {
        "type": "consumer",
        "action": "list",
        "target_id": getattr(args, "target", None),
        "client_session_id": getattr(args, "client", None),
        "scope_type": getattr(args, "scope_type", None),
        "scope_id": getattr(args, "scope_id", None),
        "status": getattr(args, "status", None),
    }


def _build_consumer_status_command(args) -> Dict[str, Any]:
    return {
        "type": "consumer",
        "action": "status",
        "consumer_id": args.consumer,
        "client_session_id": getattr(args, "client", None),
    }


def _build_consumer_drain_command(args) -> Dict[str, Any]:
    return {
        "type": "consumer",
        "action": "drain",
        "consumer_id": args.consumer,
        "limit": args.limit,
        "after_sequence": args.after_sequence,
        "timeout_ms": getattr(args, "timeout_ms", 0),
        "client_session_id": getattr(args, "client", None),
    }


def _build_consumer_close_command(args) -> Dict[str, Any]:
    return {
        "type": "consumer",
        "action": "close",
        "consumer_id": args.consumer,
        "client_session_id": getattr(args, "client", None),
    }


def _build_consumer_cleanup_command(args) -> Dict[str, Any]:
    return {
        "type": "consumer",
        "action": "cleanup",
        "closed_only": not args.all,
        "client_session_id": getattr(args, "client", None),
    }


def _render_consumer_create_success(args, response) -> None:
    data = response.get("data", {})
    if args.format == "json":
        OutputFormatter.success("consumer.create", data=data)
    else:
        print(f"Consumer created: {data.get('consumer_id')}", file=sys.stderr)
        print(
            f"Scope: {data.get('scope_type')} {data.get('scope_id')}",
            file=sys.stderr,
        )


def _render_consumer_create_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("consumer.create", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_consumer_list_success(args, response) -> None:
    consumers = response.get("data", {}).get("consumers", [])
    if args.format == "json":
        for consumer in consumers:
            OutputFormatter.event("consumer.discovered", data=consumer)
    else:
        if not consumers:
            print("No consumers found.", file=sys.stderr)
        else:
            print(
                f"{'CONSUMER_ID':<20} {'SCOPE':<28} {'STATUS':<12} {'BUFFER':<10} {'DROPPED':<8}"
            )
            print("-" * 86)
            for consumer in consumers:
                scope = f"{consumer.get('scope_type')}:{consumer.get('scope_id')}"
                print(
                    f"{consumer.get('consumer_id', '-'):<20} {scope:<28} {consumer.get('status', '-'):<12} "
                    f"{consumer.get('buffer_size', 0):<10} {consumer.get('dropped_count', 0):<8}"
                )


def _render_consumer_list_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("consumer.list", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_consumer_status_success(args, response) -> None:
    data = response.get("data", {})
    if args.format == "json":
        OutputFormatter.success("consumer.status", data=data)
    else:
        for key, value in data.items():
            print(f"{key:<20} {value}")


def _render_consumer_status_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("consumer.status", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_consumer_drain_success(args, response) -> None:
    data = response.get("data", {})
    records = data.get("records", [])
    if args.format == "json":
        OutputFormatter.success(
            "consumer.drain",
            data={
                "consumer_id": data.get("consumer_id"),
                "next_sequence": data.get("next_sequence"),
                "has_more": data.get("has_more"),
                "timed_out": data.get("timed_out"),
            },
        )
        for record in records:
            print(json.dumps(record))
    else:
        print(
            f"Consumer {data.get('consumer_id')} returned {len(records)} record(s); has_more={data.get('has_more')}",
            file=sys.stderr,
        )
        for record in records:
            print(json.dumps(record))


def _render_consumer_drain_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("consumer.drain", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_consumer_close_success(args, response) -> None:
    data = response.get("data", {})
    if args.format == "json":
        OutputFormatter.success("consumer.close", data=data)
    else:
        print(f"Consumer closed: {args.consumer}", file=sys.stderr)


def _render_consumer_close_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("consumer.close", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_consumer_cleanup_success(args, response) -> None:
    data = response.get("data", {})
    removed_ids = data.get("removed_ids", [])
    if args.format == "json":
        OutputFormatter.success("consumer.cleanup", data=data)
    else:
        print(f"Removed {len(removed_ids)} consumer(s)", file=sys.stderr)
        for consumer_id in removed_ids:
            print(f"  {consumer_id}", file=sys.stderr)


def _render_consumer_cleanup_error(args, response, message, error_code) -> None:
    message = _response_error_message(response, message)
    if args.format == "json":
        OutputFormatter.error("consumer.cleanup", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
