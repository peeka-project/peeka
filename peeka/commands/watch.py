"""
Watch Command - Monitor function calls and return values
Similar to Arthas 'watch' command
"""

import sys
from typing import Any, ClassVar, Dict, TYPE_CHECKING

from peeka.commands.base import BaseCommand
from peeka.core.probes import ProbeContext
from peeka.core.instrumentation.watch import build_runtime_meta

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class WatchCommand(BaseCommand):
    is_resource_owner = False  # explicit; not a resource owner
    """
    Watch command - monitors function execution (Arthas-compatible)

    Usage:
        watch <module.class.method> [-x depth] [-n times] [--condition expr] [-b] [-e] [-s] [-f]

    Parameters:
        -x, --depth: Output depth (default: 2)
        -n, --times: Observation limit, -1 for unlimited (default: -1)
        --condition: Filter expression (e.g., "params[0] > 100" or "cost > 50")
        -b, --before: Observe before function execution (AtEnter)
        -e, --exception: Observe on exception (AtExceptionExit)
        -s, --success: Observe on success (AtExit)
        -f, --finish: Observe both success and exception (default: true)

    Examples:
        watch mymodule.MyClass.my_method
        watch mymodule.my_function -x 2 -n 5
        watch mymodule.func --condition "params[0] > 100"
        watch mymodule.func -b -s
        watch mymodule.func -e
        watch mymodule.func --condition "cost > 50"
    """

    category: ClassVar[str] = "probe"
    allows_concurrent: ClassVar[bool] = False

    def __init__(self, agent: "PeekaAgent"):
        super().__init__()
        self.agent = agent

    def _supports_probe_instrumentation(self) -> bool:
        return hasattr(self.agent, "probe_registry") and hasattr(self.agent, "track_probe_context")

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            action = params.get("action", "start")

            if action == "start":
                return self._start_watch(params)
            elif action == "stop":
                return self._stop_watch(params)
            elif action == "status":
                return self._get_status(params)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _start_watch(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self.validate_params(params, ["pattern"])

        pattern = params["pattern"]
        watch_config = {
            "depth": params.get("depth", 2),
            "times": params.get("times", -1),
            "condition_express": params.get("condition_express")
                                 or params.get("condition"),
            "before": params.get("before", False),
            "exception": params.get("exception", False),
            "success": params.get("success", False),
            "finish": params.get("finish", True),
            "client_session_id": params.get("client_session_id"),
            "watch_orphan_grace_seconds": params.get("watch_orphan_grace_seconds"),
        }
        response_config = dict(watch_config)

        probe_context = None
        if self._supports_probe_instrumentation():
            probe_context = ProbeContext(
                self.agent.probe_registry,
                target_id=self.agent._target_id_for_jobs(),
                client_session_id=params.get("client_session_id"),
                job_id=params.get("job_id"),
                type="watch",
                pattern=pattern,
                config=watch_config,
            )
            _ = probe_context.__enter__()
            watch_config["_probe_context"] = probe_context

        try:
            watch_id = self.agent.injector.inject(pattern, watch_config)
            if probe_context is not None:
                self.agent.track_probe_context(watch_id, probe_context, "watch")
            self.agent.observer.register_watch(watch_id, pattern, response_config)
            watch_info = self.agent.injector.get_watch_info(watch_id) or {}

            return {
                "status": "success",
                "watch_id": watch_id,
                "pattern": pattern,
                "config": response_config,
                "runtime_meta": build_runtime_meta(),
                "target": {
                    "is_coroutine_function": watch_info.get(
                        "is_coroutine_function", False
                    ),
                    "alias_count": watch_info.get("alias_count", 0),
                    "aliases": watch_info.get("aliases", []),
                },
            }

        except ValueError as e:
            if probe_context is not None:
                probe_context.__exit__(*sys.exc_info())
            return {"status": "error", "error": str(e)}
        except Exception:
            if probe_context is not None:
                probe_context.__exit__(*sys.exc_info())
            raise

    def _stop_watch(self, params: Dict[str, Any]) -> Dict[str, Any]:
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
                self.agent.stop_probe_contexts_by_type(["watch", "trace", "stack"])
            return {"status": "success", "stopped_count": count}

    def _get_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        watch_id = params.get("watch_id")

        if watch_id:
            watch_info = self.agent.injector.get_watch_info(watch_id)
            stats = self.agent.observer.get_watch_stats(watch_id)
            if watch_info:
                return {"status": "success", "watch": watch_info, "stats": stats}
            return {"status": "error", "error": f"Watch not found: {watch_id}"}

        watches = self.agent.injector.list_watches()
        all_stats = self.agent.observer.get_all_stats()

        return {
            "status": "success",
            "watches": watches,
            "stats": all_stats,
        }
