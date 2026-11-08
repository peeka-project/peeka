"""Tests for peeka-cli patch-status command argument parsing"""
import subprocess
import sys

# Session discovery scans the hard-coded /tmp/peeka_*.sock. Any live agent on
# the machine (another attach, a leftover from an earlier test) would make
# "patch-status" succeed with exit 0. Redirect the scan to an empty directory
# so these tests only exercise argument parsing + the "not attached" path.
_ISOLATED_CLI = """
import pathlib, runpy, sys
import peeka.cli.sessions as sessions
empty_dir = sys.argv.pop(1)
real_path = pathlib.Path
sessions.Path = lambda p, *a: real_path(empty_dir) if str(p) == "/tmp" else real_path(p, *a)
sys.argv[0] = "peeka-cli"
runpy.run_module("peeka.cli.main", run_name="__main__")
"""


def _run_isolated_cli(tmp_path, *args):
    return subprocess.run(
        [sys.executable, "-c", _ISOLATED_CLI, str(tmp_path), *args],
        capture_output=True,
        text=True,
    )


def test_patch_status_no_pid(tmp_path):
    """Test that peeka-cli patch-status without --pid gives business error (exit 1), not argparse error (exit 2)"""
    result = _run_isolated_cli(tmp_path, "patch-status")
    # Should be exit code 1 (business error: not attached), NOT 2 (argparse error)
    assert result.returncode == 1, f"Expected exit code 1, got {result.returncode}. stderr: {result.stderr}"
    assert "Not attached" in result.stdout or "Not attached" in result.stderr


def test_patch_status_with_pid(tmp_path):
    """Test that peeka-cli patch-status with --pid is accepted and gives business error (exit 1)"""
    result = _run_isolated_cli(tmp_path, "patch-status", "--pid", "99999")
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
