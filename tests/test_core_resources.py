"""Tests for peeka.core.resources centralized resolver."""

from pathlib import Path

import pytest

from peeka.core.resources import (
    PeekaResourceError,
    core_resource_path,
    require_core_resource,
)


class TestCoreResourcePath:
    def test_returns_path_object(self):
        p = core_resource_path("_attach.gdb")
        assert isinstance(p, Path)

    def test_no_existence_check(self):
        """core_resource_path does not raise for missing files."""
        p = core_resource_path("definitely_nonexistent_xyz.txt")
        assert isinstance(p, Path)

    def test_points_to_core_dir(self):
        """Resolved path is inside peeka/core."""
        p = core_resource_path("_attach.gdb")
        assert p.parent.name == "core"


class TestRequireCoreResource:
    def test_gdb_script_exists(self):
        p = require_core_resource("_attach.gdb")
        assert p.exists()
        assert p.name == "_attach.gdb"

    def test_lldb_script_exists(self):
        p = require_core_resource("_attach.lldb")
        assert p.exists()
        assert p.name == "_attach.lldb"

    def test_returns_path_object(self):
        p = require_core_resource("_attach.gdb")
        assert isinstance(p, Path)

    def test_missing_raises_peeka_resource_error(self):
        with pytest.raises(PeekaResourceError) as exc_info:
            require_core_resource("nonexistent_abc.txt")
        msg = str(exc_info.value)
        assert "nonexistent_abc.txt" in msg
        assert "resolved to" in msg.lower() or "resolved" in msg.lower()

    def test_error_message_contains_resource_name(self):
        with pytest.raises(PeekaResourceError) as exc_info:
            require_core_resource("missing_resource_name.txt")
        assert "missing_resource_name.txt" in str(exc_info.value)

    def test_error_message_contains_absolute_path(self):
        with pytest.raises(PeekaResourceError) as exc_info:
            require_core_resource("x.missing")
        msg = str(exc_info.value)
        # Should contain an absolute path hint
        assert "/" in msg or "\\" in msg
