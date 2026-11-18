"""CLI target and process resolution helpers."""

from pathlib import Path
from typing import List

from peeka.cli.sessions import TargetResolutionError


def _find_pid_by_name(name: str) -> int:
    if not name:
        raise ValueError("Process name is required when pid is not provided")
    proc_root = Path("/proc")
    matched_pids: List[int] = []
    for entry in proc_root.iterdir():
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        pid = int(entry.name)
        cmdline_path = entry / "cmdline"
        comm_path = entry / "comm"
        matched = False
        try:
            if cmdline_path.exists():
                cmdline = cmdline_path.read_text(errors="ignore").replace("\x00", " ")
                if name in cmdline:
                    matched = True
            if not matched and comm_path.exists():
                comm = comm_path.read_text(errors="ignore").strip()
                if comm == name:
                    matched = True
        except Exception:
            continue
        if matched:
            matched_pids.append(pid)

    if not matched_pids:
        raise ValueError(f"Process with name '{name}' not found")
    if len(matched_pids) > 1:
        pids_str = ", ".join(str(p) for p in sorted(matched_pids))
        raise TargetResolutionError(
            "TARGET_AMBIGUOUS",
            f"Multiple processes match '{name}' (pids: {pids_str}); pass --pid",
        )
    return matched_pids[0]


def _resolve_pid(args) -> int:
    if args.pid:
        return args.pid
    if getattr(args, "name", None):
        return _find_pid_by_name(args.name)
    raise ValueError("Either --pid or --name must be provided")
