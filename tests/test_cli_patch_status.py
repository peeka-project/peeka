"""Tests for peeka-cli patch-status command argument parsing"""
import subprocess
import sys


def test_patch_status_no_pid():
    """Test that peeka-cli patch-status without --pid gives business error (exit 1), not argparse error (exit 2)"""
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "patch-status"],
        capture_output=True,
        text=True
    )
    # Should be exit code 1 (business error: not attached), NOT 2 (argparse error)
    assert result.returncode == 1, f"Expected exit code 1, got {result.returncode}. stderr: {result.stderr}"
    assert "Not attached" in result.stdout or "Not attached" in result.stderr


def test_patch_status_with_pid():
    """Test that peeka-cli patch-status with --pid is accepted and gives business error (exit 1)"""
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "patch-status", "--pid", "99999"],
        capture_output=True,
        text=True
    )
    # Should be exit code 1 (business error: not attached), NOT 2 (argparse error)
    assert result.returncode == 1, f"Expected exit code 1, got {result.returncode}. stderr: {result.stderr}"
    assert "Not attached" in result.stdout or "Not attached" in result.stderr


def test_patch_status_help():
    """Test that --help shows --pid as optional (no 'required' marker)"""
    result = subprocess.run(
        [sys.executable, "-m", "peeka.cli.main", "patch-status", "--help"],
        capture_output=True,
        text=True
    )
    assert result.returncode == 0
    assert "--pid" in result.stdout
    # Verify that 'required' is NOT in the --pid line
    lines = result.stdout.split('\n')
    pid_line = [line for line in lines if '--pid' in line]
    assert len(pid_line) > 0, "Could not find --pid in help output"
    # The help text should NOT contain "required" for the --pid argument
    # (it may contain "optional" or "(optional, ignored)")
    assert "required" not in pid_line[0].lower() or "optional" in pid_line[0].lower()
