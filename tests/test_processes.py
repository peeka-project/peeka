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


def _patch_proc(
    monkeypatch: pytest.MonkeyPatch, proc_root: Path, exe_paths: dict
) -> None:
    def fake_readlink(path: str) -> str:
        if path not in exe_paths:
            raise PermissionError(path)
        return exe_paths[path]

    monkeypatch.setattr(processes, "PROC_DIR", proc_root)
    monkeypatch.setattr(processes.os, "getpid", lambda: 1)
    monkeypatch.setattr(processes.os, "readlink", fake_readlink)


def test_discover_python_processes_reads_minor_version_from_libpython_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    entry = _write_proc_entry(proc_root, 610, ["python3", "/app/app.py"], "python3")
    _ = (entry / "maps").write_text(
        "7f00-7f10 r-xp 0 08:01 1 /usr/lib/libc.so.6\n"
        "7f20-7f30 r-xp 0 08:01 2 /usr/local/lib/libpython3.14.so.1.0\n",
        encoding="utf-8",
    )
    _patch_proc(monkeypatch, proc_root, {str(entry / "exe"): "/usr/local/bin/python3"})

    discovered = processes.discover_python_processes()

    assert [p.python_version for p in discovered] == ["3.14"]


def test_discover_python_processes_keeps_exe_version_over_maps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    entry = _write_proc_entry(proc_root, 611, ["python3.12", "/app/app.py"], "python3.12")
    _ = (entry / "maps").write_text("x /usr/lib/libpython3.11.so\n", encoding="utf-8")
    _patch_proc(monkeypatch, proc_root, {str(entry / "exe"): "/usr/bin/python3.12"})

    assert [p.python_version for p in processes.discover_python_processes()] == ["3.12"]


def test_discover_python_processes_handles_unreadable_exe_and_maps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Processes of other users: exe/maps raise EACCES but cmdline is readable."""
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    entry = _write_proc_entry(proc_root, 620, ["/usr/bin/python3", "srv.py"], "python3")
    (entry / "maps").mkdir()  # reading a directory raises OSError
    _patch_proc(monkeypatch, proc_root, {})

    discovered = processes.discover_python_processes()

    assert [(p.pid, p.executable, p.python_version) for p in discovered] == [
        (620, "", "3")
    ]


def test_discover_python_processes_skips_fully_unreadable_entries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc_root = tmp_path / "proc"
    proc_root.mkdir()
    (proc_root / "630").mkdir()  # no cmdline/comm: vanished or hidden
    (proc_root / "self").mkdir()
    _patch_proc(monkeypatch, proc_root, {})

    assert processes.discover_python_processes() == []


@pytest.mark.parametrize(
    "command, is_tool",
    [
        ("/venv/bin/python3 /venv/bin/peeka", True),
        ("/venv/bin/python3 /venv/bin/peeka-cli attach 1", True),
        ("python3 -X dev -m peeka.tui", True),
        ("python3 -m peeka.cli.main targets", True),
        ("/usr/local/bin/peeka", True),
        ("python3 /srv/app.py --data-dir /srv/peeka", False),
        ("python3 -m uvicorn app:main --app-dir /home/u/peeka", False),
        ("python3 /home/u/peeka/examples/demo.py", False),
        ("python3 -m peekaboo", False),
        ("", False),
    ],
)
def test_is_peeka_tool_process_only_inspects_program_and_workload(
    command: str, is_tool: bool
) -> None:
    assert processes._is_peeka_tool_process(command) is is_tool
