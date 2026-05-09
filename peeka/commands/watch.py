"""
Watch Command - Monitor function calls and return values
Similar to Arthas 'watch' command
"""

from typing import Any, Dict, TYPE_CHECKING

from peeka.commands.base import BaseCommand

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class WatchCommand(BaseCommand):
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

    def __init__(self, agent: "PeekaAgent"):
        super().__init__()
        self.agent = agent

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
        }

        try:
            watch_id = self.agent.injector.inject(pattern, watch_config)
            self.agent.observer.register_watch(watch_id, pattern, watch_config)
            watch_info = self.agent.injector.get_watch_info(watch_id) or {}

            return {
                "status": "success",
                "watch_id": watch_id,
                "pattern": pattern,
                "config": watch_config,
                "target": {
                    "is_coroutine_function": watch_info.get(
                        "is_coroutine_function", False
                    ),
                    "alias_count": watch_info.get("alias_count", 0),
                    "aliases": watch_info.get("aliases", []),
                },
            }

        except ValueError as e:
            return {"status": "error", "error": str(e)}

    def _stop_watch(self, params: Dict[str, Any]) -> Dict[str, Any]:
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
