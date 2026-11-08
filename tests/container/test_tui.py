"""Host-side TUI tests - runs TUI smoke checks inside the GDB container.

These tests run
tui_smoke_inner.py (a plain-Python script, since the image has no pytest),
which uses textual's run_test() API. tui_inner_test.py is the pytest
variant of the same checks and runs on the host. This two-layer
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
        """Run the TUI smoke script inside the container.

        Args:
            gdb_container: Python 3.12 container with textual installed.
        """
        exit_code, output = exec_in_container(
            gdb_container,
            "cd /app && python tests/container/tui_smoke_inner.py",
            timeout=60,
        )
        assert exit_code == 0, f"TUI tests failed inside container:\n{output}"
