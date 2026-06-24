from pathlib import Path
from typing import List

import pytest

from peeka.core import processes


def _write_proc_entry(
    proc_root: Path, pid: int, command_parts: List[str], comm: str
) -> Path:
    proc_entry = proc_root / str(pid)
    proc_entry.mkdir()
    if command_parts:
        raw = b"\x00".join(part.encode("utf-8") for part in command_parts) + b"\x00"
    else:
        raw = b""
    _ = (proc_entry / "cmdline").write_bytes(raw)
    _ = (proc_entry / "comm").write_text(comm, encoding="utf-8")
    return proc_entry


def test_discover_python_processes_filters_proc_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    py_entry = _write_proc_entry(
        proc_root,
        101,
        ["python3.14", "/app/target.py"],
        "python3.14",
    )
    bash_entry = _write_proc_entry(proc_root, 202, ["bash"], "bash")
    current_entry = _write_proc_entry(
        proc_root,
        303,
        ["python3.14", "-m", "peeka.tui"],
        "python3.14",
    )

    exe_paths = {
        str(py_entry / "exe"): "/opt/python/bin/python3.14",
        str(bash_entry / "exe"): "/usr/bin/bash",
        str(current_entry / "exe"): "/opt/python/bin/python3.14",
    }

    def fake_readlink(path: str) -> str:
        return exe_paths[path]

    def fake_getctime(path: Path) -> float:
        return {"101": 30.0, "202": 10.0, "303": 20.0}[Path(path).name]

    monkeypatch.setattr(processes, "PROC_DIR", proc_root)
    monkeypatch.setattr(processes.os, "getpid", lambda: 303)
    monkeypatch.setattr(processes.os, "readlink", fake_readlink)
    monkeypatch.setattr(processes.os.path, "getctime", fake_getctime)

    discovered = processes.discover_python_processes()

    assert [process.pid for process in discovered] == [101]
    assert discovered[0].name == "target.py"
    assert discovered[0].command == "python3.14 /app/target.py"
    assert discovered[0].python_version == "3.14"


def test_discover_python_processes_uses_comm_when_cmdline_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    py_entry = _write_proc_entry(proc_root, 404, [], "python3")

    monkeypatch.setattr(processes, "PROC_DIR", proc_root)
    monkeypatch.setattr(processes.os, "getpid", lambda: 1)
    monkeypatch.setattr(
        processes.os,
        "readlink",
        lambda path: "/usr/bin/python3" if path == str(py_entry / "exe") else "",
    )

    discovered = processes.discover_python_processes()

    assert len(discovered) == 1
    assert discovered[0].pid == 404
    assert discovered[0].name == "python3"
    assert discovered[0].command == "python3"
    assert discovered[0].python_version == "3"


def test_discover_python_processes_excludes_peeka_tools_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    target_entry = _write_proc_entry(
        proc_root,
        501,
        ["python3.14", "/app/examples/demo.py"],
        "python3.14",
    )
    tui_entry = _write_proc_entry(
        proc_root,
        502,
        ["python3.14", "-m", "peeka.tui"],
        "python3.14",
    )

    exe_paths = {
        str(target_entry / "exe"): "/opt/python/bin/python3.14",
        str(tui_entry / "exe"): "/opt/python/bin/python3.14",
    }

    monkeypatch.setattr(processes, "PROC_DIR", proc_root)
    monkeypatch.setattr(processes.os, "getpid", lambda: 1)
    monkeypatch.setattr(processes.os, "readlink", lambda path: exe_paths[path])

    discovered = processes.discover_python_processes()
    unfiltered = processes.discover_python_processes(exclude_peeka_tools=False)

    assert [process.pid for process in discovered] == [501]
    assert [process.pid for process in unfiltered] == [501, 502]


def test_discover_python_processes_names_module_workload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    module_entry = _write_proc_entry(
        proc_root,
        601,
        ["python3.14", "-u", "-m", "package.worker"],
        "python3.14",
    )

    monkeypatch.setattr(processes, "PROC_DIR", proc_root)
    monkeypatch.setattr(processes.os, "getpid", lambda: 1)
    monkeypatch.setattr(
        processes.os,
        "readlink",
        lambda path: (
            "/opt/python/bin/python3.14"
            if path == str(module_entry / "exe")
            else ""
        ),
    )

    discovered = processes.discover_python_processes()

    assert len(discovered) == 1
    assert discovered[0].name == "package.worker"


