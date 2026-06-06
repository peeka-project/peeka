"""AgentTargetControlMixin implementation."""

import sys
import traceback
import time as _time
from typing import Any, Dict


class AgentTargetControlMixin:
    def _handle_target_hello(self) -> Dict[str, Any]:
        """Handle target.hello command - returns basic target information."""
        try:
            import peeka
            from peeka.core.targets import TARGET_SCHEMA_VERSION

            target_id = f"target_{self.session_id[:8]}"
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

            return {
                "status": "success",
                "schema_version": TARGET_SCHEMA_VERSION,
                "target_id": target_id,
                "pid": self.attached_pid or 0,
                "python_version": python_version,
                "peeka_version": peeka.__version__,
                "capabilities": {},
                "runtime": {},
                "state": "alive",
                "agent_mode": self.agent_mode,
                "injection_mode": self.injection_mode,
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

    def _handle_target_status(self) -> Dict[str, Any]:
        """Handle target.status command - returns hello payload + last_seen_at + recent_errors."""
        try:
            self._last_seen_at = _time.time()

            hello_payload = self._handle_target_hello()
            if hello_payload.get("status") != "success":
                return hello_payload

            with self._error_ring_lock:
                recent_errors = list(self._recent_errors)

            hello_payload["last_seen_at"] = self._last_seen_at
            hello_payload["recent_errors"] = recent_errors

            return hello_payload
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

    def _target_id_for_jobs(self) -> str:
        """Return the stable target identifier used by job records."""
        return f"target_{self.session_id[:8]}"
