"""Tests for process_selector TUI component using discover_targets."""

import pytest
from textual.app import App, ComposeResult
from textual.widgets import DataTable

from peeka.tui.screens.process_selector import ProcessSelectorScreen
from peeka.core.targets import TargetAgent


class MockProcessApp(App[None]):
    """Test app for process selector."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.screen_instance = ProcessSelectorScreen()

    def compose(self) -> ComposeResult:
        yield self.screen_instance

    def on_ready(self) -> None:
        self.push_screen(self.screen_instance)


@pytest.fixture
def mock_targets():
    """Return mock target data for process selector."""
    return [
        TargetAgent(
            target_id="target_00000001",
            legacy_session_id="00000001",
            pid=1001,
            socket_path="/tmp/peeka_00000001.sock",
            state="alive",
            agent_mode="injected",
            injection_mode="pep768",
            python_version="3.14.0",
            peeka_version="0.1.0",
            created_at=1000.0,
            last_seen_at=2000.0,
        ),
        TargetAgent(
            target_id="target_00000002",
            legacy_session_id="00000002",
            pid=1002,
            socket_path="/tmp/peeka_00000002.sock",
            state="stale",
            agent_mode="injected",
            injection_mode="gdb_dlopen",
            python_version="3.12.0",
            peeka_version="0.1.0",
            created_at=1500.0,
            last_seen_at=2000.0,
        ),
        TargetAgent(
            target_id="target_00000003",
            legacy_session_id="00000003",
            pid=1003,
            socket_path="/tmp/peeka_00000003.sock",
            state="unknown",
            agent_mode="injected",
            injection_mode="pep768",
            python_version="3.14.0",
            peeka_version="0.1.0",
            created_at=1200.0,
            last_seen_at=2000.0,
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.tui
async def test_process_selector_uses_discover_targets(monkeypatch, mock_targets):
    """Verify process selector populates table from discover_targets."""
    monkeypatch.setattr("peeka.tui.screens.process_selector.discover_targets", lambda: mock_targets)
    
    app = MockProcessApp()
    async with app.run_test(size=(140, 24)) as pilot:
        await pilot.pause()
        
        table = app.screen.query_one("#process-table", DataTable)
        assert len(table.rows) == 3
        
        # Verify wide columns exist
        assert len(table.columns) == 6
        
        # Check first row (alive)
        row1 = table.get_row("target_00000001")
        assert "target_00000001" in str(row1[0])
        assert "1001" in str(row1[1])
        assert "alive" in str(row1[2])


@pytest.mark.asyncio
@pytest.mark.tui
async def test_process_selector_layout_140x24(monkeypatch, mock_targets):
    """Verify wide layout geometry requirements per DoD."""
    monkeypatch.setattr("peeka.tui.screens.process_selector.discover_targets", lambda: mock_targets)

    app = MockProcessApp()
    async with app.run_test(size=(140, 24)) as pilot:
        await pilot.pause()
        
        table = app.screen.query_one("#process-table", DataTable)
        
        # Assert region width of the table
        assert table.region.width > 100
        
        # We can't directly check column header geometry in textual DataTable easily,
        # but we can verify it has exactly 6 columns and region is correct.
        assert len(table.columns) == 6
        assert table.region.x >= 0


@pytest.mark.asyncio
@pytest.mark.tui
async def test_process_selector_layout_80x24(monkeypatch, mock_targets):
    """Verify narrow layout geometry requirements per DoD."""
    monkeypatch.setattr("peeka.tui.screens.process_selector.discover_targets", lambda: mock_targets)

    app = MockProcessApp()
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        
        table = app.screen.query_one("#process-table", DataTable)
        
        assert len(table.columns) == 3
        assert table.region.width <= 80


@pytest.mark.asyncio
@pytest.mark.tui
async def test_stale_row_disabled(monkeypatch, mock_targets):
    """Verify stale rows are shown but are disabled/unselectable."""
    monkeypatch.setattr("peeka.tui.screens.process_selector.discover_targets", lambda: mock_targets)

    # Mock the attach action to verify it doesn't get called
    attach_called = False
    def mock_attach(pid):
        nonlocal attach_called
        attach_called = True

    app = MockProcessApp()
    async with app.run_test(size=(140, 24)) as pilot:
        await pilot.pause()
        
        app.screen_instance._attach_to_process = mock_attach
        
        table = app.screen.query_one("#process-table", DataTable)
        table.focus()
        await pilot.pause()
        
        # Select the alive row
        table.move_cursor(row=0)
        await pilot.press("enter")
        await pilot.pause()
        
        assert attach_called is True
        
        # Reset and try stale row
        attach_called = False
        table.move_cursor(row=1)
        await pilot.press("enter")
        await pilot.pause()
        
        assert attach_called is False  # Should skip attach because it's stale
        
        # Try unknown row
        table.move_cursor(row=2)
        await pilot.press("enter")
        await pilot.pause()
        
        assert attach_called is False


@pytest.mark.asyncio
@pytest.mark.tui
async def test_refresh_keybinding_r(monkeypatch, mock_targets):
    """Verify pressing 'r' re-invokes discover_targets."""
    call_count = 0
    def mock_discover():
        nonlocal call_count
        call_count += 1
        return mock_targets
        
    monkeypatch.setattr("peeka.tui.screens.process_selector.discover_targets", mock_discover)

    app = MockProcessApp()
    async with app.run_test(size=(140, 24)) as pilot:
        await pilot.pause()
        
        assert call_count == 1  # Called on mount
        
        await pilot.press("r")
        await pilot.pause()
        
        assert call_count == 2  # Called again on refresh


def test_no_glob_calls():
    """Verify there are no glob.glob calls left in process_selector.py."""
    from pathlib import Path
    import re
    
    file_path = Path(__file__).parents[2] / "peeka" / "tui" / "screens" / "process_selector.py"
    content = file_path.read_text()
    
    assert not re.search(r"glob\.glob", content)
    assert not re.search(r"os\.listdir.*tmp", content)
    assert not re.search(r"ps aux", content)
