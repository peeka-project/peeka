"""Source-guard for detach dynamic dispatch.

Verifies that detach.py and agent.py do not re-introduce hardcoded
probe-type literal lists passed to shutdown_agent_resources.
"""

# pyright: reportDeprecated=false

import ast
import pathlib
from typing import List, Tuple

import pytest

from peeka.core.agent_control.probes import AgentProbeControlMixin


_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _calls_with_literal_probe_list(source: str) -> List[Tuple[int, str]]:
    """Return line/snippet pairs for hardcoded probe-type list calls."""
    tree = ast.parse(source)
    hits: List[Tuple[int, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        else:
            continue

        if name != "shutdown_agent_resources" or len(node.args) < 3:
            continue

        third_arg = node.args[2]
        if not isinstance(third_arg, ast.List):
            continue

        if all(
            isinstance(element, ast.Constant) and isinstance(element.value, str)
            for element in third_arg.elts
        ):
            snippet = ast.get_source_segment(source, node) or "<source unavailable>"
            hits.append((node.lineno, snippet))

    return hits


@pytest.mark.parametrize(
    "rel_path",
    [
        "peeka/commands/detach.py",
        "peeka/core/agent.py",
    ],
)
def test_no_hardcoded_probe_type_list_in_detach_and_agent(rel_path: str) -> None:
    """shutdown_agent_resources must not receive a literal string list."""
    source = (_REPO_ROOT / rel_path).read_text()
    hits = _calls_with_literal_probe_list(source)
    assert hits == [], (
        f"{rel_path} contains hardcoded probe-type literal list(s) passed to "
        f"shutdown_agent_resources. Use agent.list_tracked_probe_types() instead. "
        f"Violations: {hits}"
    )


def test_list_tracked_probe_types_exists_on_mixin() -> None:
    """AgentProbeControlMixin must expose list_tracked_probe_types()."""
    assert hasattr(AgentProbeControlMixin, "list_tracked_probe_types"), (
        "AgentProbeControlMixin.list_tracked_probe_types() is missing. "
        "This method provides dynamic probe discovery for detach/stop paths."
    )
