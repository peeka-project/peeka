# Peeka Developer Guide (for AI Coding Agents)

This document provides actionable coding guidelines for AI agents working on Peeka. For high-level architecture,
see [ARCHITECTURE.md](ARCHITECTURE.md).

## Quick Reference

### Build & Install

```bash
# Install in development mode
pip install -e .

# Install with test dependencies
pip install -e ".[test]"

# Or using uv
uv pip install -e .
uv pip install pytest pytest-asyncio
```

### Testing

```bash
# Run all tests
pytest tests/

# Run single test file
pytest tests/test_injector.py

# Run single test class
pytest tests/test_injector.py::TestDecoratorInjector

# Run single test function
pytest tests/test_injector.py::TestDecoratorInjector::test_inject_function

# Run with verbose output
pytest tests/ -v

# Quick compatibility check (no dependencies)
python3 tests/simple_compat_test.py
```

### Code Checking

```bash
# Type checking (if mypy is installed)
mypy peeka/

# Linting (if ruff/flake8 is installed)
ruff check peeka/
flake8 peeka/

# No enforced formatter - developers choose their own
```

## Code Style Guidelines

### Import Organization

**Order**: stdlib → third-party → local (alphabetical within each group)

```python
# Standard library
import importlib
import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

# Third-party (if needed)
import pytest

# Local imports (absolute paths from peeka)
from peeka.commands.base import BaseCommand
from peeka.core.agent import PeekaAgent
from peeka.core.injector import DecoratorInjector
```

**Key patterns**:

- Use `from typing import TYPE_CHECKING` for type-only imports to avoid circular imports
- Prefer absolute imports: `from peeka.core.agent import X` (not `from .agent import X`)
- Group stdlib imports by category when many (not mandatory)

### Type Annotations

**Required**: All function signatures must have type hints.

```python
# Good
def inject(self, pattern: str, watch_config: Dict[str, Any]) -> str:
    pass


def _send_observation(self, observation: Dict[str, Any]) -> None:
    pass


# Current pattern (backwards compatible)
from typing import Dict, Any, Optional, List

# Note: Modern syntax (dict[str, any]) not yet adopted project-wide
```

**TYPE_CHECKING pattern** for circular imports:

```python
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent


class DecoratorInjector:
    def __init__(self, agent: "PeekaAgent"):  # String literal for forward reference
        self.agent = agent
```

### Naming Conventions

| Type                 | Pattern     | Example                                    |
|----------------------|-------------|--------------------------------------------|
| Classes              | PascalCase  | `PeekaAgent`, `DecoratorInjector`          |
| Functions            | snake_case  | `inject()`, `_resolve_target()`            |
| Private methods      | `_prefix`   | `_send_observation()`, `_create_wrapper()` |
| Constants            | UPPER_SNAKE | `BASIC_ALLOWED_ATTRS`                      |
| Variables            | snake_case  | `watch_id`, `target_func`                  |
| Protected attributes | `_prefix`   | `self._lock`, `self._observations`         |

### Docstrings & Comments

**Philosophy**: Code should be self-documenting. Use docstrings/comments sparingly.

**When to use docstrings**:

- Public API functions/classes (especially entry points)
- Security-critical code (e.g., `simpleeval` usage)
- Complex algorithms that aren't obvious from code
- Module-level docstrings for non-trivial modules

**Example** (from `injector.py`):

```python
"""
Decorator Injector - Runtime function instrumentation

This module provides the DecoratorInjector class that dynamically injects
observation logic into target functions at runtime, enabling function call
monitoring without modifying the original source code.
"""


class DecoratorInjector:
    """
    Injects observation decorators into target functions at runtime.

    This class is responsible for:
    - Resolving function patterns to actual Python objects
    - Creating wrapper functions that capture call information
    - Replacing original functions with instrumented versions
    - Restoring original functions when observation stops

    Example:
        injector = DecoratorInjector(agent)
        watch_id = injector.inject("mymodule.MyClass.method", {"depth": 2})
        # ... observations happen ...
        injector.uninject(watch_id)
    """
```

**When NOT to use docstrings**:

- Private helper methods with obvious purpose
- Simple getters/setters
- Test functions (test name should be descriptive)

### Error Handling

**Patterns**:

- Use specific exception types
- Provide clear error messages
- Include context in error messages

