"""
Stack Command - Print call stack when function is invoked
Similar to Arthas 'stack' command
"""

import sys
from typing import Any, ClassVar, Dict, TYPE_CHECKING

from peeka.commands.base import BaseCommand
from peeka.core.probes import ProbeContext

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class StackCommand(BaseCommand):
    """
    Stack command - captures call trace when function is invoked (Arthas-compatible)

    Usage:
        stack <module.class.method> [-n times] [--condition expr] [--depth stack_depth]

    Parameters:
        -n, --times: Observation limit, -1 for unlimited (default: -1)
        --condition: Filter expression (e.g., "params[0] > 100")
        --depth: Stack trace depth limit (default: 10)

    Examples:
        stack mymodule.MyClass.my_method
        stack mymodule.my_function --depth 5
        stack mymodule.func -n 3 --condition "params[0] > 100"
    """

    category: ClassVar[str] = "snapshot"
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
                return self._start_stack(params)
            elif action == "stop":
                return self._stop_stack(params)
            elif action == "status":
                return self._get_status(params)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _start_stack(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self.validate_params(params, ["pattern"])

        pattern = params["pattern"]
        stack_depth = params.get("depth", 10)

        if stack_depth < 0:
            return {"status": "error", "error": "Stack depth must be non-negative"}

        watch_config = {
            "depth": 2,
            "times": params.get("times", -1),
            "condition_express": params.get("condition_express")
            or params.get("condition"),
            "before": True,
            "success": False,
            "exception": False,
            "finish": False,
            "stack_depth": stack_depth,
        }
        response_config = dict(watch_config)

        probe_context = None
        if self._supports_probe_instrumentation():
            probe_context = ProbeContext(
                self.agent.probe_registry,
                target_id=self.agent._target_id_for_jobs(),
                client_session_id=params.get("client_session_id"),
                job_id=params.get("job_id"),
                type="stack",
                pattern=pattern,
                config=watch_config,
            )
            _ = probe_context.__enter__()
            watch_config["_probe_context"] = probe_context

        try:
            watch_id = self.agent.injector.inject(pattern, watch_config)
            if probe_context is not None:
                self.agent.track_probe_context(watch_id, probe_context, "stack")
            self.agent.observer.register_watch(watch_id, pattern, response_config)

            return {
                "status": "success",
                "watch_id": watch_id,
                "pattern": pattern,
                "config": response_config,
            }

        except ValueError as e:
            if probe_context is not None:
                probe_context.__exit__(*sys.exc_info())
            return {"status": "error", "error": str(e)}
        except Exception:
            if probe_context is not None:
                probe_context.__exit__(*sys.exc_info())
            raise

    def _stop_stack(self, params: Dict[str, Any]) -> Dict[str, Any]:
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
