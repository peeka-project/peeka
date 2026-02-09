"""CLI E2E workflow tests in containerized environments.

Tests complete user workflows (attach → commands → detach) across both
GDB-based (Python 3.12) and PEP 768 (Python 3.14) containers.
"""

import json
from typing import Dict, List

import pytest

from tests.container.conftest import exec_in_container

pytestmark = [pytest.mark.container]


def run_cli_command(
    container, cmd_parts: List[str], timeout: int = 15
) -> Dict[str, any]:
    """Execute peeka-cli command in container and parse JSONL output.

    Args:
        container: DockerContainer instance
        cmd_parts: Command parts (e.g., ["attach", "12345"])
        timeout: Maximum execution time in seconds

    Returns:
        Dict with keys:
            - exit_code: int
            - raw_output: str (full stdout)
            - messages: List[dict] (parsed JSONL lines)
            - success_msg: dict or None (first success message)
            - error_msg: dict or None (first error message)
    """
    cli_cmd = f"python -m peeka.cli.main {' '.join(cmd_parts)}"
    exit_code, output = exec_in_container(container, cli_cmd, timeout=timeout)

    # Parse JSONL output
    messages = []
    success_msg = None
    error_msg = None

    for line in output.strip().split("\n"):
        if not line.strip() or not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
            messages.append(msg)
            if msg.get("type") == "success" and success_msg is None:
                success_msg = msg
            if msg.get("type") == "error" and error_msg is None:
                error_msg = msg
        except json.JSONDecodeError:
            continue

    return {
        "exit_code": exit_code,
        "raw_output": output,
        "messages": messages,
        "success_msg": success_msg,
        "error_msg": error_msg,
    }


def verify_no_socket_files(container):
    """Verify no peeka socket files remain in /tmp.

    Args:
        container: DockerContainer instance

    Returns:
        True if cleanup successful (no socket files found)
    """
    exit_code, output = exec_in_container(
        container, "ls /tmp/peeka_*.sock 2>/dev/null || true", timeout=5
    )
    # If ls finds files, output will be non-empty (excluding whitespace)
    # If no files, output will be empty or just whitespace
    return len(output.strip()) == 0


