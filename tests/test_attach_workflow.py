"""Tests for attach workflow readiness helpers."""

import sys
from types import ModuleType

import pytest

from peeka.core.attach_workflow.readiness import _cleanup_peeka_modules  # pyright: ignore[reportPrivateUsage]


@pytest.fixture(autouse=True)
def _restore_peeka_sys_modules():  # pyright: ignore[reportUnusedFunction]
    original_peeka_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == "peeka" or name.startswith("peeka.")
    }
    yield
    for name in list(sys.modules.keys()):
        if name == "peeka" or name.startswith("peeka."):
            _ = sys.modules.pop(name, None)
    sys.modules.update(original_peeka_modules)


def _make_module(name: str) -> ModuleType:
    module = ModuleType(name)
    return module


class TestCleanupPeekaModules:
    def test_cleanup_removes_peeka_modules(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setitem(sys.modules, "peeka", _make_module("peeka"))
        monkeypatch.setitem(sys.modules, "peeka.core", _make_module("peeka.core"))
        monkeypatch.setitem(
            sys.modules, "peeka.core.agent", _make_module("peeka.core.agent")
        )
        monkeypatch.setitem(sys.modules, "os", sys.modules["os"])
        monkeypatch.setitem(sys.modules, "sys", sys.modules["sys"])
        monkeypatch.setitem(sys.modules, "json", sys.modules["json"])

        _cleanup_peeka_modules()

        assert "peeka" not in sys.modules
        assert "peeka.core" not in sys.modules
        assert "peeka.core.agent" not in sys.modules
        assert "os" in sys.modules
        assert "sys" in sys.modules
        assert "json" in sys.modules

    def test_cleanup_noop_when_no_peeka_modules(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setitem(sys.modules, "os", sys.modules["os"])
        monkeypatch.setitem(sys.modules, "json", sys.modules["json"])

        _cleanup_peeka_modules()

        assert "os" in sys.modules
        assert "json" in sys.modules

    def test_cleanup_idempotent(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setitem(sys.modules, "peeka", _make_module("peeka"))
        monkeypatch.setitem(sys.modules, "peeka.core", _make_module("peeka.core"))

        _cleanup_peeka_modules()
        _cleanup_peeka_modules()

        assert "peeka" not in sys.modules
        assert "peeka.core" not in sys.modules

    def test_cleanup_handles_none_module_values(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setitem(sys.modules, "peeka.fake_none", None)

        _cleanup_peeka_modules()

        assert "peeka.fake_none" not in sys.modules

    def test_cleanup_does_not_touch_peeka_adjacent_names(self, monkeypatch: pytest.MonkeyPatch):
        marker = object()
        monkeypatch.setitem(sys.modules, "peekachu", marker)
        monkeypatch.setitem(sys.modules, "not_peeka", marker)

        _cleanup_peeka_modules()

        assert sys.modules["peekachu"] is marker
        assert sys.modules["not_peeka"] is marker
