# pyright: reportAny=false, reportExplicitAny=false, reportDeprecated=false, reportMissingSuperCall=false, reportUnusedCallResult=false

"""RED tests for LoggerCommand resource-owning level restoration."""

import logging
import threading
import uuid
from typing import Dict, Generator, List, Optional

import pytest

from peeka.commands.logger import LoggerCommand
from peeka.commands.resource_owning import CleanupScope
from peeka.core.agent import PeekaAgent


class _StubAgent(PeekaAgent):
    """Plain stub for LoggerCommand construction."""

    agent: "_StubAgent"

    def __init__(self) -> None:
        self.agent = self


@pytest.fixture()
def _restore_logger_levels() -> Generator[Dict[str, int], None, None]:  # pyright: ignore[reportUnusedFunction]
    """Track logger levels and restore them after each test."""

    originals: Dict[str, int] = {}
    yield originals

    for name, level in originals.items():
        logging.getLogger(name).setLevel(level)


def _make_logger_name(suffix: str) -> str:
    """Create a unique logger name for test isolation."""

    return "peeka_test_g7_%s.%s" % (uuid.uuid4().hex[:8], suffix)


def _remember_original_level(
    tracked: Optional[Dict[str, int]], name: str
) -> int:
    """Record and return the current logger level."""

    level = logging.getLogger(name).level
    if tracked is not None:
        tracked[name] = level
    return level


def test_logger_command_is_resource_owner() -> None:
    cmd_class = LoggerCommand

    assert "is_resource_owner" in cmd_class.__dict__
    assert cmd_class.__dict__["is_resource_owner"] is True
    assert "cleanup_scope" in cmd_class.__dict__
    assert cmd_class.__dict__["cleanup_scope"] == CleanupScope.DETACH_ONLY


def test_first_set_records_original_level(_restore_logger_levels: Dict[str, int]) -> None:
    name = _make_logger_name("first")
    original_level_before_set = _remember_original_level(_restore_logger_levels, name)
    cmd = LoggerCommand(_make_stub_agent())
    set_logger_level = getattr(cmd, "_set_logger_level")

    _ = set_logger_level({"name": name, "level": "DEBUG"})

    original_levels: Dict[str, int] = getattr(cmd, "_original_levels")
    assert original_levels[name] == original_level_before_set


def test_subsequent_set_does_not_overwrite_original(
    _restore_logger_levels: Dict[str, int],
) -> None:
    name = _make_logger_name("repeat")
    original_level_before_set = _remember_original_level(_restore_logger_levels, name)
    cmd = LoggerCommand(_make_stub_agent())
    set_logger_level = getattr(cmd, "_set_logger_level")

    _ = set_logger_level({"name": name, "level": "DEBUG"})
    mid_level_after_first_set = logging.getLogger(name).level
    _ = set_logger_level({"name": name, "level": "ERROR"})

    original_levels: Dict[str, int] = getattr(cmd, "_original_levels")
    assert original_levels[name] == original_level_before_set
    assert original_levels[name] != mid_level_after_first_set


def test_stop_active_resources_restores_levels(
    _restore_logger_levels: Dict[str, int],
) -> None:
    name = _make_logger_name("restore")
    original_level = _remember_original_level(_restore_logger_levels, name)
    cmd = LoggerCommand(_make_stub_agent())
    set_logger_level = getattr(cmd, "_set_logger_level")
    stop_active_resources = getattr(cmd, "stop_active_resources")

    _ = set_logger_level({"name": name, "level": "DEBUG"})
    _ = stop_active_resources(None, "detach")

    assert logging.getLogger(name).level == original_level


def test_stop_active_resources_pattern_filter(
    _restore_logger_levels: Dict[str, int],
) -> None:
    names = ["test.a", "test.b", "other.c"]
    original_levels = {name: _remember_original_level(_restore_logger_levels, name) for name in names}
    cmd = LoggerCommand(_make_stub_agent())
    set_logger_level = getattr(cmd, "_set_logger_level")
    stop_active_resources = getattr(cmd, "stop_active_resources")

    _ = set_logger_level({"name": "test.a", "level": "DEBUG"})
    _ = set_logger_level({"name": "test.b", "level": "ERROR"})
    _ = set_logger_level({"name": "other.c", "level": "CRITICAL"})
    _ = stop_active_resources(pattern="test.*", reason="detach")

    assert logging.getLogger("test.a").level == original_levels["test.a"]
    assert logging.getLogger("test.b").level == original_levels["test.b"]
    assert logging.getLogger("other.c").level != original_levels["other.c"]


def test_stop_active_resources_returns_stopped_and_errors_keys(
    _restore_logger_levels: Dict[str, int],
) -> None:
    name = _make_logger_name("keys")
    _remember_original_level(_restore_logger_levels, name)
    cmd = LoggerCommand(_make_stub_agent())
    set_logger_level = getattr(cmd, "_set_logger_level")
    stop_active_resources = getattr(cmd, "stop_active_resources")

    _ = set_logger_level({"name": name, "level": "DEBUG"})
    result = stop_active_resources(None, "detach")

    assert isinstance(result["stopped"], list)
    assert isinstance(result["errors"], list)


def test_list_active_resources_returns_active_key(
    _restore_logger_levels: Dict[str, int],
) -> None:
    name = _make_logger_name("list")
    _remember_original_level(_restore_logger_levels, name)
    cmd = LoggerCommand(_make_stub_agent())
    set_logger_level = getattr(cmd, "_set_logger_level")
    list_active_resources = getattr(cmd, "list_active_resources")

    _ = set_logger_level({"name": name, "level": "DEBUG"})
    result = list_active_resources()

    assert isinstance(result["active"], list)
    assert result["active"]
    assert isinstance(result["active"][0], dict)
    assert {"name", "original_level", "current_level"}.issubset(result["active"][0])


def test_concurrent_first_set_records_each_name_once(
    _restore_logger_levels: Dict[str, int],
) -> None:
    names = [_make_logger_name("thread_%d" % index) for index in range(5)]
    for name in names:
        _remember_original_level(_restore_logger_levels, name)

    cmd = LoggerCommand(_make_stub_agent())
    set_logger_level = getattr(cmd, "_set_logger_level")
    errors: List[Exception] = []
    lock = threading.Lock()

    def _worker(target_name: str) -> None:
        try:
            _ = set_logger_level({"name": target_name, "level": "DEBUG"})
        except Exception as exc:  # pragma: no cover - red-phase guard
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(name,)) for name in names]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    original_levels: Dict[str, int] = getattr(cmd, "_original_levels")
    assert len(original_levels) == len(names)
    for name in names:
        assert name in original_levels


def _make_stub_agent() -> _StubAgent:
    """Build a PeekaAgent-compatible stub without running __init__."""

    stub = object.__new__(_StubAgent)
    stub.agent = stub
    return stub
