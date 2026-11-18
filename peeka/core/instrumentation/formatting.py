"""Observation value formatting helpers."""

import math
from typing import Any


class InjectorFormattingMixin:

    def _format_value(self, value: Any, depth: int) -> Any:
        """
        Format a value for JSON serialization.

        Args:
            value: Value to format
            depth: Maximum depth for nested structures

        Returns:
            JSON-serializable representation
        """
        try:
            return self._format_value_recursive(value, depth, 0)
        except Exception:
            return self._to_string(value)

    def _safe_key_str(self, key: Any) -> str:
        """Convert a mapping key to string without raising user exceptions."""
        if isinstance(key, str):
            return key
        try:
            return str(key)
        except Exception:
            return self._to_string(key)

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
            if isinstance(value, float):
                try:
                    if math.isnan(value) or math.isinf(value):
                        # Handle NaN, Inf without triggering subclass __ne__/__eq__
                        return str(value)
                except Exception:
                    return self._to_string(value)
            return value
        if isinstance(value, str):
            try:
                # Truncate long strings
                if len(value) > 1000:
                    return value[:1000] + f"... ({len(value) - 1000} more chars)"
                return value
            except Exception:
                return self._to_string(value)
        if isinstance(value, bytes):
            try:
                if len(value) > 100:
                    return f"<bytes len={len(value)}>"
                return value.hex()
            except Exception:
                return self._to_string(value)

        # List/Tuple
        if isinstance(value, (list, tuple)):
            try:
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
            except Exception:
                return self._to_string(value)

        # Dict
        if isinstance(value, dict):
            try:
                result = {}
                count = 0
                for k, v in value.items():
                    if count >= 20:
                        result["..."] = f"({len(value) - 20} more)"
                        break
                    key_str = self._safe_key_str(k)
                    result[key_str] = self._format_value_recursive(
                        v, max_depth, current_depth + 1
                    )
                    count += 1
                return result
            except Exception:
                return self._to_string(value)

        # Set
        if isinstance(value, (set, frozenset)):
            try:
                items = list(value)[:20]
                formatted = [
                    self._format_value_recursive(v, max_depth, current_depth + 1)
                    for v in items
                ]
                if len(value) > 20:
                    formatted.append(f"... ({len(value) - 20} more)")
                return {"__set__": formatted}
            except Exception:
                return self._to_string(value)

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
        try:
            obj_cls = obj.__class__
            class_name = obj_cls.__name__
            module_name = obj_cls.__module__
        except Exception:
            obj_cls = type(obj)
            class_name = obj_cls.__name__
            module_name = obj_cls.__module__

        if current_depth >= max_depth:
            return f"<{module_name}.{class_name}>"

        # Try to get __dict__ without triggering truthiness on obj itself
        try:
            obj_dict = getattr(obj, "__dict__", None)
            if isinstance(obj_dict, dict) and obj_dict:
                attrs = {}
                count = 0
                for k, v in obj_dict.items():
                    if count >= 10:
                        attrs["..."] = f"({len(obj_dict) - 10} more)"
                        break
                    key_str = self._safe_key_str(k)
                    if not key_str.startswith("_"):  # Skip private attributes
                        attrs[key_str] = self._format_value_recursive(
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
