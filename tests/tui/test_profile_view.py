"""Tests for Profile view."""

from pathlib import Path

import pytest
from textual.widgets import Button, DataTable, Static

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.profile import ProfileView


class TestProfileView:
    """Test ProfileView functionality and layout."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_list_sessions(self, mock_client_factory):
        """Test that ProfileView fetches and displays sessions."""
        client = mock_client_factory(
            responses={
                "profile": {
                    "status": "success",
                    "sessions": [
                        {
                            "profile_id": "prof_1",
                            "backend": "sys_monitoring",
                            "status": "running",
                            "started_at": "12:00:00",
                            "sample_count": 100,
                        },
                        {
                            "profile_id": "prof_2",
                            "backend": "gdb",
                            "status": "stopped",
                            "started_at": "12:05:00",
                            "sample_count": 50,
                        },
                    ],
                },
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            # Switch to Profile tab
            main_screen.action_switch_tab("profile")
            await pilot.pause()

            # Inject the mock client
            profile_view = app.screen.query_one(ProfileView)
            profile_view._client = client
            profile_view._own_client = client
            
            # Trigger refresh explicitly to bypass lazy connection logic in test
            profile_view.action_refresh()
            await pilot.pause()

            # Assert DataTable has 2 rows
            table = profile_view.query_one("#profile-table", DataTable)
            assert table.row_count == 2
            
            # Check row contents
            row0 = table.get_row_at(0)
            assert row0[0] == "prof_1"
            assert row0[2] == "running"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_geometry_80x24(self, mock_client_factory):
        """Test DataTable fills width correctly at 80x24."""
        client = mock_client_factory(responses={"profile": {"status": "success", "sessions": []}})
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(80, 24)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("profile")
            await pilot.pause()

            profile_view = app.screen.query_one(ProfileView)
            table = profile_view.query_one("#profile-table", DataTable)
            
            # Verify region width is at least 60px
            assert table.region.width >= 60

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_geometry_140x24(self, mock_client_factory):
        """Test DataTable fills width correctly at 140x24."""
        client = mock_client_factory(responses={"profile": {"status": "success", "sessions": []}})
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(140, 24)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("profile")
            await pilot.pause()

            profile_view = app.screen.query_one(ProfileView)
            table = profile_view.query_one("#profile-table", DataTable)
            
            # Verify region width is at least 100px
            assert table.region.width >= 100

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_export_flow(self, mock_client_factory):
        """Test selecting a session and exporting."""
        client = mock_client_factory(
            responses={
                "profile": {
                    "status": "success",
                    "sessions": [
                        {
                            "profile_id": "prof_123",
                            "backend": "gdb",
                            "status": "stopped",
                            "started_at": "12:00:00",
                            "sample_count": 100,
                        }
                    ],
                },
            }
        )
        client.connect()

        app = PeekaApp()
        async with app.run_test(size=(120, 40)) as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            main_screen.action_switch_tab("profile")
            await pilot.pause()

            profile_view = app.screen.query_one(ProfileView)
            profile_view._client = client
            profile_view._own_client = client
            profile_view.action_refresh()
            await pilot.pause()

            # Now mock the export response
            client.responses["profile"] = {
                "status": "success",
                "content": '{"profile_id":"prof_123"}',
                "format": "json",
            }

            table = profile_view.query_one("#profile-table", DataTable)
            
            # Select the first row to enable export button
            table.action_cursor_down()
            table.action_select_cursor()
            await pilot.pause()
            
            # The manual test workaround for triggering the event
            profile_view.on_data_table_row_selected(
                DataTable.RowSelected(
                    data_table=table,
                    row_key=table.coordinate_to_cell_key(table.cursor_coordinate).row_key,
                    cursor_row=table.cursor_coordinate.row
                )
            )
            await pilot.pause()

            # Verify export button is enabled
            export_btn = profile_view.query_one("#profile-export-btn", Button)
            assert export_btn.disabled is False

            # Click export
            profile_view.on_button_pressed(Button.Pressed(button=export_btn))
            await pilot.pause()

            # Verify export command sent
            export_cmds = [
                c for c in client.commands_received
                if c.get("type") == "profile" and c.get("action") == "export"
            ]
            assert len(export_cmds) >= 1
            assert export_cmds[0].get("profile_id") == "prof_123"
            assert export_cmds[0].get("format") == "json"

            assert profile_view._last_export_path is not None
            export_path = Path(profile_view._last_export_path)
            assert export_path.suffix == ".json"
            assert export_path.read_text(encoding="utf-8") == '{"profile_id":"prof_123"}'
            export_path.unlink()
