"""CLI target and process resolution helpers."""

from pathlib import Path


def _find_pid_by_name(name: str) -> int:
    if not name:
        raise ValueError("Process name is required when pid is not provided")
    proc_root = Path("/proc")
    for entry in proc_root.iterdir():
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        cmdline_path = entry / "cmdline"
        comm_path = entry / "comm"
        try:
            if cmdline_path.exists():
                cmdline = cmdline_path.read_text(errors="ignore").replace("\x00", " ")
                if name in cmdline:
                    return int(entry.name)
            if comm_path.exists():
                comm = comm_path.read_text(errors="ignore").strip()
                if comm == name:
                    return int(entry.name)
        except Exception:
            continue
    raise ValueError(f"Process with name '{name}' not found")


def _resolve_pid(args) -> int:
    if args.pid:
        return args.pid
    if getattr(args, "name", None):
        return _find_pid_by_name(args.name)
    raise ValueError("Either --pid or --name must be provided")
