"""Lifecycle cleanup helpers for resource-owning command handlers."""

from typing import Any, Dict, List, Optional

from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand


__all__ = [
    "shutdown_agent_resources",
    "stop_resource_owners_for_detach",
    "stop_resource_owners_for_reset",
]


def shutdown_agent_resources(
    agent: Any, logger: Any, probe_types: List[str]
) -> Dict[str, Any]:
    """Run isolated agent resource shutdown steps.

    Args:
        agent: Agent-like object with resource, probe, injector, and observer hooks.
        logger: Logger-like object used for per-step cleanup failures.
        probe_types: Probe context types to stop during shutdown.

    Returns:
        Structured shutdown summary with completed step names and errors by step.
    """
    steps_run: List[str] = []
    errors: Dict[str, Any] = {}

    def run_step(step_name: str, step_callable: Any) -> None:
        try:
            _ = step_callable()
            steps_run.append(step_name)
        except Exception as exc:
            logger.error(
                "[peeka Shutdown] step %s failed: %s",
                step_name,
                exc,
                exc_info=True,
            )
            errors[step_name] = str(exc)

    run_step(
        "stop_resource_owners",
        lambda: stop_resource_owners_for_detach(agent, logger),
    )
    run_step("stop_probe_contexts", lambda: agent.stop_probe_contexts_by_type(probe_types))
    run_step("uninject_all", agent.injector.uninject_all)
    run_step("clear_all", agent.observer.clear_all)
    if not hasattr(agent, "calls"):
        run_step(
            "probe_registry_sweep",
            lambda: agent.probe_registry.cleanup(
                older_than_seconds=0, completed_only=True
            ),
        )

    return {"steps_run": steps_run, "errors": errors}


def stop_resource_owners_for_detach(agent: Any, logger: Any) -> Dict[str, Any]:
    """Stop resource-owning command resources before detach teardown.

    Args:
        agent: Agent-like object with an optional command_handlers mapping.
        logger: Logger-like object used for per-handler cleanup failures.

    Returns:
        Structured cleanup summary with stopped handler names and errors.
    """
    handlers_stopped: List[str] = []
    errors: List[Dict[str, Any]] = []
    handlers = getattr(agent, "command_handlers", {}) or {}
    snapshot = list(handlers.values())

    for handler in snapshot:
        if not isinstance(handler, ResourceOwningCommand):
            continue
        if handler.cleanup_scope not in (
            CleanupScope.DETACH_ONLY,
            CleanupScope.DETACH_AND_RESET,
        ):
            continue
        handler_name = type(handler).__name__

        try:
            _ = handler.stop_active_resources(pattern=None, reason="detach")
            handlers_stopped.append(handler_name)
        except Exception as exc:
            logger.error(
                "[peeka Lifecycle] %s resource cleanup failed during detach",
                handler_name,
                exc_info=True,
            )
            errors.append({"handler": handler_name, "error": str(exc)})

    return {"handlers_stopped": handlers_stopped, "errors": errors}


def stop_resource_owners_for_reset(
    agent: Any, pattern: Optional[str], logger: Any
) -> Dict[str, Any]:
    """Stop reset-scoped resource-owning command resources before reset teardown.

    Args:
        agent: Agent-like object with an optional command_handlers mapping.
        pattern: Optional function pattern to pass to resource cleanup.
        logger: Logger-like object used for per-handler cleanup failures.

    Returns:
        Structured cleanup summary with stopped handler names and errors.
    """
    handlers_stopped: List[str] = []
    errors: List[Dict[str, Any]] = []
    handlers = getattr(agent, "command_handlers", {}) or {}
    snapshot = list(handlers.values())

    for handler in snapshot:
        if not isinstance(handler, ResourceOwningCommand):
            continue
        if handler.cleanup_scope != CleanupScope.DETACH_AND_RESET:
            continue
        handler_name = type(handler).__name__

        try:
            _ = handler.stop_active_resources(pattern=pattern, reason="reset")
            handlers_stopped.append(handler_name)
        except Exception as exc:
            logger.error(
                "[peeka Lifecycle] %s resource cleanup failed during reset",
                handler_name,
                exc_info=True,
            )
            errors.append({"handler": handler_name, "error": str(exc)})

    return {"handlers_stopped": handlers_stopped, "errors": errors}
