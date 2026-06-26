"""Registry for streaming observation CLI commands."""

from dataclasses import dataclass
from typing import Any, Dict, Optional

from peeka.cli.streaming import CommandBuilder, StartEmitter, StopCommandBuilder
from peeka.core.output import OutputFormatter


@dataclass
class StreamingCommandConfig:
    """Configuration for a streaming CLI command."""

    command_type: str
    limit_attr: str
    stream_id_key: str
    response_id_key: str
    command_builder: CommandBuilder
    stop_command_builder: StopCommandBuilder
    emit_started: StartEmitter
    allow_explicit_client: bool = False
    exception_status: int = 1


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


def _trace_command(args: Any, client_session_id: str) -> Dict[str, Any]:
    return {
        "type": "trace",
        "action": "start",
        "client_session_id": client_session_id,
        "pattern": args.pattern,
        "times": -1,
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


def _stack_command(args: Any, client_session_id: str) -> Dict[str, Any]:
    return {
        "type": "stack",
        "action": "start",
        "client_session_id": client_session_id,
        "pattern": args.pattern,
        "depth": args.depth,
        "times": -1,
        "condition_express": args.condition_express,
    }


def _emit_stack_started(
    args: Any, response: Dict[str, Any], stream_id: Optional[str]
) -> None:
    OutputFormatter.event(
        "stack_started", data={"stack_id": stream_id, "pattern": args.pattern}
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


STREAMING_COMMANDS: Dict[str, StreamingCommandConfig] = {
    "watch": StreamingCommandConfig(
        command_type="watch",
        limit_attr="times",
        stream_id_key="watch_id",
        response_id_key="watch_id",
        command_builder=_watch_command,
        stop_command_builder=lambda stream_id: {
            "type": "watch",
            "action": "stop",
            "watch_id": stream_id,
        },
        emit_started=_emit_watch_started,
        allow_explicit_client=True,
    ),
    "trace": StreamingCommandConfig(
        command_type="trace",
        limit_attr="times",
        stream_id_key="watch_id",
        response_id_key="watch_id",
        command_builder=_trace_command,
        stop_command_builder=lambda stream_id: {
            "type": "trace",
            "action": "stop",
            "watch_id": stream_id,
        },
        emit_started=_emit_trace_started,
        allow_explicit_client=True,
    ),
    "stack": StreamingCommandConfig(
        command_type="stack",
        limit_attr="times",
        stream_id_key="watch_id",
        response_id_key="watch_id",
        command_builder=_stack_command,
        stop_command_builder=lambda stream_id: {
            "type": "stack",
            "action": "stop",
            "watch_id": stream_id,
        },
        emit_started=_emit_stack_started,
        exception_status=0,
    ),
    "monitor": StreamingCommandConfig(
        command_type="monitor",
        limit_attr="cycles",
        stream_id_key="monitor_id",
        response_id_key="monitor_id",
        command_builder=_monitor_command,
        stop_command_builder=lambda stream_id: {
            "type": "monitor",
            "action": "stop",
            "monitor_id": stream_id,
        },
        emit_started=_emit_monitor_started,
    ),
    "top": StreamingCommandConfig(
        command_type="top",
        limit_attr="cycles",
        stream_id_key="top_id",
        response_id_key="top_id",
        command_builder=_top_command,
        stop_command_builder=lambda stream_id: {"type": "top", "action": "stop"},
        emit_started=_emit_top_started,
    ),
}