def test_discover_python_processes_falls_back_to_ps_without_proc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_proc = tmp_path / "missing-proc"
    ps_output = "\n".join(
        [
            " 101 /usr/bin/python3.12 /usr/bin/python3.12 /app/target.py",
            " 202 /bin/bash /bin/bash",
            " 303 /usr/bin/python3.12 /usr/bin/python3.12 -m peeka.tui",
        ]
    )

    monkeypatch.setattr(processes, "PROC_DIR", missing_proc)
    monkeypatch.setattr(processes.os, "getpid", lambda: 999)
    monkeypatch.setattr(
        processes.subprocess, "check_output", lambda *args, **kwargs: ps_output
    )

    discovered = processes.discover_python_processes()
    unfiltered = processes.discover_python_processes(exclude_peeka_tools=False)

    assert [process.pid for process in discovered] == [101]
    assert discovered[0].name == "target.py"
    assert discovered[0].command == "/usr/bin/python3.12 /app/target.py"
    assert discovered[0].python_version == "3.12"
    assert [process.pid for process in unfiltered] == [101, 303]


def test_discover_python_processes_ps_fallback_excludes_current_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_proc = tmp_path / "missing-proc"
    ps_output = "\n".join(
        [
            " 101 /usr/bin/python3.12 /usr/bin/python3.12 /app/target.py",
            " 404 /usr/bin/python3.12 /usr/bin/python3.12 /app/current.py",
        ]
    )

    monkeypatch.setattr(processes, "PROC_DIR", missing_proc)
    monkeypatch.setattr(processes.os, "getpid", lambda: 404)
    monkeypatch.setattr(
        processes.subprocess, "check_output", lambda *args, **kwargs: ps_output
    )

    discovered = processes.discover_python_processes()

    assert [process.pid for process in discovered] == [101]


def test_discover_python_processes_ps_fallback_skips_non_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_proc = tmp_path / "missing-proc"
    ps_output = "\n".join(
        [
            " 101 /usr/bin/python3.12 /usr/bin/python3.12 /app/target.py",
            " 202 /usr/bin/swift /usr/bin/swift /app/server",
            " 303 /sbin/init /sbin/init",
        ]
    )

    monkeypatch.setattr(processes, "PROC_DIR", missing_proc)
    monkeypatch.setattr(processes.os, "getpid", lambda: 999)
    monkeypatch.setattr(
        processes.subprocess, "check_output", lambda *args, **kwargs: ps_output
    )

    discovered = processes.discover_python_processes()

    assert [process.pid for process in discovered] == [101]


def test_discover_python_processes_ps_fallback_handles_malformed_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_proc = tmp_path / "missing-proc"
    ps_output = "\n".join(
        [
            " 101 /usr/bin/python3.12 /usr/bin/python3.12 /app/target.py",
            "",
            "not-a-pid /usr/bin/python3.12 /app/bad.py",
            " 202",
        ]
    )

    monkeypatch.setattr(processes, "PROC_DIR", missing_proc)
    monkeypatch.setattr(processes.os, "getpid", lambda: 999)
    monkeypatch.setattr(
        processes.subprocess, "check_output", lambda *args, **kwargs: ps_output
    )

    discovered = processes.discover_python_processes()

    assert [process.pid for process in discovered] == [101]


def test_discover_python_processes_ps_fallback_handles_shlex_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_proc = tmp_path / "missing-proc"
    ps_output = " 101 /usr/bin/python3.12 /usr/bin/python3.12 'unclosed-quote"

    monkeypatch.setattr(processes, "PROC_DIR", missing_proc)
    monkeypatch.setattr(processes.os, "getpid", lambda: 999)
    monkeypatch.setattr(
        processes.subprocess, "check_output", lambda *args, **kwargs: ps_output
    )

    discovered = processes.discover_python_processes()

    assert len(discovered) == 1
    assert discovered[0].pid == 101
