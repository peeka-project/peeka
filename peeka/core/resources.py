"""Centralized package resource resolver for peeka.core.

Single source of truth for all resources under peeka/core
(debugger scripts, injector templates, etc.).
"""

from pathlib import Path


class PeekaResourceError(RuntimeError):
    """Raised when a required peeka.core resource is missing."""


def core_resource_path(name: str) -> Path:
    """Return the Path for a resource under peeka/core.

    Does NOT check if the file exists.
    Use require_core_resource() when the resource must exist.
    """
    try:
        import importlib.resources as _ir

        ref = _ir.files("peeka.core") / name
        return Path(str(ref))
    except AttributeError:
        import peeka.core as _core

        return Path(_core.__file__).parent / name


def require_core_resource(name: str) -> Path:
    """Return the Path for an existing resource under peeka/core.

    Raises:
        PeekaResourceError: if the resource does not exist, with the
            resource name, resolved absolute path, and a hint.
    """
    path = core_resource_path(name)
    if not path.exists():
        raise PeekaResourceError(
            f"Peeka resource not found: {name!r} "
            f"(resolved to {path.resolve()}). "
            + "Check package-data configuration or wheel build."
        )
    return path
