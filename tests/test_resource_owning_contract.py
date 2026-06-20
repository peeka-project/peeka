"""Loose TDD contract tests for ResourceOwningCommand ABC.

Tests verify:
1. ABC enforcement — incomplete subclasses cannot be instantiated.
2. lifecycle.py contains no hardcoded command names (RED until T8).
3. Every concrete BaseCommand subclass explicitly declares is_resource_owner.
4. is_resource_owner=True iff subclass inherits ResourceOwningCommand (bidirectional).
5. Every ResourceOwningCommand subclass has a valid CleanupScope enum member.
6. Every ResourceOwningCommand subclass can be instantiated without TypeError.
"""

import inspect
import pathlib

import pytest

from peeka.commands.base import BaseCommand
from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand


def _iter_concrete_basecommand_subclasses():
    """Recursively yield all concrete (non-abstract) subclasses of BaseCommand
    that are defined in the peeka.commands package (not test fakes)."""
    def _recurse(cls):
        for sub in cls.__subclasses__():
            module = getattr(sub, "__module__", "") or ""
            if not inspect.isabstract(sub) and module.startswith("peeka.commands"):
                yield sub
            yield from _recurse(sub)
    yield from _recurse(BaseCommand)


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

    def test_all_concrete_basecommand_subclasses_explicitly_declare_is_resource_owner(self):
        missing = [
            cls.__name__
            for cls in _iter_concrete_basecommand_subclasses()
            if 'is_resource_owner' not in cls.__dict__
        ]
        assert missing == [], f"Missing explicit is_resource_owner declaration: {missing}"

    def test_bidirectional_consistency_is_resource_owner_and_resource_owning_command(self):
        violations = []
        for cls in _iter_concrete_basecommand_subclasses():
            declares_true = cls.__dict__.get('is_resource_owner', False) is True
            is_resource_owning = issubclass(cls, ResourceOwningCommand)
            if declares_true != is_resource_owning:
                violations.append(
                    f"{cls.__name__}: is_resource_owner={declares_true}, "
                    f"issubclass(ResourceOwningCommand)={is_resource_owning}"
                )
        assert violations == [], f"Bidirectional consistency violations: {violations}"

    def test_resource_owning_subclasses_have_valid_cleanup_scope(self):
        invalid = []
        for cls in _iter_concrete_basecommand_subclasses():
            if issubclass(cls, ResourceOwningCommand):
                if not isinstance(getattr(cls, 'cleanup_scope', None), CleanupScope):
                    invalid.append(f"{cls.__name__}: cleanup_scope={getattr(cls, 'cleanup_scope', 'MISSING')}")
        assert invalid == [], f"Invalid cleanup_scope: {invalid}"

    def test_resource_owning_subclasses_can_be_instantiated(self):
        FA = type('FA', (), {'observer': None})
        errors = []
        for cls in _iter_concrete_basecommand_subclasses():
            if issubclass(cls, ResourceOwningCommand):
                try:
                    instance = cls(FA())
                    assert hasattr(instance, 'stop_active_resources')
                    assert hasattr(instance, 'list_active_resources')
                except TypeError as e:
                    errors.append(f"{cls.__name__}: {e}")
                except Exception:
                    pass
        assert errors == [], f"TypeError on instantiation (ABC methods missing): {errors}"
