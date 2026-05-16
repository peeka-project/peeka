"""
Output Formatters
Format Python objects for display
"""

from typing import Any


def format_value(value: Any, depth: int = 2, current_depth: int = 0) -> str:
    """
    Format a Python value for display
    
    Args:
        value: Value to format
        depth: Maximum depth to traverse
        current_depth: Current traversal depth
        
    Returns:
        Formatted string representation
    """
    if current_depth >= depth:
        return repr(value)

    # Handle None
    if value is None:
        return 'None'

    # Handle primitives
    if isinstance(value, (bool, int, float, str)):
        return repr(value)

    # Handle lists
    if isinstance(value, list):
        if not value:
            return '[]'
        items = [format_value(item, depth, current_depth + 1) for item in value[:10]]
        if len(value) > 10:
            items.append(f'... ({len(value) - 10} more)')
        return '[' + ', '.join(items) + ']'

    # Handle tuples
    if isinstance(value, tuple):
        if not value:
            return '()'
        items = [format_value(item, depth, current_depth + 1) for item in value[:10]]
        if len(value) > 10:
            items.append(f'... ({len(value) - 10} more)')
        return '(' + ', '.join(items) + ')'

    # Handle dicts
    if isinstance(value, dict):
        if not value:
            return '{}'
        items = []
        for i, (k, v) in enumerate(value.items()):
            if i >= 10:
                items.append(f'... ({len(value) - 10} more)')
                break
            key_str = format_value(k, depth, current_depth + 1)
            val_str = format_value(v, depth, current_depth + 1)
            items.append(f'{key_str}: {val_str}')
        return '{' + ', '.join(items) + '}'

    # Handle sets
    if isinstance(value, set):
        if not value:
            return 'set()'
        items = [format_value(item, depth, current_depth + 1) for item in list(value)[:10]]
        if len(value) > 10:
            items.append(f'... ({len(value) - 10} more)')
        return '{' + ', '.join(items) + '}'

    # Handle objects
    return format_object(value, depth, current_depth)


def format_object(obj: Any, depth: int = 2, current_depth: int = 0) -> str:
    """
    Format a Python object for display
    
    Args:
        obj: Object to format
        depth: Maximum depth
        current_depth: Current depth
        
    Returns:
        Formatted string
    """
    class_name = obj.__class__.__name__
    module_name = obj.__class__.__module__

    if current_depth >= depth:
        return f'<{module_name}.{class_name} object>'

    # Try to get useful attributes
    try:
        if hasattr(obj, '__dict__'):
            attrs = obj.__dict__
            if attrs:
                formatted_attrs = []
                for i, (k, v) in enumerate(attrs.items()):
                    if i >= 5:  # Limit to 5 attributes
                        formatted_attrs.append(f'... ({len(attrs) - 5} more)')
                        break
                    val_str = format_value(v, depth, current_depth + 1)
                    formatted_attrs.append(f'{k}={val_str}')
                return f'<{class_name}({", ".join(formatted_attrs)})>'
    except Exception:
        pass

    # Fallback to repr
    try:
        return repr(obj)
    except Exception:
        return f'<{module_name}.{class_name} object at {hex(id(obj))}>'


def format_table(headers: list, rows: list, max_width: int = 100) -> str:
    """
    Format data as a table
    
    Args:
        headers: List of column headers
        rows: List of row data (each row is a list)
        max_width: Maximum width for each column
        
    Returns:
        Formatted table string
    """
    if not rows:
        return "No data"

    # Calculate column widths
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    # Cap widths
    col_widths = [min(w, max_width) for w in col_widths]

    # Create separator
    separator = '+' + '+'.join('-' * (w + 2) for w in col_widths) + '+'

    # Format header
    header_row = '|' + '|'.join(
        f' {h:<{w}} ' for h, w in zip(headers, col_widths)
    ) + '|'

    # Format rows
    data_rows = []
    for row in rows:
        cells = [str(cell)[:w] for cell, w in zip(row, col_widths)]
        row_str = '|' + '|'.join(
            f' {c:<{w}} ' for c, w in zip(cells, col_widths)
        ) + '|'
        data_rows.append(row_str)

    # Combine
    lines = [separator, header_row, separator] + data_rows + [separator]
    return '\n'.join(lines)


def format_duration(seconds: float) -> str:
    """
    Format duration in human-readable form
    
    Args:
        seconds: Duration in seconds
        
    Returns:
        Formatted string
        
    Examples:
        >>> format_duration(0.001)
        '1.00ms'
        >>> format_duration(1.5)
        '1.50s'
        >>> format_duration(65)
        '1m 5s'
    """
    if seconds < 0.001:
        return f'{seconds * 1000000:.2f}μs'
    elif seconds < 1:
        return f'{seconds * 1000:.2f}ms'
    elif seconds < 60:
        return f'{seconds:.2f}s'
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f'{minutes}m {secs}s'
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f'{hours}h {minutes}m'
