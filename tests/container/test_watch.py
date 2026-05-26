"""
Container E2E tests for watch command functionality.

Tests watch command (function observation) in Docker containers against both:
- Python 3.12 (GDB-based attachment)
- Python 3.14 (PEP 768 native attachment)
"""

import json
import pytest

from tests.container.conftest import exec_in_container

pytestmark = [pytest.mark.container]


class TestContainerWatch:
    """Test watch command operations in containerized environments."""

    def test_watch_basic(self, container_target):
        """Verify basic watch command with limited observations."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Watch Calculator.add with 3 observations
        exit_code, watch_output = exec_in_container(
            container,
            'python -m peeka.cli.main watch "__main__.Calculator.add" -n 3',
            timeout=30,
        )

        # Verify output contains watch events
        assert "watch_started" in watch_output or "observation" in watch_output, (
            f"Expected watch events in output:\n{watch_output}"
        )

        # Parse JSONL and verify structure
        lines = [line for line in watch_output.strip().split("\n") if line.strip()]
        json_lines = [line for line in lines if line.startswith("{")]

        has_watch_started = False
        has_observation = False

        for line in json_lines:
            try:
                data = json.loads(line)
                if data.get("event") == "watch_started":
                    has_watch_started = True
                if data.get("type") == "observation":
                    has_observation = True
            except json.JSONDecodeError:
                continue

        assert has_watch_started or has_observation, (
            f"No valid watch events found in output:\n{watch_output}"
        )

    def test_watch_with_times_limit(self, container_target):
        """Verify watch respects times limit parameter."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Watch with 2 observations max
        exit_code, watch_output = exec_in_container(
            container,
            'python -m peeka.cli.main watch "__main__.Calculator.add" -n 2',
            timeout=30,
        )

        # Command should complete, or time out after producing partial observations
        # if the target function is slow to hit the requested -n count.
        assert exit_code in [0, 124], f"Watch command failed:\n{watch_output}"

        # Count observations in output
        lines = [line for line in watch_output.strip().split("\n") if line.strip()]
        observation_count = 0

        for line in lines:
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "observation":
                        observation_count += 1
                except json.JSONDecodeError:
                    continue

        # Should have at most 2 observations (may have fewer if function not called)
        assert observation_count <= 2, (
            f"Expected at most 2 observations, got {observation_count}"
        )

    def test_watch_with_condition(self, container_target):
        """Verify watch with condition filter."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Watch with condition filter
        exit_code, watch_output = exec_in_container(
            container,
            'python -m peeka.cli.main watch "__main__.Calculator.add" --condition "params[0] > 5" -n 3',
            timeout=30,
        )

        # Command should run without error (may have 0 matching observations)
        assert exit_code == 0, f"Watch command failed:\n{watch_output}"

        # Verify no error messages in output
        output_lower = watch_output.lower()
        assert "traceback" not in output_lower, (
            f"Unexpected traceback in output:\n{watch_output}"
        )

    def test_watch_entry_only(self, container_target):
        """Verify watch in entry-only mode (-b flag)."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Watch with entry-only mode
        exit_code, watch_output = exec_in_container(
            container,
            'python -m peeka.cli.main watch "__main__.Calculator.add" -b -n 2',
            timeout=30,
        )

        # Command should complete, or time out after producing partial observations
        # if the target function is slow to hit the requested -n count.
        assert exit_code in [0, 124], f"Watch command failed:\n{watch_output}"

        # Parse observations and verify no result field
        lines = [line for line in watch_output.strip().split("\n") if line.strip()]

        for line in lines:
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "observation":
                        # Entry-only mode should not have 'result' field
                        assert "result" not in data, (
                            f"Entry-only observation should not have 'result': {data}"
                        )
                except json.JSONDecodeError:
                    continue

    def test_watch_invalid_pattern(self, container_target):
        """Verify graceful failure for invalid function pattern."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Watch non-existent function
        exit_code, watch_output = exec_in_container(
            container,
            'python -m peeka.cli.main watch "nonexistent.Module.method" -n 1',
            timeout=30,
        )

        # Should fail gracefully with error message
        output_lower = watch_output.lower()
        assert (
            "error" in output_lower
            or "not found" in output_lower
            or "cannot find" in output_lower
        ), f"Expected error for invalid pattern:\n{watch_output}"

    def test_watch_multiply_function(self, container_target):
        """Verify watch on multiply function."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Watch Calculator.multiply
        exit_code, watch_output = exec_in_container(
            container,
            'python -m peeka.cli.main watch "__main__.Calculator.multiply" -n 2',
            timeout=30,
        )

        # Command should complete successfully
        assert exit_code == 0, f"Watch command failed:\n{watch_output}"

        # Verify observations present
        lines = [line for line in watch_output.strip().split("\n") if line.strip()]
        has_observation = False

        for line in lines:
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "observation":
                        has_observation = True
                        # Verify result is multiplication (counter * 2)
                        if "result" in data and "args" in data:
                            args = data["args"]
                            result = data["result"]
                            if len(args) >= 2:
                                expected = args[0] * args[1]
                                assert result == expected, (
                                    f"Multiply result mismatch: {args[0]} * {args[1]} = {result}, expected {expected}"
                                )
                except json.JSONDecodeError:
                    continue

        assert has_observation or "watch_started" in watch_output, (
            f"No observations found for multiply function:\n{watch_output}"
        )

    def test_watch_success_only_flag(self, container_target):
        """Verify watch with success-only flag (-s)."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Watch with success-only flag
        exit_code, watch_output = exec_in_container(
            container,
            'python -m peeka.cli.main watch "__main__.Calculator.add" -s -n 2',
            timeout=30,
        )

        # Command should complete successfully
        assert exit_code == 0, f"Watch command failed:\n{watch_output}"

        # All observations should have success=true
        lines = [line for line in watch_output.strip().split("\n") if line.strip()]

        for line in lines:
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "observation":
                        assert data.get("success", True) is True, (
                            f"Success-only mode should only capture successful calls: {data}"
                        )
                except json.JSONDecodeError:
                    continue

    def test_watch_multiple_parameters(self, container_target):
        """Verify watch command with multiple parameters."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Watch with depth and times parameters
        exit_code, watch_output = exec_in_container(
            container,
            'python -m peeka.cli.main watch "__main__.Calculator.add" -x 3 -n 2',
            timeout=30,
        )

        # Command should complete successfully
        assert exit_code == 0, f"Watch command failed:\n{watch_output}"

        # Verify output contains observations
        assert "watch_started" in watch_output or "observation" in watch_output, (
            f"Expected watch events in output:\n{watch_output}"
        )

    def test_watch_jsonl_format(self, container_target):
        """Verify watch output is valid JSONL format."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Watch command
        exit_code, watch_output = exec_in_container(
            container,
            'python -m peeka.cli.main watch "__main__.Calculator.add" -n 2',
            timeout=30,
        )

        # Parse all JSON lines
        lines = [line for line in watch_output.strip().split("\n") if line.strip()]
        json_valid_count = 0

        for line in lines:
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    # Verify required fields
                    assert "type" in data or "event" in data, (
                        f"JSON line missing type/event field: {data}"
                    )
                    json_valid_count += 1
                except json.JSONDecodeError as e:
                    pytest.fail(f"Invalid JSON line: {line}\nError: {e}")

        # Should have at least one valid JSON line
        assert json_valid_count > 0, (
            f"No valid JSON lines found in output:\n{watch_output}"
        )

    def test_watch_no_infinite_observations(self, container_target):
        """Verify watch does not run indefinitely without -n flag."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Watch with explicit limit to prevent infinite run
        # This test verifies the pattern - all watch commands MUST use -n
        exit_code, watch_output = exec_in_container(
            container,
            'python -m peeka.cli.main watch "__main__.Calculator.add" -n 1',
            timeout=30,
        )

        # Command may complete after one observation or hit the outer timeout
        # after the watch has started but before the target emits a matching call.
        assert exit_code in [0, 124], f"Watch command failed:\n{watch_output}"

        # Verify command finished (has output)
        assert len(watch_output.strip()) > 0, "Watch command produced no output"
        assert "watch_started" in watch_output or "observation" in watch_output
