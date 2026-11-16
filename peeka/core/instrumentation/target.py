"""Target resolution and function replacement helpers."""

import importlib
import inspect
import logging
import sys
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class InjectorTargetMixin:

    def _resolve_target(self, pattern: str) -> Optional[Tuple[Any, Any, Any]]:
        """
        Resolve pattern to (function, parent_object, attr_name).

        When the target process runs a script as ``python script.py``, the
        module is loaded as ``__main__`` rather than its filename-based name.
        This method detects that situation and transparently redirects
        resolution to ``__main__`` so that users can use the natural
        ``demo.Calculator.add`` pattern without needing to know about
        ``__main__``.

        Args:
            pattern: Dotted path like 'module.Class.method' or 'module.function'

        Returns:
            Tuple of (target_func, parent_obj, attr_name) or None if not found
        """
        parts = pattern.split(".")
        if len(parts) < 2:
            return None

        # Try progressively shorter module prefixes
        for i in range(len(parts) - 1, 0, -1):
            module_name = ".".join(parts[:i])
            attrs = parts[i:]

            # Try to get module from sys.modules first (already imported)
            module = sys.modules.get(module_name)

            if module is None:
                # Try to import it
                try:
                    module = importlib.import_module(module_name)
                except (ImportError, ModuleNotFoundError):
                    continue

            # When a script runs as ``python script.py``, its module lives
            # under ``__main__`` in sys.modules.  If we resolved the module
            # via import (or from sys.modules under a non-__main__ name),
            # the classes/functions we patch there will be *different objects*
            # from the ones the running code actually uses.  Detect this by
            # comparing __file__ paths and prefer __main__ when they match.
            main_module = sys.modules.get("__main__")
            if (
                main_module is not None
                and module is not main_module
                and hasattr(module, "__file__")
                and hasattr(main_module, "__file__")
                and module.__file__
                and main_module.__file__
            ):
                try:
                    from pathlib import Path

                    if (
                        Path(module.__file__).resolve()
                        == Path(main_module.__file__).resolve()
                    ):
                        module = main_module
                except (OSError, TypeError):
                    pass

            # Navigate to the target
            obj = module
            parent = None
            attr_name = None

            for j, attr in enumerate(attrs):
                parent = obj
                attr_name = attr
                try:
                    raw_attr = inspect.getattr_static(obj, attr) if inspect.isclass(obj) else None
                    if j == len(attrs) - 1 and isinstance(raw_attr, (staticmethod, classmethod)):
                        obj = raw_attr.__func__
                    else:
                        obj = getattr(obj, attr)
                except AttributeError:
                    obj = None
                    break

            if obj is not None and callable(obj):
                return (obj, parent, attr_name)

        return None

    def _inspect_descriptor(
        self, parent_obj: Any, attr_name: str
    ) -> Tuple[Optional[str], Any, bool]:
        """Inspect a descriptor, retaining the original slot metadata for stacks."""
        if not inspect.isclass(parent_obj):
            return None, None, False
        raw = inspect.getattr_static(parent_obj, attr_name)
        kind = (
            "staticmethod" if isinstance(raw, staticmethod)
            else "classmethod" if isinstance(raw, classmethod) else None
        )
        for info in self.instrumented.values():
            if info["parent"] is parent_obj and info["attr_name"] == attr_name:
                return (
                    info.get("root_descriptor_kind", info.get("descriptor_kind", kind)),
                    info.get("root_raw_descriptor", info.get("raw_descriptor", raw)),
                    info.get("root_defined_in_dict", info.get("defined_in_dict", True)),
                )
        return kind, raw, attr_name in parent_obj.__dict__

    def _replace_function(
        self, parent_obj: Any, attr_name: str, new_func: Callable[..., Any],
        descriptor_kind: Optional[str] = None,
    ) -> None:
        """Replace a callable while preserving its descriptor binding."""
        if not isinstance(new_func, (staticmethod, classmethod)):
            if descriptor_kind == "staticmethod":
                new_func = staticmethod(new_func)
            elif descriptor_kind == "classmethod":
                new_func = classmethod(new_func)
        setattr(parent_obj, attr_name, new_func)

    def _restore_target_attribute(self, info: Dict[str, Any]) -> None:
        """Restore the original descriptor, removing inherited-slot overrides."""
        if info.get("descriptor_kind") in ("staticmethod", "classmethod") and inspect.isclass(info["parent"]):
            if info.get("defined_in_dict", True):
                setattr(info["parent"], info["attr_name"], info.get("raw_descriptor", info["original"]))
            else:
                delattr(info["parent"], info["attr_name"])
        else:
            self._replace_function(info["parent"], info["attr_name"], info["original"])

    def _find_module_aliases(
        self, target_func: Callable[..., Any], parent: Any, attr_name: str
    ) -> List[Dict[str, Any]]:
        """
        Find module-level globals that cache the same function object.

        Frameworks often resolve ``module.func`` once and store the function in
        a long-lived global such as ``handler``. Replacing only the canonical
        attribute would leave those cached aliases pointing at the original
        function, so calls through the framework would bypass the watch wrapper.
        """
        aliases: List[Dict[str, Any]] = []
        seen = set()

        for module in list(sys.modules.values()):
            namespace = getattr(module, "__dict__", None)
            if not isinstance(namespace, dict):
                continue

            module_name = getattr(module, "__name__", None)
            for name, value in list(namespace.items()):
                if value is not target_func:
                    continue
                if module is parent and name == attr_name:
                    continue

                key = (id(module), name)
                if key in seen:
                    continue
                seen.add(key)

                label = f"{module_name}.{name}" if module_name else name
                aliases.append({"parent": module, "attr_name": name, "label": label})

        return aliases

    def _replace_aliases(
        self, aliases: List[Dict[str, Any]], wrapper: Callable[..., Any]
    ) -> None:
        """Replace cached module-global aliases on a best-effort basis."""
        for alias in aliases:
            try:
                setattr(alias["parent"], alias["attr_name"], wrapper)
            except Exception:
                logger.debug(
                    "Best-effort alias replacement failed for %s",
                    alias.get("label", "<unknown>"),
                    exc_info=True,
                )

    def _restore_aliases(self, info: Dict[str, Any]) -> None:
        """Restore cached aliases if they still point at this watch wrapper."""
        wrapper = info.get("wrapper")
        original = info.get("original")
        for alias in info.get("aliases", []):
            try:
                parent = alias["parent"]
                attr_name = alias["attr_name"]
                if getattr(parent, attr_name, None) is wrapper:
                    setattr(parent, attr_name, original)
            except Exception:
                logger.debug(
                    "Best-effort alias restoration failed for %s",
                    alias.get("label", "<unknown>"),
                    exc_info=True,
                )
