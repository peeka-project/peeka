"""
Complete Command - Provides code completion data.

This command introspects the target process's modules to provide
auto-completion suggestions for module names, class names, and function names.
"""

import sys
from typing import Any, ClassVar, Dict, List

from peeka.commands.base import BaseCommand


class CompleteCommand(BaseCommand):
    """Provides completion suggestions by introspecting sys.modules."""

    category: ClassVar[str] = "snapshot"
    allows_concurrent: ClassVar[bool] = True

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the complete command.

        Args:
            params: {
                "prefix": str - The prefix to complete
                "type": str - "modules", "classes", "functions", or "all"
                "limit": int - Maximum number of results (default 100)
            }

        Returns:
            {
                "status": "success",
                "data": {
                    "completions": List[str],
                    "prefix": str
                }
            }
        """
        prefix = params.get("prefix", "")
        comp_type = params.get("type", "all")
        limit = params.get("limit", 100)

        completions = []

        if not prefix:
            # Return top-level module names + __main__ attributes as shortcuts
            completions = self._get_top_modules(limit)
        elif "." in prefix:
            # Complete within a module/class
            completions = self._get_nested_completions(prefix, comp_type, limit)
        else:
            # Complete module names + search __main__ attributes
            completions = self._get_module_completions(prefix, comp_type, limit)

        return {
            "status": "success",
            "data": {
                "completions": completions[:limit],
                "prefix": prefix,
            },
        }

    def _get_top_modules(self, limit: int) -> List[str]:
        """Get top-level module names including __main__."""
        modules = set()
        for name in sys.modules:
            if not name.startswith("_"):
                top = name.split(".")[0]
                modules.add(top)
        # Always include __main__ — it's the user's code
        if "__main__" in sys.modules:
            modules.add("__main__")
        result = sorted(modules)
        # Put __main__ first since it's most relevant
        if "__main__" in result:
            result.remove("__main__")
            result.insert(0, "__main__")
        return result[:limit]

    def _get_module_completions(
        self, prefix: str, comp_type: str, limit: int
    ) -> List[str]:
        """Get module names matching prefix + __main__ attributes as shortcuts."""
        prefix_lower = prefix.lower()
        matches = []

        # Match top-level module names
        for name in sys.modules:
            if not name.startswith("_"):
                top = name.split(".")[0]
                if top.lower().startswith(prefix_lower):
                    matches.append(top)

        # Include __main__ if it matches
        if "__main__".startswith(prefix_lower) and "__main__" in sys.modules:
            matches.append("__main__")

        # Also search __main__ attributes — users often type function/class
        # names directly (e.g. "Calc" to find __main__.Calculator)
        main_mod = sys.modules.get("__main__")
        if main_mod is not None:
            try:
                for attr_name in dir(main_mod):
                    if attr_name.startswith("_"):
                        continue
                    if attr_name.lower().startswith(prefix_lower):
                        full_name = f"__main__.{attr_name}"
                        if comp_type != "all":
                            try:
                                attr = getattr(main_mod, attr_name)
                                if comp_type == "classes" and not isinstance(attr, type):
                                    continue
                                if comp_type == "functions" and not callable(attr):
                                    continue
                            except Exception:
                                continue
                        matches.append(full_name)
            except Exception:
                pass

        return sorted(set(matches))[:limit]

    def _get_nested_completions(
        self, prefix: str, comp_type: str, limit: int
    ) -> List[str]:
        """Get completions for nested paths (module.attr or module.Class.method)."""
        parts = prefix.rsplit(".", 1)
        base_path = parts[0]
        partial = parts[1] if len(parts) > 1 else ""
        partial_lower = partial.lower()

        completions = []

        # Try to get the base object
        obj = self._resolve_path(base_path)
        if obj is None:
            return []

        # Get attributes
        try:
            for attr_name in dir(obj):
                if attr_name.startswith("_"):
                    continue
                if partial and not attr_name.lower().startswith(partial_lower):
                    continue

                full_name = f"{base_path}.{attr_name}"

                # Filter by type if requested
                if comp_type != "all":
                    try:
                        attr = getattr(obj, attr_name)
                        if comp_type == "classes" and not isinstance(attr, type):
                            continue
                        if comp_type == "functions" and not callable(attr):
                            continue
                    except Exception:
                        continue

                completions.append(full_name)

        except Exception:
            pass

        return sorted(completions)[:limit]

    def _resolve_path(self, path: str) -> Any:
        """Resolve a dotted path to an object."""
        parts = path.split(".")

        # Try to find in sys.modules first
        for i in range(len(parts), 0, -1):
            module_path = ".".join(parts[:i])
            if module_path in sys.modules:
                obj = sys.modules[module_path]
                # Navigate remaining parts
                for attr_name in parts[i:]:
                    try:
                        obj = getattr(obj, attr_name)
                    except AttributeError:
                        return None
                return obj

        return None
