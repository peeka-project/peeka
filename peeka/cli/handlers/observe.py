"""Streaming observation CLI handlers."""

from typing import Any, Callable, Dict, Optional

from peeka.cli._client_helper import ephemeral_client
from peeka.cli.connection import _socket_path_to_target_id
from peeka.cli.sessions import _check_agent_attached
from peeka.cli.streaming_config import STREAMING_COMMANDS
from peeka.cli.streaming_config import StreamingCommandConfig
from peeka.cli.streaming_config import _emit_monitor_started
from peeka.cli.streaming_config import _emit_stack_started
from peeka.cli.streaming_config import _emit_top_started
from peeka.cli.streaming_config import _emit_trace_started
from peeka.cli.streaming_config import _emit_watch_started
from peeka.cli.streaming_config import _monitor_command
from peeka.cli.streaming_config import _stack_command
from peeka.cli.streaming_config import _top_command
from peeka.cli.streaming_config import _trace_command
from peeka.cli.streaming_config import _watch_command
from peeka.cli.streaming import LimitPredicate
from peeka.cli.streaming import run_streaming_command
from peeka.cli.streaming import stream_counted_limit
from peeka.core.client import StreamingAgentClient
from peeka.core.output import OutputFormatter

__all__ = [
    "_emit_monitor_started",
    "_emit_stack_started",
    "_emit_top_started",
    "_emit_trace_started",
    "_emit_watch_started",
    "_monitor_command",
    "_stack_command",
    "_top_command",
    "_trace_command",
    "_watch_command",
    "cmd_monitor",
    "cmd_stack",
    "cmd_top",
    "cmd_trace",
    "cmd_watch",
]


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
        exception_status=exception_status,
    )


def _emit_with_stream_id(
    config: StreamingCommandConfig,
    set_stream_id: Callable[[Optional[str]], None],
):
    def _emit_started_with_id(
        args: Any, response: Dict[str, Any], stream_id: Optional[str]
    ) -> None:
        set_stream_id(stream_id)
        config.emit_started(args, response, stream_id)

    return _emit_started_with_id


def _run_configured_streaming_command(
    args: Any, config: StreamingCommandConfig
) -> int:
    limit_predicate, set_stream_id = stream_counted_limit(
        config.limit_attr, config.stream_id_key
    )
    return _run_streaming_command(
        args,
        command_name=config.command_type,
        start_error=f"{config.command_type.capitalize()} start failed",
        command_builder=config.command_builder,
        response_id_key=config.response_id_key,
        stop_command_builder=config.stop_command_builder,
        emit_started=_emit_with_stream_id(config, set_stream_id),
        limit_reached=limit_predicate,
        allow_explicit_client=config.allow_explicit_client,
        exception_status=config.exception_status,
    )


def cmd_watch(args) -> int:
    return _run_configured_streaming_command(args, STREAMING_COMMANDS["watch"])


def cmd_trace(args) -> int:
    return _run_configured_streaming_command(args, STREAMING_COMMANDS["trace"])


def cmd_stack(args) -> int:
    return _run_configured_streaming_command(args, STREAMING_COMMANDS["stack"])


def cmd_monitor(args) -> int:
    return _run_configured_streaming_command(args, STREAMING_COMMANDS["monitor"])


def cmd_top(args) -> int:
    return _run_configured_streaming_command(args, STREAMING_COMMANDS["top"])
