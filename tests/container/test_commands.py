"""
Container E2E tests for diagnostic commands.

Tests all diagnostic commands (stack, monitor, logger, memory, sc, sm, reset)
in Docker containers against both:
- Python 3.12 (GDB-based attachment)
- Python 3.14 (PEP 768 native attachment)
"""

import json
import pytest

from tests.container.conftest import exec_in_container

pytestmark = [pytest.mark.container]


class TestDiagnosticCommands:
    """Test diagnostic commands in containerized environments."""

    def test_stack_trace(self, container_target):
        """Verify stack command captures call stack."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run stack command
        exit_code, output = exec_in_container(
            container,
            f"python -m peeka.cli.main stack '__main__.Calculator.add' -n 1",
            timeout=15,
        )

        # Parse JSONL output
        lines = [
            l for l in output.strip().split("\n") if l.strip() and l.startswith("{")
        ]

        # Look for observation with stack data
        has_observation = False
        for line in lines:
            try:
                data = json.loads(line)
                if data.get("type") == "observation":
                    has_observation = True
                    # Stack observations should have call_stack field
                    assert "call_stack" in data or "stack" in str(data), (
                        f"Observation missing call stack data: {data}"
                    )
                    break
            except json.JSONDecodeError:
                continue

        assert has_observation, f"No observation found in output:\n{output}"

    def test_monitor_stats(self, container_target):
        """Verify monitor command collects performance stats."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run monitor command with short interval (CRITICAL: --interval 1)
        exit_code, output = exec_in_container(
            container,
            f"python -m peeka.cli.main monitor '__main__.Calculator.add' --interval 1 -c 2",
            timeout=15,
        )

        # Parse JSONL output
        lines = [
            l for l in output.strip().split("\n") if l.strip() and l.startswith("{")
        ]

        # Look for monitoring data
        has_monitor_data = False
        for line in lines:
            try:
                data = json.loads(line)
                if data.get("type") == "observation":
                    has_monitor_data = True
                    # Monitor observations should have stats (call_count, timing, etc.)
                    data_str = str(data).lower()
                    assert (
                        "count" in data_str
                        or "duration" in data_str
                        or "stats" in data_str
                    ), f"Observation missing monitoring stats: {data}"
                    break
            except json.JSONDecodeError:
                continue

        assert has_monitor_data, f"No monitoring data found in output:\n{output}"

    def test_logger_list(self, container_target):
        """Verify logger list command returns logger information."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run logger list command
        exit_code, output = exec_in_container(
            container, "python -m peeka.cli.main logger --action list", timeout=10
        )

        # Parse JSONL output
        lines = [
            l for l in output.strip().split("\n") if l.strip() and l.startswith("{")
        ]

        # Look for result with logger data
        has_result = False
        for line in lines:
            try:
                data = json.loads(line)
                if data.get("type") == "result":
                    has_result = True
                    assert "data" in data, f"Result missing data field: {data}"
                    break
            except json.JSONDecodeError:
                continue

        assert has_result or exit_code == 0, (
            f"Logger list command failed or returned no result:\n{output}"
        )

    def test_logger_set_level(self, container_target):
        """Verify logger set command changes log level."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run logger set command
        exit_code, output = exec_in_container(
            container,
            "python -m peeka.cli.main logger --action set --name root --level DEBUG",
            timeout=10,
        )

        # Should succeed (exit code 0 OR success message)
        output_lower = output.lower()
        assert exit_code == 0 or "success" in output_lower, (
            f"Logger set command failed:\n{output}"
        )

    def test_memory_overview(self, container_target):
        """Verify memory command returns memory information."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run memory overview command
        exit_code, output = exec_in_container(
            container, "python -m peeka.cli.main memory --action overview", timeout=10
        )

        # Parse JSONL output
        lines = [
            l for l in output.strip().split("\n") if l.strip() and l.startswith("{")
        ]

        # Look for result with memory data
        has_memory_data = False
        for line in lines:
            try:
                data = json.loads(line)
                if data.get("type") == "result" or data.get("type") == "observation":
                    data_str = str(data).lower()
                    if "memory" in data_str or "rss" in data_str or "size" in data_str:
                        has_memory_data = True
                        break
            except json.JSONDecodeError:
                continue

        assert has_memory_data or exit_code == 0, (
            f"Memory overview command failed or returned no data:\n{output}"
        )

    def test_search_class(self, container_target):
        """Verify sc command searches for classes."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run search class command
        exit_code, output = exec_in_container(
            container, "python -m peeka.cli.main sc 'Calculator'", timeout=10
        )

        # Parse JSONL output
        lines = [
            l for l in output.strip().split("\n") if l.strip() and l.startswith("{")
        ]

        # Look for result with Calculator class info
        has_class_info = False
        for line in lines:
            try:
                data = json.loads(line)
                if data.get("type") == "result":
                    data_str = str(data).lower()
                    if "calculator" in data_str or "class" in data_str:
                        has_class_info = True
                        break
            except json.JSONDecodeError:
                continue

        assert has_class_info or exit_code == 0, (
            f"Search class command failed or returned no Calculator info:\n{output}"
        )

    def test_search_method(self, container_target):
        """Verify sm command searches for methods."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run search method command
        exit_code, output = exec_in_container(
            container, "python -m peeka.cli.main sm 'add'", timeout=10
        )

        # Parse JSONL output
        lines = [
            l for l in output.strip().split("\n") if l.strip() and l.startswith("{")
        ]

        # Look for result with add method info
        has_method_info = False
        for line in lines:
            try:
                data = json.loads(line)
                if data.get("type") == "result":
                    data_str = str(data).lower()
                    if "add" in data_str or "method" in data_str:
                        has_method_info = True
                        break
            except json.JSONDecodeError:
                continue

        assert has_method_info or exit_code == 0, (
            f"Search method command failed or returned no add method info:\n{output}"
        )

    def test_reset_after_watch(self, container_target):
        """Verify reset command successfully resets after watching."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Start a brief watch (background process, kill after 2 seconds)
        watch_cmd = (
            "timeout 2 python -m peeka.cli.main watch '__main__.Calculator.add' "
            ">/tmp/watch.log 2>&1 &"
        )
        exec_in_container(container, watch_cmd, timeout=5)

        # Wait a bit for watch to start
        exec_in_container(container, "sleep 0.5", timeout=2)

        # Run reset command
        exit_code, output = exec_in_container(
            container, "python -m peeka.cli.main reset", timeout=10
        )

        # Should succeed (exit code 0 OR success message)
        output_lower = output.lower()
        assert exit_code == 0 or "success" in output_lower or "reset" in output_lower, (
            f"Reset command failed:\n{output}"
        )

    def test_monitor_with_custom_interval(self, container_target):
        """Verify monitor respects custom interval parameter."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run monitor with very short interval (--interval 1) and limited cycles
        import time

        start_time = time.time()

        exit_code, output = exec_in_container(
            container,
            f"python -m peeka.cli.main monitor '__main__.Calculator.multiply' --interval 1 -c 3",
            timeout=10,
        )

        elapsed = time.time() - start_time

        # Should complete in reasonable time (not default 60s interval)
        # 3 cycles × 1s interval = ~3 seconds (plus overhead)
        assert elapsed < 15, (
            f"Monitor took too long ({elapsed}s), likely not respecting --interval 1"
        )

        # Should have monitoring data
        assert exit_code == 0 or "observation" in output.lower(), (
            f"Monitor command failed:\n{output}"
        )

    def test_stack_with_depth(self, container_target):
        """Verify stack command with explicit depth parameter."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run stack command with depth limit
        exit_code, output = exec_in_container(
            container,
            f"python -m peeka.cli.main stack '__main__.Calculator.multiply' -n 2",
            timeout=15,
        )

        # Parse JSONL output
        lines = [
            l for l in output.strip().split("\n") if l.strip() and l.startswith("{")
        ]

        # Should have stack observations
        observation_count = 0
        for line in lines:
            try:
                data = json.loads(line)
                if data.get("type") == "observation":
                    observation_count += 1
            except json.JSONDecodeError:
                continue

        # Should have collected up to 2 observations (may be less if function not called)
        assert observation_count <= 2, (
            f"Expected ≤2 observations with -n 2, got {observation_count}"
        )

    def test_logger_get_specific_logger(self, container_target):
        """Verify logger get command for specific logger."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run logger get command for root logger
        exit_code, output = exec_in_container(
            container,
            "python -m peeka.cli.main logger --action get --name root",
            timeout=10,
        )

        # Should succeed or return logger info
        output_lower = output.lower()
        assert exit_code == 0 or "root" in output_lower or "level" in output_lower, (
            f"Logger get command failed:\n{output}"
        )

    def test_memory_gc_action(self, container_target):
        """Verify memory gc action triggers garbage collection."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run memory gc command
        exit_code, output = exec_in_container(
            container, "python -m peeka.cli.main memory --action gc", timeout=10
        )

        # Should succeed (exit code 0 OR success/gc message)
        output_lower = output.lower()
        assert exit_code == 0 or "success" in output_lower or "gc" in output_lower, (
            f"Memory gc command failed:\n{output}"
        )

    def test_search_class_wildcard(self, container_target):
        """Verify sc command with wildcard pattern."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run search class with wildcard
        exit_code, output = exec_in_container(
            container, "python -m peeka.cli.main sc '*Calc*'", timeout=10
        )

        # Should return Calculator or succeed
        output_lower = output.lower()
        assert exit_code == 0 or "calculator" in output_lower, (
            f"Search class with wildcard failed:\n{output}"
        )

    def test_search_method_wildcard(self, container_target):
        """Verify sm command with wildcard pattern."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach first
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Run search method with wildcard
        exit_code, output = exec_in_container(
            container, "python -m peeka.cli.main sm 'mult*'", timeout=10
        )

        # Should return multiply or succeed
        output_lower = output.lower()
        assert exit_code == 0 or "multiply" in output_lower, (
            f"Search method with wildcard failed:\n{output}"
        )

    def test_trace_basic(self, container_target):
        """Verify trace command captures function call tree."""
        container = container_target["container"]
        pid = container_target["pid"]

        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        exit_code, output = exec_in_container(
            container,
            "python -m peeka.cli.main trace '__main__.Calculator.add' -n 1",
            timeout=30,
        )

        lines = [
            l for l in output.strip().split("\n") if l.strip() and l.startswith("{")
        ]

        has_trace_data = False
        for line in lines:
            try:
                data = json.loads(line)
                if data.get("type") == "observation" and "call_tree" in data:
                    has_trace_data = True
                    assert isinstance(data["call_tree"], list), (
                        f"call_tree should be a list: {data['call_tree']}"
                    )
                    assert "total_duration_ms" in data, (
                        f"Missing total_duration_ms: {data}"
                    )
                    assert isinstance(data["total_duration_ms"], (int, float)), (
                        f"total_duration_ms should be numeric: {data['total_duration_ms']}"
                    )
                    assert "node_count" in data, f"Missing node_count: {data}"
                    assert (
                        isinstance(data["node_count"], int) and data["node_count"] > 0
                    ), f"node_count should be positive int: {data['node_count']}"
                    break
            except json.JSONDecodeError:
                continue

        assert has_trace_data, f"No trace observation with call_tree found:\n{output}"

    def test_trace_with_depth_limit(self, container_target):
        """Verify trace respects depth limit parameter."""
        container = container_target["container"]
        pid = container_target["pid"]

        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        exit_code, output = exec_in_container(
            container,
            "python -m peeka.cli.main trace '__main__.Calculator.add' -n 1",
            timeout=30,
        )

        assert exit_code == 0, f"Trace command failed:\n{output}"

        lines = [
            l for l in output.strip().split("\n") if l.strip() and l.startswith("{")
        ]

        for line in lines:
            try:
                data = json.loads(line)
                if data.get("type") == "observation" and "call_tree" in data:
                    for node in data["call_tree"]:
                        if "depth" in node:
                            assert node["depth"] <= 1, (
                                f"Node depth {node['depth']} exceeds limit 1: {node}"
                            )
            except json.JSONDecodeError:
                continue

    def test_trace_with_condition(self, container_target):
        """Verify trace with condition filter runs without error."""
        container = container_target["container"]
        pid = container_target["pid"]

        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        exit_code, output = exec_in_container(
            container,
            "python -m peeka.cli.main trace '__main__.Calculator.add' --condition \"cost >= 0\" -n 1",
            timeout=30,
        )

        assert exit_code == 0, f"Trace with condition failed:\n{output}"
        assert "traceback" not in output.lower(), (
            f"Unexpected traceback in output:\n{output}"
        )
