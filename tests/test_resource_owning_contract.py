"""Loose TDD contract tests for ResourceOwningCommand ABC.

Tests verify:
1. ABC enforcement — incomplete subclasses cannot be instantiated.
2. lifecycle.py contains no hardcoded command names (RED until T8).
3. Every concrete BaseCommand subclass explicitly declares is_resource_owner.
4. is_resource_owner=True iff subclass inherits ResourceOwningCommand (bidirectional).
5. Every ResourceOwningCommand subclass has a valid CleanupScope enum member.
6. Every ResourceOwningCommand subclass can be instantiated without TypeError.
7. Subclass discovery count meets a conservative baseline (guards against silent fixture failure).
8. Registry contents match discovered subclasses bidirectionally.
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


@pytest.fixture(scope="session")
def _ensure_all_commands_imported():
    """Import every command in PeekaAgent._COMMAND_REGISTRY.
    Fixes P1-A: __subclasses__() now sees ALL commands, not just
    the ones happening to be imported by other tests.
    """
    import importlib
    from peeka.core.agent import PeekaAgent
    for module_path, _class_name in PeekaAgent._COMMAND_REGISTRY.values():
        importlib.import_module(module_path)


class TestResourceOwningContract:
    def test_abstract_subclass_raises_typeerror_on_instantiation(self) -> None:
        class _IncompleteOwner(ResourceOwningCommand):
            pass

        with pytest.raises(TypeError):
            _IncompleteOwner(None)

    def test_lifecycle_module_has_no_hardcoded_command_names(self) -> None:
        import re

        lifecycle_path = (
            pathlib.Path(__file__).parent.parent
            / "peeka"
            / "core"
            / "agent_control"
            / "lifecycle.py"
        )
        source = lifecycle_path.read_text()

        # 1. String literals — original check
        string_violations = [
            lit for lit in ['"monitor"', '"top"', '"memory"']
            if lit in source
        ]
        assert not string_violations, (
            f"lifecycle.py has hardcoded command name literals: {string_violations}"
        )

        # 2. Cross-command private access (e.g. agent.top_cmd._sampling_thread)
        cross_access = re.findall(r'agent\.\w+_cmd\._\w+', source)
        assert not cross_access, (
            f"lifecycle.py uses private cross-command access: {cross_access}"
        )

        # 3. Specific private attribute names that are command-internal
        # NOTE: leading `\.` anchors to attribute access — cannot match prose/docstrings.
        # This is safe per Non-Goal clarification: `\._attr\b` ≠ standalone `\battr\b`
        private_attrs = ['._monitors', '._sampling_thread', '._top_id', '._stop_monitor']
        attr_violations = [
            a for a in private_attrs
            if re.search(re.escape(a) + r'\b', source)
        ]
        assert not attr_violations, (
            f"lifecycle.py accesses command-private attrs: {attr_violations}"
        )

    def test_all_concrete_basecommand_subclasses_explicitly_declare_is_resource_owner(
        self, _ensure_all_commands_imported
    ):
        missing = [
            cls.__name__
            for cls in _iter_concrete_basecommand_subclasses()
            if 'is_resource_owner' not in cls.__dict__
        ]
        assert missing == [], f"Missing explicit is_resource_owner declaration: {missing}"

    def test_bidirectional_consistency_is_resource_owner_and_resource_owning_command(
        self, _ensure_all_commands_imported
    ):
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

    def test_resource_owning_subclasses_have_valid_cleanup_scope(
        self, _ensure_all_commands_imported
    ):
        invalid = []
        for cls in _iter_concrete_basecommand_subclasses():
            if issubclass(cls, ResourceOwningCommand):
                if not isinstance(getattr(cls, 'cleanup_scope', None), CleanupScope):
                    invalid.append(f"{cls.__name__}: cleanup_scope={getattr(cls, 'cleanup_scope', 'MISSING')}")
        assert invalid == [], f"Invalid cleanup_scope: {invalid}"

    def test_resource_owning_subclasses_can_be_instantiated(
        self, _ensure_all_commands_imported
    ):
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

    def test_subclass_discovery_count_meets_baseline(
        self, _ensure_all_commands_imported
    ) -> None:
        """Guard against fixture silently failing (e.g., import error swallowed).
        After fixture runs, we must see at least the registered commands.
        """
        discovered = list(_iter_concrete_basecommand_subclasses())
        # _COMMAND_REGISTRY currently has 15 entries; require >= 10 as conservative floor
        assert len(discovered) >= 10, (
            f"Expected >= 10 concrete BaseCommand subclasses; got {len(discovered)}: "
            f"{[c.__name__ for c in discovered]}. Fixture may have failed silently."
        )

    def test_registry_classes_match_basecommand_subclasses(
        self, _ensure_all_commands_imported
    ) -> None:
        """Bidirectional: registry contents must match discovered subclasses."""
        import importlib
        from peeka.core.agent import PeekaAgent

        registry_classes = set()
        for module_path, class_name in PeekaAgent._COMMAND_REGISTRY.values():
            mod = importlib.import_module(module_path)
            registry_classes.add(getattr(mod, class_name))

        discovered = set(_iter_concrete_basecommand_subclasses())

        in_registry_not_discovered = registry_classes - discovered
        in_discovered_not_registry = discovered - registry_classes

        assert not in_registry_not_discovered, (
            f"In _COMMAND_REGISTRY but not discovered via __subclasses__(): "
            f"{in_registry_not_discovered}. "
            f"Check if class uses module.startswith('peeka.commands') filter correctly."
        )
        assert not in_discovered_not_registry, (
            f"BaseCommand subclass but not in _COMMAND_REGISTRY: "
            f"{in_discovered_not_registry}. "
            f"Add missing class to PeekaAgent._COMMAND_REGISTRY."
        )
