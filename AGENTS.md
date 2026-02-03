# Peeka Developer Guide (for AI Coding Agents)

Runtime diagnostic tool for Python 3.9-3.14+ using PEP 768 remote debugging.

## Quick Reference

### Build & Test Commands

```bash
# Install
pip install -e .                    # Development mode
pip install -e ".[tui]"             # With TUI (textual)
uv pip install -e .                 # Using uv

# Test - ALL tests
pytest tests/

# Test - SINGLE file
pytest tests/test_injector.py -v

# Test - SINGLE class
pytest tests/test_injector.py::TestDecoratorInjector -v

# Test - SINGLE function
pytest tests/test_injector.py::TestDecoratorInjector::test_inject_function -v

# Test - Quick compatibility (no pytest)
python3 tests/simple_compat_test.py

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

### Docstrings: Minimal, only when needed

- Public API classes/methods
- Security-critical code
- Complex algorithms

Skip for: private helpers, simple getters, tests.

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

## Key Files to Know

- `peeka/core/injector.py` - Function wrapping logic
- `peeka/core/agent.py` - Command registration
- `peeka/commands/base.py` - Command interface
- `peeka/core/safeeval/simpleeval.py` - Expression security
- `tests/test_injector.py` - Core test patterns
