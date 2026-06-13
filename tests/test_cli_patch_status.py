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
    help_text = result.stdout.lower()
    assert "--pid" in help_text
    assert "currently attached session" in help_text
    assert "optional" in help_text or "ignored" in help_text
