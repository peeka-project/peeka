"""Test command category and concurrency declarations."""

import pytest

from peeka.commands.base import BaseCommand
from peeka.commands.watch import WatchCommand  # noqa: F401
from peeka.commands.trace import TraceCommand  # noqa: F401
from peeka.commands.monitor import MonitorCommand  # noqa: F401
from peeka.commands.logger import LoggerCommand  # noqa: F401
from peeka.commands.reset import ResetCommand  # noqa: F401
from peeka.commands.detach import DetachCommand  # noqa: F401
from peeka.commands.memory import MemoryCommand  # noqa: F401
from peeka.commands.thread import ThreadCommand  # noqa: F401
from peeka.commands.stack import StackCommand  # noqa: F401
from peeka.commands.search import SearchClassCommand, SearchMethodCommand  # noqa: F401
from peeka.commands.top import TopCommand  # noqa: F401
from peeka.commands.vmtool import VMToolCommand  # noqa: F401
from peeka.commands.complete import CompleteCommand  # noqa: F401


def get_all_concrete_subclasses(cls):
    """Recursively enumerate all non-abstract subclasses of a given class."""
    subclasses = []
    for subclass in cls.__subclasses__():
        if not getattr(subclass, "__abstractmethods__", None):
            subclasses.append(subclass)
        subclasses.extend(get_all_concrete_subclasses(subclass))
    return subclasses


class TestCommandCategories:
    """Test that all command subclasses properly declare category and allows_concurrent."""

    def test_all_concrete_commands_declare_category_in_own_dict(self):
        """Every concrete BaseCommand subclass must declare 'category' in its own __dict__."""
        concrete_commands = get_all_concrete_subclasses(BaseCommand)
        assert len(concrete_commands) > 0, "Expected at least one concrete command"

        missing = []
        for cmd_class in concrete_commands:
            if "category" not in cmd_class.__dict__:
                missing.append(cmd_class.__name__)

        assert not missing, f"Commands missing 'category' declaration: {missing}"

    def test_all_concrete_commands_declare_allows_concurrent_in_own_dict(self):
        """Every concrete BaseCommand subclass must declare 'allows_concurrent' in its own __dict__."""
        concrete_commands = get_all_concrete_subclasses(BaseCommand)
        assert len(concrete_commands) > 0

        missing = []
        for cmd_class in concrete_commands:
            if "allows_concurrent" not in cmd_class.__dict__:
                missing.append(cmd_class.__name__)

        assert not missing, f"Commands missing 'allows_concurrent' declaration: {missing}"

    def test_category_values_are_valid(self):
        """Category values must be one of: snapshot, probe, mutation."""
        valid_categories = {"snapshot", "probe", "mutation"}
        concrete_commands = get_all_concrete_subclasses(BaseCommand)

        invalid = []
        for cmd_class in concrete_commands:
            category = cmd_class.__dict__.get("category")
            if category not in valid_categories:
                invalid.append((cmd_class.__name__, category))

        assert not invalid, f"Commands with invalid category: {invalid}"

    def test_allows_concurrent_is_bool(self):
        """allows_concurrent must be a bool."""
        concrete_commands = get_all_concrete_subclasses(BaseCommand)

        invalid = []
        for cmd_class in concrete_commands:
            allows_concurrent = cmd_class.__dict__.get("allows_concurrent")
            if not isinstance(allows_concurrent, bool):
                invalid.append((cmd_class.__name__, type(allows_concurrent).__name__))

        assert not invalid, f"Commands with non-bool allows_concurrent: {invalid}"

    @pytest.mark.parametrize(
        "cmd_name,expected_category",
        [
            ("WatchCommand", "probe"),
            ("TraceCommand", "probe"),
            ("ResetCommand", "mutation"),
            ("MemoryCommand", "snapshot"),
            ("SearchClassCommand", "snapshot"),
            ("SearchMethodCommand", "snapshot"),
        ],
    )
    def test_specific_command_categories(self, cmd_name, expected_category):
        """Spot-check specific command categories match plan rules."""
        concrete_commands = get_all_concrete_subclasses(BaseCommand)
        cmd_map = {cmd.__name__: cmd for cmd in concrete_commands}

        assert cmd_name in cmd_map, f"Command {cmd_name} not found"
        assert cmd_map[cmd_name].category == expected_category, (
            f"{cmd_name}.category={cmd_map[cmd_name].category}, expected {expected_category}"
        )

    def test_mutation_commands_never_concurrent(self):
        """Mutation commands must have allows_concurrent=False."""
        concrete_commands = get_all_concrete_subclasses(BaseCommand)

        violations = []
        for cmd_class in concrete_commands:
            if cmd_class.category == "mutation" and cmd_class.allows_concurrent:
                violations.append(cmd_class.__name__)

        assert not violations, (
            f"Mutation commands must have allows_concurrent=False: {violations}"
        )

    def test_probe_commands_typically_not_concurrent(self):
        """Probe commands should have allows_concurrent=False (soft check)."""
        concrete_commands = get_all_concrete_subclasses(BaseCommand)

        concurrent_probes = []
        for cmd_class in concrete_commands:
            if cmd_class.category == "probe" and cmd_class.allows_concurrent:
                concurrent_probes.append(cmd_class.__name__)

        if concurrent_probes:
            pytest.skip(
                f"Probe commands with allows_concurrent=True: {concurrent_probes}. "
                "This is unusual but not forbidden."
            )
