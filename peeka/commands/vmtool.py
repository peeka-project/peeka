"""
VMTool Command - Runtime object inspection and heap analysis

This module provides runtime VM introspection capabilities:
- get: Retrieve object attributes by dotted path
- instances: Find live instances of a type in the heap
- count: Count instances of a type
"""

import gc
import sys
from typing import Dict, Any, TYPE_CHECKING

from peeka.commands.base import BaseCommand
from peeka.core.safeeval.simpleeval import SimpleEval, BASIC_ALLOWED_ATTRS

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class VMToolCommand(BaseCommand):
    """VM introspection command - inspect objects and heap at runtime."""

    def __init__(self, agent: "PeekaAgent"):
        super().__init__()
        self.agent = agent

    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute vmtool command with specified action.

        Args:
            params: Command parameters including 'action' key

        Returns:
            Dict containing action results or error information
        """
        try:
            action = params.get("action")

            if not action:
                return {
                    "status": "error",
                    "error": "Missing required parameter: action",
                }

            if action == "get":
                return self._get(params)
            elif action == "instances":
                return self._instances(params)
            elif action == "count":
                return self._count(params)
            else:
                return {"status": "error", "error": f"Unknown action: {action}"}

        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _get(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get object attribute by dotted path.

        Args:
            params: Must contain 'target' (dotted path), optional 'depth'

        Returns:
            Dict with status, target, type, value
        """
        target = params.get("target")
        if not target:
            return {"status": "error", "error": "Missing required parameter: target"}

        depth = params.get("depth", 2)

        try:
            obj = self._resolve_target(target)
            value = self._format_value(obj, depth)
            type_name = type(obj).__name__

            return {
                "status": "success",
                "action": "get",
                "target": target,
                "type": type_name,
                "value": value,
            }
        except Exception as e:
            return {"status": "error", "action": "get", "error": str(e)}

    def _instances(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Find instances of a type in the heap.

        Args:
            params: Must contain 'class_name', optional 'limit', 'filter_express', 'depth', 'gc_first'

        Returns:
            Dict with status, class_name, count, limit, truncated, instances
        """
        class_name = params.get("class_name")
        if not class_name:
            return {
                "status": "error",
                "error": "Missing required parameter: class_name",
            }

        limit = self._clamp_limit(params.get("limit", 10))
        depth = params.get("depth", 2)
        filter_express = params.get("filter_express")
        gc_first = params.get("gc_first", False)

        try:
            # Validate filter expression
            safe_evaluator = None
            if filter_express:
                try:
                    safe_evaluator = SimpleEval(
                        allowed_attrs=BASIC_ALLOWED_ATTRS,
                        functions={
                            "len": len,
                            "str": str,
                            "int": int,
                            "float": float,
                            "bool": bool,
                        },
                    )
                    safe_evaluator.parse(filter_express)
                except SyntaxError as e:
                    return {
                        "status": "error",
                        "action": "instances",
                        "error": f"Invalid filter expression: {e}",
                    }
                except Exception as e:
                    return {
                        "status": "error",
                        "action": "instances",
                        "error": f"Filter validation failed: {e}",
                    }

            # Resolve type
            target_type = self._resolve_type(class_name)

            # Run GC if requested
            if gc_first:
                gc.collect()

            # Scan heap for instances
            instances = []
            truncated = False

            for obj in gc.get_objects():
                if isinstance(obj, target_type):
                    # Apply filter if present
                    if filter_express and safe_evaluator:
                        try:
                            safe_evaluator.names = {"obj": obj}
                            if not safe_evaluator.eval(filter_express):
                                continue
                        except Exception:
                            # Runtime errors (e.g., missing attribute) skip object
                            continue

                    # Add to results
                    instances.append(self._format_value(obj, depth))

                    # Check limit
                    if len(instances) >= limit:
                        # Check if more exist
                        truncated = self._check_more_instances(
                            obj, target_type, gc.get_objects()
                        )
                        break

            return {
                "status": "success",
                "action": "instances",
                "class_name": class_name,
                "count": len(instances),
                "limit": limit,
                "truncated": truncated,
                "instances": instances,
            }

        except Exception as e:
            return {"status": "error", "action": "instances", "error": str(e)}

    def _count(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Count instances of a type in the heap.

        Args:
            params: Must contain 'class_name', optional 'filter_express', 'gc_first'

        Returns:
            Dict with status, class_name, count
        """
        class_name = params.get("class_name")
        if not class_name:
            return {
                "status": "error",
                "error": "Missing required parameter: class_name",
            }

        filter_express = params.get("filter_express")
        gc_first = params.get("gc_first", False)

        try:
            # Validate filter expression
            safe_evaluator = None
            if filter_express:
                try:
                    safe_evaluator = SimpleEval(
                        allowed_attrs=BASIC_ALLOWED_ATTRS,
                        functions={
                            "len": len,
                            "str": str,
                            "int": int,
                            "float": float,
                            "bool": bool,
                        },
                    )
                    safe_evaluator.parse(filter_express)
                except SyntaxError as e:
                    return {
                        "status": "error",
                        "action": "count",
                        "error": f"Invalid filter expression: {e}",
                    }
                except Exception as e:
                    return {
                        "status": "error",
                        "action": "count",
                        "error": f"Filter validation failed: {e}",
                    }

            # Resolve type
            target_type = self._resolve_type(class_name)

            # Run GC if requested
            if gc_first:
                gc.collect()

            # Count instances (no limit enforcement)
            count = 0
            for obj in gc.get_objects():
                if isinstance(obj, target_type):
                    # Apply filter if present
                    if filter_express and safe_evaluator:
                        try:
                            safe_evaluator.names = {"obj": obj}
                            if not safe_evaluator.eval(filter_express):
                                continue
                        except Exception:
                            # Runtime errors skip object
                            continue

                    count += 1

            return {
                "status": "success",
                "action": "count",
                "class_name": class_name,
                "count": count,
            }

        except Exception as e:
            return {"status": "error", "action": "count", "error": str(e)}

    def _resolve_target(self, target: str) -> Any:
        """
        Resolve dotted path to object.

        Args:
            target: Dotted path like "module.Class.attr"

        Returns:
            Resolved object

        Raises:
            ValueError: If path cannot be resolved
        """
        parts = target.split(".")
        if not parts:
            raise ValueError(f"Invalid target: {target}")

        # First segment must be a module
        module_name = parts[0]
        if module_name not in sys.modules:
            raise ValueError(f"Module '{module_name}' not loaded")

        obj = sys.modules[module_name]

        # Walk remaining segments via getattr
        for i, attr in enumerate(parts[1:], start=1):
            try:
                obj = getattr(obj, attr)
            except AttributeError:
                raise ValueError(
                    f"Attribute '{attr}' not found in '{'.'.join(parts[:i])}'"
                )

        return obj

    def _resolve_type(self, type_name: str) -> type:
        """
        Resolve type name to type object.

        Args:
            type_name: Type name (builtin or qualified name)

        Returns:
            Type object

        Raises:
            ValueError: If type cannot be resolved
        """
        # Check builtins
        builtin_types = {
            "str": str,
            "int": int,
            "list": list,
            "dict": dict,
            "set": set,
            "tuple": tuple,
            "bytes": bytes,
            "bool": bool,
            "float": float,
        }

        if type_name in builtin_types:
            return builtin_types[type_name]

        # Qualified name: module.Class
        if "." in type_name:
            parts = type_name.split(".")
            module_name = parts[0]
            class_name = parts[1]

            if module_name not in sys.modules:
                raise ValueError(f"Module '{module_name}' not loaded")

            module = sys.modules[module_name]
            if not hasattr(module, class_name):
                raise ValueError(
                    f"Class '{class_name}' not found in module '{module_name}'"
                )

            cls = getattr(module, class_name)
            if not isinstance(cls, type):
                raise ValueError(f"'{type_name}' is not a type")

            return cls

        # Not a builtin and not qualified
        raise ValueError(
            f"Type '{type_name}' not found (must be builtin or qualified name)"
        )

    def _clamp_limit(self, limit: Any) -> int:
        """
        Clamp limit parameter to valid range.

        Args:
            limit: Raw limit value

        Returns:
            Clamped limit (1-1000)
        """
        try:
            limit = int(limit)
        except (ValueError, TypeError):
            limit = 10

        return max(1, min(limit, 1000))

    def _check_more_instances(
        self, last_obj: Any, target_type: type, all_objects: list
    ) -> bool:
        """
        Check if more instances exist after reaching limit.

        Args:
            last_obj: Last object added to results
            target_type: Target type
            all_objects: All objects from gc.get_objects()

        Returns:
            True if more instances exist
        """
        found_last = False
        for obj in all_objects:
            if obj is last_obj:
                found_last = True
                continue
            if found_last and isinstance(obj, target_type):
                return True
        return False

    # Formatting methods (copied from injector.py)

    def _format_value(self, value: Any, depth: int) -> Any:
        """
        Format a value for JSON serialization.

        Args:
            value: Value to format
            depth: Maximum depth for nested structures

        Returns:
            JSON-serializable representation
        """
        return self._format_value_recursive(value, depth, 0)

    def _format_value_recursive(
        self, value: Any, max_depth: int, current_depth: int
    ) -> Any:
        """
        Recursively format value for JSON serialization.

        Args:
            value: Value to format
            max_depth: Maximum depth
            current_depth: Current recursion depth

        Returns:
            JSON-serializable value
        """
        if current_depth >= max_depth:
            return self._to_string(value)

        # None
        if value is None:
            return None

        # Primitives
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if isinstance(value, float) and (
                value != value or value == float("inf") or value == float("-inf")
            ):
                # Handle NaN, Inf
                return str(value)
            return value
        if isinstance(value, str):
            # Truncate long strings
            if len(value) > 1000:
                return value[:1000] + f"... ({len(value) - 1000} more chars)"
            return value
        if isinstance(value, bytes):
            if len(value) > 100:
                return f"<bytes len={len(value)}>"
            return value.hex()

        # List/Tuple
        if isinstance(value, (list, tuple)):
            if len(value) > 20:
                items = [
                    self._format_value_recursive(v, max_depth, current_depth + 1)
                    for v in value[:20]
                ]
                items.append(f"... ({len(value) - 20} more)")
                return items
            return [
                self._format_value_recursive(v, max_depth, current_depth + 1)
                for v in value
            ]

        # Dict
        if isinstance(value, dict):
            result = {}
            count = 0
            for k, v in value.items():
                if count >= 20:
                    result["..."] = f"({len(value) - 20} more)"
                    break
                key_str = str(k) if not isinstance(k, str) else k
                result[key_str] = self._format_value_recursive(
                    v, max_depth, current_depth + 1
                )
                count += 1
            return result

        # Set
        if isinstance(value, (set, frozenset)):
            items = list(value)[:20]
            formatted = [
                self._format_value_recursive(v, max_depth, current_depth + 1)
                for v in items
            ]
            if len(value) > 20:
                formatted.append(f"... ({len(value) - 20} more)")
            return {"__set__": formatted}

        # Objects
        return self._format_object(value, max_depth, current_depth)

    def _format_object(self, obj: Any, max_depth: int, current_depth: int) -> Any:
        """
        Format an object for JSON serialization.

        Args:
            obj: Object to format
            max_depth: Maximum depth
            current_depth: Current depth

        Returns:
            JSON-serializable representation
        """
        class_name = obj.__class__.__name__
        module_name = obj.__class__.__module__

        if current_depth >= max_depth:
            return f"<{module_name}.{class_name}>"

        # Try to get __dict__
        try:
            if hasattr(obj, "__dict__") and obj.__dict__:
                attrs = {}
                count = 0
                for k, v in obj.__dict__.items():
                    if count >= 10:
                        attrs["..."] = f"({len(obj.__dict__) - 10} more)"
                        break
                    if not k.startswith("_"):  # Skip private attributes
                        attrs[k] = self._format_value_recursive(
                            v, max_depth, current_depth + 1
                        )
                        count += 1
                return {"__class__": f"{module_name}.{class_name}", "__attrs__": attrs}
        except Exception:
            pass

        # Fallback to string representation
        return self._to_string(obj)

    def _to_string(self, value: Any) -> str:
        """
        Convert value to string safely.

        Args:
            value: Value to convert

        Returns:
            String representation
        """
        try:
            s = repr(value)
            if len(s) > 200:
                return s[:200] + "..."
            return s
        except Exception:
            try:
                return f"<{type(value).__name__}>"
            except Exception:
                return "<unknown>"