```python
# Good - Specific exception with context
if target_info is None:
    raise ValueError(f"Cannot find target: {pattern}")

# Good - Validation with clear message
with pytest.raises(ValueError, match="Invalid condition expression"):
    injector.inject("module.func", {"condition": "invalid!@#"})

# Good - Catch and re-raise with context
try:
    result = handler.execute(command)
except Exception as e:
    return {
        "status": "error",
        "error": str(e),
        "traceback": traceback.format_exc(),
    }
```

**Exception guidelines**:

- Prefer `ValueError` for invalid arguments
- Use `RuntimeError` for state errors
- Catch broad exceptions only at top-level handlers
- Always clean up resources (use `finally` or context managers)

### Security Patterns

**Critical**: User-provided expressions MUST use `simpleeval`, never `eval()`.

```python
from peeka.core.safeeval.simpleeval import SimpleEval, BASIC_ALLOWED_ATTRS

# Good - Safe evaluation
evaluator = SimpleEval()
evaluator.names = {"params": args, "kwargs": kwargs}
result = evaluator.eval(condition_expr)

# FORBIDDEN - Code injection vulnerability
result = eval(condition_expr)  # ❌ NEVER DO THIS
```

**simpleeval configuration**:

- AST whitelist: Only safe operations (compare, arithmetic, logic)
- Blocked: `__import__`, `eval`, `exec`, `compile`, `open`, `__class__`, `__subclasses__`
- See `peeka/core/safeeval/simpleeval.py` for full configuration

### Resource Management

**Patterns**:

- Use context managers for cleanup
- Use `finally` blocks for critical cleanup
- Use `threading.Lock()` for shared state

```python
# Good - Lock for thread safety
with self._lock:
    self.instrumented[watch_id] = {...}
    self._replace_function(parent_obj, attr_name, wrapper)

# Good - Cleanup in finally
try:
# ... work ...
finally:
    with self._connections_lock:
        if conn in self._client_connections:
            self._client_connections.remove(conn)
    conn.close()
```

### Threading

**Patterns observed**:

- Use `daemon=True` for background threads
- Protect shared state with locks
- Clean up connections in `finally` blocks

```python
thread = threading.Thread(target=self._accept_loop, daemon=True)
thread.start()
```

## Architecture Patterns

### Module Structure

```
peeka/
├── cli.py                 # Command-line interface
├── core/
│   ├── agent.py          # PeekaAgent - main coordinator
│   ├── attach.py         # Process attachment (PEP 768 + GDB fallback)
│   ├── injector.py       # DecoratorInjector - function instrumentation
│   ├── observer.py       # ObservationManager - data buffering
│   └── safeeval/
│       └── simpleeval.py # Safe expression evaluation
├── commands/
│   ├── base.py           # BaseCommand abstract class
│   └── watch.py          # WatchCommand implementation
└── client/               # Client-side communication
```

### Command Pattern

All commands inherit from `BaseCommand`:

```python
from peeka.commands.base import BaseCommand


class MyCommand(BaseCommand):
    def execute(self, params: dict) -> dict:
        # Implementation
        return {"status": "success", ...}
```

Register in `PeekaAgent._register_handlers()`:

```python
def _register_handlers(self) -> None:
    from peeka.commands.watch import WatchCommand
    from peeka.commands.mycommand import MyCommand

    self.command_handlers["watch"] = WatchCommand(self)
    self.command_handlers["mycmd"] = MyCommand(self)
```

### Communication Protocol

**Format**: `[4-byte length prefix][JSON payload]`

```python
# Sending
message = json.dumps(data).encode("utf-8")
conn.sendall(len(message).to_bytes(4, "big"))
conn.sendall(message)

# Receiving
length = int.from_bytes(conn.recv(4), "big")
data = conn.recv(length)
message = json.loads(data.decode("utf-8"))
```

## Python Version Support

**Supported**: Python 3.9 - 3.14+

### Version-Specific Features

| Python Version | Attach Mechanism            | Requirements                     |
|----------------|-----------------------------|----------------------------------|
| 3.14+          | PEP 768 `sys.remote_exec()` | None                             |
| 3.9-3.13       | GDB + ptrace fallback       | GDB, python3-dbg, CAP_SYS_PTRACE |

### GDB Fallback (Python <3.14)

Implementation in `peeka/core/attach.py`:

```python
def _attach_fallback(self, pid: int) -> bool:
    # Check GDB availability
    if not self._check_gdb_available():
        return False

    # Check ptrace permissions
    if not self._check_ptrace_permissions(pid):
        return False

    # Inject via GDB
    return self._inject_via_gdb(pid, script_path)
```

