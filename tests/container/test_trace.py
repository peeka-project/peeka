"""
Container E2E tests for trace command functionality.

Tests trace command (function call tree tracing) in Docker containers against both:
- Python 3.12 (GDB-based attachment)
- Python 3.14 (PEP 768 native attachment)
"""

import json
import pytest

from tests.container.conftest import exec_in_container

pytestmark = [pytest.mark.container]


class TestContainerTrace:
    """Test trace command operations in containerized environments."""

    def test_trace_times_limit_exact_n_py314(self, py314_target):
        """Verify py314 trace -n emits exactly the requested observation count."""
        container = py314_target["container"]
        pid = py314_target["pid"]

        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        exit_code, trace_output = exec_in_container(
            container,
            'python -m peeka.cli.main trace "__main__.Calculator.add" -n 2',
            timeout=30,
        )
        assert exit_code == 0, f"Trace command failed:\n{trace_output}"

        observations = []
        for line in trace_output.strip().splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("type") == "observation":
                observations.append(record)

        assert len(observations) == 2, (
            f"Expected exactly 2 trace observations, got {len(observations)}:\n"
            f"{trace_output}"
        )

    def test_trace_basic(self, container_target):
        """Verify basic trace command captures call tree."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Trace Calculator.add with 2 observations
        exit_code, trace_output = exec_in_container(
            container,
            'python -m peeka.cli.main trace "__main__.Calculator.add" -n 2',
            timeout=30,
        )

        # Verify output contains trace events
        assert "trace_started" in trace_output or "observation" in trace_output, (
            f"Expected trace events in output:\n{trace_output}"
        )

        # Parse JSONL and verify structure
        lines = [line for line in trace_output.strip().split("\n") if line.strip()]
        json_lines = [line for line in lines if line.startswith("{")]

        has_trace_started = False
        has_observation_with_call_tree = False

        for line in json_lines:
            try:
                data = json.loads(line)
                if data.get("event") == "trace_started":
                    has_trace_started = True
                if data.get("type") == "observation":
                    # Trace observations should have call_tree field
                    if "call_tree" in data:
                        has_observation_with_call_tree = True
                        # Verify call_tree is a list
                        assert isinstance(data["call_tree"], list), (
                            f"call_tree should be a list: {data['call_tree']}"
                        )
            except json.JSONDecodeError:
                continue

        assert has_trace_started or has_observation_with_call_tree, (
            f"No valid trace events found in output:\n{trace_output}"
        )

    def test_trace_with_depth_limit(self, container_target):
        """Verify trace respects depth limit parameter."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Trace with depth limit of 2
        exit_code, trace_output = exec_in_container(
            container,
            'python -m peeka.cli.main trace "__main__.Calculator.add" -d 2 -n 1',
            timeout=30,
        )

        # Command should complete successfully
        assert exit_code == 0, f"Trace command failed:\n{trace_output}"

        # Parse observations and verify depth constraint
        lines = [line for line in trace_output.strip().split("\n") if line.strip()]

        for line in lines:
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "observation" and "call_tree" in data:
                        # Check that all nodes have depth <= 2
                        call_tree = data["call_tree"]
                        for node in call_tree:
                            if "depth" in node:
                                assert node["depth"] <= 2, (
                                    f"Node depth {node['depth']} exceeds limit 2: {node}"
                                )
                except json.JSONDecodeError:
                    continue

    def test_trace_with_times_limit(self, container_target):
        """Verify trace respects times limit parameter."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Trace with 1 observation max
        exit_code, trace_output = exec_in_container(
            container,
            'python -m peeka.cli.main trace "__main__.Calculator.add" -n 1',
            timeout=30,
        )

        # Command should complete successfully
        assert exit_code == 0, f"Trace command failed:\n{trace_output}"

        # Count observations in output
        lines = [line for line in trace_output.strip().split("\n") if line.strip()]
        observation_count = 0

        for line in lines:
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "observation":
                        observation_count += 1
                except json.JSONDecodeError:
                    continue

        # Should have at most 1 observation
        assert observation_count <= 1, (
            f"Expected at most 1 observation, got {observation_count}"
        )

    def test_trace_call_tree_structure(self, container_target):
        """Verify trace call tree has correct structure."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Trace command
        exit_code, trace_output = exec_in_container(
            container,
            'python -m peeka.cli.main trace "__main__.Calculator.add" -n 1',
            timeout=30,
        )

        # Parse observations and verify call tree structure
        lines = [line for line in trace_output.strip().split("\n") if line.strip()]

        for line in lines:
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "observation" and "call_tree" in data:
                        call_tree = data["call_tree"]

                        # Verify call_tree is a list
                        assert isinstance(call_tree, list), "call_tree should be a list"

                        # Verify at least one node exists
                        assert len(call_tree) > 0, "call_tree should not be empty"

                        # Verify root node structure
                        root = call_tree[0]
                        assert "depth" in root, "Root node should have depth field"
                        assert root["depth"] == 0, "Root node depth should be 0"
                        assert "function" in root, "Root node should have function field"
                        assert "duration_ms" in root, "Root node should have duration_ms field"

                        # Root should be the target function
                        assert "Calculator.add" in root["function"], (
                            f"Root function should be Calculator.add: {root['function']}"
                        )

                        return  # Test passed

                except json.JSONDecodeError:
                    continue

        pytest.fail(f"No valid trace observation with call_tree found:\n{trace_output}")

    def test_trace_with_condition(self, container_target):
        """Verify trace with condition filter."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Trace with condition filter (cost > 0 should always match)
        exit_code, trace_output = exec_in_container(
            container,
            'python -m peeka.cli.main trace "__main__.Calculator.add" --condition "cost >= 0" -n 2',
            timeout=30,
        )

        # Command should run without error
        assert exit_code == 0, f"Trace command failed:\n{trace_output}"

        # Verify no error messages in output
        output_lower = trace_output.lower()
        assert "traceback" not in output_lower, (
            f"Unexpected traceback in output:\n{trace_output}"
        )

    def test_trace_skip_builtin_default(self, container_target):
        """Verify trace skips builtin functions by default."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Trace command (skip-builtin is true by default)
        exit_code, trace_output = exec_in_container(
            container,
            'python -m peeka.cli.main trace "__main__.Calculator.add" -n 1',
            timeout=30,
        )

        # Command should complete successfully
        assert exit_code == 0, f"Trace command failed:\n{trace_output}"

        # Parse observations and verify no builtin functions in call tree
        lines = [line for line in trace_output.strip().split("\n") if line.strip()]

        for line in lines:
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "observation" and "call_tree" in data:
                        call_tree = data["call_tree"]

                        # Check that builtin functions are not in the tree
                        for node in call_tree:
                            if "function" in node:
                                func_name = node["function"].lower()
                                # Builtin functions typically have names like <built-in> or start with <
                                assert not func_name.startswith("<"), (
                                    f"Found builtin function in call tree: {node['function']}"
                                )

                        return  # Test passed

                except json.JSONDecodeError:
                    continue

    def test_trace_multiply_function(self, container_target):
        """Verify trace on multiply function."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Trace Calculator.multiply
        exit_code, trace_output = exec_in_container(
            container,
            'python -m peeka.cli.main trace "__main__.Calculator.multiply" -n 1',
            timeout=30,
        )

        # Command should complete successfully
        assert exit_code == 0, f"Trace command failed:\n{trace_output}"

        # Verify observations present with call_tree
        lines = [line for line in trace_output.strip().split("\n") if line.strip()]
        has_observation = False

        for line in lines:
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "observation":
                        has_observation = True
                        # Should have call_tree
                        assert "call_tree" in data, (
                            f"Trace observation should have call_tree: {data}"
                        )
                        # Should have total_duration_ms
                        assert "total_duration_ms" in data, (
                            f"Trace observation should have total_duration_ms: {data}"
                        )
                        break
                except json.JSONDecodeError:
                    continue

        assert has_observation or "trace_started" in trace_output, (
            f"No observations found for multiply function:\n{trace_output}"
        )

    def test_trace_invalid_pattern(self, container_target):
        """Verify graceful failure for invalid function pattern."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Trace non-existent function
        exit_code, trace_output = exec_in_container(
            container,
            'python -m peeka.cli.main trace "nonexistent.Module.method" -n 1',
            timeout=30,
        )

        # Should fail gracefully with error message
        output_lower = trace_output.lower()
        assert (
            "error" in output_lower
            or "not found" in output_lower
            or "cannot find" in output_lower
        ), f"Expected error for invalid pattern:\n{trace_output}"

    def test_trace_jsonl_format(self, container_target):
        """Verify trace output is valid JSONL format."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Trace command
        exit_code, trace_output = exec_in_container(
            container,
            'python -m peeka.cli.main trace "__main__.Calculator.add" -n 1',
            timeout=30,
        )

        # Parse all JSON lines
        lines = [line for line in trace_output.strip().split("\n") if line.strip()]
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
            f"No valid JSON lines found in output:\n{trace_output}"
        )

    def test_trace_duration_fields(self, container_target):
        """Verify trace observations have duration fields."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Trace command
        exit_code, trace_output = exec_in_container(
            container,
            'python -m peeka.cli.main trace "__main__.Calculator.add" -n 1',
            timeout=30,
        )

        # Parse observations
        lines = [line for line in trace_output.strip().split("\n") if line.strip()]

        for line in lines:
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "observation" and "call_tree" in data:
                        # Should have total_duration_ms
                        assert "total_duration_ms" in data, (
                            f"Missing total_duration_ms: {data}"
                        )

                        # Verify total_duration_ms is a number >= 0
                        duration = data["total_duration_ms"]
                        assert isinstance(duration, (int, float)), (
                            f"total_duration_ms should be numeric: {duration}"
                        )
                        assert duration >= 0, (
                            f"total_duration_ms should be >= 0: {duration}"
                        )

                        # Each node in call_tree should have duration_ms
                        call_tree = data["call_tree"]
                        for node in call_tree:
                            assert "duration_ms" in node, (
                                f"Node missing duration_ms: {node}"
                            )
                            node_duration = node["duration_ms"]
                            assert isinstance(node_duration, (int, float)), (
                                f"Node duration_ms should be numeric: {node_duration}"
                            )

                        return  # Test passed

                except json.JSONDecodeError:
                    continue

    def test_trace_node_count(self, container_target):
        """Verify trace observations have node_count field."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Trace command
        exit_code, trace_output = exec_in_container(
            container,
            'python -m peeka.cli.main trace "__main__.Calculator.add" -n 1',
            timeout=30,
        )

        # Parse observations
        lines = [line for line in trace_output.strip().split("\n") if line.strip()]

        for line in lines:
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    if data.get("type") == "observation" and "call_tree" in data:
                        # Should have node_count
                        assert "node_count" in data, (
                            f"Missing node_count: {data}"
                        )

                        # Verify node_count is a positive integer
                        node_count = data["node_count"]
                        assert isinstance(node_count, int), (
                            f"node_count should be an integer: {node_count}"
                        )
                        assert node_count > 0, (
                            f"node_count should be > 0: {node_count}"
                        )

                        return  # Test passed

                except json.JSONDecodeError:
                    continue
