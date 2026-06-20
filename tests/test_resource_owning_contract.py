"""Loose TDD contract tests for ResourceOwningCommand ABC.

Tests verify:
1. ABC enforcement — incomplete subclasses cannot be instantiated.
2. lifecycle.py contains no hardcoded command names (RED until T8).
"""

import pathlib

import pytest

from peeka.commands.resource_owning import ResourceOwningCommand


class TestResourceOwningContract:
    def test_abstract_subclass_raises_typeerror_on_instantiation(self) -> None:
        class _IncompleteOwner(ResourceOwningCommand):
            pass

        with pytest.raises(TypeError):
            _IncompleteOwner(None)

    def test_lifecycle_module_has_no_hardcoded_command_names(self) -> None:
        lifecycle_path = (
            pathlib.Path(__file__).parent.parent
            / "peeka"
            / "core"
            / "agent_control"
            / "lifecycle.py"
        )
        source = lifecycle_path.read_text()
        hardcoded = ['"monitor"', '"top"', '"memory"']
        for literal in hardcoded:
            assert literal not in source, (
                f"lifecycle.py still has hardcoded command name: {literal!r}"
            )
