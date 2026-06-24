"""Lifecycle cleanup helpers for resource-owning command handlers."""

from typing import Any, Dict, List, Optional

from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand


__all__ = [
    "shutdown_agent_resources",
    "stop_resource_owners_for_detach",
    "stop_resource_owners_for_reset",
    "_has_cleanup_errors",
    "_collect_cleanup_errors",
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
        Structured shutdown summary with completed step names, step-level errors,
        and a ``resource_owners`` sub-summary from the resource-owner cleanup step.
    """
    steps_run: List[str] = []
    step_errors: Dict[str, str] = {}
    resource_owners_summary: Dict[str, Any] = {"handlers_stopped": [], "errors": []}
    probe_contexts_summary: Dict[str, Any] = {"errors": []}

    def run_step(step_name: str, step_callable: Any) -> Optional[Any]:
        try:
            result = step_callable()
            steps_run.append(step_name)
            return result
        except Exception as exc:
            logger.error(
                "[peeka Shutdown] step %s failed: %s",
                step_name,
                exc,
                exc_info=True,
            )
            step_errors[step_name] = str(exc)
            return None

    resource_owners_result = run_step(
        "stop_resource_owners",
        lambda: stop_resource_owners_for_detach(agent, logger),
    )
    if isinstance(resource_owners_result, dict):
        resource_owners_summary = resource_owners_result

    probe_contexts_result = run_step(
        "stop_probe_contexts", lambda: agent.stop_probe_contexts_by_type(probe_types)
    )
    if isinstance(probe_contexts_result, dict):
        exit_errors = probe_contexts_result.get("exit_errors", [])
        if isinstance(exit_errors, list):
            probe_contexts_summary["errors"] = exit_errors

    run_step("uninject_all", agent.injector.uninject_all)
    run_step("clear_all", agent.observer.clear_all)
    run_step(
        "probe_registry_sweep",
        lambda: agent.probe_registry.cleanup(
            older_than_seconds=0, completed_only=True
        ),
    )
    run_step(
        "orphan_watch_sweep",
        lambda: agent.injector.cleanup_orphan_watches(),
    )

    return {
        "steps_run": steps_run,
        "step_errors": step_errors,
        "resource_owners": resource_owners_summary,
        "probe_contexts": probe_contexts_summary,
    }


def stop_resource_owners_for_detach(agent: Any, logger: Any) -> Dict[str, Any]:
    """Stop resource-owning command resources before detach teardown.

    Args:
        agent: Agent-like object with an optional command_handlers mapping.
        logger: Logger-like object used for per-handler cleanup failures.

    Returns:
        Structured cleanup summary with stopped handler names and errors.
        Per-handler errors include both exceptions raised by stop_active_resources
        and error entries returned inside the result dict.
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
            result = handler.stop_active_resources(pattern=None, reason="detach")
            handlers_stopped.append(handler_name)
            # Surface per-handler errors returned inside the result dict.
            if isinstance(result, dict):
                returned_errors = result.get("errors") or []
                if isinstance(returned_errors, list) and returned_errors:
                    for entry in returned_errors:
                        if isinstance(entry, dict):
                            errors.append(entry)
                        else:
                            errors.append({"handler": handler_name, "error": str(entry)})
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
        Per-handler errors include both exceptions raised by stop_active_resources
        and error entries returned inside the result dict.
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
            result = handler.stop_active_resources(pattern=pattern, reason="reset")
            handlers_stopped.append(handler_name)
            # Surface per-handler errors returned inside the result dict.
            if isinstance(result, dict):
                returned_errors = result.get("errors") or []
                if isinstance(returned_errors, list) and returned_errors:
                    for entry in returned_errors:
                        if isinstance(entry, dict):
                            errors.append(entry)
                        else:
                            errors.append({"handler": handler_name, "error": str(entry)})
        except Exception as exc:
            logger.error(
                "[peeka Lifecycle] %s resource cleanup failed during reset",
                handler_name,
                exc_info=True,
            )
            errors.append({"handler": handler_name, "error": str(exc)})

    return {"handlers_stopped": handlers_stopped, "errors": errors}


def _has_cleanup_errors(cleanup_summary: Dict[str, Any]) -> bool:
    """Return True if any cleanup layer reported errors."""
    if not isinstance(cleanup_summary, dict):
        return False
    step_errors = cleanup_summary.get("step_errors", {})
    if step_errors:
        return True
    layers = ("resource_owners", "probe_contexts", "injector")
    for layer in layers:
        layer_summary = cleanup_summary.get(layer, {})
        if not isinstance(layer_summary, dict):
            continue
        errors = layer_summary.get("errors", [])
        if isinstance(errors, list) and errors:
            return True
    return False


def _collect_cleanup_errors(cleanup_summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return combined error list from all cleanup layers."""
    if not isinstance(cleanup_summary, dict):
        return []
    result: List[Dict[str, Any]] = []
    layers = ("resource_owners", "probe_contexts", "injector")
    for layer in layers:
        layer_summary = cleanup_summary.get(layer, {})
        if not isinstance(layer_summary, dict):
            continue
        errors = layer_summary.get("errors", [])
        if isinstance(errors, list):
            result.extend(e for e in errors if isinstance(e, dict))
    return result
