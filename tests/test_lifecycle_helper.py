import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand
from peeka.core.agent_control.lifecycle import (
    shutdown_agent_resources,
    stop_resource_owners_for_detach,
    stop_resource_owners_for_reset,
)

_LOG = logging.getLogger("test")


class _FakeDetachAndReset(ResourceOwningCommand):
    cleanup_scope = CleanupScope.DETACH_AND_RESET
    is_resource_owner = True
    category = "probe"
    allows_concurrent = False

    def __init__(self, agent: Any = None) -> None:
        super().__init__(agent=agent)
        self.stop_calls: List[Dict[str, Any]] = []

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "success"}

    def stop_active_resources(
        self, pattern: Optional[str], reason: str
    ) -> Dict[str, Any]:
        self.stop_calls.append({"pattern": pattern, "reason": reason})
        return {"stopped": [], "errors": []}

    def list_active_resources(self) -> Dict[str, Any]:
        return {"active": []}


class _FakeDetachOnly(ResourceOwningCommand):
    cleanup_scope = CleanupScope.DETACH_ONLY
    is_resource_owner = True
    category = "probe"
    allows_concurrent = False

    def __init__(self, agent: Any = None) -> None:
        super().__init__(agent=agent)
        self.stop_calls: List[Dict[str, Any]] = []

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"status": "success"}

    def stop_active_resources(
        self, pattern: Optional[str], reason: str
    ) -> Dict[str, Any]:
        self.stop_calls.append({"pattern": pattern, "reason": reason})
        return {"stopped": [], "errors": []}

    def list_active_resources(self) -> Dict[str, Any]:
        return {"active": []}


def _make_agent(handlers_dict: Any) -> Any:
    class _Agent:
        def __init__(self, h: Any) -> None:
            self.command_handlers = h

    return _Agent(handlers_dict)


