"""Static gate for unsafe __wrapped__ access patterns."""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PEEKA_SOURCE_ROOT = PROJECT_ROOT / "peeka"

# Keep this allowlist tight and file-based so future additions are explicit.
ALLOWED_WRAPPED_ACCESS_FILES = {
    "peeka/core/instrumentation/registry.py": "_live_previous_probe_wrapper uses __wrapped__ to walk live Peeka wrappers",
    "peeka/core/instrumentation/watch.py": "inspect.unwrap is used only for classification",
    "peeka/commands/monitor.py": "_nearest_lower_live_wrapper uses __wrapped__ to walk live Peeka wrappers below a monitor wrapper",
}

WRAPPED_ACCESS_PATTERNS = (
    ("attribute", re.compile(r"\.\s*__wrapped__\b")),
    (
        "lookup",
        re.compile(r"\b(?:getattr|hasattr)\s*\([\s\S]*?['\"]__wrapped__['\"]"),
    ),
    ("unwrap", re.compile(r"\binspect\.unwrap\s*\(")),
)


def _relative_py_paths(source_root: Path, project_root: Path) -> Iterable[Path]:
    for path in sorted(source_root.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        if "tests" in path.parts:
            continue
        yield path.relative_to(project_root)


def _scan_wrapped_accesses(source_root: Path, project_root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for rel_path in _relative_py_paths(source_root, project_root):
        source_path = project_root / rel_path
        source = source_path.read_text(encoding="utf-8")
        for kind, pattern in WRAPPED_ACCESS_PATTERNS:
            for match in pattern.finditer(source):
                findings.append(
                    {
                        "path": rel_path.as_posix(),
                        "kind": kind,
                        "line": source.count("\n", 0, match.start()) + 1,
                        "match": match.group(0),
                    }
                )
    return findings


def _assert_no_new_wrapped_access(source_root: Path, project_root: Path) -> None:
    findings = _scan_wrapped_accesses(source_root, project_root)
    unexpected = [
        finding
        for finding in findings
        if finding["path"] not in ALLOWED_WRAPPED_ACCESS_FILES
    ]

    assert not unexpected, _format_findings(unexpected)


def _format_findings(findings: list[dict[str, object]]) -> str:
    lines = ["Unexpected wrapped-access sites detected:"]
    for finding in findings:
        lines.append(
            "- {path}:{line} [{kind}] {match}".format(
                path=finding["path"],
                line=finding["line"],
                kind=finding["kind"],
                match=finding["match"],
            )
        )
    return "\n".join(lines)


class TestWrappedAccessGate:
    def test_no_new_wrapped_access_outside_allowlist(self, tmp_path: Path):
        _assert_no_new_wrapped_access(PEEKA_SOURCE_ROOT, PROJECT_ROOT)

        unsafe_root = tmp_path / "wrapped_access_negative"
        unsafe_root.mkdir()
        unsafe_file = unsafe_root / "unsafe_site.py"
        _ = unsafe_file.write_text(
            """def unsafe_lookup(value):\n    return getattr(value, \"__wrapped__\", None)\n""",
            encoding="utf-8",
        )

        with pytest.raises(AssertionError):
            _assert_no_new_wrapped_access(unsafe_root, tmp_path)
