"""Backward-compatible CLI helper re-exports."""

from pathlib import Path

from peeka.cli.connection import StreamingAgentClient
from peeka.cli.connection import TargetResolutionError
from peeka.cli.connection import _check_agent_for_target
from peeka.cli.connection import _connect_streaming_agent
from peeka.cli.connection import _socket_path_to_target_id
from peeka.cli.connection import get_target
from peeka.cli.parsers.types import _parse_duration
from peeka.cli.sessions import _check_agent_attached
from peeka.cli.sessions import _find_active_session
from peeka.cli.targets import _find_pid_by_name
from peeka.cli.targets import _resolve_pid
from peeka.core.output import OutputFormatter

__all__ = [
    "OutputFormatter",
    "Path",
    "StreamingAgentClient",
    "TargetResolutionError",
    "_check_agent_attached",
    "_check_agent_for_target",
    "_connect_streaming_agent",
    "_find_active_session",
    "_find_pid_by_name",
    "_parse_duration",
    "_resolve_pid",
    "_socket_path_to_target_id",
    "get_target",
]
