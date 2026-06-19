"""Lifecycle cleanup helpers for resource-owning command handlers."""

from typing import Any, Dict, List, Optional


__all__ = ["stop_resource_owners_for_detach", "stop_resource_owners_for_reset"]


def stop_resource_owners_for_detach(agent: Any, logger: Any) -> Dict[str, Any]:
    """Stop monitor and top resources before detach teardown.

    Args:
        agent: Agent-like object with an optional command_handlers mapping.
        logger: Logger-like object used for per-handler cleanup failures.

    Returns:
        Structured cleanup summary with stopped handler names and errors.
    """
    handlers = getattr(agent, "command_handlers", {})
    handlers_stopped: List[str] = []
    errors: List[Dict[str, Any]] = []

    for name in ["monitor", "top"]:
        handler = handlers.get(name)
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
    handlers = getattr(agent, "command_handlers", {})
    handlers_stopped: List[str] = []
    errors: List[Dict[str, Any]] = []

    handler = handlers.get("monitor")
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
