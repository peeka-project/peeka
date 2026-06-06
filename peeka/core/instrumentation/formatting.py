"""Observation value formatting helpers."""

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
