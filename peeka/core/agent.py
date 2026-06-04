# pyright: reportImportCycles=false
"""
Agent Code - Runs inside target process
This code is injected into the target process and handles command execution
"""

import json
import socket
import sys
import threading
import time as _time
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast

from peeka.core.injector import DecoratorInjector
from peeka.core.jobs import JobCategory
from peeka.core.jobs import TERMINAL_STATUSES
from peeka.core.jobs import job_registry
from peeka.core import probes as probes_module
from peeka.core.observer import ObservationManager
from peeka.core.probes import ProbeContext
from peeka.core.probes import ProbeRegistry
from peeka.core.runtime import primitives as _rpl

# Lazy import to avoid circular dependency issues
_client_registry = None
_consumer_registry = None
_dx_case_registry = None


def _get_client_registry():
    """Lazily initialize and return the global client registry singleton."""
    global _client_registry
    if _client_registry is None:
        from peeka.core.client_sessions import ClientRegistry
        _client_registry = ClientRegistry()
    return _client_registry


def _get_consumer_registry():
    """Lazily initialize and return the global result consumer registry singleton."""
    global _consumer_registry
    if _consumer_registry is None:
        from peeka.core.result_consumers import ResultConsumerRegistry
        _consumer_registry = ResultConsumerRegistry()
    return _consumer_registry


def _get_dx_case_registry():
    """Lazily initialize and return the global DX case registry singleton."""
    global _dx_case_registry
    if _dx_case_registry is None:
        from peeka.core.dx_cases import DXCaseRegistry

        _dx_case_registry = DXCaseRegistry()
    return _dx_case_registry


def _get_requesting_client_session_id(command: Dict[str, Any]) -> Optional[str]:
    """Return the explicit client session id associated with a command."""
    client_session_id = command.get("client_session_id")
    if client_session_id in (None, ""):
        return None
    return str(client_session_id)


def _consumer_owner_matches(consumer: Any, requesting_client_session_id: Optional[str]) -> bool:
    """Return True if the requesting client is allowed to access the consumer."""
    owner = consumer.client_session_id
    if owner in (None, ""):
        return requesting_client_session_id is None
    return owner == requesting_client_session_id


def _dx_owner_matches(dx_case: Any, requesting_client_session_id: Optional[str]) -> bool:
    """Return True if the requesting client is allowed to access the DX case."""
    owner = dx_case.client_session_id
    if owner in (None, ""):
        return requesting_client_session_id is None
    return owner == requesting_client_session_id


def _client_success(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a standard success envelope for client namespace handlers."""
    return {"status": "success", "data": data}


def _client_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for client namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
    }


def _job_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for job namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "error": f"{error_code}: {message}",
    }


def _consumer_success(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a standard success envelope for consumer namespace handlers."""
    return {"status": "success", "data": data}


def _consumer_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for consumer namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "error": f"{error_code}: {message}",
    }


def _dx_success(data: Dict[str, Any]) -> Dict[str, Any]:
    """Return a standard success envelope for dx namespace handlers."""
    return {"status": "success", "data": data}


def _dx_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for dx namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "error": f"{error_code}: {message}",
    }


def _probe_error(error_code: str, message: str) -> Dict[str, Any]:
    """Return a standard error envelope for probe namespace handlers."""
    return {
        "status": "error",
        "error_code": error_code,
        "message": message,
        "error": f"{error_code}: {message}",
    }


def _write_session_log(
    session_id: str, level: str, message: str, details: Optional[str] = None
) -> None:
    """Persist agent diagnostics without touching the target process stdio."""
    try:
        log_path = Path(f"/tmp/peeka_{session_id}.log")
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{_time.time():.3f} {level} {message}\n")
            if details:
                log_file.write(details.rstrip() + "\n")
    except OSError:
        pass


