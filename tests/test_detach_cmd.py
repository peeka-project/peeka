"""
Tests for peeka.commands.detach.DetachCommand
"""

import sys
from typing import Any, List, cast
from unittest.mock import MagicMock

from peeka.commands.detach import DetachCommand


class LocalDetachAgent:
    """Small agent double that exercises real injector and observer cleanup."""

    def __init__(self):
        from peeka.core.injector import DecoratorInjector
        from peeka.core.observer import ObservationManager

        self.attached_pid: int = 12345
        self.observer = ObservationManager()
        self.injector = DecoratorInjector(cast(Any, self))
        self.stop_calls: int = 0

    def _send_observation(self, observation: Any) -> None:
        _ = observation
        pass

    def stop(self) -> None:
        self.stop_calls += 1
        _ = self.injector.uninject_all()


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
        result = cmd.execute({})

        assert result["status"] == "success"
        assert "uninject_all" in call_order
        assert "stop" in call_order

    def test_execute_error_during_uninject(self):
        """shutdown_agent_resources swallows per-step errors; detach must still return success."""
        mock_agent = MagicMock()
        mock_agent.injector.uninject_all.side_effect = Exception("Uninject failed")

        cmd = DetachCommand(mock_agent)
        result = cmd.execute({})

        assert result["status"] == "success"

    def test_execute_error_during_clear(self):
        """shutdown_agent_resources swallows per-step errors; detach must still return success."""
        mock_agent = MagicMock()
        mock_agent.injector = MagicMock()
        mock_agent.observer.clear_all.side_effect = Exception("Clear failed")

        cmd = DetachCommand(mock_agent)
        result = cmd.execute({})

        assert result["status"] == "success"

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

    def test_detach_clears_observers_and_uninjects(self):
        """Detach clears stream registrations and restores injected functions."""

        def func():
            return "original"

        test_module = type(sys)("test_detach_stream_observer")
        test_module.func = func
        sys.modules["test_detach_stream_observer"] = test_module

        try:
            agent = LocalDetachAgent()
            watch_id = agent.injector.inject(
                "test_detach_stream_observer.func",
                {"depth": 2, "command": "watch"},
            )
            agent.observer.register_watch(
                watch_id,
                "test_detach_stream_observer.func",
                {"command": "watch"},
            )

            assert test_module.func is not func
            assert agent.observer.get_all_stats()["active_watches"] == 1

            result = DetachCommand(cast(Any, agent)).execute({})

            assert result["status"] == "success"
            assert test_module.func is func
            assert agent.injector.instrumented == {}
            assert agent.observer.get_all_stats()["active_watches"] == 0
            assert agent.observer.get_watch_stats(watch_id) is None
            assert agent.stop_calls == 1

        finally:
            del sys.modules["test_detach_stream_observer"]

    def test_double_uninject_is_idempotent(self):
        """Detach uninjects first; a later agent stop can uninject again safely."""

        def func():
            return "original"

        test_module = type(sys)("test_detach_double_uninject")
        test_module.func = func
        sys.modules["test_detach_double_uninject"] = test_module

        try:
            agent = LocalDetachAgent()
            _ = agent.injector.inject(
                "test_detach_double_uninject.func",
                {"depth": 2, "command": "watch"},
            )

            result = DetachCommand(cast(Any, agent)).execute({})
            second_count = agent.injector.uninject_all()

            assert result["status"] == "success"
            assert second_count == 0
            assert test_module.func is func
            assert agent.injector.instrumented == {}

            agent.stop()
            assert agent.stop_calls == 2
            assert test_module.func is func

        finally:
            del sys.modules["test_detach_double_uninject"]


class TestDetachProbeContextCleanup:
    """Regression: detach stops all active probe contexts via probe registry."""

    def test_detach_calls_stop_probe_contexts_by_type(self):
        stopped_types: List[str] = []

        class _FakeAgent:
            attached_pid = 12345
            injector = MagicMock()
            observer = MagicMock()

            def stop_probe_contexts_by_type(self, probe_types: List[str]) -> None:
                stopped_types.extend(probe_types)

            def stop(self) -> None:
                pass

        result = DetachCommand(cast(Any, _FakeAgent())).execute({})

        assert result["status"] == "success"
        assert set(stopped_types) == {"watch", "trace", "stack", "monitor", "top"}

    def test_detach_probe_cleanup_before_uninject(self):
        call_order: List[str] = []

        class _FakeAgent:
            attached_pid = 12345

            def stop_probe_contexts_by_type(self, types: List[str]) -> None:
                _ = types
                call_order.append("stop_probe_contexts")

            @property
            def injector(self):
                class _Inj:
                    def uninject_all(self) -> None:
                        call_order.append("uninject_all")

                    def __getattr__(self, name: str) -> Any:
                        _ = name
                        return MagicMock()

                return _Inj()

            @property
            def observer(self):
                class _Obs:
                    def clear_all(self) -> None:
                        call_order.append("clear_all")

                return _Obs()

            def stop(self) -> None:
                call_order.append("stop")

        result = DetachCommand(cast(Any, _FakeAgent())).execute({})
        assert result["status"] == "success"
        assert "stop_probe_contexts" in call_order
        assert "uninject_all" in call_order
        assert "stop" in call_order
