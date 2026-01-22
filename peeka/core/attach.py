"""
Process Attacher - Based on PEP 768
Attach to running Python processes and inject agent code
"""

import os
import sys
import tempfile
import time
import uuid
from importlib import resources
from pathlib import Path


class ProcessAttacher:
    """
    Process attacher using PEP 768 interface

    For Python 3.14+, uses sys.remote_exec()
    For older versions, uses fallback mechanism
    """

    def __init__(self, pid: int):
        self.pid = pid
        self.agent_script = None
        self.session_id = str(uuid.uuid4())

    def attach(self) -> bool:
        """
        Attach to target process

        Returns:
            bool: True if successful, False otherwise
        """
        try:
            print(f"[Peeka] Attaching to process {self.pid}...")

            # Check if PEP 768 is supported
            if hasattr(sys, "remote_exec"):
                return self._attach_pep768()
            else:
                print("[Peeka] Warning: PEP 768 not available (Python 3.14+ required)")
                print("[Peeka] Using fallback mechanism for demonstration")
                return self._attach_fallback()

        except Exception as e:
            print(f"[Peeka] Attach failed: {e}")
            import traceback

            traceback.print_exc()
            return False

    def _attach_pep768(self) -> bool:
        """Attach using PEP 768 sys.remote_exec()"""
        # from peeka.core.agent import AGENT_CODE
        agent_code = (
            resources.files("peeka.core")
            .joinpath("agent.py")
            .read_text(encoding="utf-8")
        )

        # Create agent script
        self.agent_script = self._create_agent_script(agent_code)
        if not os.path.exists(self.agent_script):
            raise FileNotFoundError(f"Agent script not found: {self.agent_script}")
        else:
            print(f"[Peeka] Agent script created at {self.agent_script}")

        # Inject to target process
        sys.remote_exec(self.pid, self.agent_script)

        # Wait for agent ready
        if self._wait_for_agent_ready():
            print(f"[Peeka] Successfully attached to process {self.pid}")
            return True

        return False

    def _attach_fallback(self) -> bool:
        """Fallback mechanism for older Python versions"""
        # For demonstration, create a local agent simulation
        print(f"[Peeka] Creating simulated agent for PID {self.pid}")
        print(f"[Peeka] Session ID: {self.session_id}")

        # Create ready marker
        ready_file = Path(f"/tmp/peeka_{self.session_id}.ready")
        ready_file.touch()

        # Also create a dummy socket path placeholder (no server)
        sock_path = Path(self.get_socket_path())
        try:
            if sock_path.exists():
                sock_path.unlink()
            sock_path.touch()
        except Exception:
            # Non-fatal; just a placeholder so callers know where to look
            pass

        print(
            f"[Peeka] Agent simulation ready (no live socket) at {self.get_socket_path()}"
        )
        return True

    def _create_agent_script(self, agent_code: str) -> str:
        agent_path = Path(tempfile.gettempdir()) / f"peeka_agent_{self.session_id}.py"

        agent_code_injected = agent_code.replace("{{SESSION_ID}}", self.session_id)

        peeka_root = str(Path(__file__).parent.parent.parent.resolve())
        path_bootstrap = f"import sys; sys.path.insert(0, {peeka_root!r}) if {peeka_root!r} not in sys.path else None\n"

        with open(agent_path, "w") as f:
            print(f"[Peeka] Creating agent script at {agent_path}")
            f.write(path_bootstrap + agent_code_injected)

        return str(agent_path)

    def _wait_for_agent_ready(self, timeout: int = 5) -> bool:
        """Wait for agent initialization"""
        ready_file = Path(f"/tmp/peeka_{self.session_id}.ready")

        start_time = time.time()
        while time.time() - start_time < timeout:
            if ready_file.exists():
                return True
            time.sleep(0.1)

        raise TimeoutError("Agent initialization timeout")

    def get_socket_path(self) -> str:
        """Get Unix domain socket path for communication"""
        return f"/tmp/peeka_{self.session_id}.sock"

    def cleanup(self):
        return
        """Cleanup temporary files"""
        if self.agent_script and os.path.exists(self.agent_script):
            os.remove(self.agent_script)

        ready_file = Path(f"/tmp/peeka_{self.session_id}.ready")
        if ready_file.exists():
            ready_file.unlink()

        sock_path = Path(self.get_socket_path())
        if sock_path.exists():
            sock_path.unlink()
