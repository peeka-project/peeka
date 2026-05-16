"""
Patch Status Command - Runtime environment introspection

This module provides diagnostic capabilities for detecting monkey-patching,
verifying stdlib origins, inspecting asyncio loop state, thread model, and
Runtime Primitive Layer (RPL) integrity.

REPORT-ONLY: This command observes runtime state without modification.
"""

import os
import threading
from typing import Any, Dict, Optional, TYPE_CHECKING

from peeka.commands.base import BaseCommand
from peeka.commands import patch_status_schema
from peeka.core.runtime import primitives as _rpl

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class PatchStatusCommand(BaseCommand):
    """
    Patch status command - introspect runtime environment for monkey-patching.

    Usage:
        patch-status    # Full runtime introspection report

    Returns a comprehensive report containing:
    - monkey_patch: gevent/eventlet detection and patch status
    - stdlib_origin: Current vs RPL-captured native primitive IDs
    - asyncio_loop: Running loop state and policy
    - thread_model: Main thread, total threads, daemon counts
    - rpl_integrity: RPL integrity check results
    """

    def __init__(self, agent: Optional["PeekaAgent"] = None):
        super().__init__()
        self.agent = agent

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute patch-status introspection.

        Args:
            params: Command parameters (currently unused)

        Returns:
            Dict containing status and introspection data
        """
        try:
            # Build 8-key payload matching T5 schema
            payload = {
                "schema_version": "1",
                "pid": os.getpid(),
                "timestamp": _rpl.time_now(),
                "monkey_patch": self._detect_monkey_patch(),
                "stdlib_origin": self._check_stdlib_origin(),
                "asyncio_loop": self._inspect_asyncio_loop(),
                "thread_model": self._inspect_thread_model(),
                "rpl_integrity": _rpl.integrity_check(),
            }

            errors = patch_status_schema.validate(payload)
            if errors:
                return {
                    "status": "error",
                    "error": f"Schema validation failed: {errors}",
                }

            return {"status": "success", "data": payload}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _detect_monkey_patch(self) -> Dict[str, Any]:
        """
        Detect gevent and eventlet monkey-patching status.

        Returns:
            Dict with gevent and eventlet detection results.
            - For each library: "not_imported" (str) if not present, or
              dict with {"status": "active"|"imported_not_active", ...}
        """
        result: Dict[str, Any] = {}

        # gevent detection
        try:
            import gevent.monkey

            socket_patched = gevent.monkey.is_module_patched("socket")
            threading_patched = gevent.monkey.is_module_patched("threading")

            if socket_patched or threading_patched:
                status = "active"
            else:
                status = "imported_not_active"

            # Get list of patched modules (if saved dict is available)
            patched_modules = []
            if hasattr(gevent.monkey, "saved"):
                patched_modules = list(gevent.monkey.saved.keys())

            result["gevent"] = {
                "status": status,
                "patched_modules": patched_modules,
            }
        except ImportError:
            result["gevent"] = "not_imported"

        # eventlet detection
        try:
            import eventlet.patcher

            if hasattr(eventlet.patcher, "already_patched") and eventlet.patcher.already_patched:
                status = "active"
            else:
                status = "imported_not_active"

            result["eventlet"] = {"status": status}
        except ImportError:
            result["eventlet"] = "not_imported"

        return result

    def _check_stdlib_origin(self) -> Dict[str, Any]:
        """
        Compare current stdlib primitive IDs with RPL-captured native IDs.

        Returns:
            Dict mapping primitive names to comparison results.
            Each entry contains current ID, native ID, and match status.
        """
        import _socket
        import _thread
        import socket
        import time

        # Access RPL's captured native IDs via module-level constants
        from peeka.core.runtime.primitives import (
            _NATIVE_SOCKET,
            _NATIVE_START_NEW_THREAD,
            _NATIVE_ALLOCATE_LOCK,
            _NATIVE_RLOCK,
            _NATIVE_EVENT,
            _NATIVE_TIME,
        )

        result = {
            "socket.socket": {
                "current_id": id(socket.socket),
                "native_id": id(_NATIVE_SOCKET),
                "matches": socket.socket is _NATIVE_SOCKET,
            },
            "_socket.socket": {
                "current_id": id(_socket.socket),
                "native_id": id(_NATIVE_SOCKET),
                "matches": _socket.socket is _NATIVE_SOCKET,
            },
            "_thread.start_new_thread": {
                "current_id": id(_thread.start_new_thread),
                "native_id": id(_NATIVE_START_NEW_THREAD),
                "matches": _thread.start_new_thread is _NATIVE_START_NEW_THREAD,
            },
            "_thread.allocate_lock": {
                "current_id": id(_thread.allocate_lock),
                "native_id": id(_NATIVE_ALLOCATE_LOCK),
                "matches": _thread.allocate_lock is _NATIVE_ALLOCATE_LOCK,
            },
            "threading.RLock": {
                "current_id": id(threading.RLock),
                "native_id": id(_NATIVE_RLOCK),
                "matches": threading.RLock is _NATIVE_RLOCK,
            },
            "threading.Event": {
                "current_id": id(threading.Event),
                "native_id": id(_NATIVE_EVENT),
                "matches": threading.Event is _NATIVE_EVENT,
            },
            "time.time": {
                "current_id": id(time.time),
                "native_id": id(_NATIVE_TIME),
                "matches": time.time is _NATIVE_TIME,
            },
        }

        return result

    def _inspect_asyncio_loop(self) -> Dict[str, Any]:
        """
        Inspect asyncio event loop state.

        Returns:
            Dict with running status, policy, and loop class.
            Gracefully handles RuntimeError if no loop is running.
        """
        result: Dict[str, Any] = {
            "running": False,
            "policy": None,
            "loop_class": None,
        }

        try:
            import asyncio

            # Check if a loop is running (raises RuntimeError if not)
            try:
                loop = asyncio.get_running_loop()
                result["running"] = True
                result["loop_class"] = type(loop).__name__
            except RuntimeError:
                result["running"] = False

            try:
                policy = asyncio.get_event_loop_policy()
                result["policy"] = type(policy).__name__
            except Exception:
                result["policy"] = "unknown"

        except ImportError:
            result["policy"] = "asyncio_not_available"

        return result

    def _inspect_thread_model(self) -> Dict[str, Any]:
        """
        Inspect thread model - main thread ID, total threads, daemon counts.

        Returns:
            Dict with thread model metadata.
        """
        threads = threading.enumerate()
        total_threads = len(threads)

        daemon_threads = sum(1 for t in threads if t.daemon)

        main_thread = threading.main_thread()
        main_thread_id = main_thread.ident if main_thread else None

        # Classify thread model (simplified heuristic)
        if total_threads == 1 and not daemon_threads:
            classification = "single_threaded"
        elif daemon_threads > 0:
            classification = "multi_threaded_with_daemons"
        else:
            classification = "multi_threaded"

        return {
            "main_thread_id": main_thread_id,
            "total_threads": total_threads,
            "daemon_threads": daemon_threads,
            "classification": classification,
        }
