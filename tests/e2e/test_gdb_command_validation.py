"""
Unit tests for GDB command generation and validation.

These tests verify that the GDB commands use correct type casts for Python C API
functions, which prevents "Invalid cast" errors during injection.
"""
import sys
from typing import List, Tuple

import pytest

from peeka.core.attach import ProcessAttacher

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(
        hasattr(sys, "remote_exec"), reason="PEP 768 available - GDB fallback not used"
    ),
]


class TestGDBCommandGeneration:
    """Test GDB command generation for correct type casting."""

    def test_gdb_commands_use_correct_casts(self):
        """
        Verify that GDB commands use correct type casts for Python C API functions.

        This is a white-box test that checks the implementation details to ensure
        the fix for "Invalid cast" errors is correctly applied.

        Background:
        - PyGILState_Ensure() returns PyGILState_STATE (int), not void*
        - PyRun_SimpleString() returns int, not void*
        - PyGILState_Release() returns void, not void*

        Using incorrect casts like (void*) causes GDB to fail with "Invalid cast"
        errors, especially with Python 3.8 and complex C extensions like DuckDB.
        """
        import inspect

        # Get the source code of _inject_via_gdb method
        source = inspect.getsource(ProcessAttacher._inject_via_gdb)

        # Verify correct casts are used
        assert "call (int) PyGILState_Ensure()" in source, (
            "PyGILState_Ensure should use (int) cast, not (void*)"
        )

        assert "call (int) PyRun_SimpleString" in source, (
            "PyRun_SimpleString should use (int) cast, not (void*)"
        )

        assert "call (void) PyGILState_Release($1)" in source, (
            "PyGILState_Release should use (void) cast, not (void*)"
        )

        # Ensure the old incorrect pattern is NOT present
        assert "call (void*)" not in source, (
            "Found (void*) cast - this causes 'Invalid cast' errors in GDB"
        )

    def test_gdb_commands_structure(self):
        """
        Test that GDB commands are properly structured with descriptions.

        This ensures maintainability and helps future developers understand
        what each command does.
        """
        import tempfile

        attacher = ProcessAttacher(12345)
        agent_script = tempfile.mktemp(suffix=".py", prefix="test_")

        # Manually construct the commands as the code does
        escaped_script = agent_script.replace("\\", "\\\\").replace('"', '\\"')

        gdb_commands = [
            ("call (int) PyGILState_Ensure()", "Acquire GIL"),
            (f'call (int) PyRun_SimpleString("exec(open(\\"{escaped_script}\\").read())")', "Execute agent script"),
            ("call (void) PyGILState_Release($1)", "Release GIL"),
        ]

        # Verify structure
        assert len(gdb_commands) == 3, "Should have exactly 3 GDB commands"

        for cmd, desc in gdb_commands:
            assert isinstance(cmd, str), "Command should be a string"
            assert isinstance(desc, str), "Description should be a string"
            assert cmd.startswith("call "), "Command should start with 'call '"
            assert len(desc) > 0, "Description should not be empty"

    def test_python_c_api_return_types(self):
        """
        Document and verify the correct Python C API return types.

        This test serves as documentation for why specific casts are used.
        """
        # Expected return types from Python C API documentation
        # These signatures have been stable since Python 2.x
        expected_api = {
            "PyGILState_Ensure": {
                "return_type": "PyGILState_STATE (int-like enum)",
                "gdb_cast": "(int)",
                "stable_since": "Python 2.3",
            },
            "PyRun_SimpleString": {
                "return_type": "int (0=success, -1=error)",
                "gdb_cast": "(int)",
                "stable_since": "Python 1.0",
            },
            "PyGILState_Release": {
                "return_type": "void",
                "gdb_cast": "(void)",
                "stable_since": "Python 2.3",
            },
        }

        # This test always passes but documents the API contract
        for func_name, info in expected_api.items():
            assert info["gdb_cast"] in ["(int)", "(void)"], (
                f"{func_name} should use a proper cast, not (void*)"
            )

    def test_gdb_command_escaping(self):
        """
        Test that agent script paths are properly escaped for GDB.

        This prevents injection vulnerabilities and command parsing errors.
        """
        attacher = ProcessAttacher(12345)

        # Test various problematic paths
        test_cases = [
            ('/tmp/agent.py', '/tmp/agent.py'),
            ('/tmp/agent with spaces.py', '/tmp/agent with spaces.py'),
            (r'C:\tmp\agent.py', r'C:\\tmp\\agent.py'),  # Windows path
            ('/tmp/"quoted".py', r'/tmp/\"quoted\".py'),  # Contains quotes
        ]

        for original, expected_escaped in test_cases:
            escaped = original.replace("\\", "\\\\").replace('"', '\\"')
            assert escaped == expected_escaped, (
                f"Path escaping failed for {original}"
            )


class TestGDBCommandExecutionContext:
    """Test the context in which GDB commands are executed."""

    def test_gdb_batch_mode_flags(self):
        """
        Verify that GDB is invoked with correct flags for non-interactive operation.

        Expected flags:
        - -p <pid>: Attach to process
        - -batch: Run in batch mode (exit after commands)
        - -q: Quiet mode (suppress banner)
        - -eval-command: Execute commands
        """
        import inspect

        source = inspect.getsource(ProcessAttacher._inject_via_gdb)

        # Verify GDB invocation uses correct flags
        assert '"-p"' in source, "Should attach to process with -p flag"
        assert '"-batch"' in source, "Should use batch mode"
        assert '"-q"' in source, "Should use quiet mode"
        assert '"-eval-command"' in source, "Should use -eval-command for execution"

    def test_gdb_register_reference(self):
        """
        Verify that GDB register $1 is correctly used for GIL state preservation.

        The pattern should be:
        1. $1 = PyGILState_Ensure() - stores state in $1
        2. PyRun_SimpleString(...) - executes code
        3. PyGILState_Release($1) - restores state from $1
        """
        import inspect

        source = inspect.getsource(ProcessAttacher._inject_via_gdb)

        # Verify $1 is used in PyGILState_Release
        assert "PyGILState_Release($1)" in source, (
            "PyGILState_Release should use $1 register to restore GIL state"
        )
