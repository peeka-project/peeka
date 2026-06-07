"""Basic tests for peeka-cli run command argument parsing"""
import subprocess
import sys

from peeka.cli.handlers.run import _build_run_command


def test_run_help_flag():
    """Test that peeka-cli run --help works"""
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "run", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "Run a Python script with Peeka attached from startup" in result.stdout


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
