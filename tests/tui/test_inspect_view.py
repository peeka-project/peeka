"""Tests for InspectView - data-flow and error handling."""

import pytest
from textual.widgets import Input, Tree, Pretty

from peeka.tui.app import PeekaApp
from peeka.tui.screens.main import MainScreen
from peeka.tui.views.inspect import InspectView


class ActionRoutingClient:
    """Mock client that routes vmtool commands by action field."""

    def __init__(self, action_responses):
        self.action_responses = action_responses
        self.connected = False
        self.commands_received = []

    def connect(self):
        self.connected = True
        return {"status": "success"}

    def disconnect(self):
        self.connected = False

    def send_command(self, command):
        if not self.connected:
            return {"status": "error", "error": "Not connected"}
        self.commands_received.append(command)
        if command.get("type") == "vmtool":
            action = command.get("action")
            if action in self.action_responses:
                return self.action_responses[action]
            return {"status": "error", "error": f"Unknown action: {action}"}
        return {"status": "error", "error": f"Unknown type: {command.get('type')}"}


class TestInspectView:
    """Test InspectView widget population from mock client responses."""

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_inspect_simple_object_populates_tree(self):
        """Inspecting a simple object populates Tree widget with attributes."""
        inspect_client = ActionRoutingClient(
            action_responses={
                "get": {
                    "status": "success",
                    "type": "str",
                    "value": "3.12.0",
                },
            }
        )
        inspect_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            inspect_view = app.screen.query_one("InspectView", InspectView)
            inspect_view.set_client(inspect_client)

            input_widget = app.screen.query_one("#inspect-path", Input)
            input_widget.value = "sys.version"
            await pilot.pause()

            await inspect_view._inspect_object()
            await pilot.pause()

            commands = [cmd.get("action") for cmd in inspect_client.commands_received]
            assert "get" in commands

            tree = app.screen.query_one("#inspect-tree", Tree)
            assert str(tree.root.label) == "sys.version (str)"

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_inspect_nested_object_creates_tree_nodes(self):
        """Inspecting nested object creates expandable tree nodes."""
        inspect_client = ActionRoutingClient(
            action_responses={
                "get": {
                    "status": "success",
                    "type": "dict",
                    "value": {
                        "__class__": "MyClass",
                        "name": "test",
                        "config": {"debug": True, "timeout": 30},
                        "items": ["item1", "item2"],
                    },
                },
            }
        )
        inspect_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            inspect_view = app.screen.query_one("InspectView", InspectView)
            inspect_view.set_client(inspect_client)

            input_widget = app.screen.query_one("#inspect-path", Input)
            input_widget.value = "module.MyClass"
            await pilot.pause()

            await inspect_view._inspect_object()
            await pilot.pause()

            tree = app.screen.query_one("#inspect-tree", Tree)
            assert str(tree.root.label) == "module.MyClass (dict)"
            assert len(list(tree.root.children)) > 0

            child_labels = [str(child.label) for child in tree.root.children]
            assert any("config" in label for label in child_labels)
            assert any("items" in label for label in child_labels)

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_inspect_list_creates_indexed_nodes(self):
        """Inspecting list creates indexed tree nodes."""
        inspect_client = ActionRoutingClient(
            action_responses={
                "get": {
                    "status": "success",
                    "type": "list",
                    "value": [
                        {"name": "item1", "value": 100},
                        {"name": "item2", "value": 200},
                        "simple_string",
                    ],
                },
            }
        )
        inspect_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            inspect_view = app.screen.query_one("InspectView", InspectView)
            inspect_view.set_client(inspect_client)

            input_widget = app.screen.query_one("#inspect-path", Input)
            input_widget.value = "module.items"
            await pilot.pause()

            await inspect_view._inspect_object()
            await pilot.pause()

            tree = app.screen.query_one("#inspect-tree", Tree)
            assert str(tree.root.label) == "module.items (list)"
            assert len(list(tree.root.children)) >= 3

            child_labels = [str(child.label) for child in tree.root.children]
            assert any("[0]" in label for label in child_labels)
            assert any("[1]" in label for label in child_labels)
            assert any("[2]" in label for label in child_labels)

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_inspect_updates_pretty_widget(self):
        """Inspecting object updates Pretty widget with formatted value."""
        inspect_client = ActionRoutingClient(
            action_responses={
                "get": {
                    "status": "success",
                    "type": "dict",
                    "value": {"key1": "value1", "key2": 123, "key3": True},
                },
            }
        )
        inspect_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            inspect_view = app.screen.query_one("InspectView", InspectView)
            inspect_view.set_client(inspect_client)

            input_widget = app.screen.query_one("#inspect-path", Input)
            input_widget.value = "module.data"
            await pilot.pause()

            await inspect_view._inspect_object()
            await pilot.pause()

            pretty = app.screen.query_one("#inspect-details", Pretty)
            assert pretty._pretty_renderable is not None

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_inspect_error_displays_notification(self, mock_client_factory):
        """InspectView displays error notification for failed inspection."""
        error_client = mock_client_factory(
            responses={
                "vmtool": {"status": "error", "error": "Object not found"},
            }
        )
        error_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            inspect_view = app.screen.query_one("InspectView", InspectView)
            inspect_view.set_client(error_client)

            input_widget = app.screen.query_one("#inspect-path", Input)
            input_widget.value = "invalid.object"
            await pilot.pause()

            await inspect_view._inspect_object()
            await pilot.pause()

            tree = app.screen.query_one("#inspect-tree", Tree)
            assert len(list(tree.root.children)) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_empty_expression_shows_warning(self):
        """InspectView shows warning when inspecting empty expression."""
        inspect_client = ActionRoutingClient(action_responses={})
        inspect_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            inspect_view = app.screen.query_one("InspectView", InspectView)
            inspect_view.set_client(inspect_client)

            input_widget = app.screen.query_one("#inspect-path", Input)
            input_widget.value = "   "
            await pilot.pause()

            await inspect_view._inspect_object()
            await pilot.pause()

            assert len(inspect_client.commands_received) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_no_client_shows_warning(self):
        """InspectView shows warning when no client is connected."""
        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            inspect_view = app.screen.query_one("InspectView", InspectView)

            input_widget = app.screen.query_one("#inspect-path", Input)
            input_widget.value = "sys.version"
            await pilot.pause()

            await inspect_view._inspect_object()
            await pilot.pause()

            tree = app.screen.query_one("#inspect-tree", Tree)
            assert len(list(tree.root.children)) == 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_inspect_deeply_nested_structure(self):
        """InspectView handles deeply nested structures with depth limit."""
        inspect_client = ActionRoutingClient(
            action_responses={
                "get": {
                    "status": "success",
                    "type": "dict",
                    "value": {
                        "level1": {
                            "level2": {
                                "level3": {"level4": {"level5": "deep"}},
                            },
                        },
                    },
                },
            }
        )
        inspect_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            inspect_view = app.screen.query_one("InspectView", InspectView)
            inspect_view.set_client(inspect_client)

            input_widget = app.screen.query_one("#inspect-path", Input)
            input_widget.value = "module.nested"
            await pilot.pause()

            await inspect_view._inspect_object()
            await pilot.pause()

            tree = app.screen.query_one("#inspect-tree", Tree)
            assert str(tree.root.label) == "module.nested (dict)"
            assert len(list(tree.root.children)) > 0

    @pytest.mark.asyncio
    @pytest.mark.tui
    async def test_inspect_truncates_long_strings(self):
        """InspectView truncates long string values in tree display."""
        long_string = "a" * 100
        inspect_client = ActionRoutingClient(
            action_responses={
                "get": {
                    "status": "success",
                    "type": "dict",
                    "value": {
                        "short": "test",
                        "long": long_string,
                    },
                },
            }
        )
        inspect_client.connect()

        app = PeekaApp()
        async with app.run_test() as pilot:
            main_screen = MainScreen(
                pid=12345, session_id="test-session", socket_path="/tmp/test.sock"
            )
            await app.push_screen(main_screen)
            await pilot.pause()

            inspect_view = app.screen.query_one("InspectView", InspectView)
            inspect_view.set_client(inspect_client)

            input_widget = app.screen.query_one("#inspect-path", Input)
            input_widget.value = "module.data"
            await pilot.pause()

            await inspect_view._inspect_object()
            await pilot.pause()

            tree = app.screen.query_one("#inspect-tree", Tree)
            child_labels = [str(child.label) for child in tree.root.children]
            long_label = [label for label in child_labels if "long" in label][0]
            assert "..." in long_label or len(long_label) < len(long_string)
