"""
Tests for peeka.commands.detach.DetachCommand
"""

import pytest
from unittest.mock import MagicMock, PropertyMock

from peeka.commands.detach import DetachCommand


class TestDetachCommand:
    """Test the DetachCommand class."""

    def test_execute_success(self):
        """Test successful detach execution."""
        # Create mock agent
        mock_agent = MagicMock()
        mock_agent.attached_pid = 12345
        mock_agent.injector = MagicMock()
        mock_agent.observer = MagicMock()

        cmd = DetachCommand(mock_agent)
        result = cmd.execute({})

        # Verify result
        assert result["status"] == "success"
        assert result["pid"] == 12345
        assert "Detached from process" in result["message"]

        # Verify cleanup was called
        mock_agent.injector.uninject_all.assert_called_once()
        mock_agent.observer.clear_all.assert_called_once()
        mock_agent.stop.assert_called_once()

    def test_execute_calls_in_order(self):
        """Test that cleanup happens in correct order."""
        mock_agent = MagicMock()
        mock_agent.attached_pid = 9999

        call_order = []

        def track_uninject():
            call_order.append("uninject_all")

        def track_clear():
            call_order.append("clear_all")

        def track_stop():
            call_order.append("stop")

        mock_agent.injector.uninject_all.side_effect = track_uninject
        mock_agent.observer.clear_all.side_effect = track_clear
        mock_agent.stop.side_effect = track_stop

        cmd = DetachCommand(mock_agent)
        cmd.execute({})

        # uninject_all and clear_all should happen before stop
        assert call_order == ["uninject_all", "clear_all", "stop"]

    def test_execute_error_during_uninject(self):
        """Test error handling when uninject fails."""
        mock_agent = MagicMock()
        mock_agent.injector.uninject_all.side_effect = Exception("Uninject failed")

        cmd = DetachCommand(mock_agent)
        result = cmd.execute({})

        assert result["status"] == "error"
        assert "Uninject failed" in result["error"]

    def test_execute_error_during_clear(self):
        """Test error handling when clear_all fails."""
        mock_agent = MagicMock()
        mock_agent.injector = MagicMock()
        mock_agent.observer.clear_all.side_effect = Exception("Clear failed")

        cmd = DetachCommand(mock_agent)
        result = cmd.execute({})

        assert result["status"] == "error"
        assert "Clear failed" in result["error"]

    def test_execute_error_during_stop(self):
        """Test error handling when stop fails."""
        mock_agent = MagicMock()
        mock_agent.attached_pid = 12345
        mock_agent.injector = MagicMock()
        mock_agent.observer = MagicMock()
        mock_agent.stop.side_effect = Exception("Stop failed")

        cmd = DetachCommand(mock_agent)
        result = cmd.execute({})

        assert result["status"] == "error"
        assert "Stop failed" in result["error"]

    def test_execute_with_params_ignored(self):
        """Test that params are accepted but not used."""
        mock_agent = MagicMock()
        mock_agent.attached_pid = 1000

        cmd = DetachCommand(mock_agent)
        result = cmd.execute({"unused": "param", "another": 123})

        assert result["status"] == "success"
        assert result["pid"] == 1000

    def test_command_stores_agent(self):
        """Test that command stores agent reference."""
        mock_agent = MagicMock()
        cmd = DetachCommand(mock_agent)

        assert cmd.agent is mock_agent
