"""
Trace Command - Trace function call paths and execution time
Similar to Arthas 'trace' command
"""

from typing import Any, Dict, TYPE_CHECKING

from peeka.commands.base import BaseCommand
from peeka.core.runtime.compat import get_policy, policy_meta
from peeka.core.runtime.gevent_probe import probe

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class TraceCommand(BaseCommand):
    """
    Trace command - traces function call tree and timing (Arthas-compatible)

    Usage:
        trace <module.class.method> [-d depth] [-n times] [--condition expr] [--skip-builtin] [--min-duration ms]

    Parameters:
        -d, --depth: Trace depth (max call levels, default: 3)
        -n, --times: Observation limit, -1 for unlimited (default: -1)
        --condition: Filter expression (e.g., "cost > 50")
        --skip-builtin: Skip built-in functions and standard library (default: True)
        --min-duration: Minimum duration in ms to record child calls (default: 0)

    Examples:
        trace mymodule.MyClass.my_method
        trace mymodule.my_function -d 5 -n 10
        trace mymodule.func --condition "cost > 50"
        trace mymodule.func --skip-builtin=false
        trace mymodule.func --min-duration 10
    """

    def __init__(self, agent: "PeekaAgent"):
        super().__init__()
        self.agent = agent

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
        self.validate_params(params, ["pattern"])

        pattern = params["pattern"]
        trace_config = {
            "depth": params.get("depth", 3),
            "trace_depth": params.get("depth", 3),  # for trace-specific depth
            "times": params.get("times", -1),
            "condition_express": params.get("condition_express")
                                 or params.get("condition"),
            "skip_builtin": params.get("skip_builtin", True),
            "min_duration": params.get("min_duration", 0),
            "command": "trace",  # mark this as trace command
        }
        gevent_state = probe()
        policy = get_policy("trace", gevent_state)
        meta = policy_meta(gevent_state, policy)

        try:
            watch_id = self.agent.injector.inject_trace(
                pattern, trace_config, force_backend=policy.backend
            )
            self.agent.observer.register_watch(watch_id, pattern, trace_config)

            return {
                "status": "success",
                "watch_id": watch_id,
                "pattern": pattern,
                "config": trace_config,
                "meta": meta,
            }

        except ValueError as e:
            return {"status": "error", "error": str(e)}

    def _stop_trace(self, params: Dict[str, Any]) -> Dict[str, Any]:
        watch_id = params.get("watch_id")

        if watch_id:
            try:
                result = self.agent.injector.uninject(watch_id)
                stats = self.agent.observer.unregister_watch(watch_id)
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
