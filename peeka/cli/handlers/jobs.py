"""Command job CLI handlers."""

import json
import sys

from peeka.cli import command_runner as command_runner_module
from peeka.cli.command_runner import run_command
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
    return run_command(
        args,
        "job.list",
        build_command=_build_job_list_command,
        render_success=_render_job_list_success,
        render_error=_render_job_list_error,
    )


def cmd_job_status(args) -> int:
    return run_command(
        args,
        "job.status",
        build_command=lambda a: {
            "type": "job",
            "action": "status",
            "job_id": a.job,
        },
        render_success=_render_job_status_success,
        render_error=_render_job_status_error,
        error_exit_codes={"JOB_NOT_FOUND": 2},
    )


def cmd_job_inspect(args) -> int:
    return run_command(
        args,
        "job.inspect",
        build_command=lambda a: {
            "type": "job",
            "action": "inspect",
            "job_id": a.job,
        },
        render_success=_render_job_inspect_success,
        render_error=_render_job_inspect_error,
        error_exit_codes={"JOB_NOT_FOUND": 2},
    )


def cmd_job_interrupt(args) -> int:
    return run_command(
        args,
        "job.interrupt",
        build_command=lambda a: {
            "type": "job",
            "action": "interrupt",
            "job_id": a.job,
        },
        render_success=_render_job_interrupt_success,
        render_error=_render_job_interrupt_error,
        error_exit_codes={"UNSUPPORTED_CAPABILITY": 2, "JOB_NOT_FOUND": 2},
    )


def cmd_job_cleanup(args) -> int:
    return run_command(
        args,
        "job.cleanup",
        build_command=lambda a: _build_job_cleanup_command(a),
        render_success=_render_job_cleanup_success,
        render_error=_render_job_cleanup_error,
    )


def cmd_job_pull(args) -> int:
    original_connect = command_runner_module._connect_streaming_agent

    class _JobPullStubClient:
        def send_command(self, command):
            return {
                "status": "error",
                "error_code": "UNSUPPORTED_CAPABILITY",
                "message": "job pull is not yet implemented (see Phase 5 boulder result-consumer.md)",
            }

        def disconnect(self):
            pass

    try:
        command_runner_module._connect_streaming_agent = lambda command_name, target_id=None: _JobPullStubClient()
        return run_command(
            args,
            "job.pull",
            build_command=lambda a: {
                "type": "job",
                "action": "pull",
                "job_id": a.job,
                "consumer": a.consumer,
            },
            render_success=lambda a, r: None,
            render_error=_render_job_pull_error,
            error_exit_codes={"UNSUPPORTED_CAPABILITY": 2},
        )
    finally:
        command_runner_module._connect_streaming_agent = original_connect


def _build_job_list_command(args):
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
    return command


def _build_job_cleanup_command(args):
    command = {
        "type": "job",
        "action": "cleanup",
        "completed_only": args.completed,
        "older_than_seconds": args.older_than,
    }
    if args.target:
        command["target_id"] = args.target
    return command


def _render_job_list_success(args, response) -> None:
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
                type_action = f"{job.get('command_type', '-')}/{job.get('action', '-')}"
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


def _render_job_list_error(args, response, message, error_code) -> None:
    if args.format == "json":
        OutputFormatter.error("job.list", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_job_status_success(args, response) -> None:
    data = response.get("data", {})
    job = data.get("job", {})

    if args.format == "json":
        OutputFormatter.success("job.status", data=data)
    else:
        for key, value in job.items():
            print(f"{key:<20} {value}")


def _render_job_status_error(args, response, message, error_code) -> None:
    if args.format == "json":
        OutputFormatter.error("job.status", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_job_inspect_success(args, response) -> None:
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


def _render_job_inspect_error(args, response, message, error_code) -> None:
    if args.format == "json":
        OutputFormatter.error("job.inspect", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_job_interrupt_success(args, response) -> None:
    data = response.get("data", {})

    if args.format == "json":
        OutputFormatter.success("job.interrupt", data=data)
    else:
        job_id = data.get("job_id", args.job)
        new_status = data.get("status", "interrupted")
        print(f"Job {job_id} status: {new_status}", file=sys.stderr)


def _render_job_interrupt_error(args, response, message, error_code) -> None:
    if args.format == "json":
        OutputFormatter.error("job.interrupt", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_job_cleanup_success(args, response) -> None:
    data = response.get("data", {})
    removed = data.get("removed", [])

    if args.format == "json":
        OutputFormatter.success("job.cleanup", data=data)
    else:
        print(f"Removed {len(removed)} job(s)", file=sys.stderr)
        for job_id in removed:
            print(f"  {job_id}", file=sys.stderr)


def _render_job_cleanup_error(args, response, message, error_code) -> None:
    if args.format == "json":
        OutputFormatter.error("job.cleanup", error=message, error_code=error_code)
    else:
        print(f"{error_code}: {message}", file=sys.stderr)


def _render_job_pull_error(args, response, message, error_code) -> None:
    print(json.dumps(response))
