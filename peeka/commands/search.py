"""
Search Commands - Discover classes and methods in loaded modules

Provides sc (search class) and sm (search method) commands for exploring
available classes and methods at runtime, similar to Arthas 'sc' command.
"""

import sys
import inspect
import fnmatch
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from peeka.commands.base import BaseCommand

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class SearchClassCommand(BaseCommand):
    """
    Search Class command - discovers classes in loaded modules (Arthas-compatible)

    Usage:
        sc <pattern> [-d]

    Parameters:
        pattern: Module/class pattern (e.g., "module.*", "module.Class*", "*Command")
        -d, --details: Show detailed info (module path, file, docstring)
        --limit: Max results (default: 50)

    Examples:
        sc "json.*"
        sc "collections.OrderedDict"
        sc "*Command" -d
    """

    def __init__(self, agent: Optional["PeekaAgent"] = None):
        super().__init__()
        self.agent = agent

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute search class command."""
        try:
            pattern = params.get("pattern", "").strip()

            # Validate pattern
            if not pattern:
                return {"status": "error", "error": "Pattern cannot be empty"}

            details = params.get("details", False)
            limit = params.get("limit", 50)

            classes = self._search_classes(pattern, details, limit)

            return {
                "status": "success",
                "classes": classes,
                "count": len(classes),
                "limit": limit,
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _search_classes(
        self, pattern: str, details: bool = False, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Search for classes matching pattern.

        Pattern format:
        - "module.*" - all classes in module
        - "module.Class" - specific class
        - "module.Class*" - classes starting with prefix
        - "*Command" - classes matching wildcard

        Returns:
            List of class info dicts with name and optional details
        """
        results: List[Dict[str, Any]] = []

        # Parse pattern to extract module and class patterns
        parts = pattern.split(".")

        # Handle different pattern formats
        if len(parts) == 1:
            # Pattern like "*Command" - search all modules
            module_pattern = "*"
            class_pattern = parts[0]
        else:
            # Pattern like "module.Class" or "module.*"
            module_pattern = ".".join(parts[:-1])
            class_pattern = parts[-1]

        # Iterate through loaded modules
        for module_name, module in list(sys.modules.items()):
            if module is None:
                continue

            # Match module pattern
            if not fnmatch.fnmatch(module_name, module_pattern):
                continue

            # Get all classes in this module
            try:
                members = inspect.getmembers(module, inspect.isclass)
            except Exception:
                # Skip modules that can't be inspected
                continue

            for class_name, class_obj in members:
                # Match class pattern
                if not fnmatch.fnmatch(class_name, class_pattern):
                    continue

                full_name = f"{module_name}.{class_name}"
                class_info = {"name": full_name}

                if details:
                    class_info.update(self._get_class_details(class_obj, module))

                results.append(class_info)

                if len(results) >= limit:
                    return results

        return results

    def _get_class_details(self, class_obj: type, module: Any) -> Dict[str, Any]:
        """Get detailed information about a class."""
        details: Dict[str, Any] = {}

        # Module path
        details["module"] = module.__name__

        # File location
        try:
            file_path = inspect.getfile(class_obj)
            details["file"] = file_path
        except Exception:
            details["file"] = None

        # Docstring
        docstring = inspect.getdoc(class_obj)
        details["docstring"] = docstring if docstring else None

        return details


class SearchMethodCommand(BaseCommand):
    """
    Search Method command - discovers methods in classes (Arthas-compatible)

    Usage:
        sm <pattern> [-d]

    Parameters:
        pattern: Class/method pattern (e.g., "module.Class.*", "module.Class.method*")
        -d, --details: Show detailed info (module path, docstring)
        --limit: Max results (default: 50)

    Examples:
        sm "json.JSONEncoder.*"
        sm "collections.OrderedDict.keys"
        sm "*.OrderedDict.update" -d
    """

    def __init__(self, agent: Optional["PeekaAgent"] = None):
        super().__init__()
        self.agent = agent

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute search method command."""
        try:
            pattern = params.get("pattern", "").strip()

            # Validate pattern
            if not pattern:
                return {"status": "error", "error": "Pattern cannot be empty"}

            details = params.get("details", False)
            limit = params.get("limit", 50)

            methods = self._search_methods(pattern, details, limit)

            return {
                "status": "success",
                "methods": methods,
                "count": len(methods),
                "limit": limit,
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _search_methods(
        self, pattern: str, details: bool = False, limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Search for methods matching pattern.

        Pattern format:
        - "module.Class.*" - all methods in class
        - "module.Class.method" - specific method
        - "module.Class.method_*" - methods matching prefix
        - "*.Class.method" - methods in class with wildcard module

        Returns:
            List of method info dicts with name, signature and optional details
        """
        results: List[Dict[str, Any]] = []

        # Parse pattern to extract components
        parts = pattern.split(".")

        if len(parts) < 2:
            # Need at least "Module.Class" or similar
            return results

        # Extract method pattern (last component)
        method_pattern = parts[-1]
        class_pattern = parts[-2]
        module_pattern = ".".join(parts[:-2]) if len(parts) > 2 else "*"

        # Iterate through loaded modules
        for module_name, module in list(sys.modules.items()):
            if module is None:
                continue

            # Match module pattern
            if not fnmatch.fnmatch(module_name, module_pattern):
                continue

            # Get all classes in this module
            try:
                members = inspect.getmembers(module, inspect.isclass)
            except Exception:
                continue

            for class_name, class_obj in members:
                # Match class pattern
                if not fnmatch.fnmatch(class_name, class_pattern):
                    continue

                # Get all methods in this class
                try:
                    methods = inspect.getmembers(
                        class_obj,
                        predicate=lambda x: (
                            inspect.ismethod(x)
                            or inspect.isfunction(x)
                            or inspect.isbuiltin(x)
                        ),
                    )
                except Exception:
                    continue

                for method_name, method_obj in methods:
                    # Skip magic methods for now (can be added with flag)
                    if method_name.startswith("__"):
                        continue

                    # Match method pattern
                    if not fnmatch.fnmatch(method_name, method_pattern):
                        continue

                    method_info = {"name": method_name}

                    # Always include signature
                    try:
                        sig = inspect.signature(method_obj)
                        method_info["signature"] = str(sig)
                    except Exception:
                        method_info["signature"] = None

                    if details:
                        method_info.update(
                            self._get_method_details(
                                method_obj, module_name, class_name
                            )
                        )

                    results.append(method_info)

                    if len(results) >= limit:
                        return results

        return results

    def _get_method_details(
        self, method_obj: Any, module_name: str, class_name: str
    ) -> Dict[str, Any]:
        """Get detailed information about a method."""
        details: Dict[str, Any] = {}

        # Module info
        details["module"] = module_name
        details["class"] = class_name

        # Docstring
        docstring = inspect.getdoc(method_obj)
        details["docstring"] = docstring if docstring else None

        return details
