"""Release-gate regression tests."""

import ast
from pathlib import Path
from typing import List


class _UvSubprocessVisitor(ast.NodeVisitor):
    """Find subprocess calls that hard-code uv as the executable."""

    def __init__(self) -> None:
        self.lines = []

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


def _find_uv_subprocess_calls(root: Path) -> List[str]:
    offenders = []
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
