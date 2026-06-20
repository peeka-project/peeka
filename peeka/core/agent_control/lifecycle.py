"""Lifecycle cleanup helpers for resource-owning command handlers."""

from typing import Any, Dict, List, Optional

from peeka.commands.resource_owning import CleanupScope, ResourceOwningCommand


__all__ = ["stop_resource_owners_for_detach", "stop_resource_owners_for_reset"]


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
