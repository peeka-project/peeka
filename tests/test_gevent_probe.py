"""Tests for zero-side-effect gevent runtime probing."""

import sys
from typing import Optional

import pytest

from peeka.core.runtime.gevent_probe import GeventState, has_greenlet, probe


class FakeGeventMonkey:
    """Fake gevent.monkey module for state probing tests."""

    def __init__(self, socket_patched: bool = False, threading_patched: bool = False):
        self._socket_patched = socket_patched
        self._threading_patched = threading_patched

    def is_module_patched(self, module_name: str) -> bool:
        """Return configured patch state."""
        if module_name == "socket":
            return self._socket_patched
        if module_name == "threading":
            return self._threading_patched
        return False


class FakeGeventHub:
    """Fake gevent.hub module for active hub detection."""

    def __init__(self, hub: Optional[object]):
        self._hub = hub

    def _get_hub(self):
        """Return fake hub without creating one."""
        return self._hub


@pytest.mark.unit
class TestGeventProbe:
    """Probe contract tests."""

    def test_enum_values_are_frozen(self):
        """Verify public gevent state string values."""
        assert GeventState.NONE.value == "none"
        assert GeventState.IMPORTED.value == "imported"
        assert GeventState.PATCHED.value == "patched"
        assert GeventState.ACTIVE_HUB.value == "active_hub"

    def test_none_when_gevent_monkey_not_loaded(self, monkeypatch):
        """No gevent.monkey in sys.modules means none."""
        monkeypatch.delitem(sys.modules, "gevent.monkey", raising=False)
        monkeypatch.delitem(sys.modules, "gevent.hub", raising=False)

        assert probe() is GeventState.NONE

    def test_imported_when_gevent_monkey_loaded_but_unpatched(self, monkeypatch):
        """Loaded gevent.monkey without patched modules means imported."""
        monkeypatch.setitem(sys.modules, "gevent.monkey", FakeGeventMonkey())
        monkeypatch.delitem(sys.modules, "gevent.hub", raising=False)

        assert probe() is GeventState.IMPORTED

    def test_patched_when_socket_or_threading_is_patched(self, monkeypatch):
        """Patched socket/threading without hub means patched."""
        monkeypatch.setitem(
            sys.modules,
            "gevent.monkey",
            FakeGeventMonkey(socket_patched=True),
        )
        monkeypatch.delitem(sys.modules, "gevent.hub", raising=False)

        assert probe() is GeventState.PATCHED

    def test_active_hub_when_patched_and_hub_exists(self, monkeypatch):
        """Patched modules plus initialized hub means active_hub."""
        monkeypatch.setitem(
            sys.modules,
            "gevent.monkey",
            FakeGeventMonkey(threading_patched=True),
        )
        monkeypatch.setitem(sys.modules, "gevent.hub", FakeGeventHub(object()))

        assert probe() is GeventState.ACTIVE_HUB

    def test_probe_does_not_change_sys_modules_keys(self, monkeypatch):
        """Probe must not import gevent or greenlet as a side effect."""
        monkeypatch.delitem(sys.modules, "gevent", raising=False)
        monkeypatch.delitem(sys.modules, "gevent.monkey", raising=False)
        monkeypatch.delitem(sys.modules, "gevent.hub", raising=False)
        monkeypatch.delitem(sys.modules, "greenlet", raising=False)
        before = set(sys.modules)

        assert probe() is GeventState.NONE

        assert set(sys.modules) == before

    def test_has_greenlet_uses_sys_modules_only(self, monkeypatch):
        """has_greenlet reflects already-loaded greenlet state."""
        monkeypatch.delitem(sys.modules, "greenlet", raising=False)
        assert has_greenlet() is False

        monkeypatch.setitem(sys.modules, "greenlet", object())
        assert has_greenlet() is True
