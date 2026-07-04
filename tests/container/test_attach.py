"""
Container E2E tests for attach/detach lifecycle.

Tests core attach/detach operations in Docker containers against:
- Python 3.8 (GDB-based attachment)
- Python 3.12 (GDB-based attachment)
- Python 3.14 (PEP 768 native attachment)
"""

import base64
import json
import textwrap

import pytest

from tests.container.conftest import exec_in_container

pytestmark = [pytest.mark.container]


class TestContainerAttach:
    """Test attach/detach operations in containerized environments."""

    def test_attach_success(self, container_target):
        """Verify successful attachment to target process."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Execute attach command
        exit_code, output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )

        # Parse JSONL output
        lines = [line for line in output.strip().split("\n") if line.strip()]
        json_lines = [line for line in lines if line.startswith("{")]

        success_line = None
        for line in json_lines:
            try:
                data = json.loads(line)
                if data.get("type") == "success" and data.get("command") == "attach":
                    success_line = data
                    break
            except json.JSONDecodeError:
                continue

        assert success_line is not None, f"No success line found in output:\n{output}"
        assert "data" in success_line, (
            f"Missing 'data' field in success line: {success_line}"
        )
        assert "socket" in success_line["data"], (
            f"Missing 'socket' in data: {success_line['data']}"
        )

    def test_attach_creates_socket_file(self, container_target):
        """Verify that attach creates a Unix socket file in /tmp."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach to target
        exit_code, output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )

        # Verify socket file exists
        exit_code, ls_output = exec_in_container(
            container, "ls /tmp/peeka_*.sock", timeout=5
        )

        assert exit_code == 0, f"Socket file not found in /tmp. ls output:\n{ls_output}"
        assert ".sock" in ls_output, f"No .sock file in output:\n{ls_output}"

    def test_detach_after_attach(self, container_target):
        """Verify successful detachment after attaching."""
        container = container_target["container"]
        pid = container_target["pid"]

        # First attach
        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Attach failed:\n{attach_output}"

        # Then detach
        exit_code, detach_output = exec_in_container(
            container, "python -m peeka.cli.main detach", timeout=10
        )

        # Verify detach success (either explicit success or detach message)
        output_lower = detach_output.lower()
        assert (
            exit_code == 0 or "success" in output_lower or "detach" in output_lower
        ), f"Detach operation failed:\n{detach_output}"

    def test_attach_invalid_pid(self, container_target):
        """Verify graceful failure when attaching to invalid PID."""
        container = container_target["container"]

        # Attempt to attach to non-existent PID
        exit_code, output = exec_in_container(
            container, "python -m peeka.cli.main attach 99999", timeout=30
        )

        # Should fail gracefully
        assert exit_code != 0 or "error" in output.lower(), (
            f"Expected failure for invalid PID, got:\n{output}"
        )

    def test_attach_twice_same_pid(self, container_target):
        """Verify behavior when attaching to same PID twice."""
        container = container_target["container"]
        pid = container_target["pid"]

        # First attach
        exit_code1, output1 = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code1 == 0, f"First attach failed:\n{output1}"

        # Second attach to same PID
        exit_code2, output2 = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )

        # Either succeeds with reuse message or fails gracefully (no crash)
        # Both are acceptable behaviors - key is no segfault/crash
        output2_lower = output2.lower()
        acceptable = (
            exit_code2 == 0
            or "already" in output2_lower
            or "attached" in output2_lower
            or "error" in output2_lower
        )
        assert acceptable, f"Unexpected behavior on double attach:\n{output2}"

    def test_attach_process_cleanup(self, container_target):
        """Verify target process remains healthy after attach/detach cycle."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach
        exit_code, _ = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, "Attach failed"

        # Detach
        exit_code, _ = exec_in_container(
            container, "python -m peeka.cli.main detach", timeout=10
        )

        # Verify target process still running
        exit_code, output = exec_in_container(
            container, f"test -d /proc/{pid} && echo alive", timeout=5
        )

        assert exit_code == 0, f"Target process {pid} died after detach cycle"
        assert "alive" in output, f"Process {pid} not running after detach cycle"

    def test_attach_socket_cleanup_on_detach(self, container_target):
        """Verify socket file is cleaned up after detach."""
        container = container_target["container"]
        pid = container_target["pid"]

        # Attach
        exit_code, output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, "Attach failed"

        # Parse socket path from output
        lines = [line for line in output.strip().split("\n") if line.strip()]
        json_lines = [line for line in lines if line.startswith("{")]

        socket_path = None
        for line in json_lines:
            try:
                data = json.loads(line)
                if data.get("type") == "success" and "socket" in data.get("data", {}):
                    socket_path = data["data"]["socket"]
                    break
            except json.JSONDecodeError:
                continue

        assert socket_path is not None, (
            f"Could not find socket path in output:\n{output}"
        )

        # Detach
        exit_code, _ = exec_in_container(
            container, "python -m peeka.cli.main detach", timeout=10
        )

        # Verify socket file removed
        exit_code, ls_output = exec_in_container(
            container, f"ls {socket_path}", timeout=5
        )

        # ls should fail (socket removed) OR return "No such file"
        assert exit_code != 0 or "No such file" in ls_output, (
            f"Socket file {socket_path} still exists after detach"
        )


@pytest.mark.container
class TestModuleCacheRefresh:
    """Regression: re-attach must load fresh peeka modules, not stale cached ones."""

    def test_reattach_evicts_stale_peeka_modules(self, py314_target):
        """After detach and re-attach, peeka.* modules must be free of stale attributes."""
        container = py314_target["container"]
        pid = py314_target["pid"]

        exit_code, attach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"First attach failed:\n{attach_output}"

        inject_py = textwrap.dedent(
            """
            import sys, os
            for _n, _m in list(sys.modules.items()):
                if _n == "peeka" or _n.startswith("peeka."):
                    _m._STALE_SENTINEL = True
            with open("/tmp/peeka_sentinel_injected.flag", "w") as _f:
                _f.write("ok")
            """
        ).strip()
        inject_b64 = base64.b64encode(inject_py.encode()).decode()
        exec_in_container(
            container,
            f"echo {inject_b64} | base64 -d > /tmp/inject_sentinel.py",
            timeout=5,
        )
        run_inject_cmd = (
            f"python3 -c \"import sys, time, os; "
            f"sys.remote_exec({pid}, '/tmp/inject_sentinel.py'); "
            "time.sleep(2); "
            "print('INJECTED' if os.path.exists('/tmp/peeka_sentinel_injected.flag') else 'TIMEOUT')\""
        )
        exit_code, inject_output = exec_in_container(
            container, run_inject_cmd, timeout=15
        )
        if exit_code != 0 or "INJECTED" not in inject_output:
            pytest.skip(
                f"Could not inject sentinel via PEP 768 sys.remote_exec — "
                f"skipping (output: {inject_output!r})"
            )

        exec_in_container(
            container, "python -m peeka.cli.main detach", timeout=15
        )
        exec_in_container(
            container,
            "rm -f /tmp/peeka_*.sock /tmp/peeka_*.ready /tmp/peeka_agent_*.py 2>/dev/null; true",
            timeout=5,
        )

        exit_code, reattach_output = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Re-attach failed:\n{reattach_output}"

        check_py = textwrap.dedent(
            """
            import sys, os
            found_stale = any(
                hasattr(_m, "_STALE_SENTINEL")
                for _n, _m in sys.modules.items()
                if _n == "peeka" or _n.startswith("peeka.")
            )
            with open("/tmp/peeka_sentinel_check.result", "w") as _f:
                _f.write("STALE" if found_stale else "FRESH")
            """
        ).strip()
        check_b64 = base64.b64encode(check_py.encode()).decode()
        exec_in_container(
            container,
            f"echo {check_b64} | base64 -d > /tmp/check_sentinel.py",
            timeout=5,
        )
        run_check_cmd = (
            f"python3 -c \"import sys, time, os; "
            f"sys.remote_exec({pid}, '/tmp/check_sentinel.py'); "
            "time.sleep(2); "
            "result = open('/tmp/peeka_sentinel_check.result').read().strip() "
            "if os.path.exists('/tmp/peeka_sentinel_check.result') else 'TIMEOUT'; "
            "print(result)\""
        )
        exit_code, check_output = exec_in_container(
            container, run_check_cmd, timeout=15
        )
        result = check_output.strip()

        assert result == "FRESH", (
            f"After re-attach, peeka.* modules still carry the stale sentinel. "
            f"Expected FRESH, got: {result!r}. "
            f"This means the module cache cleanup in _create_agent_script() is NOT working."
        )


@pytest.mark.container
class TestModuleCacheSignalRestoration:
    """P2 validation: signal/excepthook handlers must restore after each detach.

    Even after a re-attach cycle that triggers sys.modules eviction and class reload,
    SIGTERM/SIGINT/sys.excepthook must return to their pre-attach state after detach.
    """

    def test_signal_handlers_restored_after_reattach(self, py314_target):
        import base64 as _b64
        import time

        container = py314_target["container"]
        pid = py314_target["pid"]

        def capture_handlers(label: str) -> dict:
            script = textwrap.dedent(f"""
                import sys, signal, os, json
                def _handler_name(h):
                    if h is None:
                        return "None"
                    if h == signal.SIG_DFL:
                        return "SIG_DFL"
                    if h == signal.SIG_IGN:
                        return "SIG_IGN"
                    return getattr(h, '__qualname__', getattr(h, '__name__', repr(h)))
                info = {{
                    "SIGTERM": _handler_name(signal.getsignal(signal.SIGTERM)),
                    "SIGINT":  _handler_name(signal.getsignal(signal.SIGINT)),
                    "excepthook": getattr(sys.excepthook, '__qualname__',
                                         getattr(sys.excepthook, '__name__', repr(sys.excepthook))),
                }}
                with open('/tmp/peeka_handler_check_{label}.json', 'w') as _f:
                    _f.write(json.dumps(info))
            """).strip()
            b64 = _b64.b64encode(script.encode()).decode()
            exec_in_container(
                container,
                f"echo {b64} | base64 -d > /tmp/check_handlers_{label}.py",
                timeout=5,
            )
            rc, _ = exec_in_container(
                container,
                (
                    f"python3 -c \"import sys, time; "
                    f"sys.remote_exec({pid}, '/tmp/check_handlers_{label}.py'); "
                    f"time.sleep(1.5)\""
                ),
                timeout=10,
            )
            if rc != 0:
                pytest.skip("sys.remote_exec unavailable — cannot inspect signal handlers")
            rc2, raw = exec_in_container(
                container,
                f"cat /tmp/peeka_handler_check_{label}.json",
                timeout=5,
            )
            assert rc2 == 0, f"Could not read handler check {label}"
            import json as _json

            return _json.loads(raw.strip())

        # ── Baseline: capture handlers before ANY attach ──────────────────────
        baseline = capture_handlers("baseline")

        # ── First attach ───────────────────────────────────────────────────────
        rc, out = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert rc == 0, f"First attach failed:\n{out}"
        time.sleep(1)

        # Handlers during attach — should be peeka-installed
        during_attach1 = capture_handlers("during_attach1")

        # ── First detach ───────────────────────────────────────────────────────
        exec_in_container(container, "python -m peeka.cli.main detach", timeout=15)
        exec_in_container(
            container,
            "rm -f /tmp/peeka_*.sock /tmp/peeka_*.ready /tmp/peeka_agent_*.py 2>/dev/null; true",
            timeout=5,
        )
        time.sleep(1)

        after_detach1 = capture_handlers("after_detach1")

        # ── Re-attach (triggers sys.modules eviction + module reload) ──────────
        rc, out2 = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert rc == 0, f"Re-attach failed:\n{out2}"
        time.sleep(1)

        # ── Second detach ──────────────────────────────────────────────────────
        exec_in_container(container, "python -m peeka.cli.main detach", timeout=15)
        exec_in_container(
            container,
            "rm -f /tmp/peeka_*.sock /tmp/peeka_*.ready /tmp/peeka_agent_*.py 2>/dev/null; true",
            timeout=5,
        )
        time.sleep(1)

        after_detach2 = capture_handlers("after_detach2")

        # ── Assertions ─────────────────────────────────────────────────────────
        # During attach, peeka should have installed its handlers
        assert (
            during_attach1["SIGTERM"] != baseline["SIGTERM"]
            or during_attach1["excepthook"] != baseline["excepthook"]
        ), "Peeka did not install signal/excepthook handlers after attach — test may be invalid"

        # After first detach: handlers must be restored to baseline
        assert after_detach1["SIGTERM"] == baseline["SIGTERM"], (
            f"P2 BUG after first detach: SIGTERM handler not restored.\n"
            f"  baseline={baseline['SIGTERM']!r}\n"
            f"  after_detach1={after_detach1['SIGTERM']!r}"
        )
        assert after_detach1["excepthook"] == baseline["excepthook"], (
            f"P2 BUG after first detach: excepthook not restored.\n"
            f"  baseline={baseline['excepthook']!r}\n"
            f"  after_detach1={after_detach1['excepthook']!r}"
        )

        # After second detach (post re-attach): handlers must still be baseline
        assert after_detach2["SIGTERM"] == baseline["SIGTERM"], (
            f"P2 BUG after re-attach+detach: SIGTERM handler not restored.\n"
            f"  baseline={baseline['SIGTERM']!r}\n"
            f"  after_detach2={after_detach2['SIGTERM']!r}"
        )
        assert after_detach2["excepthook"] == baseline["excepthook"], (
            f"P2 BUG after re-attach+detach: excepthook not restored.\n"
            f"  baseline={baseline['excepthook']!r}\n"
            f"  after_detach2={after_detach2['excepthook']!r}"
        )


@pytest.mark.container
class TestModuleCacheResourceOwnerCleanup:
    """P1 validation: resource-owning command handlers must clean up after module reload.

    Scenario: attach → start monitor (ResourceOwningCommand) → detach →
              re-attach to same PID (triggers sys.modules eviction + class reload) →
              detach → assert no leaked peeka threads or sockets.
    """

    def test_resource_owners_cleaned_after_reattach(self, py314_target):
        import time

        container = py314_target["container"]
        pid = py314_target["pid"]

        # ── Step 1: First attach ────────────────────────────────────────────
        exit_code, out = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"First attach failed:\n{out}"

        # ── Step 2: Start monitor (ResourceOwningCommand) for 2 seconds ────
        # Run in background via timeout, let it register and then get killed
        exec_in_container(
            container,
            "timeout 3 python -m peeka.cli.main monitor '__main__.Calculator.add' || true",
            timeout=10,
        )

        # ── Step 3: Detach cleanly ──────────────────────────────────────────
        exec_in_container(container, "python -m peeka.cli.main detach", timeout=15)
        exec_in_container(
            container,
            "rm -f /tmp/peeka_*.sock /tmp/peeka_*.ready /tmp/peeka_agent_*.py 2>/dev/null; true",
            timeout=5,
        )
        time.sleep(1)

        # ── Step 4: Re-attach to SAME PID (triggers module reload) ──────────
        exit_code, out2 = exec_in_container(
            container, f"python -m peeka.cli.main attach {pid}", timeout=30
        )
        assert exit_code == 0, f"Re-attach failed:\n{out2}"

        # ── Step 5: Detach again ─────────────────────────────────────────────
        exec_in_container(container, "python -m peeka.cli.main detach", timeout=15)
        exec_in_container(
            container,
            "rm -f /tmp/peeka_*.sock /tmp/peeka_*.ready /tmp/peeka_agent_*.py 2>/dev/null; true",
            timeout=5,
        )
        time.sleep(1)

        # ── Step 6: Inspect target process for leaks via sys.remote_exec ────
        inspect_py = textwrap.dedent("""
            import sys, threading, os, json
            peeka_threads = [t.name for t in threading.enumerate()
                             if 'peeka' in t.name.lower() or 'Peeka' in t.name]
            peeka_socks   = [f for f in os.listdir('/tmp')
                             if f.startswith('peeka_') and f.endswith('.sock')]
            result = json.dumps({"threads": peeka_threads, "sockets": peeka_socks})
            with open('/tmp/peeka_leak_check.json', 'w') as _f:
                _f.write(result)
        """).strip()
        b64 = base64.b64encode(inspect_py.encode()).decode()
        exec_in_container(
            container,
            f"echo {b64} | base64 -d > /tmp/inspect_leaks.py",
            timeout=5,
        )

        run_cmd = (
            f"python3 -c \"import sys, time, os; "
            f"sys.remote_exec({pid}, '/tmp/inspect_leaks.py'); "
            "time.sleep(2)\""
        )
        rc, _ = exec_in_container(container, run_cmd, timeout=15)
        if rc != 0:
            pytest.skip("Could not inspect target via sys.remote_exec")

        rc, result_raw = exec_in_container(
            container, "cat /tmp/peeka_leak_check.json", timeout=5
        )
        assert rc == 0, "Could not read leak check result"

        import json as _json

        result = _json.loads(result_raw.strip())
        leaked_threads = result.get("threads", [])
        leaked_socks = result.get("sockets", [])

        assert not leaked_threads, (
            f"P1 BUG CONFIRMED: {len(leaked_threads)} peeka thread(s) leaked after re-attach+detach: "
            f"{leaked_threads}\n"
            f"This means ResourceOwningCommand cleanup failed due to class identity mismatch "
            f"after module reload."
        )
        assert not leaked_socks, (
            f"P1 BUG: {len(leaked_socks)} peeka socket(s) leaked after detach: {leaked_socks}"
        )
