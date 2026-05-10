"""
Container E2E tests for asyncio watch command functionality.

Tests watch command on async functions in Docker containers against:
- Python 3.12 (GDB-based attachment)
- Python 3.14 (PEP 768 native attachment)
"""

import json
from typing import Any, Dict, List

import pytest

from tests.container.conftest import exec_in_container

pytestmark = pytest.mark.container


class TestAsyncWatchPy314:
    """Test asyncio watch command on Python 3.14 (PEP 768 path)."""

    @pytest.mark.timeout(180)
    def test_async_watch_pep768(self, py314_async_target):
        """Verify watch on async functions using PEP 768 attachment."""
        container, pid = py314_async_target  # pid is str

        # Step 1: Attach
        rc_a, out_a = exec_in_container(
            container,
            f"python -m peeka.cli.main attach {pid}",
            timeout=30
        )
        assert rc_a == 0, f"Attach failed: {out_a}"

        try:
            # Step 2: Watch (NO --pid flag)
            rc_w, out_w = exec_in_container(
                container,
                "python -m peeka.cli.main watch examples.asyncio_attach_target.handle_request -n 3",
                timeout=60
            )
            assert rc_w == 0, f"Watch failed: {out_w}"

            # Parse JSONL
            events: List[Dict[str, Any]] = []
            for line in out_w.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # Skip malformed lines

            # Assert watch_started with is_coroutine_function=true
            watch_started = [e for e in events if e.get("event") == "watch_started"]
            assert len(watch_started) >= 1, f"No watch_started event in {events}"
            assert watch_started[0]["data"]["target"]["is_coroutine_function"] is True

            # Assert observations with cost and returnObj
            observations = [e for e in events if e.get("type") == "observation"]
            assert len(observations) >= 1, f"No observations in {events}"

            for obs in observations:
                assert "cost" in obs, f"Missing cost in {obs}"
                assert isinstance(obs["cost"], (int, float)), f"Invalid cost type in {obs}"
                assert obs["cost"] >= 0, f"Negative cost in {obs}"

            assert any(obs.get("success") is True for obs in observations), "No successful observations"
            assert any(obs.get("returnObj") is not None for obs in observations), "All returnObj are None"

        finally:
            # Step 3: Detach (best-effort cleanup)
            rc_d, out_d = exec_in_container(
                container,
                "python -m peeka.cli.main detach",
                timeout=30
            )
            if rc_d != 0:
                print(f"Warning: Detach failed with rc={rc_d}: {out_d}")


class TestAsyncWatchGdb:
    """Test asyncio watch command on Python 3.12 (GDB + ptrace fallback)."""

    @pytest.mark.timeout(180)
    def test_async_watch_gdb(self, gdb_async_target):
        """Verify watch on async functions using GDB ptrace fallback."""
        container, pid = gdb_async_target  # pid is str

        # Step 1: Attach
        rc_a, out_a = exec_in_container(
            container,
            f"python -m peeka.cli.main attach {pid}",
            timeout=30
        )
        assert rc_a == 0, f"Attach failed: {out_a}"

        try:
            # Step 2: Watch (NO --pid flag)
            rc_w, out_w = exec_in_container(
                container,
                "python -m peeka.cli.main watch examples.asyncio_attach_target.handle_request -n 3",
                timeout=60
            )
            assert rc_w == 0, f"Watch failed: {out_w}"

            # Parse JSONL
            events: List[Dict[str, Any]] = []
            for line in out_w.splitlines():
                line = line.strip()
                if line.startswith("{"):
                    try:
                        events.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass  # Skip malformed lines

            # Assert watch_started with is_coroutine_function=true
            watch_started = [e for e in events if e.get("event") == "watch_started"]
            assert len(watch_started) >= 1, f"No watch_started event in {events}"
            assert watch_started[0]["data"]["target"]["is_coroutine_function"] is True

            # Assert observations with cost and returnObj
            observations = [e for e in events if e.get("type") == "observation"]
            assert len(observations) >= 1, f"No observations in {events}"

            for obs in observations:
                assert "cost" in obs, f"Missing cost in {obs}"
                assert isinstance(obs["cost"], (int, float)), f"Invalid cost type in {obs}"
                assert obs["cost"] >= 0, f"Negative cost in {obs}"

            assert any(obs.get("success") is True for obs in observations), "No successful observations"
            assert any(obs.get("returnObj") is not None for obs in observations), "All returnObj are None"

        finally:
            # Step 3: Detach (best-effort cleanup)
            rc_d, out_d = exec_in_container(
                container,
                "python -m peeka.cli.main detach",
                timeout=30
            )
            if rc_d != 0:
                print(f"Warning: Detach failed with rc={rc_d}: {out_d}")
