"""
Tests for peeka.utils.patterns
"""

import pytest

from peeka.utils.patterns import match_pattern, parse_pattern, expand_pattern


class TestMatchPattern:
    """Test the match_pattern() function."""

    def test_exact_match(self):
        """Test exact string match."""
        assert match_pattern("module.func", "module.func") is True
        assert match_pattern("module.func", "module.other") is False

    def test_asterisk_wildcard(self):
        """Test * wildcard matches any characters."""
        assert match_pattern("mymodule.*", "mymodule.MyClass") is True
        assert match_pattern("mymodule.*", "mymodule.func") is True
        assert match_pattern("*.func", "module.func") is True
        assert match_pattern("*.func", "other.func") is True
        assert match_pattern("*.func", "module.other") is False

    def test_question_wildcard(self):
        """Test ? wildcard matches single character."""
        assert match_pattern("test_?", "test_a") is True
        assert match_pattern("test_?", "test_b") is True
        assert match_pattern("test_?", "test_ab") is False
        assert match_pattern("test_?", "test_") is False

    def test_combined_wildcards(self):
        """Test combined * and ? wildcards."""
        assert match_pattern("test_*_?", "test_func_a") is True
        assert match_pattern("test_*_?", "test_something_b") is True
        assert match_pattern("test_*_?", "test_func_ab") is False

    def test_prefix_wildcard(self):
        """Test prefix matching with *."""
        assert match_pattern("test_*", "test_function") is True
        assert match_pattern("test_*", "test_") is True
        assert match_pattern("test_*", "other_function") is False

    def test_dot_escaping(self):
        """Test that dots are escaped properly (not treated as regex .)."""
        assert match_pattern("a.b.c", "a.b.c") is True
        assert match_pattern("a.b.c", "axbxc") is False  # dot should not match any char

    def test_empty_pattern(self):
        """Test empty pattern."""
        assert match_pattern("", "") is True
        assert match_pattern("", "anything") is False

    def test_middle_wildcard(self):
        """Test wildcard in middle of pattern."""
        assert match_pattern("prefix.*.suffix", "prefix.middle.suffix") is True
        assert match_pattern("prefix.*.suffix", "prefix.a.b.suffix") is True
        assert (
            match_pattern("prefix.*.suffix", "prefix.suffix") is False
        )  # Requires two literal dots in target


class TestParsePattern:
    """Test the parse_pattern() function."""

    def test_full_pattern(self):
        """Test parsing module.Class.method pattern."""
        result = parse_pattern("mymodule.MyClass.my_method")

        assert result["full"] == "mymodule.MyClass.my_method"
        assert result["parts"] == ["mymodule", "MyClass", "my_method"]
        assert result["module"] == "mymodule"
        assert result["class"] == "MyClass"
        assert result["method"] == "my_method"

    def test_two_part_pattern(self):
        """Test parsing module.function pattern."""
        result = parse_pattern("mymodule.func")

        assert result["full"] == "mymodule.func"
        assert result["parts"] == ["mymodule", "func"]
        assert result["module"] == "mymodule"
        assert result["class"] == "mymodule"  # class is second-to-last
        assert result["method"] == "func"

    def test_single_part_pattern(self):
        """Test parsing single name pattern."""
        result = parse_pattern("function_name")

        assert result["full"] == "function_name"
        assert result["parts"] == ["function_name"]
        assert result["module"] == "function_name"
        assert result["function"] == "function_name"
        assert "class" not in result
        assert "method" not in result

    def test_deep_nested_pattern(self):
        """Test parsing deeply nested pattern."""
        result = parse_pattern("a.b.c.d.e")

        assert result["full"] == "a.b.c.d.e"
        assert result["parts"] == ["a", "b", "c", "d", "e"]
        assert result["module"] == "a"
        assert result["class"] == "d"
        assert result["method"] == "e"


class TestExpandPattern:
    """Test the expand_pattern() function."""

    def test_expand_prefix_wildcard(self):
        """Test expanding prefix wildcard."""
        targets = ["test_a", "test_b", "other"]
        result = expand_pattern("test_*", targets)

        assert result == ["test_a", "test_b"]

    def test_expand_suffix_wildcard(self):
        """Test expanding suffix wildcard."""
        targets = ["prefix_func", "other_func", "prefix_other"]
        result = expand_pattern("*_func", targets)

        assert result == ["prefix_func", "other_func"]

    def test_expand_no_matches(self):
        """Test expanding pattern with no matches."""
        targets = ["test_a", "test_b", "other"]
        result = expand_pattern("nomatch_*", targets)

        assert result == []

    def test_expand_exact_match(self):
        """Test expanding exact pattern (no wildcards)."""
        targets = ["module.func", "other.func"]
        result = expand_pattern("module.func", targets)

        assert result == ["module.func"]

    def test_expand_all_match(self):
        """Test expanding pattern that matches all."""
        targets = ["a", "b", "c"]
        result = expand_pattern("*", targets)

        assert result == ["a", "b", "c"]

    def test_expand_empty_targets(self):
        """Test expanding against empty target list."""
        result = expand_pattern("test_*", [])

        assert result == []

    def test_expand_complex_pattern(self):
        """Test expanding complex dotted pattern."""
        targets = [
            "mymodule.ClassA.method1",
            "mymodule.ClassA.method2",
            "mymodule.ClassB.method1",
            "other.ClassA.method1",
        ]
        result = expand_pattern("mymodule.ClassA.*", targets)

        assert result == ["mymodule.ClassA.method1", "mymodule.ClassA.method2"]
