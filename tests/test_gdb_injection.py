"""
Tests for GDB injection command generation in ProcessAttacher.

Verifies correct type casts for Python C API functions to prevent
"Invalid cast" errors (regression test for #10).
"""

import subprocess
import sys
from unittest.mock import patch, MagicMock

import pytest

from peeka.core.attach import ProcessAttacher


pytestmark = pytest.mark.skipif(
    hasattr(sys, "remote_exec"),
    reason="PEP 768 available — GDB fallback not used",
)


class MockCompletedProcess:
    """Minimal mock for subprocess.CompletedProcess."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class TestGDBInjectionCasts:
    """Verify _inject_via_gdb generates correct GDB commands with proper type casts."""

    @pytest.fixture
    def attacher(self):
        return ProcessAttacher(pid=99999)

    @pytest.fixture
    def captured_cmd(self):
        """Capture the actual cmd list passed to subprocess.run."""
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return MockCompletedProcess()

        captured["fake_run"] = fake_run
        return captured

    def _extract_eval_commands(self, cmd_list):
        """Extract -eval-command values from a GDB command list."""
        evals = []
        it = iter(cmd_list)
        for arg in it:
            if arg == "-eval-command":
                evals.append(next(it))
        return evals

    def test_cast_types_are_correct(self, attacher, captured_cmd):
        """
        Core regression test: GDB commands must use (int) and (void) casts,
        never (void*) which causes "Invalid cast" on targets with debug symbols.

        - PyGILState_Ensure() returns PyGILState_STATE (enum → int)
        - PyRun_SimpleString() returns int
        - PyGILState_Release() returns void
        """
        with patch("subprocess.run", side_effect=captured_cmd["fake_run"]):
            attacher._inject_via_gdb("/tmp/test_agent.py")

        evals = self._extract_eval_commands(captured_cmd["cmd"])
        assert len(evals) == 3

        assert evals[0] == "call (int) PyGILState_Ensure()"
        assert evals[1].startswith("call (int) PyRun_SimpleString(")
        assert evals[2] == "call (void) PyGILState_Release($1)"

    def test_no_void_star_casts(self, attacher, captured_cmd):
        """Ensure no (void*) casts remain — the exact bug from #10."""
        with patch("subprocess.run", side_effect=captured_cmd["fake_run"]):
            attacher._inject_via_gdb("/tmp/test_agent.py")

        evals = self._extract_eval_commands(captured_cmd["cmd"])
        for eval_cmd in evals:
            assert "(void*)" not in eval_cmd, f"Found (void*) cast in: {eval_cmd}"

    def test_gil_state_passed_via_register(self, attacher, captured_cmd):
        """PyGILState_Release must receive $1 (the return value of PyGILState_Ensure)."""
        with patch("subprocess.run", side_effect=captured_cmd["fake_run"]):
            attacher._inject_via_gdb("/tmp/test_agent.py")

        evals = self._extract_eval_commands(captured_cmd["cmd"])
        assert "PyGILState_Release($1)" in evals[2]


class TestGDBCommandStructure:
    """Verify the overall GDB command line structure."""

    @pytest.fixture
    def attacher(self):
        return ProcessAttacher(pid=12345)

    @pytest.fixture
    def captured_cmd(self):
        captured = {}

        def fake_run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return MockCompletedProcess()

        captured["fake_run"] = fake_run
        return captured

    def test_gdb_flags(self, attacher, captured_cmd):
        """GDB must run in batch + quiet mode attached to the target PID."""
        with patch("subprocess.run", side_effect=captured_cmd["fake_run"]):
            attacher._inject_via_gdb("/tmp/agent.py")

        cmd = captured_cmd["cmd"]
        assert cmd[0] == "gdb"
        assert "-p" in cmd
        assert cmd[cmd.index("-p") + 1] == "12345"
        assert "-batch" in cmd
        assert "-q" in cmd

    def test_script_path_in_exec_open(self, attacher, captured_cmd):
        """The agent script path must appear inside exec(open(...).read())."""
        script = "/tmp/peeka_agent_abc123.py"
        with patch("subprocess.run", side_effect=captured_cmd["fake_run"]):
            attacher._inject_via_gdb(script)

        evals = self._extract_eval_commands(captured_cmd["cmd"])
        run_cmd = evals[1]
        assert "exec(open(" in run_cmd
        assert "peeka_agent_abc123" in run_cmd
        assert ".read())" in run_cmd

    def test_path_with_special_chars_escaped(self, attacher, captured_cmd):
        """Backslashes and quotes in paths must be escaped for GDB."""
        with patch("subprocess.run", side_effect=captured_cmd["fake_run"]):
            attacher._inject_via_gdb('/tmp/has"quote.py')

        evals = self._extract_eval_commands(captured_cmd["cmd"])
        run_cmd = evals[1]
        # The quote should be escaped as \"
        assert r"has\"quote" in run_cmd
        # No unescaped double quotes inside the string (other than the outer ones)

    def test_subprocess_timeout(self, attacher, captured_cmd):
        """GDB subprocess must have a timeout to avoid hanging."""
        with patch("subprocess.run", side_effect=captured_cmd["fake_run"]):
            attacher._inject_via_gdb("/tmp/agent.py")

        kwargs = captured_cmd["kwargs"]
        assert "timeout" in kwargs
        assert kwargs["timeout"] > 0

    def _extract_eval_commands(self, cmd_list):
        evals = []
        it = iter(cmd_list)
        for arg in it:
            if arg == "-eval-command":
                evals.append(next(it))
        return evals


class TestGDBErrorHandling:
    """Verify error detection from GDB stderr."""

    @pytest.fixture
    def attacher(self):
        return ProcessAttacher(pid=12345)

    def test_permission_denied_raises(self, attacher):
        mock_result = MockCompletedProcess(
            returncode=1, stderr="Operation not permitted"
        )
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(PermissionError, match="Permission denied"):
                attacher._inject_via_gdb("/tmp/agent.py")

    def test_missing_debug_symbols_raises(self, attacher):
        mock_result = MockCompletedProcess(
            returncode=1,
            stderr='No symbol "PyGILState_Ensure" in current context.',
        )
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="debugging symbols"):
                attacher._inject_via_gdb("/tmp/agent.py")

    def test_nonzero_exit_raises(self, attacher):
        mock_result = MockCompletedProcess(returncode=1, stderr="some unknown error")
        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="exit code 1"):
                attacher._inject_via_gdb("/tmp/agent.py")

    def test_timeout_raises(self, attacher):
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("gdb", 30)):
            with pytest.raises(TimeoutError, match="timed out"):
                attacher._inject_via_gdb("/tmp/agent.py")

    def test_gdb_not_found_raises(self, attacher):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(RuntimeError, match="not found"):
                attacher._inject_via_gdb("/tmp/agent.py")
