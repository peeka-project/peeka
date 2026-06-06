"""Command job CLI handlers."""

import json
import sys

from peeka.cli.context import _connect_streaming_agent
from peeka.core.output import OutputFormatter


def cmd_job(args) -> int:
    if not args.job_action:
        OutputFormatter.error("job", error="Missing job subcommand")
        return 1

    try:
        if args.job_action == "list":
            return cmd_job_list(args)
        elif args.job_action == "status":
            return cmd_job_status(args)
        elif args.job_action == "inspect":
            return cmd_job_inspect(args)
        elif args.job_action == "interrupt":
            return cmd_job_interrupt(args)
        elif args.job_action == "cleanup":
            return cmd_job_cleanup(args)
        elif args.job_action == "pull":
            return cmd_job_pull(args)
        else:
            OutputFormatter.error("job", error=f"Unknown job action: {args.job_action}")
            return 1
    except Exception as e:
        OutputFormatter.error("job", error=str(e))
        return 1


def cmd_job_list(args) -> int:
    streaming_client = _connect_streaming_agent("job.list", args.target)
    if streaming_client is None:
        return 1

    command = {
        "type": "job",
        "action": "list",
    }
    if args.target:
        command["target_id"] = args.target
    if args.client:
        command["client_session_id"] = args.client
    if args.status:
        command["status"] = args.status

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        jobs = data.get("jobs", [])

        if args.format == "json":
            for job in jobs:
                print(json.dumps(job))
        else:
            if not jobs:
                print("No jobs found.", file=sys.stderr)
            else:
                print(
                    f"{'JOB_ID':<15} {'TARGET':<20} {'CLIENT':<20} {'TYPE/ACTION':<25} {'STATUS':<12} {'CATEGORY':<10} {'UPDATED':<20}"
                )
                print("-" * 142)
                for job in jobs:
                    job_id = job.get("id", "-")
                    target_id = job.get("target_id", "-")
                    client_id = job.get("client_session_id", "-")
                    type_action = (
                        f"{job.get('command_type', '-')}/{job.get('action', '-')}"
                    )
                    status = job.get("status", "-")
                    category = job.get("category", "-")
                    updated_at = job.get("updated_at", 0)
                    import datetime

                    updated_str = (
                        datetime.datetime.fromtimestamp(updated_at).strftime(
                            "%Y-%m-%d %H:%M:%S"
                        )
                        if updated_at
                        else "-"
                    )
                    print(
                        f"{job_id:<15} {target_id:<20} {client_id:<20} {type_action:<25} {status:<12} {category:<10} {updated_str:<20}"
                    )
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Job list failed")
        if args.format == "json":
            OutputFormatter.error("job.list", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 1


def cmd_job_status(args) -> int:
    streaming_client = _connect_streaming_agent("job.status")
    if streaming_client is None:
        return 1

    command = {
        "type": "job",
        "action": "status",
        "job_id": args.job,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        job = data.get("job", {})

        if args.format == "json":
            OutputFormatter.success("job.status", data=data)
        else:
            for key, value in job.items():
                print(f"{key:<20} {value}")
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Job status query failed")
        if args.format == "json":
            OutputFormatter.error("job.status", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "JOB_NOT_FOUND" else 1


def cmd_job_inspect(args) -> int:
    streaming_client = _connect_streaming_agent("job.inspect")
    if streaming_client is None:
        return 1

    command = {
        "type": "job",
        "action": "inspect",
        "job_id": args.job,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        job = data.get("job", {})

        if args.format == "json":
            OutputFormatter.success("job.inspect", data=data)
        else:
            for key, value in job.items():
                if isinstance(value, dict):
                    print(f"{key:<20}")
                    for k, v in value.items():
                        print(f"  {k:<18} {v}")
                else:
                    print(f"{key:<20} {value}")
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Job inspect query failed")
        if args.format == "json":
            OutputFormatter.error("job.inspect", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code == "JOB_NOT_FOUND" else 1


def cmd_job_interrupt(args) -> int:
    streaming_client = _connect_streaming_agent("job.interrupt")
    if streaming_client is None:
        return 1

    command = {
        "type": "job",
        "action": "interrupt",
        "job_id": args.job,
    }

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})

        if args.format == "json":
            OutputFormatter.success("job.interrupt", data=data)
        else:
            job_id = data.get("job_id", args.job)
            new_status = data.get("status", "interrupted")
            print(f"Job {job_id} status: {new_status}", file=sys.stderr)
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Job interrupt failed")
        if args.format == "json":
            OutputFormatter.error("job.interrupt", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 2 if error_code in ("UNSUPPORTED_CAPABILITY", "JOB_NOT_FOUND") else 1


def cmd_job_cleanup(args) -> int:
    streaming_client = _connect_streaming_agent("job.cleanup", args.target)
    if streaming_client is None:
        return 1

    command = {
        "type": "job",
        "action": "cleanup",
        "completed_only": args.completed,
        "older_than_seconds": args.older_than,
    }
    if args.target:
        command["target_id"] = args.target

    response = streaming_client.send_command(command)
    streaming_client.disconnect()

    if response.get("status") == "success":
        data = response.get("data", {})
        removed = data.get("removed", [])

        if args.format == "json":
            OutputFormatter.success("job.cleanup", data=data)
        else:
            print(f"Removed {len(removed)} job(s)", file=sys.stderr)
            for job_id in removed:
                print(f"  {job_id}", file=sys.stderr)
        return 0
    else:
        error_code = response.get("error_code", "TRANSPORT_ERROR")
        message = response.get("message", "Job cleanup failed")
        if args.format == "json":
            OutputFormatter.error("job.cleanup", error=message, error_code=error_code)
        else:
            print(f"{error_code}: {message}", file=sys.stderr)
        return 1


def cmd_job_pull(args) -> int:
    error_payload = {
        "status": "error",
        "error_code": "UNSUPPORTED_CAPABILITY",
        "message": "job pull is not yet implemented (see Phase 5 boulder result-consumer.md)",
    }
    print(json.dumps(error_payload))
    return 2
