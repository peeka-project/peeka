"""Release-gate regression tests."""

# pyright: reportImplicitOverride=false

from __future__ import annotations

import ast
import re
from pathlib import Path


class _UvSubprocessVisitor(ast.NodeVisitor):
    """Find subprocess calls that hard-code uv as the executable."""

    def __init__(self) -> None:
        self.lines: list[int] = []

    def visit_Call(self, node: ast.Call) -> None:
        if self._is_subprocess_call(node) and self._first_arg_is_uv(node):
            self.lines.append(node.lineno)
        self.generic_visit(node)

    @staticmethod
    def _is_subprocess_call(node: ast.Call) -> bool:
        func = node.func
        if not isinstance(func, ast.Attribute):
            return False
        if func.attr not in {"run", "call", "check_call", "check_output", "Popen"}:
            return False
        value = func.value
        return isinstance(value, ast.Name) and value.id == "subprocess"

    @staticmethod
    def _first_arg_is_uv(node: ast.Call) -> bool:
        if not node.args:
            return False
        command = node.args[0]
        if not isinstance(command, (ast.List, ast.Tuple)) or not command.elts:
            return False
        first = command.elts[0]
        return isinstance(first, ast.Constant) and first.value == "uv"


def _find_uv_subprocess_calls(root: Path) -> list[str]:
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _UvSubprocessVisitor()
        visitor.visit(tree)
        for line in visitor.lines:
            offenders.append(f"{path.relative_to(root.parent)}:{line}")
    return offenders


def test_tests_do_not_hardcode_uv_subprocess_commands() -> None:
    """Tests must use the current interpreter, not local dev tools."""
    offenders = _find_uv_subprocess_calls(Path(__file__).resolve().parent)

    assert offenders == []


def test_release_check_excludes_perf_and_slow_markers() -> None:
    """Release gate must exclude perf and slow tests from pytest collection."""
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "release_check.sh"
    script_text = script_path.read_text(encoding="utf-8")

    match = re.search(r'-m\s+"([^"]+)"', script_text)
    assert match is not None, "release_check.sh must pass a pytest -m marker expression"

    marker_expr = match.group(1)

    assert "not perf" in marker_expr
    assert "not slow" in marker_expr
