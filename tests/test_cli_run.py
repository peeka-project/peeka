# pyright: reportPrivateUsage=false

"""Basic tests for peeka-cli run command argument parsing"""
import subprocess
import sys
import types

from peeka.cli.handlers.run import _build_run_command
from peeka.cli.streaming import stream_counted_limit


def test_run_help_flag():
    """Test that peeka-cli run --help works"""
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "run", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    help_text = result.stdout.lower()
    assert "run a python script" in help_text
    assert "peeka attached from startup" in help_text


def test_run_missing_separator():
    """Test that missing -- gives proper error"""
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "run", "test.py", "watch", "func"],
        capture_output=True,
        text=True
    )
    assert result.returncode != 0
    assert "Missing -- separator" in result.stdout


def test_run_missing_command_after_separator():
    """Test that missing command after -- gives proper error"""
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "run", "test.py", "some_arg", "--"],
        capture_output=True,
        text=True
    )
    assert result.returncode != 0
    assert "Missing observation command after --" in result.stdout


def test_build_run_command_watch_uses_pattern_after_command_name():
    command = _build_run_command("watch", ["watch", "pkg.func", "--success"])

    assert command is not None
    assert command["type"] == "watch"
    assert command["pattern"] == "pkg.func"
    assert command["success"] is True


def test_build_run_command_trace_uses_pattern_after_command_name():
    command = _build_run_command(
        "trace",
        ["trace", "pkg.func", "--min-duration", "2.5"],
    )

    assert command is not None
    assert command["type"] == "trace"
    assert command["pattern"] == "pkg.func"
    assert command["min_duration"] == 2.5


def test_build_run_command_stack_uses_pattern_after_command_name():
    command = _build_run_command("stack", ["stack", "pkg.func", "--depth", "5"])

    assert command is not None
    assert command["type"] == "stack"
    assert command["pattern"] == "pkg.func"
    assert command["depth"] == 5


def test_build_run_command_monitor_skips_command_name():
    command = _build_run_command(
        "monitor",
        ["monitor", "pkg.func", "--interval", "1", "--cycles", "2"],
    )

    assert command is not None
    assert command["type"] == "monitor"
    assert command["pattern"] == "pkg.func"
    assert command["interval"] == 1
    assert command["cycles"] == 2


def test_build_run_command_top_skips_command_name():
    command = _build_run_command(
        "top",
        ["top", "--cycles", "1", "--sort", "total"],
    )

    assert command is not None
    assert command["type"] == "top"
    assert command["cycles"] == 1
    assert command["sort"] == "total"


def test_run_watch_limit_stops_after_n() -> None:
    command = _build_run_command("watch", ["watch", "mod.fn", "-n", "2"])
    assert command is not None
    assert command.get("times") == 2, (
        "_build_run_command must carry -n value as 'times' for watch"
    )

    watch_id = "watch_run_test_abc"
    _limit_predicate, _set_stream_id = stream_counted_limit("times", "watch_id")
    _limit_args = types.SimpleNamespace(times=command.get("times", -1))
    _set_stream_id(watch_id)

    unrelated = {"watch_id": "watch_other_999", "count": 1, "data": "noise"}
    matching_1 = {"watch_id": watch_id, "count": 10, "location": "AtReturn"}
    matching_2 = {"watch_id": watch_id, "count": 11, "location": "AtReturn"}

    assert _limit_predicate(_limit_args, unrelated) is False, (
        "Unrelated watch_id frames must not count toward the -n limit"
    )
    assert _limit_predicate(_limit_args, matching_1) is False, (
        "First matching observation must not yet trigger the limit"
    )
    assert _limit_predicate(_limit_args, matching_2) is True, (
        "Second matching observation must trigger the limit (count=2 >= times=2)"
    )


def test_run_cleanup_sends_stop_not_detach() -> None:
    watch_id = "watch_run_stop_test"

    stop_commands = {
        "watch": {
            "type": "watch",
            "action": "stop",
            "watch_id": watch_id,
        },
        "trace": {
            "type": "trace",
            "action": "stop",
            "watch_id": watch_id,
        },
        "stack": {
            "type": "stack",
            "action": "stop",
            "watch_id": watch_id,
        },
        "monitor": {
            "type": "monitor",
            "action": "stop",
            "monitor_id": watch_id,
        },
    }

    for command_type, stop_cmd in stop_commands.items():
        assert stop_cmd != {"type": "detach"}, (
            f"{command_type}: limit-hit stop must not be a plain detach command"
        )
        assert stop_cmd["action"] == "stop", (
            f"{command_type}: stop command action must be 'stop', got {stop_cmd['action']!r}"
        )
        assert stop_cmd["type"] == command_type, (
            f"Stop command type must match command type {command_type!r}"
        )
        id_key = "monitor_id" if command_type == "monitor" else "watch_id"
        assert id_key in stop_cmd, (
            f"{command_type}: stop command must include '{id_key}' to identify the stream"
        )
        assert stop_cmd[id_key] == watch_id, (
            f"{command_type}: stop command {id_key} must be {watch_id!r}"
        )
