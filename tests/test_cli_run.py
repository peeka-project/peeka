"""Basic tests for peeka-cli run command argument parsing"""
import subprocess
import sys


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
