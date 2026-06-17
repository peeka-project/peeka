"""Reusable streaming CLI command runner."""

import json
import signal
import sys
from contextlib import nullcontext
from typing import Any, Callable, ContextManager, Dict, Optional, Tuple

from peeka.core.output import OutputFormatter

CommandBuilder = Callable[[Any, str], Dict[str, Any]]
StopCommandBuilder = Callable[[Optional[str]], Optional[Dict[str, Any]]]
StartEmitter = Callable[[Any, Dict[str, Any], Optional[str]], None]
LimitPredicate = Callable[[Any, Dict[str, Any]], bool]
CheckAttached = Callable[[], Tuple[str, int]]
ClientFactory = Callable[[str], Any]
EphemeralClientFactory = Callable[[str], ContextManager[str]]
TargetIdResolver = Callable[[str], str]


def counted_limit(attr_name: str) -> LimitPredicate:
    """Return a predicate that stops after a local emitted-observation count."""
    emitted = {"count": 0}

    def reached(args: Any, observation: Dict[str, Any]) -> bool:
        limit = int(getattr(args, attr_name, -1))
        if limit <= 0:
            return False
        emitted["count"] += 1
        return emitted["count"] >= limit

    return reached


def stream_counted_limit(attr_name: str, stream_id_key: str) -> "Tuple[LimitPredicate, Callable[[Optional[str]], None]]":
    """Return a (predicate, set_stream_id) pair for stream-filtered local counting.

    The predicate only increments when observation[stream_id_key] matches the
    active stream id. Call set_stream_id(stream_id) from emit_started before
    the streaming loop begins.

    If set_stream_id is never called or the stream id key is absent from an
    observation, the observation is not counted toward the limit.
    """
    emitted = {"count": 0}
    holder: Dict[str, Optional[str]] = {"stream_id": None}

    def set_stream_id(stream_id: Optional[str]) -> None:
        holder["stream_id"] = stream_id

    def reached(args: Any, observation: Dict[str, Any]) -> bool:
        limit = int(getattr(args, attr_name, -1))
        if limit <= 0:
            return False
        expected = holder["stream_id"]
        if expected is None:
            return False
        if observation.get(stream_id_key) != expected:
            return False
        emitted["count"] += 1
        return emitted["count"] >= limit

    return reached, set_stream_id


def observation_count_limit(args: Any, observation: Dict[str, Any]) -> bool:
    """Stop when the agent-reported observation count reaches args.times."""
    times = int(getattr(args, "times", -1))
    return times > 0 and int(observation.get("count", 0)) >= times


def _client_session_context(
    socket_path: str,
    args: Any,
    allow_explicit_client: bool,
    ephemeral_client_factory: EphemeralClientFactory,
    target_id_resolver: TargetIdResolver,
) -> ContextManager[str]:
    explicit_client = getattr(args, "client", None) if allow_explicit_client else None
    if explicit_client:
        return nullcontext(str(explicit_client))

    target_id = target_id_resolver(socket_path)
    return ephemeral_client_factory(target_id)


def _cleanup_stream(
    client: Optional[Any],
    stream_id: Optional[str],
    stop_command_builder: StopCommandBuilder,
) -> None:
    if client is None:
        return

    try:
        if stream_id:
            stop_command = stop_command_builder(stream_id)
            if stop_command:
                client.send_command(stop_command)
    except Exception:
        pass
    finally:
        client.disconnect()


def run_streaming_command(
    args: Any,
    command_name: str,
    start_error: str,
    command_builder: CommandBuilder,
    response_id_key: str,
    stop_command_builder: StopCommandBuilder,
    emit_started: StartEmitter,
    limit_reached: LimitPredicate,
    *,
    check_agent_attached: CheckAttached,
    client_factory: ClientFactory,
    ephemeral_client_factory: EphemeralClientFactory,
    target_id_resolver: TargetIdResolver,
    output_formatter: Any = OutputFormatter,
    allow_explicit_client: bool = False,
    exception_status: int = 1,
) -> int:
    """Run a start/stream/cleanup CLI command against the attached agent."""
    try:
        socket_path, _ = check_agent_attached()
    except ValueError as e:
        output_formatter.error(command_name, error=str(e))
        return 1

    streaming_client: Optional[Any] = None
    stream_id: Optional[str] = None

    def cleanup(signum=None, frame=None):
        _cleanup_stream(
            streaming_client,
            stream_id,
            stop_command_builder,
        )
        if signum is not None:
            sys.exit(130)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    streaming_client = client_factory(socket_path)
    assert streaming_client is not None
    connect_result = streaming_client.connect()
    if connect_result.get("status") != "success":
        output_formatter.error(
            command_name, error=connect_result.get("error", "Connection failed")
        )
        return 1

    try:
        with _client_session_context(
            socket_path,
            args,
            allow_explicit_client,
            ephemeral_client_factory,
            target_id_resolver,
        ) as client_session_id:
            client = streaming_client
            command = command_builder(args, client_session_id)
            response = client.send_command(command)
            if response.get("status") != "success":
                output_formatter.error(
                    command_name, error=response.get("error", start_error)
                )
                client.disconnect()
                streaming_client = None
                return 1

            stream_id = response.get(response_id_key)
            emit_started(args, response, stream_id)
            sys.stdout.flush()

            try:
                for observation in client.stream_observations():
                    print(json.dumps(observation))
                    sys.stdout.flush()
                    if limit_reached(args, observation):
                        break
            finally:
                cleanup()

            return 0
    except Exception as e:
        output_formatter.error(command_name, error=str(e))
        cleanup()
        return exception_status