**Requirements**:

- GDB 7.3+
- Python debug symbols (`python3-dbg` or `python3-debuginfo`)
- ptrace_scope <= 1 (`/proc/sys/kernel/yama/ptrace_scope`)
- CAP_SYS_PTRACE or same UID

## Testing Guidelines

### Test Structure

```python
import pytest
import sys


class TestMyFeature:
    @pytest.fixture
    def setup_data(self):
        # Setup
        return data

    def test_basic_functionality(self, setup_data):
        # Arrange
        expected = ...

        # Act
        result = function_under_test(setup_data)

        # Assert
        assert result == expected

    def test_error_handling(self):
        with pytest.raises(ValueError, match="expected message"):
            function_under_test(invalid_input)
```

### Fixtures for Module Mocking

```python
@pytest.fixture
def mock_module(self):
    test_module = type(sys)("test_module")
    test_module.sample_function = lambda x: x * 2
    sys.modules["test_module"] = test_module

    yield test_module

    # Cleanup
    del sys.modules["test_module"]
```

### Compatibility Testing

**Simple tests** (no dependencies):

```python
# tests/simple_compat_test.py
# Should work on all Python versions without pytest
def test_basic_functionality():
    assert 1 + 1 == 2
    print("✓ Basic test passed")


if __name__ == "__main__":
    test_basic_functionality()
```

**Full tests** (pytest):

```python
# tests/test_compatibility.py
import pytest


@pytest.mark.skipif(sys.version_info < (3, 14), reason="PEP 768 only in 3.14+")
def test_pep768_attach():
    # Test PEP 768 specific features
    pass
```

## Common Tasks

### Adding a New Command

1. Create command file: `peeka/commands/mycommand.py`
2. Inherit from `BaseCommand`
3. Implement `execute(params: dict) -> dict`
4. Register in `PeekaAgent._register_handlers()`
5. Add CLI integration in `peeka/cli.py`
6. Write tests in `tests/test_mycommand.py`

### Modifying Observation Logic

1. Core logic: `peeka/core/injector.py` → `_create_wrapper()`
2. Data formatting: `peeka/core/injector.py` → `_format_value()`
3. Buffering: `peeka/core/observer.py` → `ObservationManager`
4. Update tests: `tests/test_injector.py`

### Adding Condition Expression Features

1. Modify: `peeka/core/safeeval/simpleeval.py`
2. **CRITICAL**: Ensure no code injection vulnerabilities
3. Add tests: `tests/test_injector.py` → `test_inject_with_condition()`
4. Document supported syntax in README.md

## CI/CD

### GitHub Actions

Workflow: `.github/workflows/test-compatibility.yml`

**Runs on**:

- Push to `master` branch
- Pull requests to `master`

**Test matrix**: Python 3.9, 3.10, 3.11, 3.12, 3.13, 3.14

**Steps**:

1. Install GDB + python3-dbg (for <3.14)
2. Configure ptrace_scope = 0
3. Run `python3 tests/simple_compat_test.py`
4. Run `pytest tests/` (if available)

## Security Considerations

### Code Injection Prevention

**ALWAYS**:

- Use `simpleeval` for user expressions
- Validate function patterns before injection
- Sanitize error messages (avoid leaking internal state)

**NEVER**:

- Use `eval()` on user input
- Execute arbitrary code from network input
- Trust file paths from untrusted sources

### Resource Limits

- Observation count: Use `times` parameter
- Buffer size: `PEEKA_BUFFER_SIZE` (default 10000)
- Connection timeout: `PEEKA_TIMEOUT` (default 30s)

### Permissions

- Attach requires: CAP_SYS_PTRACE or same UID
- Socket files: 0600 permissions (owner only)
- Agent inherits target process privileges

## Environment Variables

| Variable            | Default | Description                     |
|---------------------|---------|---------------------------------|
| `PEEKA_SOCKET_DIR`  | `/tmp`  | Directory for Unix socket files |
| `PEEKA_TIMEOUT`     | `30`    | Command timeout (seconds)       |
| `PEEKA_BUFFER_SIZE` | `10000` | Max observations in memory      |

## References

- Architecture: [ARCHITECTURE.md](ARCHITECTURE.md)
- README: [README.md](README.md)
- PEP 768: https://peps.python.org/pep-0768/
- simpleeval: https://github.com/danthedeckie/simpleeval
- Inspiration: [Alibaba Arthas](https://github.com/alibaba/arthas)
