"""Lifecycle cleanup helpers for resource-owning command handlers."""

from typing import Any, Dict, List, Optional


__all__ = ["stop_resource_owners_for_detach", "stop_resource_owners_for_reset"]


def _resolve_handler(agent: Any, name: str) -> Any:
    """Return the already-instantiated handler for *name* without lazy creation.

    Checks ``agent.command_handlers[name]`` first, then falls back to
    ``agent.<name>_cmd`` for legacy test fixtures that set the attribute
    directly (e.g. ``agent.monitor_cmd = MonitorCommand(agent)``).
    """
    handlers = getattr(agent, "command_handlers", {})
    handler = handlers.get(name)
    if handler is not None:
        return handler
    # Legacy/test-fixture fallback: some tests set agent.monitor_cmd directly
    # without populating command_handlers.
    return getattr(agent, f"{name}_cmd", None)


def stop_resource_owners_for_detach(agent: Any, logger: Any) -> Dict[str, Any]:
    """Stop monitor and top resources before detach teardown.

    Args:
        agent: Agent-like object with an optional command_handlers mapping.
        logger: Logger-like object used for per-handler cleanup failures.

    Returns:
        Structured cleanup summary with stopped handler names and errors.
    """
    handlers_stopped: List[str] = []
    errors: List[Dict[str, Any]] = []

    for name in ["monitor", "top"]:
        handler = _resolve_handler(agent, name)
        stop_active_resources = getattr(handler, "stop_active_resources", None)
        if handler is None or not callable(stop_active_resources):
            continue

        try:
            _ = stop_active_resources(pattern=None, reason="detach")
            handlers_stopped.append(name)
        except Exception as exc:
            logger.error(
                "[peeka Lifecycle] %s resource cleanup failed during detach",
                name,
                exc_info=True,
            )
            errors.append({"handler": name, "error": str(exc)})

    return {"handlers_stopped": handlers_stopped, "errors": errors}


def stop_resource_owners_for_reset(
    agent: Any, pattern: Optional[str], logger: Any
) -> Dict[str, Any]:
    """Stop monitor resources matching *pattern* before reset teardown.

    Args:
        agent: Agent-like object with an optional command_handlers mapping.
        pattern: Optional function pattern to pass to monitor cleanup.
        logger: Logger-like object used for per-handler cleanup failures.

    Returns:
        Structured cleanup summary with stopped handler names and errors.
    """
    handlers_stopped: List[str] = []
    errors: List[Dict[str, Any]] = []

    handler = _resolve_handler(agent, "monitor")
    stop_active_resources = getattr(handler, "stop_active_resources", None)
    if handler is not None and callable(stop_active_resources):
        try:
            _ = stop_active_resources(pattern=pattern, reason="reset")
            handlers_stopped.append("monitor")
        except Exception as exc:
            logger.error(
                "[peeka Lifecycle] monitor resource cleanup failed during reset",
                exc_info=True,
            )
            errors.append({"handler": "monitor", "error": str(exc)})

    return {"handlers_stopped": handlers_stopped, "errors": errors}
