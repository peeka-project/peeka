"""
Trace Command - Trace function call paths and execution time
Similar to Arthas 'trace' command
"""

import sys
from typing import Any, ClassVar, Dict, TYPE_CHECKING

from peeka.commands.base import BaseCommand
from peeka.core.probes import ProbeContext
from peeka.core.runtime.compat import BACKEND_WRAPPER_ONLY, get_policy, policy_meta
from peeka.core.runtime.gevent_probe import probe

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class TraceCommand(BaseCommand):
    is_resource_owner = False  # explicit; not a resource owner
    """
    Trace command - traces function call tree and timing (Arthas-compatible)

    Usage:
        trace <module.class.method> [-n times] [--condition expr] [--skip-builtin] [--min-duration ms]

    Parameters:
        -n, --times: Observation limit, -1 for unlimited (default: -1)
        --condition: Filter expression (e.g., "cost > 50")
        --skip-builtin: Skip built-in functions and standard library (default: True)
        --min-duration: Minimum duration in ms to record child calls (default: 0)

    Examples:
        trace mymodule.MyClass.my_method
        trace mymodule.my_function -n 10
        trace mymodule.func --condition "cost > 50"
        trace mymodule.func --skip-builtin=false
        trace mymodule.func --min-duration 10
    """

    category: ClassVar[str] = "probe"
    allows_concurrent: ClassVar[bool] = False

    def __init__(self, agent: "PeekaAgent"):
        super().__init__()
        self.agent = agent

    def _runtime_meta_for_downgrade(self, startup_backend: str) -> Dict[str, Any]:
        """Build trace runtime downgrade metadata.

        Args:
            startup_backend: Backend selected at trace startup.

        Returns:
            Runtime metadata payload for downgraded trace execution.
        """
        return {
            "trace": {
                "startup_backend": startup_backend,
                "effective_backend": BACKEND_WRAPPER_ONLY,
                "downgraded": True,
                "downgrade_reason": "gevent_patched_runtime",
                "gevent_patched_now": True,
            }
        }

    def _supports_probe_instrumentation(self) -> bool:
        return hasattr(self.agent, "probe_registry") and hasattr(self.agent, "track_probe_context")

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = params.get("action", "start")

            if action == "start":
                return self._start_trace(params)
            elif action == "stop":
                return self._stop_trace(params)
            elif action == "status":
                return self._get_status(params)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _start_trace(self, params: Dict[str, Any]) -> Dict[str, Any]:
        params.pop("depth", None)  # silently ignore legacy depth param from TUI/old clients
        self.validate_params(params, ["pattern"])

        pattern = params["pattern"]
        trace_config = {
            "times": params.get("times", -1),
            "condition_express": params.get("condition_express")
                                 or params.get("condition"),
            "skip_builtin": params.get("skip_builtin", True),
            "min_duration": params.get("min_duration", 0),
            "command": "trace",  # mark this as trace command
        }
        response_config = dict(trace_config)
        gevent_state = probe()
        policy = get_policy("trace", gevent_state)
        meta = policy_meta(gevent_state, policy)

        probe_context = None
        if self._supports_probe_instrumentation():
            probe_context = ProbeContext(
                self.agent.probe_registry,
                target_id=self.agent._target_id_for_jobs(),
                client_session_id=params.get("client_session_id"),
                job_id=params.get("job_id"),
                type="trace",
                pattern=pattern,
                config=trace_config,
            )
            _ = probe_context.__enter__()
            trace_config["_probe_context"] = probe_context

        try:
            watch_id = self.agent.injector.inject_trace(
                pattern, trace_config, force_backend=policy.backend
            )
            if probe_context is not None:
                self.agent.track_probe_context(watch_id, probe_context, "trace")
            self.agent.observer.register_watch(watch_id, pattern, response_config)
            result = {
                "status": "success",
                "watch_id": watch_id,
                "pattern": pattern,
                "config": response_config,
                "meta": meta,
            }
            if policy.backend == BACKEND_WRAPPER_ONLY:
                result["runtime_meta"] = self._runtime_meta_for_downgrade(policy.backend)
            return result

        except ValueError as e:
            if probe_context is not None:
                probe_context.__exit__(*sys.exc_info())
            return {"status": "error", "error": str(e)}
        except Exception:
            if probe_context is not None:
                probe_context.__exit__(*sys.exc_info())
            raise

    def _stop_trace(self, params: Dict[str, Any]) -> Dict[str, Any]:
        watch_id = params.get("watch_id")

        if watch_id:
            try:
                result = self.agent.injector.uninject(watch_id)
                stats = self.agent.observer.unregister_watch(watch_id)
                if self._supports_probe_instrumentation():
                    self.agent.stop_probe_context(watch_id)
                return {
                    "status": "success",
                    "watch_id": watch_id,
                    "observation_count": result.get("count", 0),
                    "stats": stats,
                }
            except ValueError as e:
                return {"status": "error", "error": str(e)}
        else:
            count = self.agent.injector.uninject_all()
            self.agent.observer.clear_all()
            if self._supports_probe_instrumentation():
                self.agent.stop_probe_contexts_by_type(list(ProbeContext.injector_managed_streaming_types()))
            return {"status": "success", "stopped_count": count}

    def _get_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        watch_id = params.get("watch_id")

        if watch_id:
            watch_info = self.agent.injector.get_watch_info(watch_id)
            stats = self.agent.observer.get_watch_stats(watch_id)
            if watch_info:
                result = {"status": "success", "watch": watch_info, "stats": stats}
                runtime_meta = watch_info.get("runtime_meta") or watch_info.get(
                    "config", {}
                ).get("runtime_meta")
                if runtime_meta is not None:
                    result["runtime_meta"] = runtime_meta
                    result["meta"] = {"runtime_meta": runtime_meta}
                return result
            return {"status": "error", "error": f"Watch not found: {watch_id}"}

        watches = self.agent.injector.list_watches()
        all_stats = self.agent.observer.get_all_stats()

        return {
            "status": "success",
            "watches": watches,
            "stats": all_stats,
        }
