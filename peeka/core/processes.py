"""Helpers for discovering local Python processes."""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List
from typing import Optional


PROC_DIR = Path("/proc")
_PYTHON_NAME_RE = re.compile(r"^python(?:\d+(?:\.\d+)*)?[a-z]?$", re.IGNORECASE)
_PYTHON_VERSION_RE = re.compile(r"python(?P<version>\d+(?:\.\d+)*)", re.IGNORECASE)


@dataclass
class PythonProcess:
    """Represents a local Python interpreter process that may be attachable."""

    pid: int
    name: str
    command: str
    executable: str
    python_version: str
    created_at: float


def discover_python_processes(
    exclude_current: bool = True, exclude_peeka_tools: bool = True
) -> List[PythonProcess]:
    """Discover local Python processes from /proc.

    Args:
        exclude_current: Whether to omit the current Peeka process.
        exclude_peeka_tools: Whether to omit Peeka CLI/TUI helper processes.

    Returns:
        Sorted list of visible Python interpreter processes. Returns an empty
        list on non-/proc platforms.
    """
    if not PROC_DIR.exists():
        return []

    current_pid = os.getpid()
    processes = []
    for entry in PROC_DIR.iterdir():
        if not entry.is_dir() or not entry.name.isdigit():
            continue

        pid = int(entry.name)
        if exclude_current and pid == current_pid:
            continue

        process = _read_python_process(entry, pid)
        if process is not None:
            if exclude_peeka_tools and _is_peeka_tool_process(process.command):
                continue
            processes.append(process)

    return sorted(processes, key=lambda process: (process.created_at, process.pid))


def _read_python_process(proc_entry: Path, pid: int) -> Optional[PythonProcess]:
    cmdline_parts = _read_cmdline_parts(proc_entry / "cmdline")
    command = " ".join(cmdline_parts)
    comm = _read_text(proc_entry / "comm")
    executable = _read_executable(proc_entry / "exe")

    if not _looks_like_python(executable, cmdline_parts, comm):
        return None

    name = _process_name(executable, cmdline_parts, comm, pid)
    display_command = command or comm or name
    python_version = _extract_python_version(executable)
    if not python_version:
        python_version = _extract_python_version(display_command)

    return PythonProcess(
        pid=pid,
        name=name,
        command=display_command,
        executable=executable,
        python_version=python_version,
        created_at=_get_created_at(proc_entry),
    )


def _read_cmdline_parts(path: Path) -> List[str]:
    try:
        raw = path.read_bytes()
    except OSError:
        return []

    return [
        part.decode("utf-8", errors="ignore")
        for part in raw.split(b"\x00")
        if part
    ]


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


def _read_executable(path: Path) -> str:
    try:
        return os.readlink(str(path))
    except OSError:
        return ""


def _looks_like_python(
    executable: str, cmdline_parts: List[str], comm: str
) -> bool:
    names = []
    if executable:
        names.append(Path(executable).name)
    if cmdline_parts:
        names.append(Path(cmdline_parts[0]).name)
    if comm:
        names.append(comm)

    return any(_PYTHON_NAME_RE.match(name) for name in names if name)


def _process_name(
    executable: str, cmdline_parts: List[str], comm: str, pid: int
) -> str:
    workload_name = _python_workload_name(cmdline_parts)
    if workload_name:
        return workload_name
    if executable:
        return Path(executable).name
    if cmdline_parts:
        return Path(cmdline_parts[0]).name
    if comm:
        return comm
    return f"pid {pid}"


def _python_workload_name(cmdline_parts: List[str]) -> str:
    index = 1
    while index < len(cmdline_parts):
        arg = cmdline_parts[index]
        if arg == "-m" and index + 1 < len(cmdline_parts):
            return cmdline_parts[index + 1]
        if arg == "-c":
            return "python -c"
        if arg == "--":
            index += 1
            continue
        if arg.startswith("-"):
            index += _python_option_size(cmdline_parts, index)
            continue
        return Path(arg).name
    return ""


def _python_option_size(cmdline_parts: List[str], index: int) -> int:
    option = cmdline_parts[index]
    if option in ("-W", "-X") and index + 1 < len(cmdline_parts):
        return 2
    return 1


def _is_peeka_tool_process(command: str) -> bool:
    parts = command.split()
    for part in parts:
        name = Path(part).name
        if name in ("peeka", "peeka-cli"):
            return True
        if part in ("peeka.tui", "peeka.cli", "peeka.cli.main"):
            return True
    return False


def _extract_python_version(text: str) -> str:
    match = _PYTHON_VERSION_RE.search(text)
    if match:
        return match.group("version")
    return ""


def _get_created_at(path: Path) -> float:
    try:
        return os.path.getctime(path)
    except OSError:
        return 0.0