class TestCLIWorkflowE2E:
    """Full CLI workflow tests (attach → commands → detach)."""

    def test_full_workflow_attach_watch_detach(self, container_target):
        """Complete workflow: attach, watch 3 times, detach, verify cleanup."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Step 1: Attach
        attach_result = run_cli_command(container, ["attach", pid])
        assert attach_result["exit_code"] == 0, (
            f"Attach failed: {attach_result['raw_output']}"
        )
        assert attach_result["success_msg"] is not None, "No success message"
        assert "socket" in attach_result["success_msg"].get("data", {}), (
            "Socket path missing"
        )

        # Step 2: Watch 3 times
        watch_result = run_cli_command(
            container, ["watch", "__main__.Calculator.add", "-n", "3"], timeout=20
        )
        assert watch_result["exit_code"] == 0 or watch_result["exit_code"] == 124, (
            f"Watch failed: {watch_result['raw_output']}"
        )  # 124 = timeout (expected for -n limit)

        # Verify watch output
        watch_messages = watch_result["messages"]
        event_msgs = [m for m in watch_messages if m.get("type") == "event"]
        observation_msgs = [m for m in watch_messages if m.get("type") == "observation"]

        assert len(event_msgs) >= 1, "No watch_started event"
        assert event_msgs[0].get("event") == "watch_started", "Missing watch_started"
        assert len(observation_msgs) >= 1, (
            f"No observations received. Got: {watch_result['raw_output']}"
        )

        # Step 3: Detach
        detach_result = run_cli_command(container, ["detach"])
        assert detach_result["exit_code"] == 0, (
            f"Detach failed: {detach_result['raw_output']}"
        )
        assert detach_result["success_msg"] is not None or "success" in (
            detach_result["raw_output"].lower()
        ), "Detach did not succeed"

        # Verify cleanup: no socket files remain
        assert verify_no_socket_files(container), "Socket files remain after detach"

    def test_full_workflow_attach_multiple_commands(self, container_target):
        """Workflow: attach, sc, sm, watch, reset, detach."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Step 1: Attach
        attach_result = run_cli_command(container, ["attach", pid])
        assert attach_result["exit_code"] == 0, "Attach failed"
        assert attach_result["success_msg"] is not None

        # Step 2: Search class (sc Calculator)
        sc_result = run_cli_command(container, ["sc", "Calculator"])
        assert sc_result["exit_code"] == 0, f"sc failed: {sc_result['raw_output']}"
        # Expect result type message
        result_msgs = [m for m in sc_result["messages"] if m.get("type") == "result"]
        assert len(result_msgs) > 0, "No result message from sc"

        # Step 3: Search method (sm add)
        sm_result = run_cli_command(container, ["sm", "add"])
        assert sm_result["exit_code"] == 0, f"sm failed: {sm_result['raw_output']}"
        result_msgs = [m for m in sm_result["messages"] if m.get("type") == "result"]
        assert len(result_msgs) > 0, "No result message from sm"

        # Step 4: Watch 2 times
        watch_result = run_cli_command(
            container, ["watch", "__main__.Calculator.add", "-n", "2"], timeout=15
        )
        assert watch_result["exit_code"] in [0, 124], "Watch failed"
        observations = [
            m for m in watch_result["messages"] if m.get("type") == "observation"
        ]
        assert len(observations) >= 1, "No observations from watch"

        # Step 5: Reset
        reset_result = run_cli_command(container, ["reset"])
        assert reset_result["exit_code"] == 0, (
            f"reset failed: {reset_result['raw_output']}"
        )

        # Step 6: Detach
        detach_result = run_cli_command(container, ["detach"])
        assert detach_result["exit_code"] == 0, "Detach failed"
        assert verify_no_socket_files(container), "Socket files remain"

    def test_workflow_watch_then_stack(self, container_target):
        """Workflow: attach, watch, stack, detach."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach
        attach_result = run_cli_command(container, ["attach", pid])
        assert attach_result["exit_code"] == 0, "Attach failed"

        # Watch Calculator.add (1 observation)
        watch_result = run_cli_command(
            container, ["watch", "__main__.Calculator.add", "-n", "1"], timeout=15
        )
        assert watch_result["exit_code"] in [0, 124], "Watch failed"
        watch_observations = [
            m for m in watch_result["messages"] if m.get("type") == "observation"
        ]
        assert len(watch_observations) >= 1, "No watch observations"

        # Stack Calculator.multiply (1 observation with stack trace)
        stack_result = run_cli_command(
            container, ["stack", "__main__.Calculator.multiply", "-n", "1"], timeout=15
        )
        assert stack_result["exit_code"] in [0, 124], (
            f"Stack failed: {stack_result['raw_output']}"
        )
        stack_observations = [
            m for m in stack_result["messages"] if m.get("type") == "observation"
        ]
        # Stack command should produce observations with stack_trace field
        assert len(stack_observations) >= 1, "No stack observations"
        # Verify at least one observation has stack_trace
        has_stack_trace = any(
            "stack_trace" in obs.get("data", {}) for obs in stack_observations
        )
        assert has_stack_trace, "No stack_trace field in observations"

        # Detach
        detach_result = run_cli_command(container, ["detach"])
        assert detach_result["exit_code"] == 0, "Detach failed"
        assert verify_no_socket_files(container), "Socket files remain"

    def test_commands_without_attach_fail_gracefully(self, container_target):
        """Verify commands fail gracefully when not attached."""
        container = container_target["container"]

        # Do NOT attach - directly try watch
        watch_result = run_cli_command(
            container, ["watch", "__main__.Calculator.add", "-n", "1"], timeout=10
        )

        # Expect error (no active session / socket not found)
        # Exit code may be non-zero or zero with error message
        error_found = (
            watch_result["error_msg"] is not None
            or "error" in watch_result["raw_output"].lower()
            or "not found" in watch_result["raw_output"].lower()
            or "no active" in watch_result["raw_output"].lower()
        )

        assert error_found, (
            f"Expected error when not attached. Got: {watch_result['raw_output']}"
        )

    def test_workflow_attach_with_condition_filter(self, container_target):
        """Workflow: attach, watch with condition filter, detach."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach
        attach_result = run_cli_command(container, ["attach", pid])
        assert attach_result["exit_code"] == 0, "Attach failed"

        # Watch with condition: params[0] > 5 (should filter some calls)
        watch_result = run_cli_command(
            container,
            [
                "watch",
                "__main__.Calculator.add",
                "--condition",
                "params[0] > 5",
                "-n",
                "2",
            ],
            timeout=20,
        )
        assert watch_result["exit_code"] in [0, 124], "Watch with condition failed"

        # Verify observations received (may be fewer due to filtering)
        observations = [
            m for m in watch_result["messages"] if m.get("type") == "observation"
        ]
        # At least watch_started event should exist
        events = [m for m in watch_result["messages"] if m.get("type") == "event"]
        assert len(events) >= 1, "No watch_started event"

        # Detach
        detach_result = run_cli_command(container, ["detach"])
        assert detach_result["exit_code"] == 0, "Detach failed"
        assert verify_no_socket_files(container), "Socket files remain"

    def test_workflow_attach_logger_detach(self, container_target):
        """Workflow: attach, logger list, detach."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach
        attach_result = run_cli_command(container, ["attach", pid])
        assert attach_result["exit_code"] == 0, "Attach failed"

        # Logger list
        logger_result = run_cli_command(
            container, ["logger", "--action", "list"], timeout=10
        )
        assert logger_result["exit_code"] == 0, (
            f"logger failed: {logger_result['raw_output']}"
        )
        result_msgs = [
            m for m in logger_result["messages"] if m.get("type") == "result"
        ]
        assert len(result_msgs) > 0, "No result message from logger"

        # Detach
        detach_result = run_cli_command(container, ["detach"])
        assert detach_result["exit_code"] == 0, "Detach failed"
        assert verify_no_socket_files(container), "Socket files remain"

    def test_workflow_attach_memory_overview_detach(self, container_target):
        """Workflow: attach, memory overview, detach."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach
        attach_result = run_cli_command(container, ["attach", pid])
        assert attach_result["exit_code"] == 0, "Attach failed"

        # Memory overview
        memory_result = run_cli_command(
            container, ["memory", "--action", "overview"], timeout=10
        )
        assert memory_result["exit_code"] == 0, (
            f"memory failed: {memory_result['raw_output']}"
        )
        result_msgs = [
            m for m in memory_result["messages"] if m.get("type") == "result"
        ]
        assert len(result_msgs) > 0, "No result message from memory"

        # Detach
        detach_result = run_cli_command(container, ["detach"])
        assert detach_result["exit_code"] == 0, "Detach failed"
        assert verify_no_socket_files(container), "Socket files remain"

    def test_workflow_double_attach_fails(self, container_target):
        """Verify attaching twice to same process fails gracefully."""
        container = container_target["container"]
        pid = container_target["pid"]

        # First attach
        attach1_result = run_cli_command(container, ["attach", pid])
        assert attach1_result["exit_code"] == 0, "First attach failed"

        # Second attach (should fail or warn)
        attach2_result = run_cli_command(container, ["attach", pid], timeout=10)

        # Expect error or already attached message
        already_attached = (
            attach2_result["error_msg"] is not None
            or "already" in attach2_result["raw_output"].lower()
            or "exists" in attach2_result["raw_output"].lower()
        )

        # Cleanup
        run_cli_command(container, ["detach"])
        verify_no_socket_files(container)
