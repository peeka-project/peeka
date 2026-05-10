"""End-to-end tests for asyncio watch command via subprocess CLI invocation."""

import json
import subprocess
import sys
from typing import Any, Dict, List

import pytest

pytestmark = pytest.mark.e2e


def _run_cli(args: List[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """Helper to run peeka CLI command."""
    return subprocess.run(
        [sys.executable, "-m", "peeka.cli", *args],
        capture_output=True,
        text=True,
        timeout=timeout
    )


class TestAsyncWatchE2E:
    """End-to-end tests for watching async functions via CLI."""

    @pytest.mark.timeout(120)
    def test_watch_started_emits_async_metadata(self, async_target_process, has_ptrace_permission):
        """Test watch_started event contains is_coroutine_function=True metadata."""
        if not has_ptrace_permission:
            pytest.skip("Requires ptrace permission")

        proc, pid = async_target_process

        # Attach to target process
        attach_result = _run_cli(["attach", str(pid)], timeout=30)
        assert attach_result.returncode == 0, f"Attach failed: {attach_result.stderr}"

        try:
            # Watch async function (no --pid, agent already attached)
            watch_result = _run_cli(
                ["watch", "examples.asyncio_attach_target.handle_request", "-n", "3"],
                timeout=60
            )
            assert watch_result.returncode == 0, f"Watch failed: {watch_result.stderr}"

            # Parse JSONL output
            events: List[Dict[str, Any]] = []
            for line in watch_result.stdout.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

            # Find watch_started event
            watch_started = None
            for event in events:
                if event.get("event") == "watch_started":
                    watch_started = event
                    break

            assert watch_started is not None, "No watch_started event found"
            data = watch_started["data"]
            target = data["target"]

            # Assert async metadata
            assert target["is_coroutine_function"] is True
            assert isinstance(target["alias_count"], int)
            assert isinstance(target["aliases"], list)

        finally:
            # Best-effort detach
            _run_cli(["detach"], timeout=15)

    @pytest.mark.timeout(120)
    def test_observation_emitted_with_cost_and_returnobj(self, async_target_process, has_ptrace_permission):
        """Test observations contain cost and returnObj fields."""
        if not has_ptrace_permission:
            pytest.skip("Requires ptrace permission")

        proc, pid = async_target_process

        # Attach to target process
        attach_result = _run_cli(["attach", str(pid)], timeout=30)
        assert attach_result.returncode == 0, f"Attach failed: {attach_result.stderr}"

        try:
            # Watch async function
            watch_result = _run_cli(
                ["watch", "examples.asyncio_attach_target.handle_request", "-n", "3"],
                timeout=60
            )
            assert watch_result.returncode == 0, f"Watch failed: {watch_result.stderr}"

            # Parse JSONL output and filter observations
            observations: List[Dict[str, Any]] = []
            for line in watch_result.stdout.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        event = json.loads(line)
                        if event.get("type") == "observation":
                            observations.append(event)
                    except json.JSONDecodeError:
                        continue

            # Assert at least one observation
            assert len(observations) >= 1, "No observations emitted"

            # Assert all observations have cost field
            for obs in observations:
                assert "cost" in obs, f"Observation missing cost: {obs}"
                assert isinstance(obs["cost"], (int, float))
                assert obs["cost"] >= 0

            # Assert at least one successful observation
            assert any(obs.get("success") is True for obs in observations)

            # Assert at least one observation has returnObj
            assert any(obs.get("returnObj") is not None for obs in observations)

        finally:
            # Best-effort detach
            _run_cli(["detach"], timeout=15)

    @pytest.mark.timeout(120)
    def test_clean_detach(self, async_target_process, has_ptrace_permission):
        """Test detach leaves target process alive."""
        if not has_ptrace_permission:
            pytest.skip("Requires ptrace permission")

        proc, pid = async_target_process

        # Attach to target process
        attach_result = _run_cli(["attach", str(pid)], timeout=30)
        assert attach_result.returncode == 0, f"Attach failed: {attach_result.stderr}"

        try:
            # Watch async function (single observation)
            watch_result = _run_cli(
                ["watch", "examples.asyncio_attach_target.handle_request", "-n", "1"],
                timeout=60
            )
            assert watch_result.returncode == 0, f"Watch failed: {watch_result.stderr}"

            # Detach (happy path assertion)
            detach_result = _run_cli(["detach"], timeout=15)
            assert detach_result.returncode == 0, f"Detach failed: {detach_result.stderr}"

        finally:
            # Best-effort detach (no assertions)
            _run_cli(["detach"], timeout=15)

        # Assert target still alive
        assert proc.poll() is None, "Target process died after detach"
