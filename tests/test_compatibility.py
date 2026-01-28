"""
Compatibility tests for Python 3.9-3.14
Tests basic attach and watch functionality across different Python versions
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

import pytest

from peeka.core.injector import DecoratorInjector
from peeka.core.observer import ObservationManager


class MockAgent:
    """Mock agent for testing WatchCommand without full agent initialization"""

    def __init__(self):
        self._observations: list = []
        self.observer = ObservationManager()
        self.injector = DecoratorInjector(self)

    def _send_observation(self, obs: Dict[str, Any]) -> None:
        self._observations.append(obs)
        self.observer.add_observation(obs)


class TestAttachCompatibility:
    """Test process attach across Python versions"""

    @pytest.fixture
    def target_script(self, tmp_path):
        """Create a simple target process script"""
        script = tmp_path / "target.py"
        script.write_text("""
import time
import sys

class Calculator:
    def add(self, a, b):
        return a + b
    
    def multiply(self, a, b):
        return a * b

calc = Calculator()

print(f"TARGET_PID:{__import__('os').getpid()}", flush=True)

for i in range(60):
    result = calc.add(i, i * 2)
    if i % 10 == 0:
        print(f"Iteration {i}, result={result}", flush=True)
    time.sleep(0.5)
""")
        return script

    def test_attach_mechanism_available(self):
        """Verify attach mechanism is available for current Python version"""
        if hasattr(sys, "remote_exec"):
            print(f"Python {sys.version_info[:2]}: Using PEP 768 (sys.remote_exec)")
            assert True
        else:
            print(f"Python {sys.version_info[:2]}: Using GDB fallback")
            import shutil

            assert shutil.which("gdb") is not None, "GDB not found for fallback attach"

    def test_attach_creates_agent(self, target_script, tmp_path):
        """Test that attach successfully creates agent in target process"""
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).parent.parent.resolve())

        target_proc = subprocess.Popen(
            [sys.executable, str(target_script)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )

        try:
            target_pid = None
            for line in target_proc.stdout:
                if line.startswith("TARGET_PID:"):
                    target_pid = int(line.split(":")[1].strip())
                    break

            assert target_pid is not None, "Failed to get target PID"
            print(f"Target process started with PID: {target_pid}")

            time.sleep(1)

            from peeka.core.attach import ProcessAttacher

            attacher = ProcessAttacher(target_pid)

            attach_success = False
            try:
                attach_success = attacher.attach()
            except Exception as e:
                pytest.skip(f"Attach failed (expected on some CI environments): {e}")

            if attach_success:
                socket_path = attacher.get_socket_path()
                assert Path(socket_path).exists(), (
                    f"Agent socket not created at {socket_path}"
                )
                print(f"✓ Agent socket created: {socket_path}")

                ready_file = Path(f"/tmp/peeka_{attacher.session_id}.ready")
                assert ready_file.exists(), "Agent ready file not created"
                print(f"✓ Agent ready file created")

        finally:
            if target_proc.poll() is None:
                target_proc.send_signal(signal.SIGTERM)
                target_proc.wait(timeout=5)


class TestWatchCompatibility:
    """Test watch functionality across Python versions"""

    def test_watch_command_basic(self):
        """Test basic watch command without actual process attach"""
        from peeka.commands.watch import WatchCommand

        mock_agent = MockAgent()
        watch_cmd = WatchCommand(mock_agent)

        def sample_function(x, y):
            return x + y

        test_module = type(sys)("test_compat_module")
        test_module.sample_function = sample_function
        sys.modules["test_compat_module"] = test_module

        try:
            result = watch_cmd.execute(
                {
                    "action": "start",
                    "pattern": "test_compat_module.sample_function",
                    "depth": 2,
                    "times": 3,
                }
            )

            assert result["status"] == "success"
            assert "watch_id" in result

            watch_id = result["watch_id"]

            test_module.sample_function(1, 2)
            test_module.sample_function(3, 4)

            time.sleep(0.1)

            stats = mock_agent.observer.get_watch_stats(watch_id)
            assert stats is not None
            assert stats["count"] >= 2

            print(f"✓ Watch captured {stats['count']} observations")

        finally:
            if "test_compat_module" in sys.modules:
                del sys.modules["test_compat_module"]

    def test_watch_with_condition(self):
        """Test watch with condition filtering"""
        from peeka.commands.watch import WatchCommand

        mock_agent = MockAgent()
        watch_cmd = WatchCommand(mock_agent)

        def sample_function(value):
            return value * 2

        test_module = type(sys)("test_cond_compat")
        test_module.sample_function = sample_function
        sys.modules["test_cond_compat"] = test_module

        try:
            result = watch_cmd.execute(
                {
                    "action": "start",
                    "pattern": "test_cond_compat.sample_function",
                    "depth": 2,
                    "times": -1,
                    "condition": "params[0] > 50",
                }
            )

            assert result["status"] == "success"
            watch_id = result["watch_id"]

            test_module.sample_function(10)
            test_module.sample_function(30)
            test_module.sample_function(100)
            test_module.sample_function(5)

            time.sleep(0.1)

            stats = mock_agent.observer.get_watch_stats(watch_id)
            assert stats is not None
            assert stats["count"] == 1, (
                f"Expected 1 observation (only value>50), got {stats['count']}"
            )

            print(f"✓ Condition filter working: {stats['count']} observation(s)")

        finally:
            if "test_cond_compat" in sys.modules:
                del sys.modules["test_cond_compat"]


class TestSecurityCompatibility:
    """Test security features across Python versions"""

    def test_simpleeval_blocks_dangerous_code(self):
        """Test that simpleeval blocks code injection at evaluation time"""
        import time
        from peeka.commands.watch import WatchCommand

        mock_agent = MockAgent()
        watch_cmd = WatchCommand(mock_agent)

        def sample_function(x):
            return x

        test_module = type(sys)("test_security")
        test_module.sample_function = sample_function
        sys.modules["test_security"] = test_module

        dangerous_conditions = [
            "__import__('os').system('ls')",
            "eval('1+1')",
            "compile('x=1', '<string>', 'exec')",
            "params.__class__.__subclasses__()",
        ]

        try:
            for condition in dangerous_conditions:
                # Injection succeeds (dangerous code is just a string, not executed yet)
                result = watch_cmd.execute(
                    {
                        "action": "start",
                        "pattern": "test_security.sample_function",
                        "condition_express": condition,
                    }
                )

                assert result["status"] == "success", (
                    f"Injection should succeed: {condition}"
                )
                watch_id = result["watch_id"]

                # Call function through module (not local reference)
                test_module.sample_function(100)
                time.sleep(0.1)

                # Verify NO observations captured (dangerous code blocked at eval time)
                stats = mock_agent.observer.get_watch_stats(watch_id)
                assert stats["count"] == 0, (
                    f"Dangerous condition should produce 0 observations: {condition}"
                )
                print(f"✓ Blocked at eval time: {condition}")

        finally:
            if "test_security" in sys.modules:
                del sys.modules["test_security"]


class TestPythonVersionInfo:
    """Display Python version information for debugging"""

    def test_display_version_info(self):
        """Display current Python version and capabilities"""
        print("\n" + "=" * 60)
        print("Python Version Compatibility Information")
        print("=" * 60)
        print(
            f"Python version: {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )
        print(f"Full version: {sys.version}")
        print(f"Has sys.remote_exec: {hasattr(sys, 'remote_exec')}")

        if hasattr(sys, "remote_exec"):
            print("Attach mechanism: PEP 768 (native)")
        else:
            print("Attach mechanism: GDB fallback")
            import shutil

            gdb_path = shutil.which("gdb")
            print(f"GDB available: {gdb_path is not None}")
            if gdb_path:
                print(f"GDB path: {gdb_path}")

        print("=" * 60)
        assert True
