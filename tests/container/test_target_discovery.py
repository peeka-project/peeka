"""
Container E2E tests for target discovery alive/stale state matrix.

Tests the complete lifecycle of multiple target agents:
- Attach to multiple targets
- Query alive targets
- Kill one target
- Verify alive/stale classification
- Clean up stale targets

Note: Due to T4 CLI bug (cmd_target functions defined after __main__ guard),
this test calls discovery APIs directly via Python exec instead of shelling
out to peeka-cli. Once T4 fixes the CLI structure, this can be refactored
to use CLI commands for better e2e coverage.
"""

import json
import shlex
import pytest
from typing import Dict, Any, List, Optional

from tests.container.conftest import exec_in_container

pytestmark = [pytest.mark.container, pytest.mark.timeout(180)]


class TestTargetDiscoveryMatrix:
    """Test target discovery with alive/stale state transitions."""

    def test_alive_stale_cleanup_matrix(self, gdb_container):
        """Verify state transitions: alive -> stale -> cleanup -> alive.

        Strategy:
        1. Attach to target1, verify 1 alive
        2. Kill target1 PID (leaves markers orphaned)
        3. Discover immediately: should show 1 stale
        4. Cleanup: removes stale markers
        5. Discover: 0 targets
        6. Attach to target2, verify 1 alive

        Note: Cannot test "2 alive" state because attach auto-cleans stale
        markers from other sessions during its socket scan.
        """
        container = gdb_container

        # Step 1: Start target1
        target1_pid = self._start_target(container, suffix="1")

        # Step 2: Attach peeka to target1
        self._attach_target(container, target1_pid)

        # Step 3: Verify 1 alive target
        targets = self._list_targets(container)
        assert len(targets) == 1, f"Expected 1 target after attach, got {len(targets)}"
        assert targets[0].get("state") == "alive"
        target1_id = targets[0].get("target_id")

        # Step 4: SIGKILL target1 PID (leaves marker files orphaned)
        self._kill_target(container, target1_pid)

        # Step 5: Discover immediately - should show 1 stale
        targets = self._list_targets(container)
        assert len(targets) == 1, f"Expected 1 stale target after kill, got {len(targets)}"
        assert targets[0].get("state") == "stale", (
            f"Expected state=stale, got {targets[0].get('state')}"
        )
        assert targets[0].get("target_id") == target1_id

        # Step 6: Cleanup stale targets
        cleanup_result = self._cleanup_stale_targets(container)

        removed_ids = cleanup_result.get("removed", [])
        assert len(removed_ids) == 1, f"Expected 1 removed target, got {len(removed_ids)}"
        assert target1_id in removed_ids, (
            f"Expected killed target {target1_id} in removed list, got {removed_ids}"
        )

        # Step 7: Discover after cleanup - should be empty
        targets = self._list_targets(container)
        assert len(targets) == 0, f"Expected 0 targets after cleanup, got {len(targets)}"

        # Step 8: Start target2 and attach
        target2_pid = self._start_target(container, suffix="2")
        self._attach_target(container, target2_pid)

        # Step 9: Verify final state - 1 alive
        targets = self._list_targets(container)
        assert len(targets) == 1, f"Expected 1 target after second attach, got {len(targets)}"
        assert targets[0].get("state") == "alive"

        self._kill_target(container, target2_pid)

    def _start_target(self, container, suffix: str = "") -> str:
        """Start a target process in the container and return its PID.

        Args:
            container: Docker container instance
            suffix: Suffix for pid/ready files to avoid collision

        Returns:
            PID as string
        """
        # Use suffix to avoid file collision
        pid_file = f"/tmp/peeka_e2e_target{suffix}.pid"
        ready_file = f"/tmp/peeka_e2e_target{suffix}.ready"
        log_file = f"/tmp/target{suffix}.log"

        shell_cmd = f"""
export PEEKA_TEST_PID_FILE={pid_file}
export PEEKA_TEST_READY_FILE={ready_file}
python /app/tests/e2e/target_scripts/simple_loop.py >{log_file} 2>&1 &
echo $! > {pid_file}
PID=$!
for i in $(seq 1 100); do
    if [ -f {ready_file} ]; then
        echo "READY"
        break
    fi
    sleep 0.1
done
if [ ! -f {ready_file} ]; then
    kill $PID 2>/dev/null || true
    echo "TIMEOUT: Target failed to start" >&2
    exit 1
fi
cat {pid_file}
""".strip()

        exit_code, output = exec_in_container(container, shell_cmd, timeout=15)
        assert exit_code == 0, f"Target startup failed: {output}"

        lines = output.strip().split("\n")
        pid = lines[-1].strip()
        assert pid.isdigit(), f"Invalid PID: {pid}"

        return pid

    def _attach_target(self, container, pid: str) -> None:
        """Attach peeka to a target process.

        Args:
            container: Docker container instance
            pid: Target PID as string
        """
        exit_code, output = exec_in_container(
            container,
            f"python -m peeka.cli.main attach {pid}",
            timeout=30,
        )
        assert exit_code == 0, f"Attach to PID {pid} failed:\n{output}"

        # Verify attach success by checking JSONL output
        lines = [line for line in output.strip().split("\n") if line.strip()]
        json_lines = [line for line in lines if line.startswith("{")]

        success_found = False
        for line in json_lines:
            try:
                data = json.loads(line)
                if data.get("type") == "success" and data.get("command") == "attach":
                    success_found = True
                    break
            except json.JSONDecodeError:
                continue

        assert success_found, f"Attach success not found in output:\n{output}"

    def _list_targets(self, container) -> List[Dict[str, Any]]:
        """List all targets using discovery API.

        Args:
            container: Docker container instance

        Returns:
            List of target dictionaries
        """
        python_code = """
import json
from peeka.core.targets import discover_targets

targets = discover_targets()
for target in targets:
    print(json.dumps(target.to_dict()))
"""
        exit_code, output = exec_in_container(
            container,
            f"cd /app && python3 -c {shlex.quote(python_code)}",
            timeout=10,
        )
        assert exit_code == 0, f"discover_targets failed:\n{output}"

        targets = []
        lines = [line for line in output.strip().split("\n") if line.strip()]

        for line in lines:
            if not line.startswith("{"):
                continue
            try:
                target = json.loads(line)
                targets.append(target)
            except json.JSONDecodeError:
                continue

        return targets

    def _kill_target(self, container, pid: str) -> None:
        """SIGKILL a target process.

        Args:
            container: Docker container instance
            pid: Target PID as string
        """
        exit_code, output = exec_in_container(
            container,
            f"kill -KILL {pid}",
            timeout=5,
        )
        # SIGKILL may return non-zero if process already dead; that's fine
        # as long as the command executed

    def _cleanup_stale_targets(self, container) -> Dict[str, Any]:
        """Run cleanup_stale_targets API.

        Args:
            container: Docker container instance

        Returns:
            Cleanup result dictionary with keys: removed, skipped, errors
        """
        python_code = """
import json
from peeka.core.targets import cleanup_stale_targets

result = cleanup_stale_targets(dry_run=False)
print(json.dumps(result))
"""
        exit_code, output = exec_in_container(
            container,
            f"cd /app && python3 -c {shlex.quote(python_code)}",
            timeout=10,
        )
        assert exit_code == 0, f"cleanup_stale_targets failed:\n{output}"

        # Parse single JSON object response
        lines = [line for line in output.strip().split("\n") if line.strip()]
        json_lines = [line for line in lines if line.startswith("{")]

        assert len(json_lines) > 0, f"No JSON output from cleanup:\n{output}"

        result = json.loads(json_lines[0])
        return result

    def test_two_alive_distinct_pids(self, gdb_container):
        """Verify 2 alive targets from distinct PIDs (separate Peeka sessions).

        Strategy:
        1. Start 2 target processes
        2. Attach to both concurrently (background processes)
        3. Discover: should see 2 alive targets
        4. Inspect both targets
        5. Cleanup
        """
        container = gdb_container

        # Step 1: Start two distinct target processes
        target1_pid = self._start_target(container, suffix="1")
        target2_pid = self._start_target(container, suffix="2")

        # Step 2: Attach to both concurrently
        self._attach_target_background(container, target1_pid, log_suffix="1")
        self._attach_target_background(container, target2_pid, log_suffix="2")

        # Give attach operations time to complete
        exec_in_container(container, "sleep 2", timeout=5)

        # Step 3: Discover - should see 2 alive targets
        targets = self._list_targets(container)
        assert len(targets) == 2, f"Expected 2 targets, got {len(targets)}"

        alive_targets = [t for t in targets if t.get("state") == "alive"]
        assert len(alive_targets) == 2, (
            f"Expected 2 alive targets, got {len(alive_targets)}"
        )

        # Step 4: Verify both target IDs correspond to our PIDs
        target1_id = self._find_target_id_by_pid(targets, target1_pid)
        target2_id = self._find_target_id_by_pid(targets, target2_pid)
        assert target1_id is not None, f"Could not find target_id for PID {target1_pid}"
        assert target2_id is not None, f"Could not find target_id for PID {target2_pid}"

        # Step 5: Inspect both targets using get_target API
        target1_detail = self._get_target(container, target1_id)
        assert target1_detail is not None, f"Could not inspect target {target1_id}"
        assert target1_detail.get("state") == "alive"
        assert target1_detail.get("pid") == int(target1_pid)

        target2_detail = self._get_target(container, target2_id)
        assert target2_detail is not None, f"Could not inspect target {target2_id}"
        assert target2_detail.get("state") == "alive"
        assert target2_detail.get("pid") == int(target2_pid)

        # Step 6: Cleanup
        self._kill_target(container, target1_pid)
        self._kill_target(container, target2_pid)
        self._cleanup_stale_targets(container)

    def _attach_target_background(
        self, container, pid: str, log_suffix: str = ""
    ) -> None:
        """Attach peeka to a target process in background.

        Args:
            container: Docker container instance
            pid: Target PID as string
            log_suffix: Suffix for attach log file
        """
        log_file = f"/tmp/attach{log_suffix}.log"
        shell_cmd = f"nohup python -m peeka.cli.main attach {pid} >{log_file} 2>&1 &"

        exit_code, output = exec_in_container(container, shell_cmd, timeout=5)
        assert exit_code == 0, f"Failed to start background attach to PID {pid}: {output}"

    def _get_target(self, container, target_id: str) -> Optional[Dict[str, Any]]:
        """Get target details using get_target API.

        Args:
            container: Docker container instance
            target_id: Target ID to inspect

        Returns:
            Target dictionary or None if not found
        """
        python_code = f"""
import json
from peeka.core.targets import get_target

target = get_target({repr(target_id)})
if target:
    print(json.dumps(target.to_dict()))
"""
        exit_code, output = exec_in_container(
            container,
            f"cd /app && python3 -c {shlex.quote(python_code)}",
            timeout=10,
        )

        if exit_code != 0 or not output.strip():
            return None

        lines = [line for line in output.strip().split("\n") if line.strip()]
        for line in lines:
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue

        return None

    def _find_target_id_by_pid(
        self, targets: List[Dict[str, Any]], pid: str
    ) -> Optional[str]:
        """Find target_id for a given PID from target list.

        Args:
            targets: List of target dictionaries
            pid: Target PID as string

        Returns:
            target_id if found, None otherwise
        """
        pid_int = int(pid)
        for target in targets:
            if target.get("pid") == pid_int:
                return target.get("target_id")
        return None
