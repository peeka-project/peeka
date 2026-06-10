"""Tests for DashboardView runtime metadata rendering."""

from collections.abc import Callable
from typing import cast

import pytest
from textual.widgets import Static

from peeka.tui.app import PeekaApp
from peeka.core.client import StreamingAgentClient
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.dashboard import DashboardView
from tests.tui.conftest import MockStreamingAgentClient


def _runtime_text(app: PeekaApp) -> str:
    """Return the rendered dashboard runtime text."""
    runtime_info = app.screen.query_one("#dash-runtime-info", Static)
    return str(runtime_info.render())


@pytest.mark.tui
class TestDashboardRuntimeMeta:
    """Test dashboard runtime metadata contract for gevent-aware targets."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_runtime_info_shows_gevent_patched_status(
        self, mock_client_factory: Callable[..., MockStreamingAgentClient]
    ):
        """Dashboard runtime info should show gevent patched status."""
        client: MockStreamingAgentClient = mock_client_factory(
            responses={
                "patch-status": {
                    "status": "success",
                    "gevent_state": "patched",
                    "backend": "wrapper_only",
                    "downgraded": False,
                    "degraded_reason": None,
                }
            }
        )
        _ = client.connect()

        app = PeekaApp()
        async with app.run_test(size=(140, 24)) as pilot:  # pyright: ignore[reportUnknownVariableType]
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(cast(StreamingAgentClient, cast(object, client)))

            await pilot.pause()
            await pilot.pause()

            content = _runtime_text(app)
            assert "Gevent" in content
            assert "patched" in content

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_runtime_info_shows_backend_mode(
        self, mock_client_factory: Callable[..., MockStreamingAgentClient]
    ):
        """Dashboard runtime info should show gevent backend mode."""
        client: MockStreamingAgentClient = mock_client_factory(
            responses={
                "patch-status": {
                    "status": "success",
                    "gevent_state": "patched",
                    "backend": "wrapper_only",
                    "downgraded": False,
                    "degraded_reason": None,
                }
            }
        )
        _ = client.connect()

        app = PeekaApp()
        async with app.run_test(size=(140, 24)) as pilot:  # pyright: ignore[reportUnknownVariableType]
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(cast(StreamingAgentClient, cast(object, client)))

            await pilot.pause()
            await pilot.pause()

            content = _runtime_text(app)
            assert "Backend" in content
            assert "wrapper_only" in content

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_runtime_info_shows_downgraded_reason(
        self, mock_client_factory: Callable[..., MockStreamingAgentClient]
    ):
        """Dashboard runtime info should show gevent downgrade reason."""
        client: MockStreamingAgentClient = mock_client_factory(
            responses={
                "patch-status": {
                    "status": "success",
                    "gevent_state": "patched",
                    "backend": "wrapper_only",
                    "downgraded": True,
                    "degraded_reason": "sys.settrace under gevent can violate frame stack invariants",
                }
            }
        )
        _ = client.connect()

        app = PeekaApp()
        async with app.run_test(size=(140, 24)) as pilot:  # pyright: ignore[reportUnknownVariableType]
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            dashboard = app.screen.query_one("DashboardView", DashboardView)
            dashboard.set_client(cast(StreamingAgentClient, cast(object, client)))

            await pilot.pause()
            await pilot.pause()

            content = _runtime_text(app)
            assert "Downgraded" in content
            assert "frame stack invariants" in content

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_runtime_info_geometrically_stable(
        self, mock_client_factory: Callable[..., MockStreamingAgentClient]
    ):
        """Dashboard runtime info should keep a non-zero region at common widths."""
        client: MockStreamingAgentClient = mock_client_factory(
            responses={
                "patch-status": {
                    "status": "success",
                    "gevent_state": "patched",
                    "backend": "wrapper_only",
                    "downgraded": False,
                    "degraded_reason": None,
                }
            }
        )
        _ = client.connect()

        for size in ((140, 24), (80, 24)):
            app = PeekaApp()
            async with app.run_test(size=size) as pilot:  # pyright: ignore[reportUnknownVariableType]
                main_screen = MainScreen(
                    pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
                )
                await app.push_screen(main_screen)
                await pilot.pause()

                dashboard = app.screen.query_one("DashboardView", DashboardView)
                dashboard.set_client(cast(StreamingAgentClient, cast(object, client)))

                await pilot.pause()
                await pilot.pause()

                runtime_info = app.screen.query_one("#dash-runtime-info", Static)
                region = runtime_info.region
                assert region.x >= 0
                assert region.y >= 0
                assert region.width > 0
                assert region.height > 0
                assert "Gevent" in str(runtime_info.render())
