import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand
from peeka.core.agent_control.lifecycle import (
    stop_resource_owners_for_detach,
    stop_resource_owners_for_reset,
)

_LOG = logging.getLogger("test")


class _FakeDetachAndReset(ResourceOwningCommand):
    cleanup_scope = CleanupScope.DETACH_AND_RESET
    is_resource_owner = True

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
