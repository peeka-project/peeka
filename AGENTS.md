# Peeka Developer Guide (for AI Coding Agents)

Runtime diagnostic tool for Python 3.9-3.14+ using PEP 768 remote debugging.

## Build & Test Commands

```bash
# Install
pip install -e .                    # Development mode
pip install -e ".[tui]"             # With TUI (textual)
uv pip install -e .                 # Using uv (preferred)

# Test - Run ALL tests
pytest tests/ -v

# Test - CI-safe (excludes e2e/container)
pytest tests/ -v -m "not e2e and not container"

# Test - SINGLE file
pytest tests/test_injector.py -v

# Test - SINGLE test function
pytest tests/test_injector.py::TestDecoratorInjector::test_inject_function -v

# Test - E2E tests (requires ptrace permission)
pytest tests/e2e/ -v

# Test - TUI E2E tests (requires textual + ptrace)
pytest tests/e2e/test_tui_e2e.py -v

# Quick compatibility check (no pytest)
python3 tests/simple_compat_test.py

# Lint (optional, not enforced)
ruff check peeka/
```

## Entry Points

- `peeka-cli` → CLI interface (`peeka/cli/main.py`)
- `peeka` → TUI interface (`peeka/tui/__init__.py`, requires textual)

## Code Style

### Imports: stdlib → third-party → local (alphabetical within groups)

```python
import json
import threading
from typing import Any, Dict, Optional, TYPE_CHECKING

import pytest

from peeka.commands.base import BaseCommand
from peeka.core.agent import PeekaAgent
```

### Type Hints: REQUIRED on all function signatures

```python
def inject(self, pattern: str, config: Dict[str, Any]) -> str:
    pass

def _send_observation(self, observation: Dict[str, Any]) -> None:
    pass
```

### TYPE_CHECKING for circular imports

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent

class Command:
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

### Error Handling

```python
# Specific exceptions with context
if target_info is None:
    raise ValueError(f"Cannot find target: {pattern}")

# Agent/CLI: return structured error responses
def execute(self, params: dict) -> dict:
    try:
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Best-effort restoration (don't break target process)
try:
    self._restore_function(target)
except Exception:
    pass  # Log but don't propagate
```

## Architecture

```
peeka/
├── cli/main.py           # CLI entry point
├── tui/                   # TUI (requires textual)
│   ├── app.py            # PeekaApp main
│   ├── screens/          # Process selector, main
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
    └── ...
```

### Adding a New Command

1. Create `peeka/commands/mycommand.py` extending `BaseCommand`
2. Register in `peeka/core/agent.py` → `_register_handlers()`
3. Add CLI in `peeka/cli/main.py`
4. Write tests in `tests/test_mycommand.py`

## Security - CRITICAL

**NEVER use `eval()` on user input:**

```python
# GOOD - Safe evaluation
from peeka.core.safeeval.simpleeval import SimpleEval
evaluator = SimpleEval()
result = evaluator.eval(condition_expr)

# BAD - Code injection vulnerability
result = eval(condition_expr)  # NEVER DO THIS
```

## TUI Patterns (Textual Framework)

### Thread-Safe UI Updates

```python
# Background worker for blocking I/O
worker = self.run_worker(
    self._stream_observations(watch_id),
    thread=True,
    exclusive=False
)

# From background thread - MUST use call_from_thread
self.app.call_from_thread(self._update_ui, data)
```

### Widget Queries

```python
# After push_screen, query from screen not app
widget = app.screen.query_one("#widget-id", WidgetType)

# Get text from Static widget
text = widget.render().plain
```

## Testing Patterns

```python
class TestMyFeature:
    @pytest.fixture
    def mock_agent(self):
        return MockAgent()

    def test_basic(self, mock_agent):
        result = function_under_test()
        assert result == expected

    def test_error(self):
        with pytest.raises(ValueError, match="expected"):
            function_under_test(invalid)
```

### Test Markers

- `@pytest.mark.e2e` - Requires process attachment
- `@pytest.mark.tui` - Requires textual
- `@pytest.mark.container` - Requires Docker

## Python Version Support

| Version  | Attach Mechanism          | Requirements                     |
|----------|---------------------------|----------------------------------|
| 3.14+    | PEP 768 `sys.remote_exec` | None                             |
| 3.9-3.13 | GDB + ptrace fallback     | GDB, python3-dbg, CAP_SYS_PTRACE |

## Key Files

- `peeka/core/injector.py` - Function wrapping, decorator pattern
- `peeka/core/agent.py` - Command registration, main loop
- `peeka/core/safeeval/simpleeval.py` - Expression security
- `peeka/tui/views/watch.py` - Worker threading example
- `tests/e2e/conftest.py` - E2E test fixtures