class PeekaAgent:
    """Agent running inside target process"""

    _OBS_STREAM_COMMANDS = {
        "watch": {"", "start"},
        "trace": {"", "start"},
        "stack": {"", "start"},
        "monitor": {"", "start"},
        "top": {"", "start"},
    }

    _QUIET_COMMAND_ACTIONS = {
        ("complete", ""),
        ("logger", "get"),
        ("logger", "list"),
        ("memory", "gc"),
        ("memory", "overview"),
        ("memory", "top"),
        ("monitor", "status"),
        ("reset", "list"),
        ("sc", ""),
        ("sm", ""),
        ("stack", "status"),
        ("target", "hello"),
        ("target", "status"),
        ("thread", "detail"),
        ("thread", "list"),
        ("top", "snapshot"),
        ("trace", "status"),
        ("vmtool", "count"),
        ("vmtool", "get"),
        ("vmtool", "instances"),
        ("watch", "status"),
    }

    # Lazy command registry: (module_path, class_name) tuples.
    # Commands are imported and instantiated on first dispatch,
    # dramatically reducing startup time under GDB injection.
    _COMMAND_REGISTRY: Dict[str, Tuple[str, str]] = {
        "complete": ("peeka.commands.complete", "CompleteCommand"),
        "watch": ("peeka.commands.watch", "WatchCommand"),
        "trace": ("peeka.commands.trace", "TraceCommand"),
        "stack": ("peeka.commands.stack", "StackCommand"),
        "logger": ("peeka.commands.logger", "LoggerCommand"),
        "sc": ("peeka.commands.search", "SearchClassCommand"),
        "sm": ("peeka.commands.search", "SearchMethodCommand"),
        "monitor": ("peeka.commands.monitor", "MonitorCommand"),
        "memory": ("peeka.commands.memory", "MemoryCommand"),
        "reset": ("peeka.commands.reset", "ResetCommand"),
        "vmtool": ("peeka.commands.vmtool", "VMToolCommand"),
        "detach": ("peeka.commands.detach", "DetachCommand"),
        "thread": ("peeka.commands.thread", "ThreadCommand"),
        "top": ("peeka.commands.top", "TopCommand"),
        "patch-status": ("peeka.commands.patch_status", "PatchStatusCommand"),
    }

    def __init__(
        self,
        session_id: str,
        attached_pid: Optional[int] = None,
        notify_port: int = 0,
        suppress_startup_messages: bool = False,
        agent_mode: Optional[str] = None,
        injection_mode: Optional[str] = None,
    ):
        self.session_id = session_id
        self.attached_pid = attached_pid
        self.running = True
        self.suppress_startup_messages = suppress_startup_messages
        self.sock_path = f"/tmp/peeka_{session_id}.sock"
        self.server: Optional[socket.socket] = None
        self.command_handlers: Dict[str, Any] = {}
        self._client_connections: List[socket.socket] = []
        self._client_connection_kinds: Dict[socket.socket, str] = {}
        self._client_write_locks: Dict[socket.socket, Any] = {}
        self._connections_lock = _rpl.allocate_lock()
        self._mutation_lock: threading.RLock = threading.RLock()

        self._client_counter = 0
        self.observer = ObservationManager()
        self.injector = DecoratorInjector(self)
        self.probe_registry: ProbeRegistry = probes_module.probe_registry
        self._probe_contexts: Dict[str, ProbeContext] = {}
        self._probe_context_types: Dict[str, str] = {}
        self._probe_context_lock = _rpl.allocate_lock()

        self._notify_port = notify_port
        
        # Target identification fields (transitional: default from runtime)
        self.agent_mode = agent_mode or "injected"
        if injection_mode:
            self.injection_mode = injection_mode
        else:
            # Default from Python version: PEP 768 for 3.14+ else GDB fallback
            self.injection_mode = "pep768" if sys.version_info >= (3, 14) else "gdb_dlopen"
        
        # Error ring buffer for target.status (last 5 errors)
        self._recent_errors: List[Dict[str, Any]] = []
        self._error_ring_lock = _rpl.allocate_lock()
        self._last_seen_at = _time.time()

    # ------------------------------------------------------------------ #
    #  Lazy command handler loading                                      #
    # ------------------------------------------------------------------ #

    def _get_handler(self, cmd_type: str) -> Optional[Any]:
        """Return the handler for *cmd_type*, importing lazily if needed."""
        handler = self.command_handlers.get(cmd_type)
        if handler is not None:
            return handler

        spec = self._COMMAND_REGISTRY.get(cmd_type)
        if spec is None:
            return None

        module_path, class_name = spec
        try:
            import importlib

            mod = importlib.import_module(module_path)
            cls = getattr(mod, class_name)
            handler = cls(self)  # type: ignore[abstract]
            self.command_handlers[cmd_type] = handler
            return handler
        except Exception:
            self._emit_log(
                "ERROR",
                f"[peeka Agent] Failed to load handler for {cmd_type}",
                traceback.format_exc(),
            )
            return None

    def _emit_log(
        self, level: str, message: str, details: Optional[str] = None
    ) -> None:
        """Send diagnostics through side channels only."""
        self._send_log(level, message)
        _write_session_log(self.session_id, level, message, details)

    def _add_recent_error(self, error_entry: Dict[str, Any]) -> None:
        """Add an error entry to the ring buffer (max 5)."""
        with self._error_ring_lock:
            self._recent_errors.append(error_entry)
            if len(self._recent_errors) > 5:
                self._recent_errors.pop(0)
    
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

    def track_probe_context(
        self,
        stream_key: str,
        probe_context: ProbeContext,
        probe_type: str,
    ) -> None:
        """Track an active probe context by stream identifier."""
        with self._probe_context_lock:
            self._probe_contexts[stream_key] = probe_context
            self._probe_context_types[stream_key] = probe_type

    def get_probe_context(self, stream_key: str) -> Optional[ProbeContext]:
        """Return an active probe context for a stream key."""
        with self._probe_context_lock:
            return self._probe_contexts.get(stream_key)

    def stop_probe_context(
        self,
        stream_key: str,
        exc_info: Optional[Tuple[Any, Any, Any]] = None,
    ) -> None:
        """Stop and forget an active probe context."""
        with self._probe_context_lock:
            probe_context = self._probe_contexts.pop(stream_key, None)
            self._probe_context_types.pop(stream_key, None)

        if probe_context is None:
            return

        if exc_info is None:
            probe_context.__exit__(None, None, None)
            return

        probe_context.__exit__(exc_info[0], exc_info[1], exc_info[2])

    def untrack_probe_context(self, stream_key: str) -> None:
        """Forget an active probe context without closing it."""
        with self._probe_context_lock:
            self._probe_contexts.pop(stream_key, None)
            self._probe_context_types.pop(stream_key, None)

    def stop_probe_contexts_by_type(self, probe_types: List[str]) -> None:
        """Stop all tracked probe contexts whose type matches *probe_types*."""
        with self._probe_context_lock:
            stream_keys = [
                stream_key
                for stream_key, probe_type in self._probe_context_types.items()
                if probe_type in probe_types
            ]

        for stream_key in stream_keys:
            self.stop_probe_context(stream_key)

    def _handle_client_create(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.create command - create and register a client session."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict
            
            target_id = command.get("target_id", "")
            source = command.get("source", "")
            user_id = command.get("user_id")
            
            if not target_id:
                return _client_error(
                    "UNSUPPORTED_CAPABILITY",
                    "target_id is required and cannot be empty",
                )
            
            valid_sources = {"cli", "tui", "mcp", "api", "internal"}
            if source not in valid_sources:
                return _client_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"source must be one of {valid_sources}, got {source!r}",
                )
            
            registry = _get_client_registry()
            client = registry.create(target_id=target_id, source=source, user_id=user_id)
            
            return _client_success(client_to_dict(client))
        except Exception as e:
            result = _client_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_client_list(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.list command - list client sessions optionally filtered by target_id."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict
            
            target_id = command.get("target_id")
            
            registry = _get_client_registry()
            clients = registry.list(target_id=target_id)
            
            return _client_success({"clients": [client_to_dict(c) for c in clients]})
        except Exception as e:
            result = _client_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_client_status(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.status command - get client session details by ID."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict
            
            client_session_id = command.get("client_session_id", "")
            if not client_session_id:
                return _client_error("CLIENT_NOT_FOUND", "client_session_id is required")
            
            registry = _get_client_registry()
            client = registry.get(client_session_id)
            
            if client is None:
                return _client_error(
                    "CLIENT_NOT_FOUND",
                    f"Client session {client_session_id!r} not found",
                )
            
            return _client_success(client_to_dict(client))
        except Exception as e:
            result = _client_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_client_close(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle client.close command - close a client session by ID."""
        try:
            client_session_id = command.get("client_session_id", "")
            if not client_session_id:
                return _client_error("CLIENT_NOT_FOUND", "client_session_id is required")
            
            registry = _get_client_registry()
            removed = registry.close(client_session_id)
            
            if not removed:
                return _client_error(
                    "CLIENT_NOT_FOUND",
                    f"Client session {client_session_id!r} not found",
                )
            
            return _client_success({"closed": True, "client_session_id": client_session_id})
        except Exception as e:
            result = _client_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_job_list(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle job.list command - list jobs with optional filters."""
        try:
            from peeka.core.jobs import to_dict as job_to_dict
            
            target_id = command.get("target_id")
            client_session_id = command.get("client_session_id")
            status = command.get("status")
            
            jobs = job_registry.list(
                target=target_id if target_id else None,
                client=client_session_id if client_session_id else None,
                status=status if status else None,
            )
            
            return {
                "status": "success",
                "data": {"jobs": [job_to_dict(j) for j in jobs]},
            }
        except Exception as e:
            result = _job_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_job_status(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle job.status command - get job summary by ID."""
        try:
            job_id = command.get("job_id", "")
            if not job_id:
                return _job_error("JOB_NOT_FOUND", "job_id is required")
            
            job = job_registry.get(job_id)
            if job is None:
                return _job_error("JOB_NOT_FOUND", f"Job {job_id!r} not found")
            
            return {
                "status": "success",
                "data": {
                    "job": {
                        "id": job.id,
                        "status": job.status,
                        "category": job.category,
                        "updated_at": job.updated_at,
                        "completed_at": job.completed_at,
                        "last_error": job.last_error,
                    }
                },
            }
        except Exception as e:
            result = _job_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_job_inspect(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle job.inspect command - get full job details by ID."""
        try:
            from peeka.core.jobs import to_dict as job_to_dict
            
            job_id = command.get("job_id", "")
            if not job_id:
                return _job_error("JOB_NOT_FOUND", "job_id is required")
            
            job = job_registry.get(job_id)
            if job is None:
                return _job_error("JOB_NOT_FOUND", f"Job {job_id!r} not found")
            
            return {
                "status": "success",
                "data": {"job": job_to_dict(job)},
            }
        except Exception as e:
            result = _job_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_job_interrupt(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle job.interrupt command - attempt to interrupt a job."""
        try:
            job_id = command.get("job_id", "")
            if not job_id:
                return _job_error("JOB_NOT_FOUND", "job_id is required")
            
            job = job_registry.get(job_id)
            if job is None:
                return _job_error("JOB_NOT_FOUND", f"Job {job_id!r} not found")
            
            if job.status in TERMINAL_STATUSES:
                return _job_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Job is already in terminal state {job.status!r}",
                )
            
            if job.category == "probe":
                success = job_registry.set_status(job_id, "interrupted")
                if not success:
                    return _job_error(
                        "UNSUPPORTED_CAPABILITY",
                        f"Cannot transition from {job.status} to interrupted",
                    )
                
                if job.client_session_id:
                    client_registry = _get_client_registry()
                    client_registry.clear_foreground_job(
                        job.client_session_id, expected_job_id=job.id
                    )
                
                return {
                    "status": "success",
                    "data": {"job_id": job_id, "status": "interrupted"},
                }
            elif job.category in ("snapshot", "mutation"):
                return _job_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Interrupt not supported for {job.category} jobs",
                )
            else:
                return _job_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown job category: {job.category}",
                )
        except Exception as e:
            result = _job_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_job_cleanup(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle job.cleanup command - remove old terminal jobs."""
        try:
            target_id = command.get("target_id")
            completed_only = bool(command.get("completed_only", False))
            older_than_seconds = int(command.get("older_than_seconds", 600))
            
            now = _time.time()
            candidate_jobs = job_registry.list(
                target=target_id if target_id else None
            )
            
            to_remove = []
            for job in candidate_jobs:
                if job.status not in TERMINAL_STATUSES:
                    continue
                if completed_only and job.status != "completed":
                    continue
                terminal_at = job.completed_at if job.completed_at is not None else job.updated_at
                age = now - terminal_at
                if age > older_than_seconds:
                    to_remove.append(job.id)
            
            removed_ids = []
            for job_id in to_remove:
                if job_registry.remove(job_id):
                    removed_ids.append(job_id)
            
            return {
                "status": "success",
                "data": {"removed": removed_ids},
            }
        except Exception as e:
            result = _job_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_consumer_create(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consumer.create command."""
        try:
            from peeka.core.result_consumers import to_dict as consumer_to_dict

            target_id = command.get("target_id", "")
            source = command.get("source", "")
            scope_type = command.get("scope_type", "")
            scope_id = command.get("scope_id", "")
            client_session_id = command.get("client_session_id")
            max_buffer_size = int(command.get("max_buffer_size", 1000))
            backpressure_policy = command.get("backpressure_policy", "drop_oldest")

            if not target_id:
                return _consumer_error("UNSUPPORTED_CAPABILITY", "target_id is required")
            if source not in {"cli", "tui", "mcp", "api", "internal"}:
                return _consumer_error("UNSUPPORTED_CAPABILITY", f"invalid source: {source!r}")
            if scope_type not in {"job", "probe", "target"}:
                return _consumer_error("UNSUPPORTED_CAPABILITY", f"invalid scope_type: {scope_type!r}")
            if not scope_id:
                return _consumer_error("UNSUPPORTED_CAPABILITY", "scope_id is required")
            if backpressure_policy not in {"drop_oldest", "drop_newest", "fail"}:
                return _consumer_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"invalid backpressure_policy: {backpressure_policy!r}",
                )

            if client_session_id:
                client_registry = _get_client_registry()
                client = client_registry.get(str(client_session_id))
                if client is None:
                    return _consumer_error(
                        "CLIENT_NOT_FOUND",
                        f"Client session {client_session_id!r} not found",
                    )

            registry = _get_consumer_registry()
            try:
                consumer = registry.create(
                    target_id=target_id,
                    source=source,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    client_session_id=str(client_session_id) if client_session_id else None,
                    max_buffer_size=max_buffer_size,
                    backpressure_policy=backpressure_policy,
                )
            except ValueError as exc:
                return _consumer_error("UNSUPPORTED_CAPABILITY", str(exc))

            if client_session_id:
                _get_client_registry().add_result_consumer(
                    str(client_session_id), consumer.consumer_id
                )

            return _consumer_success(consumer_to_dict(consumer))
        except Exception as e:
            result = _consumer_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_consumer_list(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consumer.list command."""
        try:
            from peeka.core.result_consumers import to_dict as consumer_to_dict

            registry = _get_consumer_registry()
            requesting_client_session_id = _get_requesting_client_session_id(command)
            consumers = registry.list(
                target_id=command.get("target_id"),
                client_session_id=command.get("client_session_id"),
                scope_type=command.get("scope_type"),
                scope_id=command.get("scope_id"),
                status=command.get("status"),
            )
            consumers = [
                consumer
                for consumer in consumers
                if _consumer_owner_matches(consumer, requesting_client_session_id)
            ]
            return _consumer_success(
                {"consumers": [consumer_to_dict(consumer) for consumer in consumers]}
            )
        except Exception as e:
            result = _consumer_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_consumer_status(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consumer.status command."""
        try:
            from peeka.core.result_consumers import to_dict as consumer_to_dict

            consumer_id = command.get("consumer_id", "")
            requesting_client_session_id = _get_requesting_client_session_id(command)
            if not consumer_id:
                return _consumer_error("CONSUMER_NOT_FOUND", "consumer_id is required")

            registry = _get_consumer_registry()
            consumer = registry.get(consumer_id)
            if consumer is None:
                return _consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )
            if not _consumer_owner_matches(consumer, requesting_client_session_id):
                return _consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )
            return _consumer_success(consumer_to_dict(consumer))
        except Exception as e:
            result = _consumer_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_consumer_drain(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consumer.drain command."""
        try:
            consumer_id = command.get("consumer_id", "")
            requesting_client_session_id = _get_requesting_client_session_id(command)
            if not consumer_id:
                return _consumer_error("CONSUMER_NOT_FOUND", "consumer_id is required")

            limit = int(command.get("limit", 100))
            after_sequence = command.get("after_sequence")
            timeout_ms = int(command.get("timeout_ms", 0))
            if after_sequence is not None:
                after_sequence = int(after_sequence)

            registry = _get_consumer_registry()
            consumer = registry.get(consumer_id)
            if consumer is None:
                return _consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )
            if not _consumer_owner_matches(consumer, requesting_client_session_id):
                return _consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )
            if consumer.status == "closed":
                return _consumer_error(
                    "CONSUMER_CLOSED",
                    f"Consumer {consumer_id!r} is closed",
                )

            drained = registry.drain(
                consumer_id,
                limit=limit,
                after_sequence=after_sequence,
                timeout_ms=timeout_ms,
            )
            if drained is None:
                return _consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )
            if drained.get("timed_out") and not drained.get("records"):
                return _consumer_error(
                    "CONSUMER_DRAIN_TIMEOUT",
                    f"No records available for consumer {consumer_id!r} within {timeout_ms}ms",
                )
            return _consumer_success(drained)
        except Exception as e:
            result = _consumer_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_consumer_close(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consumer.close command."""
        try:
            consumer_id = command.get("consumer_id", "")
            requesting_client_session_id = _get_requesting_client_session_id(command)
            if not consumer_id:
                return _consumer_error("CONSUMER_NOT_FOUND", "consumer_id is required")

            registry = _get_consumer_registry()
            consumer = registry.get(consumer_id)
            if consumer is None:
                return _consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )
            if not _consumer_owner_matches(consumer, requesting_client_session_id):
                return _consumer_error(
                    "CONSUMER_NOT_FOUND",
                    f"Consumer {consumer_id!r} not found",
                )

            closed = registry.close(consumer_id)
            if consumer.client_session_id:
                _get_client_registry().remove_result_consumer(
                    consumer.client_session_id,
                    consumer_id,
                )
            return _consumer_success({"closed": closed, "consumer_id": consumer_id})
        except Exception as e:
            result = _consumer_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_consumer_cleanup(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle consumer.cleanup command."""
        try:
            closed_only = bool(command.get("closed_only", True))
            registry = _get_consumer_registry()
            requesting_client_session_id = _get_requesting_client_session_id(command)
            consumers = registry.list()
            removed_ids = []
            for consumer in consumers:
                if not _consumer_owner_matches(consumer, requesting_client_session_id):
                    continue
                if closed_only and consumer.status not in ("closed", "failed"):
                    continue
                removed = registry.remove(consumer.consumer_id)
                if removed is None:
                    continue
                removed_ids.append(removed.consumer_id)
                if removed.client_session_id:
                    _get_client_registry().remove_result_consumer(
                        removed.client_session_id,
                        removed.consumer_id,
                    )
            return _consumer_success({"removed_ids": removed_ids})
        except Exception as e:
            result = _consumer_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_create(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.create command."""
        try:
            from peeka.core.dx_cases import to_dict as dx_to_dict

            target_id = command.get("target_id", "")
            title = command.get("title", "")
            client_session_id = command.get("client_session_id")
            if not target_id or not title:
                return _dx_error("DX_CASE_INVALID", "target_id and title are required")

            if client_session_id:
                client = _get_client_registry().get(str(client_session_id))
                if client is None:
                    return _dx_error(
                        "DX_CASE_INVALID",
                        f"Client session {client_session_id!r} not found",
                    )

            dx_case = _get_dx_case_registry().create(
                target_id=target_id,
                title=title,
                client_session_id=str(client_session_id) if client_session_id else None,
            )
            return _dx_success(dx_to_dict(dx_case))
        except Exception as e:
            result = _dx_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_list(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.list command."""
        try:
            from peeka.core.dx_cases import to_dict as dx_to_dict

            requesting_client_session_id = _get_requesting_client_session_id(command)
            cases = _get_dx_case_registry().list(
                target_id=command.get("target_id"),
                client_session_id=command.get("client_session_id"),
                status=command.get("status"),
            )
            cases = [
                dx_case
                for dx_case in cases
                if _dx_owner_matches(dx_case, requesting_client_session_id)
            ]
            return _dx_success({"cases": [dx_to_dict(item) for item in cases]})
        except Exception as e:
            result = _dx_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_status(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.status command."""
        try:
            from peeka.core.dx_cases import to_dict as dx_to_dict

            dx_case_id = command.get("dx_case_id", "")
            requesting_client_session_id = _get_requesting_client_session_id(command)
            if not dx_case_id:
                return _dx_error("DX_CASE_NOT_FOUND", "dx_case_id is required")
            dx_case = _get_dx_case_registry().get(dx_case_id)
            if dx_case is None:
                return _dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            if not _dx_owner_matches(dx_case, requesting_client_session_id):
                return _dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            return _dx_success(dx_to_dict(dx_case))
        except Exception as e:
            result = _dx_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_add(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.add command."""
        try:
            dx_case_id = command.get("dx_case_id", "")
            requesting_client_session_id = _get_requesting_client_session_id(command)
            section_type = command.get("section_type", "")
            title = command.get("title", "")
            payload = command.get("payload") or {}
            object_ref_type = command.get("object_ref_type")
            object_ref_id = command.get("object_ref_id")
            if not dx_case_id or not section_type or not title:
                return _dx_error(
                    "DX_CASE_INVALID",
                    "dx_case_id, section_type, and title are required",
                )

            existing_case = _get_dx_case_registry().get(dx_case_id)
            if existing_case is None:
                return _dx_error(
                    "DX_CASE_NOT_FOUND",
                    f"DX case {dx_case_id!r} not found or cannot be modified",
                )
            if not _dx_owner_matches(existing_case, requesting_client_session_id):
                return _dx_error(
                    "DX_CASE_NOT_FOUND",
                    f"DX case {dx_case_id!r} not found or cannot be modified",
                )

            section = _get_dx_case_registry().add_section(
                dx_case_id,
                section_type=section_type,
                title=title,
                payload=payload,
                object_ref_type=object_ref_type,
                object_ref_id=object_ref_id,
            )
            if section is None:
                return _dx_error(
                    "DX_CASE_NOT_FOUND",
                    f"DX case {dx_case_id!r} not found or cannot be modified",
                )
            return _dx_success({"section": asdict(section), "dx_case_id": dx_case_id})
        except Exception as e:
            result = _dx_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_summary(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.summary command."""
        try:
            from peeka.core.dx_cases import build_text_summary

            dx_case_id = command.get("dx_case_id", "")
            requesting_client_session_id = _get_requesting_client_session_id(command)
            if not dx_case_id:
                return _dx_error("DX_CASE_NOT_FOUND", "dx_case_id is required")
            registry = _get_dx_case_registry()
            existing_case = registry.get(dx_case_id)
            if existing_case is None or not _dx_owner_matches(existing_case, requesting_client_session_id):
                return _dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            summary = registry.update_summary(dx_case_id)
            dx_case = registry.get(dx_case_id)
            if summary is None or dx_case is None:
                return _dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            return _dx_success(
                {
                    "dx_case_id": dx_case_id,
                    "summary": summary,
                    "text_summary": build_text_summary(dx_case),
                }
            )
        except Exception as e:
            result = _dx_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_export(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.export command."""
        try:
            from peeka.core.client_sessions import to_dict as client_to_dict
            from peeka.core.dx_cases import build_export_document
            from peeka.core.dx_cases import build_text_summary
            from peeka.core.dx_cases import resolve_export_path
            from peeka.core.dx_cases import to_dict as dx_to_dict
            from peeka.core.dx_cases import write_export_json
            from peeka.core.jobs import to_dict as job_to_dict
            from peeka.core.result_consumers import to_dict as consumer_to_dict

            dx_case_id = command.get("dx_case_id", "")
            output_path = command.get("output_path")
            requesting_client_session_id = _get_requesting_client_session_id(command)
            if not dx_case_id:
                return _dx_error("DX_CASE_NOT_FOUND", "dx_case_id is required")

            registry = _get_dx_case_registry()
            dx_case = registry.get(dx_case_id)
            if dx_case is None:
                return _dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            if not _dx_owner_matches(dx_case, requesting_client_session_id):
                return _dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")

            missing_ref_messages = []

            target_snapshot = {}
            target = None
            try:
                from peeka.core.targets import get_target

                target = get_target(dx_case.target_id)
            except Exception:
                target = None
            if target is not None:
                target_snapshot = target.to_dict()
            elif dx_case.target_id:
                missing_ref_messages.append(("target", dx_case.target_id, "TARGET_NOT_FOUND"))

            client_snapshot = {}
            if dx_case.client_session_id:
                client = _get_client_registry().get(dx_case.client_session_id)
                if client is not None:
                    client_snapshot = client_to_dict(client)
                else:
                    missing_ref_messages.append(("client", dx_case.client_session_id, "CLIENT_NOT_FOUND"))

            job_snapshots = []
            for job_id in dx_case.object_refs.get("jobs", []):
                job = job_registry.get(job_id)
                if job is not None:
                    job_snapshots.append(job_to_dict(job))
                else:
                    missing_ref_messages.append(("job", job_id, "JOB_NOT_FOUND"))

            probe_snapshots = []
            for probe_id in dx_case.object_refs.get("probes", []):
                probe = self.probe_registry.get(probe_id)
                if probe is not None:
                    probe_snapshots.append(probe.to_dict())
                else:
                    missing_ref_messages.append(("probe", probe_id, "PROBE_NOT_FOUND"))

            consumer_snapshots = []
            for consumer_id in dx_case.object_refs.get("consumers", []):
                consumer = _get_consumer_registry().get(consumer_id)
                if consumer is not None:
                    consumer_snapshots.append(consumer_to_dict(consumer))
                else:
                    missing_ref_messages.append(("consumer", consumer_id, "CONSUMER_NOT_FOUND"))

            if missing_ref_messages:
                for ref_type, ref_id, error_code in missing_ref_messages:
                    registry.add_section(
                        dx_case_id,
                        section_type="error",
                        title=f"Missing {ref_type} reference",
                        payload={
                            "error_code": error_code,
                            "ref_type": ref_type,
                            "ref_id": ref_id,
                            "message": f"Referenced {ref_type} {ref_id!r} was not found during export",
                        },
                    )
                refreshed_case = registry.get(dx_case_id)
                if refreshed_case is not None:
                    dx_case = refreshed_case

            document = build_export_document(
                dx_case,
                target_snapshot=target_snapshot,
                client_snapshot=client_snapshot,
                job_snapshots=job_snapshots,
                probe_snapshots=probe_snapshots,
                consumer_snapshots=consumer_snapshots,
            )
            destination = resolve_export_path(dx_case_id, str(output_path) if output_path else None)
            write_export_json(destination, document)
            registry.record_export(dx_case_id, destination)
            updated_case = registry.get(dx_case_id)
            if updated_case is None:
                return _dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            return _dx_success(
                {
                    "dx_case": dx_to_dict(updated_case),
                    "output_path": destination,
                    "text_summary": build_text_summary(updated_case),
                }
            )
        except Exception as e:
            result = _dx_error("DX_EXPORT_FAILED", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_dx_close(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Handle dx.close command."""
        try:
            dx_case_id = command.get("dx_case_id", "")
            requesting_client_session_id = _get_requesting_client_session_id(command)
            if not dx_case_id:
                return _dx_error("DX_CASE_NOT_FOUND", "dx_case_id is required")
            registry = _get_dx_case_registry()
            existing_case = registry.get(dx_case_id)
            if existing_case is None or not _dx_owner_matches(existing_case, requesting_client_session_id):
                return _dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            closed = registry.close(dx_case_id)
            if not closed:
                return _dx_error("DX_CASE_NOT_FOUND", f"DX case {dx_case_id!r} not found")
            return _dx_success({"dx_case_id": dx_case_id, "closed": True})
        except Exception as e:
            result = _dx_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_probe_list(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            target_id = params.get("target_id")
            status = params.get("status")
            probe_type = params.get("probe_type")

            probes = self.probe_registry.list(
                target_id=target_id,
                status=status,
                type=probe_type,
            )
            
            return {
                "status": "success",
                "data": {"probes": [probe.to_dict() for probe in probes]},
            }
        except Exception as e:
            result = _probe_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_probe_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            probe_id = params.get("probe_id", "")
            if not probe_id:
                return _probe_error("PROBE_NOT_FOUND", "probe_id is required")

            probe = self.probe_registry.get(probe_id)
            if probe is None:
                return _probe_error("PROBE_NOT_FOUND", f"Probe {probe_id!r} not found")
            
            return {
                "status": "success",
                "data": {"probe": probe.to_dict()},
            }
        except Exception as e:
            result = _probe_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_probe_inspect(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            probe_id = params.get("probe_id", "")
            if not probe_id:
                return _probe_error("PROBE_NOT_FOUND", "probe_id is required")

            probe = self.probe_registry.get(probe_id)
            if probe is None:
                return _probe_error("PROBE_NOT_FOUND", f"Probe {probe_id!r} not found")
            
            events_limit = int(params.get("events_limit", 100))
            if events_limit > 100:
                events_limit = 100
            
            recent_events = self.probe_registry.get_recent_events(probe_id, limit=events_limit)
            
            return {
                "status": "success",
                "data": {
                    "probe": probe.to_dict(),
                    "events": [
                        {
                            "event_id": event.event_id,
                            "probe_id": event.probe_id,
                            "target_id": event.target_id,
                            "sequence": event.sequence,
                            "timestamp": event.timestamp,
                            "payload": event.payload,
                        }
                        for event in recent_events
                    ],
                },
            }
        except Exception as e:
            result = _probe_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_probe_stop(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from peeka.core.probes import TERMINAL_STATUSES as PROBE_TERMINAL_STATUSES

            probe_id = params.get("probe_id", "")
            if not probe_id:
                return _probe_error("PROBE_NOT_FOUND", "probe_id is required")

            probe = self.probe_registry.get(probe_id)
            if probe is None:
                return _probe_error("PROBE_NOT_FOUND", f"Probe {probe_id!r} not found")
            
            if probe.status in PROBE_TERMINAL_STATUSES:
                return {
                    "status": "success",
                    "data": {
                        "probe_id": probe_id,
                        "summary": f"Probe already in terminal state {probe.status}",
                    },
                }
            
            success = self.probe_registry.set_status(probe_id, "stopped")
            if not success:
                return _probe_error(
                    "COMMAND_EXECUTION_ERROR",
                    f"Failed to transition probe from {probe.status} to stopped",
                )
            
            return {
                "status": "success",
                "data": {"probe_id": probe_id},
            }
        except Exception as e:
            result = _probe_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result

    def _handle_probe_pause(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return _probe_error(
            "UNSUPPORTED_CAPABILITY",
            "pause is not yet implemented",
        )

    def _handle_probe_cleanup(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            older_than_seconds = float(params.get("older_than_seconds", 600))
            completed_only = bool(params.get("completed_only", True))
            target_id = params.get("target_id")

            removed_ids = self.probe_registry.cleanup(
                older_than_seconds=older_than_seconds,
                target_id=target_id,
                completed_only=completed_only,
            )
            
            return {
                "status": "success",
                "data": {"removed_ids": removed_ids},
            }
        except Exception as e:
            result = _probe_error("COMMAND_EXECUTION_ERROR", str(e))
            result["traceback"] = traceback.format_exc()
            return result


    def _register_handlers(self) -> None:
        """Eagerly import and register ALL command handlers.

        Used by `start()` after the socket is ready so that commands
        are available immediately.  Runs on the agent thread so it
        does not block GIL during GDB injection.
        """
        for cmd_type in list(self._COMMAND_REGISTRY):
            self._get_handler(cmd_type)

    @staticmethod
    def _normalize_action(command: Dict[str, Any]) -> str:
        """Return a normalized action name for logging decisions."""
        action = command.get("action")
        if action is None:
            return ""
        return str(action).lower()

    def _should_log_command(self, command: Dict[str, Any]) -> bool:
        """Return True when a command is worth surfacing in agent activity logs."""
        cmd_type = str(command.get("type", "unknown"))
        action = self._normalize_action(command)
        return (cmd_type, action) not in self._QUIET_COMMAND_ACTIONS

    @staticmethod
    def _sanitize_client_field(value: Any, default: str) -> str:
        """Normalize client identity fields before placing them in logs."""
        text = str(value if value not in (None, "") else default)
        sanitized = []
        for char in text[:48]:
            if char.isalnum() or char in ("-", "_", "."):
                sanitized.append(char)
            else:
                sanitized.append("_")
        return "".join(sanitized) or default

    def _extract_client_info(self, command: Dict[str, Any]) -> Dict[str, Any]:
        """Extract sanitized client metadata from a command payload."""
        raw_info = command.get("_client")
        if not isinstance(raw_info, dict):
            return {}

        info: Dict[str, Any] = {
            "id": self._sanitize_client_field(raw_info.get("id"), "anonymous"),
            "source": self._sanitize_client_field(raw_info.get("source"), "unknown"),
            "kind": self._sanitize_client_field(raw_info.get("kind"), "client"),
        }
        pid = raw_info.get("pid")
        if isinstance(pid, int) or (isinstance(pid, str) and pid.isdigit()):
            info["pid"] = str(pid)
        return info

    @staticmethod
    def _strip_client_info(command: Dict[str, Any]) -> Dict[str, Any]:
        """Remove transport metadata before command dispatch."""
        if "_client" not in command:
            return command
        stripped = dict(command)
        stripped.pop("_client", None)
        return stripped

    def _is_client_hello(self, command: Dict[str, Any]) -> bool:
        """Return True for client identity frames handled by the transport layer."""
        cmd_type = str(command.get("type", ""))
        action = self._normalize_action(command)
        return cmd_type == "client" and action == "hello"

    @staticmethod
    def _format_client_label(client_id: int, client_info: Dict[str, Any]) -> str:
        """Return a readable stable client label for activity logs."""
        instance_id = client_info.get("id")
        source = client_info.get("source")
        if instance_id and source:
            return f"client {instance_id}/{source} conn#{client_id}"
        return f"conn#{client_id}"

    def _summarize_command(self, command: Dict[str, Any]) -> str:
        """Build a concise command summary for agent-side diagnostics."""
        cmd_type = str(command.get("type", "unknown"))
        action = self._normalize_action(command) or "execute"
        details = []

        for key in ("pattern", "watch_id", "top_id", "logger", "level", "target"):
            value = command.get(key)
            if value not in (None, ""):
                details.append(f"{key}={value}")

        if "interval" in command:
            details.append(f"interval={command.get('interval')}")
        if "times" in command:
            details.append(f"times={command.get('times')}")

        summary = f"{cmd_type}/{action}"
        if details:
            summary += " " + " ".join(details[:4])
        return summary

    @staticmethod
    def _summarize_result(result: Dict[str, Any]) -> str:
        """Build a concise result summary for command completion logs."""
        details = []
        for key in ("watch_id", "top_id", "message", "observation_count"):
            value = result.get(key)
            if value not in (None, "", []):
                details.append(f"{key}={value}")

        if not details:
            return "success"
        return "success " + " ".join(details[:3])

    def start(self) -> bool:
        try:
            self.server = _rpl.create_socket("AF_UNIX", "SOCK_STREAM")

            if Path(self.sock_path).exists():
                Path(self.sock_path).unlink()

            assert self.server is not None
            self.server.bind(self.sock_path)
            self.server.listen(5)
            # Set a timeout so accept() doesn't block forever,
            # allowing the accept loop to check self.running periodically.
            self.server.settimeout(1.0)

            # Start the accept loop with a native low-level thread. Do not use
            # target-process threading primitives here: frameworks such as
            # gevent may monkey-patch threading.Event/Thread and make blocking
            # waits illegal in the injection callback.
            _rpl.start_thread(self._accept_loop)

            # Signal readiness via TCP reverse-connect (preferred) and
            # .ready file (fallback / backward compatibility).
            self._notify_ready()
            Path(f"/tmp/peeka_{self.session_id}.ready").touch()
            msg_start = "[peeka Agent] Started and listening for connections"
            msg_ready = "[peeka Agent] Ready for commands"
            self._emit_log("INFO", msg_start)
            self._emit_log("INFO", msg_ready)

            # Eagerly load all command handlers now that the socket is
            # ready.  This runs on the agent thread (not GIL-blocking).
            self._register_handlers()
            return True

        except Exception as e:
            self.running = False
            if self.server:
                try:
                    self.server.close()
                except OSError:
                    pass
            self._cleanup_session_files()
            msg = f"[peeka Agent] Start failed: {e}"
            self._emit_log("ERROR", msg, traceback.format_exc())
            return False

    def _accept_loop(self) -> None:
        while self.running:
            try:
                if self.server is None:
                    break
                conn, _ = _rpl.native_accept(self.server)
                self._client_counter += 1
                _rpl.start_thread(self._handle_client, (conn, self._client_counter))
            except socket.timeout:
                # Periodic wakeup to re-check self.running
                continue
            except OSError:
                # Server socket closed (stop() called) — exit cleanly
                break
            except Exception as e:
                if self.running:
                    msg = f"[peeka Agent] Accept error: {e}"
                    self._emit_log("ERROR", msg, traceback.format_exc())

    def _register_client_connection(
        self, conn: socket.socket, kind: str = "control"
    ) -> int:
        """Track a live client connection and initialize its write lock."""
        with self._connections_lock:
            self._client_connections.append(conn)
            self._client_connection_kinds[conn] = kind
            self._client_write_locks[conn] = _rpl.allocate_lock()
            return len(self._client_connections)

    def _set_client_connection_kind(self, conn: socket.socket, kind: str) -> None:
        """Update the broadcast kind for a live client connection."""
        with self._connections_lock:
            if conn in self._client_connections:
                self._client_connection_kinds[conn] = kind

    def _unregister_client_connection(self, conn: socket.socket) -> int:
        """Forget a client connection and its write lock."""
        with self._connections_lock:
            if conn in self._client_connections:
                self._client_connections.remove(conn)
            self._client_connection_kinds.pop(conn, None)
            self._client_write_locks.pop(conn, None)
            return len(self._client_connections)

    def _snapshot_client_connections(
        self, kind: Optional[str] = None
    ) -> List[socket.socket]:
        """Return a snapshot of currently tracked client sockets."""
        with self._connections_lock:
            if kind is not None:
                return [
                    conn
                    for conn in self._client_connections
                    if self._client_connection_kinds.get(conn, "control") == kind
                ]
            return list(self._client_connections)

    @classmethod
    def _command_opens_observation_stream(cls, command: Dict[str, Any]) -> bool:
        """Return True when a command should receive future OBS broadcasts."""
        cmd_type = str(command.get("type", ""))
        action = str(command.get("action", ""))
        allowed_actions = cls._OBS_STREAM_COMMANDS.get(cmd_type)
        if allowed_actions is None:
            return False
        return action in allowed_actions

    def _send_frame_to_connection(self, conn: socket.socket, frame: bytes) -> bool:
        """Send one framed message to a tracked connection.

        Returns:
            True when the frame is written successfully, else False.
        """
        with self._connections_lock:
            write_lock = self._client_write_locks.get(conn)
        if write_lock is None:
            return False

        try:
            with write_lock:
                conn.sendall(frame)
            return True
        except Exception:
            return False

    def _handle_client(self, conn: socket.socket, client_id: int) -> None:
        connection_total = self._register_client_connection(conn)

        client_info: Dict[str, Any] = {}
        identified = False
        client_label = self._format_client_label(client_id, client_info)

        try:
            while True:
                length_bytes = conn.recv(4)
                if not length_bytes:
                    break

                length = int.from_bytes(length_bytes, "big")
                data = b""
                while len(data) < length:
                    chunk = conn.recv(min(length - len(data), 4096))
                    if not chunk:
                        break
                    data += chunk

                if len(data) < length:
                    break

                raw_command = json.loads(data.decode("utf-8"))
                extracted_info = self._extract_client_info(raw_command)
                if extracted_info:
                    client_info = extracted_info
                    client_label = self._format_client_label(client_id, client_info)
                    if not identified:
                        pid = client_info.get("pid")
                        pid_suffix = f" pid={pid}" if pid else ""
                        kind = client_info.get("kind", "client")
                        self._emit_log(
                            "INFO",
                            (
                                f"[peeka Agent] {client_label} connected "
                                f"({connection_total} total) kind={kind}{pid_suffix}"
                            ),
                        )
                        identified = True

                command = self._strip_client_info(raw_command)
                if self._is_client_hello(command):
                    result = {"status": "success", "client": client_label}
                else:
                    should_log = self._should_log_command(command)
                    command_summary = self._summarize_command(command)
                    if should_log:
                        self._emit_log(
                            "INFO",
                            f"[peeka Agent] {client_label} -> {command_summary}",
                        )
                    result = self._execute_command(command)

                    if (
                        result.get("status") == "success"
                        and self._command_opens_observation_stream(command)
                    ):
                        self._set_client_connection_kind(conn, "stream")

                    if result.get("status") == "error":
                        self._emit_log(
                            "ERROR",
                            f"[peeka Agent] {client_label} {command_summary} failed: "
                            f"{result.get('error', 'unknown error')}",
                            result.get("traceback"),
                        )
                    elif should_log:
                        self._emit_log(
                            "INFO",
                            f"[peeka Agent] {client_label} {command_summary} "
                            f"{self._summarize_result(result)}",
                        )

                response = json.dumps(result).encode("utf-8")
                response_frame = len(response).to_bytes(4, "big") + response
                if not self._send_frame_to_connection(conn, response_frame):
                    break

        except Exception as e:
            msg = f"[peeka Agent] Client error: {e}"
            self._emit_log("ERROR", msg, traceback.format_exc())
        finally:
            connection_total = self._unregister_client_connection(conn)
            conn.close()
            self._emit_log(
                "INFO",
                f"[peeka Agent] {client_label} disconnected ({connection_total} total)",
            )

    def _execute_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
        cmd_type = command.get("type", "")

        # Handle legacy {"command":"ping"} as alias to target.hello
        if "command" in command and command.get("command") == "ping":
            return self._handle_target_hello()

        # Handle new target namespace
        if cmd_type == "target":
            action = command.get("action", "")
            if action == "hello":
                return self._handle_target_hello()
            elif action == "status":
                return self._handle_target_status()
            else:
                return {"status": "error", "error": f"Unknown target action: {action}"}

        if cmd_type == "client":
            action = command.get("action", "")
            registry = _get_client_registry()
            registry.cleanup_idle(idle_threshold_seconds=900)
            if action == "create":
                return self._handle_client_create(command)
            elif action == "list":
                return self._handle_client_list(command)
            elif action == "status":
                return self._handle_client_status(command)
            elif action == "close":
                return self._handle_client_close(command)
            else:
                return _client_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown client action: {action}",
                )

        if cmd_type == "job":
            action = command.get("action", "")
            job_registry.cleanup(retention_seconds=600)
            if action == "list":
                return self._handle_job_list(command)
            elif action == "status":
                return self._handle_job_status(command)
            elif action == "inspect":
                return self._handle_job_inspect(command)
            elif action == "interrupt":
                return self._handle_job_interrupt(command)
            elif action == "cleanup":
                return self._handle_job_cleanup(command)
            else:
                return _job_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown job action: {action}",
                )

        if cmd_type == "probe":
            action = command.get("action", "")
            if action == "list":
                return self._handle_probe_list(command)
            elif action == "status":
                return self._handle_probe_status(command)
            elif action == "inspect":
                return self._handle_probe_inspect(command)
            elif action == "stop":
                return self._handle_probe_stop(command)
            elif action == "pause":
                return self._handle_probe_pause(command)
            elif action == "cleanup":
                return self._handle_probe_cleanup(command)
            else:
                return _probe_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown probe action: {action}",
                )

        if cmd_type == "consumer":
            action = command.get("action", "")
            if action == "create":
                return self._handle_consumer_create(command)
            elif action == "list":
                return self._handle_consumer_list(command)
            elif action == "status":
                return self._handle_consumer_status(command)
            elif action == "drain":
                return self._handle_consumer_drain(command)
            elif action == "close":
                return self._handle_consumer_close(command)
            elif action == "cleanup":
                return self._handle_consumer_cleanup(command)
            else:
                return _consumer_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown consumer action: {action}",
                )

        if cmd_type == "dx":
            action = command.get("action", "")
            if action == "create":
                return self._handle_dx_create(command)
            elif action == "list":
                return self._handle_dx_list(command)
            elif action == "status":
                return self._handle_dx_status(command)
            elif action == "add":
                return self._handle_dx_add(command)
            elif action == "summary":
                return self._handle_dx_summary(command)
            elif action == "export":
                return self._handle_dx_export(command)
            elif action == "close":
                return self._handle_dx_close(command)
            else:
                return _dx_error(
                    "UNSUPPORTED_CAPABILITY",
                    f"Unknown dx action: {action}",
                )

        handler = self._get_handler(cmd_type)
        if handler:
            job_registry.cleanup(retention_seconds=600)

            client_session_id = str(command.get("client_session_id", ""))
            action = str(command.get("action", ""))
            foreground = not bool(command.get("background", False))
            params = {
                key: value
                for key, value in command.items()
                if key not in {"type", "action", "client_session_id", "background"}
            }
            category = getattr(type(handler), "category", "snapshot")
            allows_concurrent = bool(getattr(type(handler), "allows_concurrent", False))
            if category not in {"snapshot", "probe", "mutation"}:
                category = "snapshot"
            job_category = cast(JobCategory, category)

            client_registry = None
            client = None
            foreground_rule_applies = (
                (category != "snapshot" or not allows_concurrent)
                and foreground
                and bool(client_session_id)
            )
            if foreground_rule_applies:
                client_registry = _get_client_registry()
                client = client_registry.get(client_session_id)
                if client is not None and client.foreground_job_id:
                    existing_job = job_registry.get(client.foreground_job_id)
                    if (
                        existing_job is not None
                        and existing_job.status not in TERMINAL_STATUSES
                    ):
                        message = (
                            f"Client {client_session_id} already has foreground job "
                            f"{client.foreground_job_id}"
                        )
                        return {
                            "status": "error",
                            "error_code": "JOB_ALREADY_RUNNING",
                            "message": message,
                            "error": f"JOB_ALREADY_RUNNING: {message}",
                        }

            mutation_lock_acquired = False
            if category == "mutation":
                mutation_lock_acquired = self._mutation_lock.acquire(timeout=5.0)
                if not mutation_lock_acquired:
                    message = "mutation in progress"
                    return {
                        "status": "error",
                        "error_code": "JOB_ALREADY_RUNNING",
                        "message": message,
                        "error": f"JOB_ALREADY_RUNNING: {message}",
                    }

            job = None
            try:
                if foreground and client_session_id and client is None:
                    client_registry = client_registry or _get_client_registry()
                    client = client_registry.get(client_session_id)

                job = job_registry.create(
                    target_id=self._target_id_for_jobs(),
                    client_session_id=client_session_id,
                    command_type=str(cmd_type),
                    action=action,
                    params=params,
                    category=job_category,
                    foreground=foreground,
                )
                if (
                    job.foreground
                    and client_session_id
                    and client is not None
                    and client_registry is not None
                ):
                    client_registry.set_foreground_job(client_session_id, job.id)
                job_registry.set_status(job.id, "running")

                command["job_id"] = job.id
                result = handler.execute(command)

                if isinstance(result, dict) and result.get("status") == "error":
                    last_error = {
                        "code": str(result.get("error_code", "COMMAND_ERROR")),
                        "message": str(result.get("message") or result.get("error", "")),
                    }
                    job_registry.set_status(job.id, "failed", last_error=last_error)
                    _get_consumer_registry().append_for_scope(
                        job.target_id,
                        source_type="job",
                        source_id=job.id,
                        record_type="error",
                        payload={
                            "job_id": job.id,
                            "command_type": cmd_type,
                            "action": action,
                            "error_code": last_error["code"],
                            "message": last_error["message"],
                        },
                    )
                    if (
                        job.foreground
                        and client_session_id
                        and client_registry is not None
                    ):
                        client_registry.clear_foreground_job(
                            client_session_id,
                            expected_job_id=job.id,
                        )
                    result["job_id"] = job.id
                    return result

                result_summary = result.get("data") if "data" in result else result
                final_status = "completed"
                if category == "probe" and result.get("status") == "success":
                    final_status = "streaming"
                    job_registry.set_status(
                        job.id,
                        final_status,
                        result_summary=result_summary,
                    )
                else:
                    job_registry.set_status(
                        job.id,
                        final_status,
                        result_summary=result_summary,
                    )
                _get_consumer_registry().append_for_scope(
                    job.target_id,
                    source_type="job",
                    source_id=job.id,
                    record_type="summary" if final_status in TERMINAL_STATUSES else "result",
                    payload={
                        "job_id": job.id,
                        "command_type": cmd_type,
                        "action": action,
                        "status": final_status,
                        "data": result_summary,
                    },
                )
                if (
                    final_status in TERMINAL_STATUSES
                    and job.foreground
                    and client_session_id
                    and client_registry is not None
                ):
                    client_registry.clear_foreground_job(
                        client_session_id,
                        expected_job_id=job.id,
                    )

                result["job_id"] = job.id
                return result
            except Exception as e:
                error_entry = {
                    "timestamp": _time.time(),
                    "code": "COMMAND_EXECUTION_ERROR",
                    "message": str(e),
                }
                self._add_recent_error(error_entry)
                result = {
                    "status": "error",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
                if job is not None:
                    job_registry.set_status(
                        job.id,
                        "failed",
                        last_error={
                            "code": "COMMAND_EXECUTION_ERROR",
                            "message": str(e),
                        },
                    )
                    _get_consumer_registry().append_for_scope(
                        job.target_id,
                        source_type="job",
                        source_id=job.id,
                        record_type="error",
                        payload={
                            "job_id": job.id,
                            "command_type": cmd_type,
                            "action": action,
                            "error_code": "COMMAND_EXECUTION_ERROR",
                            "message": str(e),
                        },
                    )
                    if (
                        job.foreground
                        and client_session_id
                        and client_registry is not None
                    ):
                        client_registry.clear_foreground_job(
                            client_session_id,
                            expected_job_id=job.id,
                        )
                    result["job_id"] = job.id
                return result
            finally:
                if mutation_lock_acquired:
                    self._mutation_lock.release()
        else:
            return {
                "status": "error",
                "error_code": "COMMAND_NOT_FOUND",
                "message": f"Unknown command type: {cmd_type}",
                "error": f"COMMAND_NOT_FOUND: Unknown command type: {cmd_type}",
            }

    def _send_observation(self, observation: Dict[str, Any]) -> None:
        """Called by injector when a watched function is invoked."""
        observation["type"] = "observation"
        self.observer.add_observation(observation)

        obs_json = json.dumps(observation).encode("utf-8")
        message = b"OBS:" + len(obs_json).to_bytes(4, "big") + obs_json

        dead_connections = []
        for conn in self._snapshot_client_connections(kind="stream"):
            if not self._send_frame_to_connection(conn, message):
                dead_connections.append(conn)

        for conn in dead_connections:
            self._unregister_client_connection(conn)

    def _send_log(self, level: str, message: str) -> None:
        """Send a log message from Agent to all connected host clients."""
        log_msg = {
            "type": "log",
            "level": level,
            "message": message,
            "timestamp": _time.time(),
        }
        obs_json = json.dumps(log_msg).encode("utf-8")
        frame = b"LOG:" + len(obs_json).to_bytes(4, "big") + obs_json

        dead_connections = []
        for conn in self._snapshot_client_connections():
            if not self._send_frame_to_connection(conn, frame):
                dead_connections.append(conn)

        for conn in dead_connections:
            self._unregister_client_connection(conn)

    def _notify_ready(self) -> None:
        """Notify the attacher that the agent is ready via TCP."""
        if self._notify_port <= 0:
            return
        try:
            s = _rpl.create_socket("AF_INET", "SOCK_STREAM")
            s.settimeout(5.0)
            s.connect(("127.0.0.1", self._notify_port))
            s.sendall(b"READY")
            s.close()
        except Exception:
            # Non-fatal: attacher will fall back to .ready file polling.
            pass

    def stop(self) -> None:
        self.running = False
        self.injector.uninject_all()

        if self.server:
            try:
                self.server.close()
            except OSError:
                pass

        self._cleanup_session_files()

        # Remove self from the global agent registry
        agents = cast(Optional[Dict[str, "PeekaAgent"]], getattr(sys, "_peeka_agents", None))
        if agents is not None:
            keys_to_remove = [k for k, v in agents.items() if v is self]
            for k in keys_to_remove:
                del agents[k]

    def _cleanup_session_files(self) -> None:
        """Remove .sock, .ready, and .pid files for this session.

        Called on stop/detach so that stale files don't trick
        _check_existing_attachment() into reporting a live agent.
        """
        for suffix in (".sock", ".ready", ".pid"):
            p = Path(f"/tmp/peeka_{self.session_id}{suffix}")
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass


def _init_agent(
    session_id: str,
    attached_pid: Optional[int] = None,
    notify_port: int = 0,
    suppress_startup_messages: bool = False,
) -> None:
    try:
        # Stop ALL existing agents from previous sessions to prevent thread leaks.
        # Each sys.remote_exec() call creates a new agent; without this cleanup,
        # old accept-loop and client-handler threads accumulate indefinitely.
        agents = cast(Optional[Dict[str, PeekaAgent]], getattr(sys, "_peeka_agents", None))
        if agents is not None:
            old_agents = list(agents.values())
            for old_agent in old_agents:
                try:
                    old_agent.stop()
                    msg = (
                        f"[peeka Agent] Stopped previous agent: {old_agent.session_id}"
                    )
                    old_agent._emit_log("INFO", msg)
                except Exception:
                    pass
            agents.clear()

        agent = PeekaAgent(
            session_id,
            attached_pid,
            notify_port=notify_port,
            suppress_startup_messages=suppress_startup_messages,
        )
        if agent.start():
            agents = cast(Optional[Dict[str, PeekaAgent]], getattr(sys, "_peeka_agents", None))
            if agents is None:
                agents = {}
                setattr(sys, "_peeka_agents", agents)
            agents[session_id] = agent
        else:
            msg = "[peeka Agent] Start failed; session not registered"
            _write_session_log(session_id, "ERROR", msg)

    except Exception as e:
        msg = f"[peeka Agent] Initialization failed: {e}"
        _write_session_log(session_id, "ERROR", msg, traceback.format_exc())


# Auto-initialize when injected via sys.remote_exec() or GDB
# {{SESSION_ID}}, {{ATTACHED_PID}}, and {{NOTIFY_PORT}} are replaced by
# ProcessAttacher before injection.
# This runs both when imported (PEP 768) and when exec'd (GDB fallback)
_session_id = "{{SESSION_ID}}"
_attached_pid_str = "{{ATTACHED_PID}}"
_notify_port_str = "{{NOTIFY_PORT}}"
_suppress_startup = "{{SUPPRESS_STARTUP_MESSAGES}}"
_attached_pid = int(_attached_pid_str) if _attached_pid_str.isdigit() else None
_notify_port = int(_notify_port_str) if _notify_port_str.isdigit() else 0
_suppress_startup_messages = _suppress_startup == "True"
if not _session_id.startswith("{{"):
    _init_agent(
        _session_id,
        _attached_pid,
        notify_port=_notify_port,
        suppress_startup_messages=_suppress_startup_messages,
    )


# ================================================================ #
# PEP 562 Module-level Deprecation Shim                            #
# ================================================================ #
# Backward-compatible access to relocated _NATIVE_* aliases.
# This shim coexists with the eager-capture block (lines 6-77)
# until T8 removes the eager block.


def __getattr__(name: str) -> Any:
    """PEP 562 module-level deprecation shim for relocated _NATIVE_* helpers."""
    _deprecated_aliases = {
        "_NATIVE_SOCKET": "_NATIVE_SOCKET",
        "_NATIVE_START_NEW_THREAD": "_NATIVE_START_NEW_THREAD",
        "_NATIVE_ALLOCATE_LOCK": "_NATIVE_ALLOCATE_LOCK",
        "_NATIVE_RLOCK": "_NATIVE_RLOCK",
        "_NATIVE_EVENT": "_NATIVE_EVENT",
        "_NATIVE_TIME": "_NATIVE_TIME",
        "_NATIVE_PERF_COUNTER": "_NATIVE_PERF_COUNTER",
        "_NATIVE_GET_IDENT": "_NATIVE_GET_IDENT",
        "_start_native_thread": "start_thread",
        "_native_accept": "native_accept",
        "_get_original_runtime_attr": "_get_original_runtime_attr",
    }

    if name in _deprecated_aliases:
        import warnings

        from peeka.core.runtime import primitives as _rpl

        warnings.warn(
            f"peeka.core.agent.{name} is deprecated; import from peeka.core.runtime.primitives instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return getattr(_rpl, _deprecated_aliases[name])
    raise AttributeError(f"module 'peeka.core.agent' has no attribute {name!r}")
