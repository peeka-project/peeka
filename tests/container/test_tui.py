"""Host-side TUI tests - executes pytest inside GDB container.

These tests orchestrate pytest execution inside the container to run
tui_inner_test.py, which uses textual's run_test() API. This two-layer
approach is necessary because textual requires in-process Python access
that cannot be driven via container exec commands.

Only tests against gdb_container (Python 3.12), not py314.
"""

import pytest

from tests.container.conftest import exec_in_container

pytestmark = [pytest.mark.container, pytest.mark.tui]


class TestContainerTUI:
    """Host-side orchestration of container TUI tests."""

    def test_tui_tests_pass_inside_container(self, gdb_container):
        """Run TUI tests inside container using pytest.

        Args:
            gdb_container: Python 3.12 container with textual installed.
        """
        exit_code, output = exec_in_container(
            gdb_container,
            "cd /app && python -m pytest tests/container/tui_inner_test.py -v --timeout=30",
            timeout=60,
        )
        assert exit_code == 0, f"TUI tests failed inside container:\n{output}"
