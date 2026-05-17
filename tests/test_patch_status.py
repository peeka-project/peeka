"""
Patch-Status Detection Unit Tests

Tests the sys.modules.get()-based detection logic for gevent and eventlet
monkey-patching status, ensuring no import side effects.

Test Coverage:
- gevent: not_imported, imported_not_active, active (3 states)
- eventlet: not_imported, imported_not_active, active (3 states)
"""

import sys

import pytest

from peeka.commands.patch_status import PatchStatusCommand


class FakeGeventModule:
    """Fake gevent.monkey module for testing."""

    def __init__(self, patched: bool = False):
        self.patched = patched
        self.saved = {"socket": None, "threading": None} if patched else {}

    def is_module_patched(self, module_name: str) -> bool:
        """Return patch status for a module."""
        return self.patched


class FakeEventletModule:
    """Fake eventlet.patcher module for testing."""

    def __init__(self, patched: bool = False):
        self.already_patched = patched


@pytest.mark.unit
class TestPatchStatusDetection:
    """Test suite for patch-status detection using sys.modules.get()."""

    @pytest.fixture
    def patch_status_cmd(self):
        """Create PatchStatusCommand instance."""
        return PatchStatusCommand()

    def test_gevent_not_imported(self, patch_status_cmd, monkeypatch):
        """
        Test gevent not_imported state.

        Verifies that detection returns "not_imported" when gevent.monkey
        is not in sys.modules, and that no import side effects occur.
        """
        monkeypatch.delitem(sys.modules, "gevent.monkey", raising=False)
        monkeypatch.delitem(sys.modules, "gevent", raising=False)

        result = patch_status_cmd._detect_monkey_patch()

        assert "gevent" in result
        assert result["gevent"] == "not_imported"
        assert isinstance(result["gevent"], str)
        assert "gevent.monkey" not in sys.modules
        assert "gevent" not in sys.modules

    def test_gevent_imported_not_active(self, patch_status_cmd, monkeypatch):
        """
        Test gevent imported but not active state.

        Verifies detection when gevent.monkey is imported but is_module_patched
        returns False for all modules.
        """
        monkeypatch.delitem(sys.modules, "gevent.monkey", raising=False)
        monkeypatch.delitem(sys.modules, "gevent", raising=False)

        fake_gevent = FakeGeventModule(patched=False)
        fake_gevent_parent = type(sys)("gevent")
        fake_gevent_parent.monkey = fake_gevent
        monkeypatch.setitem(sys.modules, "gevent.monkey", fake_gevent)
        monkeypatch.setitem(sys.modules, "gevent", fake_gevent_parent)

        result = patch_status_cmd._detect_monkey_patch()

        assert "gevent" in result
        assert isinstance(result["gevent"], dict)
        assert result["gevent"]["status"] == "imported_not_active"
        assert "patched_modules" in result["gevent"]
        assert result["gevent"]["patched_modules"] == []

    def test_gevent_active(self, patch_status_cmd, monkeypatch):
        """
        Test gevent active (patched) state.

        Verifies detection when gevent.monkey is imported and is_module_patched
        returns True for at least one module.
        """
        monkeypatch.delitem(sys.modules, "gevent.monkey", raising=False)
        monkeypatch.delitem(sys.modules, "gevent", raising=False)

        fake_gevent = FakeGeventModule(patched=True)
        fake_gevent_parent = type(sys)("gevent")
        fake_gevent_parent.monkey = fake_gevent
        monkeypatch.setitem(sys.modules, "gevent.monkey", fake_gevent)
        monkeypatch.setitem(sys.modules, "gevent", fake_gevent_parent)

        result = patch_status_cmd._detect_monkey_patch()

        assert "gevent" in result
        assert isinstance(result["gevent"], dict)
        assert result["gevent"]["status"] == "active"
        assert "patched_modules" in result["gevent"]
        assert result["gevent"]["patched_modules"] == ["socket", "threading"]

    def test_eventlet_not_imported(self, patch_status_cmd, monkeypatch):
        """
        Test eventlet not_imported state.

        Verifies that detection returns "not_imported" when eventlet.patcher
        is not in sys.modules, and that no import side effects occur.
        """
        monkeypatch.delitem(sys.modules, "eventlet.patcher", raising=False)
        monkeypatch.delitem(sys.modules, "eventlet", raising=False)

        result = patch_status_cmd._detect_monkey_patch()

        assert "eventlet" in result
        assert result["eventlet"] == "not_imported"
        assert isinstance(result["eventlet"], str)
        assert "eventlet.patcher" not in sys.modules
        assert "eventlet" not in sys.modules

    def test_eventlet_imported_not_active(self, patch_status_cmd, monkeypatch):
        """
        Test eventlet imported but not active state.

        Verifies detection when eventlet.patcher is imported but
        already_patched is False or empty.
        """
        monkeypatch.delitem(sys.modules, "eventlet.patcher", raising=False)
        monkeypatch.delitem(sys.modules, "eventlet", raising=False)

        fake_eventlet = FakeEventletModule(patched=False)
        fake_eventlet_parent = type(sys)("eventlet")
        fake_eventlet_parent.patcher = fake_eventlet
        monkeypatch.setitem(sys.modules, "eventlet.patcher", fake_eventlet)
        monkeypatch.setitem(sys.modules, "eventlet", fake_eventlet_parent)

        result = patch_status_cmd._detect_monkey_patch()

        assert "eventlet" in result
        assert isinstance(result["eventlet"], dict)
        assert result["eventlet"]["status"] == "imported_not_active"

    def test_eventlet_active(self, patch_status_cmd, monkeypatch):
        """
        Test eventlet active (patched) state.

        Verifies detection when eventlet.patcher is imported and
        already_patched is truthy.
        """
        monkeypatch.delitem(sys.modules, "eventlet.patcher", raising=False)
        monkeypatch.delitem(sys.modules, "eventlet", raising=False)

        fake_eventlet = FakeEventletModule(patched=True)
        fake_eventlet_parent = type(sys)("eventlet")
        fake_eventlet_parent.patcher = fake_eventlet
        monkeypatch.setitem(sys.modules, "eventlet.patcher", fake_eventlet)
        monkeypatch.setitem(sys.modules, "eventlet", fake_eventlet_parent)

        result = patch_status_cmd._detect_monkey_patch()

        assert "eventlet" in result
        assert isinstance(result["eventlet"], dict)
        assert result["eventlet"]["status"] == "active"

    def test_no_import_side_effects(self, patch_status_cmd, monkeypatch):
        """
        Test that calling _detect_monkey_patch() does not import gevent or eventlet.

        This is the critical test for the sys.modules.get() refactoring.
        """
        monkeypatch.delitem(sys.modules, "gevent.monkey", raising=False)
        monkeypatch.delitem(sys.modules, "gevent", raising=False)
        monkeypatch.delitem(sys.modules, "eventlet.patcher", raising=False)
        monkeypatch.delitem(sys.modules, "eventlet", raising=False)

        result = patch_status_cmd._detect_monkey_patch()

        assert result["gevent"] == "not_imported"
        assert result["eventlet"] == "not_imported"
        assert "gevent.monkey" not in sys.modules
        assert "gevent" not in sys.modules
        assert "eventlet.patcher" not in sys.modules
        assert "eventlet" not in sys.modules
