"""Probe lifecycle CLI handlers."""

import json
import sys

from peeka.cli.context import _connect_streaming_agent
from peeka.cli.responses import response_error_message as _response_error_message
from peeka.core.output import OutputFormatter


def cmd_probe(args) -> int:
    if not args.probe_action:
        OutputFormatter.error("probe", error="Missing probe subcommand")
        return 1

    try:
        if args.probe_action == "list":
            return cmd_probe_list(args)
        elif args.probe_action == "status":
            return cmd_probe_status(args)
        elif args.probe_action == "inspect":
            return cmd_probe_inspect(args)
        elif args.probe_action == "stop":
            return cmd_probe_stop(args)
        elif args.probe_action == "cleanup":
            return cmd_probe_cleanup(args)
        else:
            OutputFormatter.error(
                "probe", error=f"Unknown probe action: {args.probe_action}"
            )
            return 1
    except Exception as e:
        OutputFormatter.error("probe", error=str(e))
        return 1


def cmd_probe_list(args) -> int:
    streaming_client = _connect_streaming_agent("probe.list", args.target)
    if streaming_client is None:
        return 1

    command = {
        "type": "probe",
        "action": "list",
    }
    if args.target:
        command["target_id"] = args.target
    if args.probe_type:
        command["probe_type"] = args.probe_type
    if args.status:
        command["status"] = args.status

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        probes = data.get("probes", [])

        if args.format == "json":
            for probe in probes:
                print(json.dumps(probe))
        else:
            if not probes:
                print("No probes found.", file=sys.stderr)
            else:
                print(
                    f"{'PROBE_ID':<15} {'TYPE':<15} {'STATUS':<12} {'JOB_ID':<15} {'CREATED':<20} {'EVENTS':<8}"
                )
                print("-" * 90)
                for probe in probes:
                    probe_id = probe.get("id", "-")
                    probe_type = probe.get("type", "-")
                    status = probe.get("status", "-")
                    job_id = probe.get("job_id", "-")
                    created_at = probe.get("created_at", 0)
                    event_count = probe.get("event_count", 0)
                    import datetime

                    created_str = (
                        datetime.datetime.fromtimestamp(created_at).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if created_at
                        else "-"
                    )
                    print(
                        f"{probe_id:<15} {probe_type:<15} {status:<12} {job_id:<15} {created_str:<20} {event_count:<8}"
                    )
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = _response_error_message(response, "Probe list failed")
        if args.format == "json":
            OutputFormatter.error("probe.list", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 1


def cmd_probe_status(args) -> int:
    streaming_client = _connect_streaming_agent("probe.status")
    if streaming_client is None:
        return 1

    command = {
        "type": "probe",
        "action": "status",
        "probe_id": args.probe,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        probe = data.get("probe", {})

        if args.format == "json":
            OutputFormatter.success("probe.status", data=data)
        else:
            for key, value in probe.items():
                print(f"{key:<20} {value}")
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = _response_error_message(response, "Probe status query failed")
        if args.format == "json":
            OutputFormatter.error("probe.status", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "PROBE_NOT_FOUND" else 1


def cmd_probe_inspect(args) -> int:
    streaming_client = _connect_streaming_agent("probe.inspect")
    if streaming_client is None:
        return 1

    command = {
        "type": "probe",
        "action": "inspect",
        "probe_id": args.probe,
        "events_limit": args.events,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        probe = data.get("probe", {})
        events = data.get("events", [])

        if args.format == "json":
            OutputFormatter.success("probe.inspect", data={"probe": probe})
            for event in events:
                print(json.dumps(event))
        else:
            print("=== Probe Details ===")
            for key, value in probe.items():
                print(f"{key:<20} {value}")
            print("\n=== Recent Events ===")
            for event in events:
                event_id = event.get("event_id", "-")
                timestamp = event.get("timestamp", 0)
                payload = event.get("payload", {})
                import datetime

                ts_str = (
                    datetime.datetime.fromtimestamp(timestamp).strftime(
                        "%Y-%m-%d %H:%M:%S.%f"
                    )[:-3]
                    if timestamp
                    else "-"
                )
                print(f"{event_id:<20} {ts_str:<25} {json.dumps(payload)}")
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = _response_error_message(response, "Probe inspect query failed")
        if args.format == "json":
            OutputFormatter.error("probe.inspect", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "PROBE_NOT_FOUND" else 1


def cmd_probe_stop(args) -> int:
    streaming_client = _connect_streaming_agent("probe.stop")
    if streaming_client is None:
        return 1

    command = {
        "type": "probe",
        "action": "stop",
        "probe_id": args.probe,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})

        if args.format == "json":
            OutputFormatter.success("probe.stop", data=data)
        else:
            probe_id = data.get("probe_id", args.probe)
            new_status = data.get("status", "stopped")
            print(f"Probe {probe_id} status: {new_status}", file=sys.stderr)
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = _response_error_message(response, "Probe stop failed")
        if args.format == "json":
            OutputFormatter.error("probe.stop", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "PROBE_NOT_FOUND" else 1


def cmd_probe_cleanup(args) -> int:
    streaming_client = _connect_streaming_agent("probe.cleanup", args.target)
    if streaming_client is None:
        return 1

    command = {
        "type": "probe",
        "action": "cleanup",
        "completed_only": not args.all,
        "older_than_seconds": args.older_than,
    }
    if args.target:
        command["target_id"] = args.target

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        removed_ids = data.get("removed_ids", [])

        if args.format == "json":
            OutputFormatter.success("probe.cleanup", data=data)
        else:
            print(f"Removed {len(removed_ids)} probe(s)", file=sys.stderr)
            if removed_ids:
                for probe_id in removed_ids:
                    print(f"  {probe_id}", file=sys.stderr)
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = _response_error_message(response, "Probe cleanup failed")
        if args.format == "json":
            OutputFormatter.error("probe.cleanup", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 1
