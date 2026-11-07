"""Process selector: attached/attachable grouping, empty state, attach failures."""

from pathlib import Path
from typing import Optional

import pytest
from textual.widgets import DataTable, Static

from peeka.core.processes import PythonProcess
from peeka.tui.screens import process_selector
from tests.tui.test_process_selector import MockProcessApp, mock_targets, patch_discovery  # noqa: F401


def _process(pid: int, name: str, created_at: float) -> PythonProcess:
    return PythonProcess(
        pid=pid,
        name=name,
        command=f"python3.14 /app/{name}",
        executable="/usr/local/bin/python3.14",
        python_version="3.14",
        created_at=created_at,
    )


@pytest.mark.asyncio
@pytest.mark.tui
async def test_attached_targets_are_grouped_before_attachable(monkeypatch, mock_targets):  # noqa: F811
    """Attached rows come first even when attachable processes are older."""
    processes = [
        _process(2001, "old.py", 1.0),
        _process(2002, "new.py", 5000.0),
        # Already attached (alive target pid) → must not be listed twice.
        _process(1001, "attached.py", 2.0),
    ]
    patch_discovery(monkeypatch, mock_targets, processes)

    app = MockProcessApp()
    async with app.run_test(size=(140, 24)) as pilot:
        await pilot.pause()
        screen = app.screen_instance
        table = screen.query_one("#process-table", DataTable)

        keys = [row.key.value for row in table.ordered_rows]
        assert keys == [
            "target_00000001",  # alive
            "process_2001",  # attachable, oldest first
            "process_2002",
            "target_00000003",  # unknown
            "target_00000002",  # stale
        ]
        # Attached row shows process info for its pid.
        assert "attached.py" in str(table.get_row("target_00000001")[0])

        selector = screen.query_one("#process-selector")
        assert selector.border_subtitle == "1 attached · 2 attachable"
        assert screen.query_one("#empty-hint").styles.display == "none"


@pytest.mark.asyncio
@pytest.mark.tui
async def test_empty_state_hint_shown_when_no_processes(monkeypatch):
    patch_discovery(monkeypatch, [], [])

    app = MockProcessApp()
    async with app.run_test(size=(140, 24)) as pilot:
        await pilot.pause()
        screen = app.screen_instance
        hint = screen.query_one("#empty-hint", Static)
        assert hint.styles.display == "block"
        assert "PID namespace" in str(hint.render())
        assert screen.query_one("#process-selector").border_subtitle == (
            "0 attached · 0 attachable"
        )


@pytest.mark.asyncio
@pytest.mark.tui
async def test_empty_state_hint_hidden_when_filter_matches_nothing(monkeypatch):
    patch_discovery(monkeypatch, [], [_process(2001, "worker.py", 1.0)])

    app = MockProcessApp()
    async with app.run_test(size=(140, 24)) as pilot:
        await pilot.pause()
        screen = app.screen_instance
        screen.query_one("#filter").value = "zzz-no-match"
        await pilot.pause()
        table = screen.query_one("#process-table", DataTable)
        assert len(table.rows) == 0
        assert screen.query_one("#empty-hint").styles.display == "none"


class _FailingAttacher:
    def __init__(self, pid, **kwargs):
        self.pid = pid
        self.session_id = "s"

    def attach(self) -> bool:
        return False

    def get_last_error(self) -> Optional[str]:
        return "Operation not permitted"


@pytest.mark.asyncio
@pytest.mark.tui
async def test_selecting_attachable_process_shows_ptrace_failure(
    monkeypatch, tmp_path: Path
):
    """Selecting an unattached process runs attach and reports a concrete cause."""
    scope = tmp_path / "ptrace_scope"
    scope.write_text("1\n")
    monkeypatch.setattr(process_selector, "PTRACE_SCOPE_PATH", scope)
    monkeypatch.setattr(process_selector, "_geteuid", lambda: 1000)
    monkeypatch.setattr("peeka.core.attach.ProcessAttacher", _FailingAttacher)
    patch_discovery(monkeypatch, [], [_process(2001, "worker.py", 1.0)])
    # The fake pid does not exist; pretend it does so only ptrace is reported.
    monkeypatch.setattr(process_selector.os, "kill", lambda pid, sig: None)

    app = MockProcessApp()
    async with app.run_test(size=(140, 24)) as pilot:
        await pilot.pause()
        screen = app.screen_instance
        table = screen.query_one("#process-table", DataTable)
        table.focus()
        table.move_cursor(row=0)
        await pilot.press("enter")
        await app.workers.wait_for_complete()
        await pilot.pause()

        error = screen.query_one("#attach-error", Static)
        text = str(error.render())
        assert error.styles.display == "block"
        assert "Failed to attach to process 2001" in text
        assert "Operation not permitted" in text
        assert "ptrace_scope=1" in text
        assert "Python version mismatch" not in text
        assert screen._attaching is False
        assert table.disabled is False


def _hints(monkeypatch, tmp_path: Path, scope: Optional[str], euid: int, kill_exc=None):
    path = tmp_path / "ptrace_scope"
    if scope is not None:
        path.write_text(scope)
    monkeypatch.setattr(process_selector, "PTRACE_SCOPE_PATH", path)
    monkeypatch.setattr(process_selector, "_geteuid", lambda: euid)

    def fake_kill(pid, sig):
        if kill_exc is not None:
            raise kill_exc

    monkeypatch.setattr(process_selector.os, "kill", fake_kill)
    return process_selector.attach_failure_hints(42)


def test_hints_scope_2_for_non_root(monkeypatch, tmp_path):
    hints = _hints(monkeypatch, tmp_path, "2", euid=1000)
    assert len(hints) == 1 and "ptrace_scope=2" in hints[0]


def test_hints_ignore_scope_for_root(monkeypatch, tmp_path):
    hints = _hints(monkeypatch, tmp_path, "1", euid=0)
    assert not any("ptrace_scope" in hint for hint in hints)
    assert any("Python version mismatch" in hint for hint in hints)


def test_hints_missing_scope_file_falls_back_to_generic(monkeypatch, tmp_path):
    hints = _hints(monkeypatch, tmp_path, None, euid=1000)
    assert any("SYS_PTRACE" in hint for hint in hints)


def test_hints_other_user_process(monkeypatch, tmp_path):
    hints = _hints(monkeypatch, tmp_path, "0", euid=1000, kill_exc=PermissionError())
    assert hints == [
        "Process 42 is owned by another user: run peeka as that user "
        "or as root (CAP_SYS_PTRACE)."
    ]


def test_hints_exited_process(monkeypatch, tmp_path):
    hints = _hints(monkeypatch, tmp_path, "0", euid=1000, kill_exc=ProcessLookupError())
    assert hints == ["Process 42 has exited."]
