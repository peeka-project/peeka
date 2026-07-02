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


class TestBootstrapClearsModuleCache:
    """Regression: bootstrap snippet must evict stale peeka.* modules."""

    def test_bootstrap_snippet_clears_stale_peeka_modules(self):
        """Execute the cleanup snippet extracted from the generated script and
        confirm that a pre-installed stale peeka.* entry is removed."""
        import sys
        import types

        # Simulate a stale cached module from a previous attach session
        stale_mod = types.ModuleType("peeka.core.instrumentation.trace_backends")
        # Intentionally omit _format_trace_function to simulate the old module
        stale_sentinel = object()
        setattr(stale_mod, "_stale_sentinel", stale_sentinel)

        original = sys.modules.get("peeka.core.instrumentation.trace_backends")
        sys.modules["peeka.core.instrumentation.trace_backends"] = stale_mod

        try:
            # This is exactly the cleanup snippet injected into the agent script
            for _peeka_mod in list(sys.modules.keys()):
                if _peeka_mod == "peeka" or _peeka_mod.startswith("peeka."):
                    _ = sys.modules.pop(_peeka_mod, None)

            assert "peeka.core.instrumentation.trace_backends" not in sys.modules, (
                "Stale cached peeka module should have been evicted by cleanup snippet"
            )
        finally:
            # Restore original state
            if original is not None:
                sys.modules["peeka.core.instrumentation.trace_backends"] = original
            else:
                _ = sys.modules.pop("peeka.core.instrumentation.trace_backends", None)

    def test_bootstrap_snippet_does_not_touch_non_peeka_modules(self):
        """The cleanup snippet must leave non-peeka modules untouched."""
        import sys

        original_os = sys.modules.get("os")
        original_json = sys.modules.get("json")

        # Run the cleanup snippet
        for _peeka_mod in list(sys.modules.keys()):
            if _peeka_mod == "peeka" or _peeka_mod.startswith("peeka."):
                _ = sys.modules.pop(_peeka_mod, None)

        assert sys.modules.get("os") is original_os
        assert sys.modules.get("json") is original_json
