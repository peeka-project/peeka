"""
Pattern Matching Utilities
For matching function/class/module patterns
"""

import re


def match_pattern(pattern: str, target: str) -> bool:
    """
    Match a pattern against a target string

    Supports wildcards:
        * - matches any characters
        ? - matches single character

    Args:
        pattern: Pattern with optional wildcards
        target: Target string to match

    Returns:
        True if matches, False otherwise

    Examples:
        >>> match_pattern("mymodule.*", "mymodule.MyClass")
        True
        >>> match_pattern("*.func", "module.func")
        True
        >>> match_pattern("test_*", "test_function")
        True
    """
    # Convert wildcard pattern to regex
    regex_pattern = pattern.replace('.', r'\.')
    regex_pattern = regex_pattern.replace('*', '.*')
    regex_pattern = regex_pattern.replace('?', '.')
    regex_pattern = f'^{regex_pattern}$'

    return bool(re.match(regex_pattern, target))


def parse_pattern(pattern: str) -> dict:
    """
    Parse a pattern into components

    Args:
        pattern: Pattern like "module.Class.method"

    Returns:
        Dictionary with parsed components

    Examples:
        >>> parse_pattern("mymodule.MyClass.my_method")
        {'full': 'mymodule.MyClass.my_method',
         'parts': ['mymodule', 'MyClass', 'my_method'],
         'module': 'mymodule',
         'class': 'MyClass',
         'method': 'my_method'}
    """
    parts = pattern.split('.')

    result = {
        'full': pattern,
        'parts': parts,
    }

    if len(parts) >= 1:
        result['module'] = parts[0]

    if len(parts) >= 2:
        result['class'] = parts[-2]
        result['method'] = parts[-1]
    elif len(parts) == 1:
        result['function'] = parts[0]

    return result


def expand_pattern(pattern: str, available_targets: list) -> list:
    """
    Expand a pattern with wildcards to matching targets

    Args:
        pattern: Pattern with wildcards
        available_targets: List of available target names

    Returns:
        List of matching targets

    Examples:
        >>> expand_pattern("test_*", ["test_a", "test_b", "other"])
        ['test_a', 'test_b']
    """
    return [
        target for target in available_targets
        if match_pattern(pattern, target)
    ]