@pytest.mark.unit
class TestLifecycleHelper:
    def test_shutdown_helper_runs_all_steps(self) -> None:
        class _Injector:
            def __init__(self, calls: List[str]) -> None:
                self.calls = calls

            def uninject_all(self) -> None:
                self.calls.append("uninject_all")

            def cleanup_orphan_watches(self) -> int:
                self.calls.append("orphan_watch_sweep")
                return 0

        class _Observer:
            def __init__(self, calls: List[str]) -> None:
                self.calls = calls

            def clear_all(self) -> None:
                self.calls.append("clear_all")

        class _ProbeRegistry:
            def __init__(self, calls: List[str]) -> None:
                self.calls = calls

            def cleanup(self, older_than_seconds: int = 600, completed_only: bool = True) -> List[str]:
                self.calls.append("probe_registry_sweep")
                return []

        class _Agent:
            def __init__(self) -> None:
                self.calls: List[str] = []
                self.command_handlers: Dict[str, Any] = {}
                self.injector = _Injector(self.calls)
                self.observer = _Observer(self.calls)
                self.probe_registry = _ProbeRegistry(self.calls)

            def stop_probe_contexts_by_type(self, probe_types: List[str]) -> None:
                self.calls.append("stop_probe_contexts")
                self.calls.extend(probe_types)

        agent = _Agent()

        result = shutdown_agent_resources(agent, _LOG, ["custom_probe"])

        assert result["steps_run"] == [
            "stop_resource_owners",
            "stop_probe_contexts",
            "uninject_all",
            "clear_all",
            "probe_registry_sweep",
            "orphan_watch_sweep",
        ]
        assert result["step_errors"] == {}
        assert agent.calls == ["stop_probe_contexts", "custom_probe", "uninject_all", "clear_all", "probe_registry_sweep", "orphan_watch_sweep"]

    def test_shutdown_helper_isolates_exceptions(self) -> None:
        class _Injector:
            def uninject_all(self) -> None:
                raise RuntimeError("boom")

            def cleanup_orphan_watches(self) -> int:
                return 0

        class _Observer:
            def __init__(self) -> None:
                self.cleared = False

            def clear_all(self) -> None:
                self.cleared = True

        class _ProbeRegistry:
            def cleanup(self, older_than_seconds: int = 600, completed_only: bool = True) -> List[str]:
                return []

        class _Agent:
            def __init__(self) -> None:
                self.command_handlers: Dict[str, Any] = {}
                self.injector = _Injector()
                self.observer = _Observer()
                self.probe_registry = _ProbeRegistry()

            def stop_probe_contexts_by_type(self, probe_types: List[str]) -> None:
                _ = probe_types

        agent = _Agent()

        result = shutdown_agent_resources(agent, _LOG, ["custom_probe"])

        assert result["step_errors"]["uninject_all"] == "boom"
        assert "clear_all" in result["steps_run"]
        assert agent.observer.cleared is True

    def test_detach_stops_all_resource_owners(self) -> None:
        dar = _FakeDetachAndReset()
        do_ = _FakeDetachOnly()
        agent = _make_agent({"a": dar, "b": do_})

        result = stop_resource_owners_for_detach(agent, _LOG)

        assert result["errors"] == []
        assert set(result["handlers_stopped"]) == {"_FakeDetachAndReset", "_FakeDetachOnly"}
        assert dar.stop_calls == [{"pattern": None, "reason": "detach"}]
        assert do_.stop_calls == [{"pattern": None, "reason": "detach"}]

    def test_reset_stops_only_detach_and_reset_owners(self) -> None:
        dar = _FakeDetachAndReset()
        do_ = _FakeDetachOnly()
        agent = _make_agent({"a": dar, "b": do_})

        result = stop_resource_owners_for_reset(agent, "some_pattern", _LOG)

        assert result["errors"] == []
        assert result["handlers_stopped"] == ["_FakeDetachAndReset"]
        assert dar.stop_calls == [{"pattern": "some_pattern", "reason": "reset"}]
        assert do_.stop_calls == []

    def test_detach_with_missing_command_handlers_is_safe(self) -> None:
        class _NoHandlerAgent:
            pass

        result = stop_resource_owners_for_detach(_NoHandlerAgent(), _LOG)

        assert result["handlers_stopped"] == []
        assert result["errors"] == []

    def test_detach_with_none_command_handlers_is_safe(self) -> None:
        agent = _make_agent(None)

        result = stop_resource_owners_for_detach(agent, _LOG)

        assert result["handlers_stopped"] == []
        assert result["errors"] == []

    def test_detach_skips_handler_with_invalid_cleanup_scope(self) -> None:
        class _InvalidCleanupScopeFake(ResourceOwningCommand):
            cleanup_scope = "not_an_enum_value"  # pyright: ignore[reportAssignmentType]
            is_resource_owner = True
            category = "probe"
            allows_concurrent = False

            def __init__(self, agent: Any = None) -> None:
                super().__init__(agent=agent)
                self.stop_calls: List[Dict[str, Any]] = []

            def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
                return {"status": "success"}

            def stop_active_resources(
                self, pattern: Optional[str], reason: str
            ) -> Dict[str, Any]:
                self.stop_calls.append({"pattern": pattern, "reason": reason})
                return {"stopped": [], "errors": []}

            def list_active_resources(self) -> Dict[str, Any]:
                return {"active": []}

        fake = _InvalidCleanupScopeFake()
        agent = _make_agent({"a": fake})

        result = stop_resource_owners_for_detach(agent, _LOG)

        assert result["handlers_stopped"] == []
        assert result["errors"] == []
        assert fake.stop_calls == []

    def test_detach_one_handler_exception_does_not_abort_other(self) -> None:
        class _RaisingFake(ResourceOwningCommand):
            cleanup_scope = CleanupScope.DETACH_AND_RESET
            is_resource_owner = True

            def __init__(self) -> None:
                super().__init__(agent=None)

            def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
                return {"status": "success"}

            def stop_active_resources(
                self, pattern: Optional[str], reason: str
            ) -> Dict[str, Any]:
                raise RuntimeError("boom")

            def list_active_resources(self) -> Dict[str, Any]:
                return {"active": []}

        raising = _RaisingFake()
        good = _FakeDetachAndReset()
        agent = _make_agent({"a": raising, "b": good})

        result = stop_resource_owners_for_detach(agent, _LOG)

        assert len(result["errors"]) == 1
        assert result["errors"][0]["handler"] == "_RaisingFake"
        assert "boom" in result["errors"][0]["error"]
        assert result["handlers_stopped"] == ["_FakeDetachAndReset"]
        assert good.stop_calls == [{"pattern": None, "reason": "detach"}]

    def test_detach_is_idempotent(self) -> None:
        dar = _FakeDetachAndReset()
        agent = _make_agent({"a": dar})

        result1 = stop_resource_owners_for_detach(agent, _LOG)
        result2 = stop_resource_owners_for_detach(agent, _LOG)

        assert result1["errors"] == []
        assert result2["errors"] == []
        assert result1["handlers_stopped"] == ["_FakeDetachAndReset"]
        assert result2["handlers_stopped"] == ["_FakeDetachAndReset"]
        assert len(dar.stop_calls) == 2

    def test_lifecycle_source_does_not_use_get_handler(self) -> None:
        import peeka.core.agent_control.lifecycle as _lifecycle_mod

        source_path = Path(_lifecycle_mod.__file__).with_suffix(".py")  # type: ignore[arg-type]
        source = source_path.read_text(encoding="utf-8")
        assert "_get_handler(" not in source

    def test_lifecycle_source_does_not_have_hardcoded_names(self) -> None:
        import peeka.core.agent_control.lifecycle as _lifecycle_mod

        source_path = Path(_lifecycle_mod.__file__).with_suffix(".py")  # type: ignore[arg-type]
        source = source_path.read_text(encoding="utf-8")
        assert '"monitor"' not in source
        assert '"top"' not in source
        assert '"memory"' not in source
