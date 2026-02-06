# Peeka Developer Guide (for AI Coding Agents)

Runtime diagnostic tool for Python 3.9-3.14+ using PEP 768 remote debugging.

## Quick Reference

### Build & Test Commands

```bash
# Install
pip install -e .                    # Development mode
pip install -e ".[tui]"             # With TUI (textual)
pip install -e ".[dev]"             # With dev dependencies (CI-style)
uv pip install -e .                 # Using uv

# Test - ALL tests
pytest tests/ -v

# Test - CI-safe (excludes e2e/container tests)
pytest tests/ -v --tb=short -m "not e2e and not container" --timeout=30

# Test - SINGLE file
pytest tests/test_injector.py -v

# Test - SINGLE class
pytest tests/test_injector.py::TestDecoratorInjector -v

# Test - SINGLE function
pytest tests/test_injector.py::TestDecoratorInjector::test_inject_function -v

# Test - Quick compatibility (no pytest required)
python3 tests/simple_compat_test.py

# Test - Container tests (requires Docker)
pytest tests/container/ -v --timeout=180

# Lint & Type check (optional, not enforced)
ruff check peeka/
mypy peeka/
```

### Entry Points

- `peeka-cli` → CLI interface (`peeka/cli/main.py`)
- `peeka` → TUI interface (`peeka/tui/__init__.py`, requires textual)

## Code Style

### Import Order: stdlib → third-party → local (alphabetical)

```python
import json
import sys
import threading
from typing import Any, Dict, Optional, TYPE_CHECKING

import pytest  # third-party

from peeka.commands.base import BaseCommand  # local, absolute
from peeka.core.agent import PeekaAgent
```

### Type Hints: REQUIRED on all function signatures

```python
def inject(self, pattern: str, config: Dict[str, Any]) -> str:
    pass

def _send_observation(self, observation: Dict[str, Any]) -> None:
    pass
```

Use `TYPE_CHECKING` for circular imports:

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent

class DecoratorInjector:
    def __init__(self, agent: "PeekaAgent"):  # String literal
        self.agent = agent
```

### Naming Conventions

| Type              | Pattern     | Example                         |
|-------------------|-------------|---------------------------------|
| Classes           | PascalCase  | `PeekaAgent`, `WatchCommand`    |
| Functions/Methods | snake_case  | `inject()`, `_resolve_target()` |
| Private           | `_prefix`   | `_send_observation()`, `_lock`  |
| Constants         | UPPER_SNAKE | `BASIC_ALLOWED_ATTRS`           |

### Docstrings: Required for public APIs

Use docstrings for:
- Modules (brief description at top)
- Public classes and methods
- Security-critical code
- Complex algorithms

Format (Google/Sphinx-style):
```python
def inject(self, pattern: str, config: Dict[str, Any]) -> str:
    """
    Inject observation logic into a target function.
    
    Args:
        pattern: Module.Class.method pattern
        config: Configuration with depth, times, condition
    
    Returns:
        Watch ID for the injected observation
    
    Raises:
        ValueError: If target pattern not found
    """
```

Skip docstrings for: private helpers (`_method`), simple getters, test functions.

### Error Handling

```python
# Specific exceptions with context
if target_info is None:
    raise ValueError(f"Cannot find target: {pattern}")

# Clean up in finally blocks
try:
    result = handler.execute(command)
finally:
    conn.close()

# Agent/CLI boundaries: structured error responses
def execute(self, params: dict) -> dict:
    try:
        # ... command logic
        return {"status": "success", "data": result}
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "traceback": traceback.format_exc()
        }

# Best-effort restoration (don't break target process)
try:
    self._restore_function(target)
except Exception:
    pass  # Log but don't propagate
```

## Architecture

### Module Structure

```
peeka/
├── cli/main.py           # CLI entry point
├── tui/                   # TUI (optional, requires textual)
│   ├── app.py            # PeekaApp main class
│   ├── screens/          # Process selector, main, help
│   └── views/            # Dashboard, watch, stack, etc.
├── core/
│   ├── agent.py          # PeekaAgent coordinator
│   ├── attach.py         # Process attachment (PEP 768 + GDB)
│   ├── injector.py       # Function instrumentation
│   ├── client.py         # AgentClient, StreamingAgentClient
│   └── safeeval/         # Safe expression evaluation
└── commands/             # BaseCommand subclasses
    ├── base.py           # Abstract base
    ├── watch.py          # Function observation
    ├── stack.py          # Call stack tracing
    └── ...
```

### Adding a New Command

1. Create `peeka/commands/mycommand.py`:

```python
from peeka.commands.base import BaseCommand

class MyCommand(BaseCommand):
    def execute(self, params: dict) -> dict:
        return {"status": "success", "data": {...}}
```

2. Register in `peeka/core/agent.py` → `_register_handlers()`:

```python
from peeka.commands.mycommand import MyCommand

