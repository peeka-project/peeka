"""Attach preflight checks for tools, ptrace, and Python versions."""

import os
import platform
import re
import shutil
import subprocess
import warnings
from typing import Optional, Tuple


def _attach_module():
    from peeka.core import attach as attach_module

    return attach_module


class AttachCapabilityMixin:

    def _check_gdb_available(self):
        """Check if GDB is available on the system"""
        if not shutil.which("gdb"):
            raise RuntimeError(
                "GDB not found. Install with:\n"
                "  Debian/Ubuntu: sudo apt-get install gdb python3-dbg\n"
                "  RHEL/Fedora: sudo yum install gdb python3-debuginfo\n"
                "  Arch: sudo pacman -S gdb"
            )

    def _check_ptrace_permissions(self):
        """Check if ptrace is available and warn user if restricted"""
        ptrace_scope_file = "/proc/sys/kernel/yama/ptrace_scope"

        if os.path.exists(ptrace_scope_file):
            try:
                with open(ptrace_scope_file) as f:
                    scope = int(f.read().strip())

                if scope >= 2:
                    raise PermissionError(
                        f"ptrace_scope is {scope} (admin-only or disabled).\n"
                        "To enable: echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope"
                    )
                elif scope == 1:
                    warnings.warn(
                        f"ptrace_scope is {scope} (restricted mode). "
                        "Injection may fail if target is not a child process.\n"
                        "To enable: echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope",
                        RuntimeWarning,
                    )
            except (IOError, ValueError) as e:
                warnings.warn(f"Could not read ptrace_scope: {e}", RuntimeWarning)

        # Check if target process exists and we have permissions
        try:
            os.kill(self.pid, 0)  # Signal 0 checks process existence
        except ProcessLookupError:
            raise ProcessLookupError(f"Process {self.pid} does not exist")
        except PermissionError:
            raise PermissionError(
                f"No permission to access process {self.pid}. "
                "Requires same UID or CAP_SYS_PTRACE capability."
            )

    @staticmethod
    def _format_python_version(version: Optional[Tuple[int, int]]) -> Optional[str]:
        if version is None:
            return None
        return f"{version[0]}.{version[1]}"

    def _get_target_python_version(self) -> Optional[Tuple[int, int]]:
        """
        Get the Python major.minor version of the target process.

        On Linux, reads /proc/<pid>/exe to find the Python binary.
        On macOS, uses lsof to find the executable path.
        Then runs the binary with a minimal version-print snippet.

        Returns:
            Optional[Tuple[int, int]]: (major, minor) version tuple, or None
            if the version cannot be determined.
        """
        system_name = platform.system()
        exe_path = None

        if system_name == "Linux":
            try:
                exe_path = os.readlink(f"/proc/{self.pid}/exe")
            except (OSError, PermissionError):
                _attach_module().logger.debug(
                    "Cannot read /proc/%d/exe, skipping version check", self.pid
                )
                return None
        elif system_name == "Darwin":
            try:
                result = subprocess.run(
                    ["lsof", "-p", str(self.pid), "-Fn"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in result.stdout.splitlines():
                    # lsof -Fn: 'n' prefix = file name
                    if line.startswith("n") and "python" in line.lower():
                        exe_path = line[1:]
                        break
            except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
                _attach_module().logger.debug(
                    "Cannot determine executable for PID %d on macOS", self.pid
                )
                return None
        else:
            return None

        if not exe_path:
            return None

        try:
            result = subprocess.run(
                [
                    exe_path,
                    "-c",
                    "import sys; print(sys.version_info[0], sys.version_info[1])",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split()
                if len(parts) == 2:
                    return (int(parts[0]), int(parts[1]))
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError):
            pass

        # Fallback: extract version from binary name (e.g., /usr/bin/python3.12)
        match = re.search(r"python(\d+)\.(\d+)", exe_path)
        if match:
            return (int(match.group(1)), int(match.group(2)))

        return None

    def _check_python_version_match(
        self, target_version: Optional[Tuple[int, int]] = None
    ) -> None:
        """
        Verify the target process Python version matches peeka's version.

        Raises:
            RuntimeError: If versions don't match (major.minor mismatch).
        """
        if target_version is None:
            target_version = self._get_target_python_version()
        if target_version is None:
            _attach_module().logger.debug("Could not determine target Python version, skipping check")
            return

        peeka_version = (_attach_module().sys.version_info.major, _attach_module().sys.version_info.minor)

        if target_version != peeka_version:
            target_str = f"{target_version[0]}.{target_version[1]}"
            peeka_str = f"{peeka_version[0]}.{peeka_version[1]}"
            raise RuntimeError(
                f"Python version mismatch: target process (PID {self.pid}) is "
                f"Python {target_str}, but peeka is running on Python {peeka_str}.\n"
                f"The agent code injected into the target process must match "
                f"the target's Python version.\n"
                f"Fix: run peeka with Python {target_str}, e.g.:\n"
                f"  python{target_str} -m peeka.cli.main attach {self.pid}"
            )
