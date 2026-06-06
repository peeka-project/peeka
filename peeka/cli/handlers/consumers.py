"""Result consumer CLI handlers."""

import json
import sys

from peeka.cli.context import _connect_streaming_agent
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
    streaming_client = _connect_streaming_agent("consumer.create", args.target)
    if streaming_client is None:
        return 1

    command = {
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
    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("consumer.create", data=data)
        else:
            print(f"Consumer created: {data.get('consumer_id')}", file=sys.stderr)
            print(
                f"Scope: {data.get('scope_type')} {data.get('scope_id')}",
                file=sys.stderr,
            )
        return 0

    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "Consumer create failed")
    if args.format == "json":
        OutputFormatter.error("consumer.create", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return 2 if error_code in ("CLIENT_NOT_FOUND", "UNSUPPORTED_CAPABILITY") else 1


def cmd_consumer_list(args) -> int:
    streaming_client = _connect_streaming_agent("consumer.list", args.target)
    if streaming_client is None:
        return 1

    command = {
        "type": "consumer",
        "action": "list",
        "target_id": args.target,
        "client_session_id": args.client,
        "scope_type": args.scope_type,
        "scope_id": args.scope_id,
        "status": args.status,
    }
    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
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
        return 0

    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "Consumer list failed")
    if args.format == "json":
        OutputFormatter.error("consumer.list", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return 1


def cmd_consumer_status(args) -> int:
    streaming_client = _connect_streaming_agent("consumer.status")
    if streaming_client is None:
        return 1

    response = streaming_client.send_command(
        {
            "type": "consumer",
            "action": "status",
            "consumer_id": args.consumer,
            "client_session_id": getattr(args, "client", None),
        }
    )
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("consumer.status", data=data)
        else:
            for key, value in data.items():
                print(f"{key:<20} {value}")
        return 0

    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "Consumer status query failed")
    if args.format == "json":
        OutputFormatter.error("consumer.status", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return 2 if error_code == "CONSUMER_NOT_FOUND" else 1


def cmd_consumer_drain(args) -> int:
    streaming_client = _connect_streaming_agent("consumer.drain")
    if streaming_client is None:
        return 1

    command = {
        "type": "consumer",
        "action": "drain",
        "consumer_id": args.consumer,
        "limit": args.limit,
        "after_sequence": args.after_sequence,
        "timeout_ms": getattr(args, "timeout_ms", 0),
        "client_session_id": getattr(args, "client", None),
    }
    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
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
        return 0

    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "Consumer drain failed")
    if args.format == "json":
        OutputFormatter.error("consumer.drain", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return (
        2
        if error_code
        in ("CONSUMER_NOT_FOUND", "CONSUMER_CLOSED", "CONSUMER_DRAIN_TIMEOUT")
        else 1
    )


def cmd_consumer_close(args) -> int:
    streaming_client = _connect_streaming_agent("consumer.close")
    if streaming_client is None:
        return 1

    response = streaming_client.send_command(
        {
            "type": "consumer",
            "action": "close",
            "consumer_id": args.consumer,
            "client_session_id": getattr(args, "client", None),
        }
    )
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        if args.format == "json":
            OutputFormatter.success("consumer.close", data=data)
        else:
            print(f"Consumer closed: {args.consumer}", file=sys.stderr)
        return 0

    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "Consumer close failed")
    if args.format == "json":
        OutputFormatter.error("consumer.close", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return 2 if error_code == "CONSUMER_NOT_FOUND" else 1


def cmd_consumer_cleanup(args) -> int:
    streaming_client = _connect_streaming_agent("consumer.cleanup")
    if streaming_client is None:
        return 1

    response = streaming_client.send_command(
        {
            "type": "consumer",
            "action": "cleanup",
            "closed_only": not args.all,
            "client_session_id": getattr(args, "client", None),
        }
    )
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        removed_ids = data.get("removed_ids", [])
        if args.format == "json":
            OutputFormatter.success("consumer.cleanup", data=data)
        else:
            print(f"Removed {len(removed_ids)} consumer(s)", file=sys.stderr)
            for consumer_id in removed_ids:
                print(f"  {consumer_id}", file=sys.stderr)
        return 0

    error_code = response.get("error_code", "TRANSPORT_ERROR")
    message = _response_error_message(response, "Consumer cleanup failed")
    if args.format == "json":
        OutputFormatter.error("consumer.cleanup", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)
    return 1