self.command_handlers["mycmd"] = MyCommand(self)
```

3. Add CLI in `peeka/cli/main.py`
4. Write tests in `tests/test_mycommand.py`

### Communication Protocol

Format: `[4-byte length][JSON payload]`

```python
# Send
message = json.dumps(data).encode("utf-8")
conn.sendall(len(message).to_bytes(4, "big"))
conn.sendall(message)

# Receive
length = int.from_bytes(conn.recv(4), "big")
data = json.loads(conn.recv(length).decode("utf-8"))
```

Socket convention: `/tmp/peeka_{PID}.sock`

## Security

### CRITICAL: Never use `eval()` on user input

```python
# GOOD - Safe evaluation
from peeka.core.safeeval.simpleeval import SimpleEval

evaluator = SimpleEval()
evaluator.names = {"params": args}
result = evaluator.eval(condition_expr)

# BAD - Code injection vulnerability
result = eval(condition_expr)  # NEVER
```

### Protected Resources

- Socket files: 0600 permissions
- Attach requires: CAP_SYS_PTRACE or same UID
- Buffer limits: `PEEKA_BUFFER_SIZE` (default 10000)

## Testing Patterns

```python
import pytest
import sys

class TestMyFeature:
    @pytest.fixture
    def mock_agent(self):
        return MockAgent()

    def test_basic(self, mock_agent):
        # Arrange → Act → Assert
        result = function_under_test()
        assert result == expected

    def test_error(self):
        with pytest.raises(ValueError, match="expected"):
            function_under_test(invalid)
```

### Module Mocking

```python
@pytest.fixture
def mock_module(self):
    test_module = type(sys)("test_module")
    test_module.func = lambda x: x * 2
    sys.modules["test_module"] = test_module
    yield test_module
    del sys.modules["test_module"]
```

## Python Version Support

| Version  | Attach Mechanism          | Requirements                     |
|----------|---------------------------|----------------------------------|
| 3.14+    | PEP 768 `sys.remote_exec` | None                             |
| 3.9-3.13 | GDB + ptrace fallback     | GDB, python3-dbg, CAP_SYS_PTRACE |

## Environment Variables

| Variable            | Default | Description                |
|---------------------|---------|----------------------------|
| `PEEKA_SOCKET_DIR`  | `/tmp`  | Unix socket directory      |
| `PEEKA_TIMEOUT`     | `30`    | Command timeout (seconds)  |
| `PEEKA_BUFFER_SIZE` | `10000` | Max observations in memory |

## TUI-Specific Patterns (Textual Framework)

### Thread-Safe UI Updates

```python
from textual.worker import Worker, get_current_worker

# Background worker with threading
worker = self.run_worker(
    self._stream_observations(watch_id),
    thread=True,        # Run in separate thread
    exclusive=False     # Allow multiple workers
)

# Thread-safe UI updates from background thread
def _stream_observations(self, watch_id: str):
    worker = get_current_worker()
    
    for observation in blocking_generator():
        if worker.is_cancelled:
            break
        
        # MUST use call_from_thread for UI updates
        self.app.call_from_thread(
            self._update_ui, observation
        )

def _update_ui(self, data):
    """Called from main thread - safe to update widgets."""
    self.query_one("#log", RichLog).write(data)
```

### Worker Management

- Use `thread=True` for blocking I/O operations
- Store worker reference for cancellation: `self._workers[id] = worker`
- Cancel workers in cleanup: `worker.cancel()`
- Always use `call_from_thread()` to update UI from workers

## Common Patterns

### Thread Safety

```python
import threading

class Manager:
    def __init__(self):
        self._lock = threading.Lock()
        self._data = {}
    
    def update(self, key, value):
        with self._lock:  # Context manager pattern
            self._data[key] = value
```

### Observer Pattern

```python
def subscribe(self, callback: Callable) -> Callable:
    """Subscribe returns unsubscribe function."""
    self._subscribers.append(callback)
    
    def unsubscribe():
        self._subscribers.remove(callback)
    
    return unsubscribe  # Convenient cleanup
```

### Deferred Imports (Avoid Circular Dependencies)

```python
# At module level - avoid circular import
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent

class Command:
    def __init__(self, agent: "PeekaAgent"):  # String literal
        self.agent = agent

# Or defer to method
def _register_handlers(self):
    from peeka.commands.watch import WatchCommand  # Import here
    self.handlers["watch"] = WatchCommand(self)
```

## Key Files to Know

- `peeka/core/injector.py` - Function wrapping logic, decorator pattern
- `peeka/core/agent.py` - Command registration, main agent loop
- `peeka/commands/base.py` - Command interface, validation pattern
- `peeka/core/safeeval/simpleeval.py` - Expression security (NEVER use eval!)
- `peeka/core/observer.py` - Observer pattern, thread-safe subscription
- `peeka/core/client.py` - Client-side streaming, socket protocol
- `peeka/tui/views/watch.py` - TUI worker threading, call_from_thread usage
- `tests/test_injector.py` - Core test patterns, module mocking
