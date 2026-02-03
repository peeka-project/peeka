"""
Tests for peeka.utils.formatters
"""

import pytest

from peeka.utils.formatters import (
    format_value,
    format_object,
    format_table,
    format_duration,
)


class TestFormatValue:
    """Test the format_value() function."""

    # Primitives
    def test_format_none(self):
        """Test formatting None."""
        assert format_value(None) == "None"

    def test_format_bool(self):
        """Test formatting booleans."""
        assert format_value(True) == "True"
        assert format_value(False) == "False"

    def test_format_int(self):
        """Test formatting integers."""
        assert format_value(42) == "42"
        assert format_value(-100) == "-100"
        assert format_value(0) == "0"

    def test_format_float(self):
        """Test formatting floats."""
        assert format_value(3.14) == "3.14"
        assert format_value(-0.5) == "-0.5"

    def test_format_string(self):
        """Test formatting strings."""
        assert format_value("hello") == "'hello'"
        assert format_value("") == "''"

    # Collections
    def test_format_empty_list(self):
        """Test formatting empty list."""
        assert format_value([]) == "[]"

    def test_format_list(self):
        """Test formatting list."""
        assert format_value([1, 2, 3]) == "[1, 2, 3]"

    def test_format_long_list(self):
        """Test formatting list with >10 items is truncated."""
        items = list(range(15))
        result = format_value(items)

        assert "... (5 more)" in result
        assert "0" in result
        assert "9" in result

    def test_format_empty_tuple(self):
        """Test formatting empty tuple."""
        assert format_value(()) == "()"

    def test_format_tuple(self):
        """Test formatting tuple."""
        assert format_value((1, 2, 3)) == "(1, 2, 3)"

    def test_format_long_tuple(self):
        """Test formatting tuple with >10 items is truncated."""
        items = tuple(range(15))
        result = format_value(items)

        assert "... (5 more)" in result

    def test_format_empty_dict(self):
        """Test formatting empty dict."""
        assert format_value({}) == "{}"

    def test_format_dict(self):
        """Test formatting dict."""
        result = format_value({"a": 1, "b": 2})

        assert "'a': 1" in result
        assert "'b': 2" in result

    def test_format_long_dict(self):
        """Test formatting dict with >10 items is truncated."""
        items = {f"k{i}": i for i in range(15)}
        result = format_value(items)

        assert "... (5 more)" in result

    def test_format_empty_set(self):
        """Test formatting empty set."""
        assert format_value(set()) == "set()"

    def test_format_set(self):
        """Test formatting set."""
        result = format_value({1, 2, 3})
        # Set order is not guaranteed, just check format
        assert result.startswith("{")
        assert result.endswith("}")
        assert "1" in result

    def test_format_long_set(self):
        """Test formatting set with >10 items is truncated."""
        items = set(range(15))
        result = format_value(items)

        assert "... (5 more)" in result

    # Depth limiting
    def test_format_depth_limit(self):
        """Test depth limiting."""
        nested = {"level1": {"level2": {"level3": "deep"}}}
        result = format_value(nested, depth=1)

        # At depth 1, nested dicts should use repr
        assert "level1" in result

    def test_format_nested_at_depth(self):
        """Test nested structure at depth limit uses repr."""
        nested = [[["deep"]]]
        result = format_value(nested, depth=2)

        assert "[" in result


class TestFormatObject:
    """Test the format_object() function."""

    def test_format_simple_object(self):
        """Test formatting object with __dict__."""

        class MyClass:
            def __init__(self):
                self.x = 1
                self.y = 2

        obj = MyClass()
        result = format_object(obj)

        assert "MyClass" in result
        assert "x=1" in result
        assert "y=2" in result

    def test_format_object_many_attrs(self):
        """Test formatting object with >5 attributes is truncated."""

        class BigClass:
            def __init__(self):
                for i in range(10):
                    setattr(self, f"attr{i}", i)

        obj = BigClass()
        result = format_object(obj)

        assert "... (5 more)" in result

    def test_format_object_at_depth(self):
        """Test formatting object at depth limit."""

        class MyClass:
            pass

        obj = MyClass()
        result = format_object(obj, depth=2, current_depth=2)

        # Should return simple representation at depth
        assert "MyClass" in result
        assert "object" in result

    def test_format_object_no_dict(self):
        """Test formatting object without __dict__ uses repr."""
        result = format_object(42)  # int has no __dict__

        assert "42" in result


class TestFormatTable:
    """Test the format_table() function."""

    def test_format_table_basic(self):
        """Test basic table formatting."""
        headers = ["Name", "Value"]
        rows = [["foo", "123"], ["bar", "456"]]
        result = format_table(headers, rows)

        assert "Name" in result
        assert "Value" in result
        assert "foo" in result
        assert "123" in result
        assert "bar" in result
        assert "456" in result
        assert "+" in result  # separator
        assert "|" in result  # column delimiter

    def test_format_table_empty(self):
        """Test table with no rows."""
        headers = ["Name", "Value"]
        rows = []
        result = format_table(headers, rows)

        assert result == "No data"

    def test_format_table_column_width(self):
        """Test table respects max_width."""
        headers = ["Col"]
        rows = [["x" * 200]]  # Very long value
        result = format_table(headers, rows, max_width=50)

        # Value should be truncated
        lines = result.split("\n")
        for line in lines:
            # Each line should be reasonably short
            assert len(line) < 200

    def test_format_table_alignment(self):
        """Test table values are left-aligned."""
        headers = ["A", "B"]
        rows = [["1", "22"]]
        result = format_table(headers, rows)

        # Check structure exists
        assert "|" in result


class TestFormatDuration:
    """Test the format_duration() function."""

    def test_format_microseconds(self):
        """Test formatting microseconds."""
        result = format_duration(0.0001)  # 100 microseconds
        assert "μs" in result
        assert "100" in result

    def test_format_milliseconds(self):
        """Test formatting milliseconds."""
        result = format_duration(0.001)  # 1 millisecond
        assert "ms" in result
        assert "1.00" in result

    def test_format_milliseconds_range(self):
        """Test formatting in milliseconds range."""
        result = format_duration(0.5)  # 500 milliseconds
        assert "ms" in result
        assert "500" in result

    def test_format_seconds(self):
        """Test formatting seconds."""
        result = format_duration(1.5)
        assert "s" in result
        assert "1.50" in result

    def test_format_seconds_range(self):
        """Test formatting in seconds range."""
        result = format_duration(30)
        assert "s" in result
        assert "30" in result

    def test_format_minutes(self):
        """Test formatting minutes."""
        result = format_duration(65)  # 1 minute 5 seconds
        assert "m" in result
        assert "1" in result
        assert "5" in result

    def test_format_minutes_range(self):
        """Test formatting in minutes range."""
        result = format_duration(300)  # 5 minutes
        assert "m" in result
        assert "5" in result

    def test_format_hours(self):
        """Test formatting hours."""
        result = format_duration(3700)  # 1 hour 1 minute
        assert "h" in result
        assert "1" in result

    def test_format_many_hours(self):
        """Test formatting many hours."""
        result = format_duration(7200)  # 2 hours
        assert "h" in result
        assert "2" in result
