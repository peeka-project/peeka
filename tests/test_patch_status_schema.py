"""
Patch-Status JSONL Enum Contract Tests

Freezes the enum contract for monkey-patch detection status values.
Ensures that the string literals and dict structures remain stable
across refactoring and prevent schema drift.

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
class TestPatchStatusEnumContract:
    """Test suite for patch-status enum contract freezing."""

    @pytest.fixture
    def patch_status_cmd(self):
        """Create PatchStatusCommand instance."""
        return PatchStatusCommand()

    def test_gevent_not_imported(self, patch_status_cmd, monkeypatch):
        """
        Test gevent not_imported state.

        Enum contract: "not_imported" (string literal)
        """
        monkeypatch.delitem(sys.modules, "gevent.monkey", raising=False)

        result = patch_status_cmd._detect_monkey_patch()

        assert "gevent" in result
        assert result["gevent"] == "not_imported"
        assert isinstance(result["gevent"], str)

    def test_gevent_imported_not_active(self, patch_status_cmd, monkeypatch):
        """
        Test gevent imported but not active state.

        Enum contract: {"status": "imported_not_active", ...}
        """
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

    def test_gevent_active(self, patch_status_cmd, monkeypatch):
        """
        Test gevent active (patched) state.

        Enum contract: {"status": "active", ...}
        """
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

    def test_eventlet_not_imported(self, patch_status_cmd, monkeypatch):
        """
        Test eventlet not_imported state.

        Enum contract: "not_imported" (string literal)
        """
        monkeypatch.delitem(sys.modules, "eventlet.patcher", raising=False)

        result = patch_status_cmd._detect_monkey_patch()

        assert "eventlet" in result
        assert result["eventlet"] == "not_imported"
        assert isinstance(result["eventlet"], str)

    def test_eventlet_imported_not_active(self, patch_status_cmd, monkeypatch):
        """
        Test eventlet imported but not active state.

        Enum contract: {"status": "imported_not_active"}
        """
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

        Enum contract: {"status": "active"}
        """
        fake_eventlet = FakeEventletModule(patched=True)
        fake_eventlet_parent = type(sys)("eventlet")
        fake_eventlet_parent.patcher = fake_eventlet
        monkeypatch.setitem(sys.modules, "eventlet.patcher", fake_eventlet)
        monkeypatch.setitem(sys.modules, "eventlet", fake_eventlet_parent)

        result = patch_status_cmd._detect_monkey_patch()

        assert "eventlet" in result
        assert isinstance(result["eventlet"], dict)
        assert result["eventlet"]["status"] == "active"

    def test_both_not_imported(self, patch_status_cmd, monkeypatch):
        """
        Test both gevent and eventlet not imported.

        Verifies the complete enum contract for the not_imported state.
        """
        monkeypatch.delitem(sys.modules, "gevent.monkey", raising=False)
        monkeypatch.delitem(sys.modules, "eventlet.patcher", raising=False)

        result = patch_status_cmd._detect_monkey_patch()

        assert result["gevent"] == "not_imported"
        assert result["eventlet"] == "not_imported"

    def test_gevent_active_eventlet_not_imported(self, patch_status_cmd, monkeypatch):
        """
        Test mixed state: gevent active, eventlet not imported.

        Verifies enum contract across different states.
        """
        fake_gevent = FakeGeventModule(patched=True)
        fake_gevent_parent = type(sys)("gevent")
        fake_gevent_parent.monkey = fake_gevent
        monkeypatch.setitem(sys.modules, "gevent.monkey", fake_gevent)
        monkeypatch.setitem(sys.modules, "gevent", fake_gevent_parent)
        monkeypatch.delitem(sys.modules, "eventlet.patcher", raising=False)

        result = patch_status_cmd._detect_monkey_patch()

        assert isinstance(result["gevent"], dict)
        assert result["gevent"]["status"] == "active"
        assert result["eventlet"] == "not_imported"

    def test_gevent_not_imported_eventlet_active(self, patch_status_cmd, monkeypatch):
        """
        Test mixed state: gevent not imported, eventlet active.

        Verifies enum contract across different states.
        """
        monkeypatch.delitem(sys.modules, "gevent.monkey", raising=False)
        fake_eventlet = FakeEventletModule(patched=True)
        fake_eventlet_parent = type(sys)("eventlet")
        fake_eventlet_parent.patcher = fake_eventlet
        monkeypatch.setitem(sys.modules, "eventlet.patcher", fake_eventlet)
        monkeypatch.setitem(sys.modules, "eventlet", fake_eventlet_parent)

        result = patch_status_cmd._detect_monkey_patch()

        assert result["gevent"] == "not_imported"
        assert isinstance(result["eventlet"], dict)
        assert result["eventlet"]["status"] == "active"
