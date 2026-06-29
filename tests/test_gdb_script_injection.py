"""
Unit tests for GDB injection script structure.

Tests validate that _attach.gdb contains the expected commands
for dlopen-based injection (Task 5).
"""

import os
from pathlib import Path

from peeka.core.resources import require_core_resource as _core_resource_path


class TestGDBScriptInjection:
    """Tests for _attach.gdb script structure and content"""

    @staticmethod
    def _get_script_path():
        """Helper: get absolute path to _attach.gdb"""
        # Get project root (parent of tests/)
        test_dir = Path(__file__).parent
        project_root = test_dir.parent
        script_path = project_root / "peeka" / "core" / "_attach.gdb"
        return script_path

    @staticmethod
    def _read_script():
        """Helper: read _attach.gdb content"""
        script_path = TestGDBScriptInjection._get_script_path()
        with open(script_path, "r") as f:
            return f.read()

    def test_script_file_exists(self):
        """GDB script file exists at expected path"""
        script_path = self._get_script_path()
        assert script_path.exists(), f"Expected {script_path} to exist"
        assert script_path.is_file(), f"Expected {script_path} to be a file"

    def test_injector_resolves_gdb_script_from_core_dir(self):
        """Attach workflow resolves _attach.gdb from peeka/core after modularization."""
        script_path = Path(_core_resource_path("_attach.gdb"))
        assert script_path == self._get_script_path()
        assert script_path.exists()

    def test_injector_resolves_lldb_script_from_core_dir(self):
        """Attach workflow resolves _attach.lldb from peeka/core after modularization."""
        script_path = Path(_core_resource_path("_attach.lldb"))
        assert script_path == self._get_script_path().with_name("_attach.lldb")
        assert script_path.exists()

    def test_script_readable(self):
        """GDB script is readable"""
        script_path = self._get_script_path()
        assert os.access(script_path, os.R_OK), f"Expected {script_path} to be readable"

    def test_script_contains_scheduler_locking(self):
        """Script sets scheduler-locking on"""
        content = self._read_script()
        assert "set scheduler-locking on" in content, (
            "Expected 'set scheduler-locking on' command in script"
        )
        assert "set scheduler-locking off" in content, (
            "Expected 'set scheduler-locking off' command in script"
        )

    def test_script_contains_dlopen_call(self):
        """Script calls dlopen with injector path"""
        content = self._read_script()
        assert "dlopen($peeka_injector" in content, (
            "Expected dlopen call with $peeka_injector variable"
        )
        assert "$peeka_rtld_now" in content, (
            "Expected $peeka_rtld_now variable for RTLD_NOW flag"
        )

    def test_script_contains_peeka_spawn_agent(self):
        """Script calls peeka_spawn_agent with port"""
        content = self._read_script()
        assert "peeka_spawn_agent($peeka_port)" in content, (
            "Expected peeka_spawn_agent call with $peeka_port variable"
        )

    def test_script_contains_dlerror_handling(self):
        """Script prints dlerror on failure"""
        content = self._read_script()
        assert "dlerror()" in content, "Expected dlerror() call for diagnostics"

    def test_script_uses_gdb_variables(self):
        """Script references $peeka_port and $peeka_injector"""
        content = self._read_script()
        assert "$peeka_port" in content, "Expected $peeka_port variable reference"
        assert "$peeka_injector" in content, (
            "Expected $peeka_injector variable reference"
        )

    def test_script_no_pyrun_simplestring(self):
        """Script does NOT use PyRun_SimpleString approach"""
        content = self._read_script()
        assert "PyRun_SimpleString" not in content, (
            "Script should use dlopen approach, not PyRun_SimpleString"
        )

    def test_script_has_breakpoints_on_allocators(self):
        """Script sets breakpoints on malloc/calloc/realloc/free and PyMem_* variants"""
        content = self._read_script()
        # Standard allocators
        assert "b malloc" in content, "Expected breakpoint on malloc"
        assert "b calloc" in content, "Expected breakpoint on calloc"
        assert "b realloc" in content, "Expected breakpoint on realloc"
        assert "b free" in content, "Expected breakpoint on free"

        # Python allocators
        assert "b PyMem_Malloc" in content, "Expected breakpoint on PyMem_Malloc"
        assert "b PyMem_Calloc" in content, "Expected breakpoint on PyMem_Calloc"
        assert "b PyMem_Realloc" in content, "Expected breakpoint on PyMem_Realloc"
        assert "b PyMem_Free" in content, "Expected breakpoint on PyMem_Free"

        # Additional breakpoints for thread safety
        assert "b PyErr_CheckSignals" in content, (
            "Expected breakpoint on PyErr_CheckSignals"
        )
        assert "b PyCallable_Check" in content, (
            "Expected breakpoint on PyCallable_Check"
        )

    def test_script_has_commands_block(self):
        """Script has commands block that executes injection on breakpoint hit"""
        content = self._read_script()
        assert "commands 1-10" in content, (
            "Expected commands block for breakpoints 1-10"
        )
        assert "disable breakpoints" in content, (
            "Expected 'disable breakpoints' in commands block"
        )
        assert "delete breakpoints" in content, (
            "Expected 'delete breakpoints' in commands block"
        )

    def test_script_has_continue_command(self):
        """Script has continue command at the end"""
        content = self._read_script()
        lines = content.strip().split("\n")
        # Last line should be 'continue'
        assert lines[-1].strip() == "continue", "Expected 'continue' as last command"

    def test_script_has_sharedlibrary_commands(self):
        """Script loads shared libraries for symbol resolution"""
        content = self._read_script()
        assert "sharedlibrary libc" in content, "Expected sharedlibrary libc"
        assert "sharedlibrary libdl" in content, "Expected sharedlibrary libdl"
        assert "sharedlibrary libpython" in content, "Expected sharedlibrary libpython"

        # After dlopen, eval sharedlibrary for injector
        assert 'eval "sharedlibrary %s", $peeka_injector' in content, (
            "Expected eval sharedlibrary for injector .so"
        )

    def test_script_has_backtrace_in_commands(self):
        """Script includes backtrace command for debugging"""
        content = self._read_script()
        assert "bt" in content, "Expected 'bt' (backtrace) command for debugging"

    def test_script_structure_matches_memray(self):
        """Script follows memray _attach.gdb structure"""
        content = self._read_script()

        # Check for key structural elements in order
        lines = content.split("\n")

        # Find key sections
        scheduler_on_idx = None
        commands_start_idx = None
        scheduler_off_idx = None
        continue_idx = None

        for i, line in enumerate(lines):
            if "set scheduler-locking on" in line:
                scheduler_on_idx = i
            elif "commands 1-10" in line:
                commands_start_idx = i
            elif "set scheduler-locking off" in line:
                scheduler_off_idx = i
            elif line.strip() == "continue":
                continue_idx = i

        # Verify order
        assert scheduler_on_idx is not None, "Missing 'set scheduler-locking on'"
        assert commands_start_idx is not None, "Missing 'commands 1-10'"
        assert scheduler_off_idx is not None, "Missing 'set scheduler-locking off'"
        assert continue_idx is not None, "Missing 'continue'"

        assert scheduler_on_idx < commands_start_idx, (
            "scheduler-locking on should come before commands block"
        )
        assert commands_start_idx < scheduler_off_idx, (
            "commands block should come before scheduler-locking off"
        )
        assert scheduler_off_idx < continue_idx, (
            "scheduler-locking off should come before continue"
        )
