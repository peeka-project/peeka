"""
Tests for LLDB injection script

Unit tests that validate the structure and correctness of the LLDB script
used for macOS injection. No actual LLDB execution required.
"""

import os
from pathlib import Path


class TestLLDBInjection:
    """Test LLDB injection script structure"""

    @staticmethod
    def _get_lldb_script_path():
        """Get path to LLDB script"""
        return Path(__file__).parent.parent / "peeka" / "core" / "_attach.lldb"

    @staticmethod
    def _read_script():
        """Read LLDB script content"""
        script_path = TestLLDBInjection._get_lldb_script_path()
        with open(script_path, "r") as f:
            return f.read()

    def test_script_file_exists(self):
        """LLDB script file exists at expected path"""
        script_path = self._get_lldb_script_path()
        assert script_path.exists(), f"LLDB script not found at {script_path}"
        assert script_path.is_file(), f"LLDB script path is not a file: {script_path}"

    def test_script_contains_dlsym_indirection(self):
        """Script uses dlsym to get dlopen pointer (CRITICAL workaround)"""
        content = self._read_script()
        # Must use dlsym to get dlopen function pointer
        assert (
            "expr auto $dlsym = (void* (*)(void*, const char*))&::dlsym" in content
        ), "Missing dlsym function pointer assignment"
        assert 'expr auto $dlopen = $dlsym($rtld_default, "dlopen")' in content, (
            "Missing dlopen via dlsym indirection (CRITICAL LLDB workaround)"
        )

    def test_script_contains_rtld_default(self):
        """Script references RTLD_DEFAULT (-2)"""
        content = self._read_script()
        # Script must use $rtld_default variable (set to -2 by caller)
        assert "$rtld_default" in content, "Missing $rtld_default variable reference"

    def test_script_contains_peeka_spawn_agent(self):
        """Script calls peeka_spawn_agent"""
        content = self._read_script()
        assert "peeka_spawn_agent" in content, "Missing peeka_spawn_agent symbol call"
        assert 'expr auto $spawn = $dlsym($dll, "peeka_spawn_agent")' in content, (
            "Missing peeka_spawn_agent symbol lookup via dlsym"
        )
        assert "p ((int(*)(int))$spawn)($port)" in content, (
            "Missing peeka_spawn_agent function call"
        )

    def test_script_uses_lldb_expr_syntax(self):
        """Script uses LLDB expression syntax (expr, breakpoint set)"""
        content = self._read_script()
        # LLDB-specific syntax
        assert "expr auto" in content, "Missing LLDB 'expr auto' syntax"
        assert "breakpoint set" in content, "Missing LLDB 'breakpoint set' command"
        assert "breakpoint command add" in content, (
            "Missing LLDB 'breakpoint command add' command"
        )

    def test_script_no_direct_dlopen_call(self):
        """Script does NOT call dlopen directly (must be via dlsym pointer)"""
        content = self._read_script()
        # Pattern: dlopen must ONLY appear in the dlsym lookup, never as direct call
        # Allowed: expr auto $dlopen = $dlsym($rtld_default, "dlopen")
        # Forbidden: call dlopen(...) or expr dlopen(...)

        # Check no direct calls to dlopen (must be via $dlopen pointer)
        lines = content.split("\n")
        for line in lines:
            # Skip the line that defines $dlopen via dlsym - that's allowed
            if "$dlopen = $dlsym" in line:
                continue
            # Now check remaining lines don't call dlopen() directly
            if "dlopen(" in line and "$dlopen)" not in line:
                raise AssertionError(
                    f"Found direct dlopen() call (forbidden): {line.strip()}"
                )

    def test_script_no_pyrun_simplestring(self):
        """Script does NOT use PyRun_SimpleString"""
        content = self._read_script()
        assert "PyRun_SimpleString" not in content, (
            "Script should not use PyRun_SimpleString (C extension approach used instead)"
        )

    def test_script_no_gdb_syntax(self):
        """Script does NOT contain GDB-specific syntax like 'call (void)'"""
        content = self._read_script()
        # GDB uses 'call (type)function()', LLDB uses 'expr ((type)function)()'
        assert "call (" not in content.lower(), (
            "Found GDB 'call' syntax - should use LLDB 'expr' syntax"
        )
        assert "sharedlibrary" not in content, (
            "Found GDB 'sharedlibrary' command - not valid in LLDB"
        )

    def test_script_contains_peeka_branding(self):
        """Script contains PEEKA branding messages"""
        content = self._read_script()
        assert "PEEKA:" in content, "Missing PEEKA branding in status messages"
        assert "Attached to process" in content, "Missing attach confirmation message"
        assert "Python 3.7+" in content, "Missing Python version check message"

    def test_script_sets_breakpoints_on_memory_functions(self):
        """Script sets breakpoints on malloc family and PyMem functions"""
        content = self._read_script()
        # Same breakpoints as GDB script and memray LLDB script
        required_breakpoints = [
            "malloc",
            "calloc",
            "realloc",
            "free",
            "PyMem_Malloc",
            "PyMem_Calloc",
            "PyMem_Realloc",
            "PyMem_Free",
        ]
        for bp in required_breakpoints:
            assert bp in content, f"Missing breakpoint on {bp}"

    def test_script_uses_variables_from_caller(self):
        """Script uses variables that will be set by attach.py caller"""
        content = self._read_script()
        # Variables that attach.py must set before sourcing script
        assert "$rtld_default" in content, (
            "Missing $rtld_default variable (should be set to -2 by caller)"
        )
        assert "$rtld_now" in content, (
            "Missing $rtld_now variable (should be set to 2 by caller)"
        )
        assert "$libpath" in content, (
            "Missing $libpath variable (should be injector .so path from caller)"
        )
        assert "$port" in content, (
            "Missing $port variable (should be agent socket port from caller)"
        )

    def test_script_includes_error_checking(self):
        """Script includes dlerror() call for debugging"""
        content = self._read_script()
        assert "dlerror" in content, "Missing dlerror() call for error reporting"
        assert 'expr auto $dlerror = $dlsym($rtld_default, "dlerror")' in content, (
            "Missing dlerror symbol lookup"
        )

    def test_script_disables_breakpoints_after_first_hit(self):
        """Script disables breakpoints after first hit (one-shot)"""
        content = self._read_script()
        assert "breakpoint disable" in content, (
            "Missing 'breakpoint disable' - breakpoints should be one-shot"
        )

    def test_script_continues_execution(self):
        """Script continues target process execution"""
        content = self._read_script()
        assert "continue" in content, "Missing 'continue' command at end of script"
