"""Streaming observation CLI handlers."""

from typing import Any, Dict, Optional

from peeka.cli._client_helper import ephemeral_client
from peeka.cli.connection import _socket_path_to_target_id
from peeka.cli.sessions import _check_agent_attached
from peeka.cli.streaming import LimitPredicate
from peeka.cli.streaming import counted_limit
from peeka.cli.streaming import observation_count_limit
from peeka.cli.streaming import run_streaming_command
from peeka.core.client import StreamingAgentClient
from peeka.core.output import OutputFormatter


def _run_streaming_command(
    args: Any,
    command_name: str,
    start_error: str,
    command_builder,
    response_id_key: str,
    stop_command_builder,
    emit_started,
    limit_reached: LimitPredicate,
    allow_explicit_client: bool = False,
    reset_pattern: bool = True,
    exception_status: int = 1,
) -> int:
    return run_streaming_command(
        args,
        command_name,
        start_error,
        command_builder,
        response_id_key,
        stop_command_builder,
        emit_started,
        limit_reached,
        check_agent_attached=_check_agent_attached,
        client_factory=StreamingAgentClient,
        ephemeral_client_factory=ephemeral_client,
        target_id_resolver=_socket_path_to_target_id,
        output_formatter=OutputFormatter,
        allow_explicit_client=allow_explicit_client,
        reset_pattern=reset_pattern,
        exception_status=exception_status,
    )


def _watch_command(args: Any, client_session_id: str) -> Dict[str, Any]:
    return {
        "type": "watch",
        "action": "start",
        "client_session_id": client_session_id,
        "pattern": args.pattern,
        "depth": args.depth,
        "times": args.times,
        "before": args.before,
        "exception": args.exception,
        "success": args.success,
        "finish": args.finish,
        "condition_express": args.condition_express,
    }


def _emit_watch_started(
    args: Any, response: Dict[str, Any], stream_id: Optional[str]
) -> None:
    start_data = {"watch_id": stream_id, "pattern": args.pattern}
    target_info = response.get("target")
    if target_info:
        start_data["target"] = target_info
    OutputFormatter.event(
        "watch_started",
        data=start_data,
        meta=response.get("runtime_meta"),
    )


def cmd_watch(args) -> int:
    return _run_streaming_command(
        args,
        command_name="watch",
        start_error="Watch start failed",
        command_builder=_watch_command,
        response_id_key="watch_id",
        stop_command_builder=lambda stream_id: {
            "type": "watch",
            "action": "stop",
            "watch_id": stream_id,
        },
        emit_started=_emit_watch_started,
        limit_reached=counted_limit("times"),
        allow_explicit_client=True,
    )


def _trace_command(args: Any, client_session_id: str) -> Dict[str, Any]:
    return {
        "type": "trace",
        "action": "start",
        "client_session_id": client_session_id,
        "pattern": args.pattern,
        "depth": args.depth,
        "times": args.times,
        "condition_express": args.condition_express,
        "skip_builtin": args.skip_builtin,
        "min_duration": args.min_duration,
    }


def _emit_trace_started(
    args: Any, response: Dict[str, Any], stream_id: Optional[str]
) -> None:
    OutputFormatter.event(
        "trace_started",
        data={"trace_id": stream_id, "pattern": args.pattern},
        meta=response.get("meta"),
    )


def cmd_trace(args) -> int:
    return _run_streaming_command(
        args,
        command_name="trace",
        start_error="Trace start failed",
        command_builder=_trace_command,
        response_id_key="watch_id",
        stop_command_builder=lambda stream_id: {
            "type": "trace",
            "action": "stop",
            "watch_id": stream_id,
        },
        emit_started=_emit_trace_started,
        limit_reached=counted_limit("times"),
        allow_explicit_client=True,
    )


def _stack_command(args: Any, client_session_id: str) -> Dict[str, Any]:
    return {
        "type": "stack",
        "action": "start",
        "client_session_id": client_session_id,
        "pattern": args.pattern,
        "depth": args.depth,
        "times": args.times,
        "condition_express": args.condition_express,
    }


def _emit_stack_started(
    args: Any, response: Dict[str, Any], stream_id: Optional[str]
) -> None:
    OutputFormatter.event(
        "stack_started", data={"stack_id": stream_id, "pattern": args.pattern}
    )


def cmd_stack(args) -> int:
    return _run_streaming_command(
        args,
        command_name="stack",
        start_error="Stack start failed",
        command_builder=_stack_command,
        response_id_key="stack_id",
        stop_command_builder=lambda stream_id: {
            "type": "stack",
            "action": "stop",
            "stack_id": stream_id,
        },
        emit_started=_emit_stack_started,
        limit_reached=observation_count_limit,
        exception_status=0,
    )


def _monitor_command(args: Any, client_session_id: str) -> Dict[str, Any]:
    return {
        "type": "monitor",
        "action": "start",
        "client_session_id": client_session_id,
        "pattern": args.pattern,
        "cycle": args.interval,
        "cycles": args.cycles,
    }


def _emit_monitor_started(
    args: Any, response: Dict[str, Any], stream_id: Optional[str]
) -> None:
    OutputFormatter.event(
        "monitor_started", data={"monitor_id": stream_id, "pattern": args.pattern}
    )


def cmd_monitor(args) -> int:
    return _run_streaming_command(
        args,
        command_name="monitor",
        start_error="Monitor start failed",
        command_builder=_monitor_command,
        response_id_key="monitor_id",
        stop_command_builder=lambda stream_id: {
            "type": "monitor",
            "action": "stop",
            "monitor_id": stream_id,
        },
        emit_started=_emit_monitor_started,
        limit_reached=counted_limit("cycles"),
    )


def _top_command(args: Any, client_session_id: str) -> Dict[str, Any]:
    return {
        "type": "top",
        "action": "start",
        "client_session_id": client_session_id,
        "interval": args.interval,
        "stream": True,
        "filter_peeka": not args.no_filter_peeka,
    }


def _emit_top_started(
    args: Any, response: Dict[str, Any], stream_id: Optional[str]
) -> None:
    OutputFormatter.event(
        "top_started",
        data={
            "top_id": stream_id,
            "interval": args.interval,
            "filter_peeka": not args.no_filter_peeka,
        },
        meta=response.get("meta"),
    )


def cmd_top(args) -> int:
    return _run_streaming_command(
        args,
        command_name="top",
        start_error="Top start failed",
        command_builder=_top_command,
        response_id_key="top_id",
        stop_command_builder=lambda stream_id: {"type": "top", "action": "stop"},
        emit_started=_emit_top_started,
        limit_reached=counted_limit("cycles"),
        reset_pattern=False,
    )
