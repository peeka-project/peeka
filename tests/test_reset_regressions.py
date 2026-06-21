"""Regression tests for codex-reported reset.py issues (P1 and P2)."""
from __future__ import annotations

import subprocess
import sys
import threading
from typing import Any, Dict, List, Mapping, cast


from peeka.commands.reset import ResetCommand


class _StubInjector:
    """Minimal injector stub returning canned list_enhanced output."""

    def __init__(self, enhanced_entries: List[Mapping[str, object]]) -> None:
        self._enhanced: List[Mapping[str, object]] = enhanced_entries

    def list_enhanced(self) -> Dict[str, object]:
        return {
            "status": "success",
            "action": "list",
            "enhanced": list(self._enhanced),
            "total": len(self._enhanced),
        }


class _StubAgent:
    """Minimal agent stub with probe context tracking attributes."""

    def __init__(self, enhanced_entries: List[Mapping[str, object]], probe_context_types: Dict[str, str]) -> None:
        self.injector: _StubInjector = _StubInjector(enhanced_entries)
        self._probe_context_types: Dict[str, str] = probe_context_types
        self._probe_contexts: Dict[str, object] = {}
        self._probe_context_lock = threading.Lock()


class TestResetImportWithoutTypingExtensions:
    """P1: reset.py must not hard-require typing_extensions at runtime."""

    def test_reset_module_imports_without_typing_extensions(self) -> None:
        """Importing ResetCommand with typing_extensions blocked must succeed."""
        code = (
            "import sys; "
            "sys.modules['typing_extensions'] = None; "
            "from peeka.commands.reset import ResetCommand; "
            "print('OK')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"Import failed when typing_extensions blocked.\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
        assert "OK" in result.stdout


class TestListEnhancedDeduplication:
    """P2: _list_enhanced must deduplicate entries appearing in both injector and probe_context_types."""

    def test_list_enhanced_no_duplicate_for_watch_id(self) -> None:
        """A watch_id in both injector output and probe_context_types must appear exactly once."""
        shared_id = "watch_abc12345"
        injector_entry = {
            "watch_id": shared_id,
            "pattern": "module.func",
            "command": "watch",
            "count": 0,
        }
        probe_types = {shared_id: "watch"}
        agent = _StubAgent([injector_entry], probe_types)
        cmd = ResetCommand(cast(Any, agent))

        result: Dict[str, object] = cmd._list_enhanced({})

        enhanced = cast(List[Mapping[str, object]], result["enhanced"])
        assert len(enhanced) == 1, f"Expected 1 entry, got {len(enhanced)}: {enhanced}"
        assert result["total"] == 1
        assert enhanced[0]["watch_id"] == shared_id

    def test_list_enhanced_monitor_still_appears(self) -> None:
        """monitor_id only in probe_context_types (not injector) must still appear in output."""
        monitor_id = "monitor_xyz78901"
        probe_types = {monitor_id: "monitor"}
        agent = _StubAgent([], probe_types)
        cmd = ResetCommand(cast(Any, agent))

        result: Dict[str, object] = cmd._list_enhanced({})

        enhanced = cast(List[Mapping[str, object]], result["enhanced"])
        assert len(enhanced) == 1
        assert result["total"] == 1
        assert enhanced[0].get("stream_id") == monitor_id
        assert enhanced[0].get("command") == "monitor"

    def test_list_enhanced_top_still_appears(self) -> None:
        """top_id only in probe_context_types (not injector) must still appear in output."""
        top_id = "top_main"
        probe_types = {top_id: "top"}
        agent = _StubAgent([], probe_types)
        cmd = ResetCommand(cast(Any, agent))

        result: Dict[str, object] = cmd._list_enhanced({})

        enhanced = cast(List[Mapping[str, object]], result["enhanced"])
        assert len(enhanced) == 1
        assert result["total"] == 1
        assert enhanced[0].get("stream_id") == top_id
        assert enhanced[0].get("command") == "top"
