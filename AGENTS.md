# Peeka Developer Guide (for AI Coding Agents)

Runtime diagnostic tool for Python 3.8-3.14+ using PEP 768 remote debugging.

## Build & Test Commands

```bash
uv pip install -e .                 # Core only
uv pip install -e ".[tui]"         # With TUI (textual)
uv sync --dev                      # Dev (pytest, textual, testcontainers, docker, pytest-cov, pytest-timeout)

pytest tests/ -v                                          # All tests
pytest tests/ -v -m "not e2e and not container"           # CI-safe (no ptrace/docker)
pytest tests/test_injector.py -v                          # Single file
pytest tests/test_injector.py::TestDecoratorInjector::test_inject_function -v  # Single test
pytest tests/e2e/ -v                                      # E2E (requires ptrace)
ruff check peeka/                                         # Lint (no enforced config)
```

Pytest config: `pytest.ini` (timeout=60s, filterwarnings ignores DeprecationWarning).

## Entry Points

- `peeka-cli` → CLI (`peeka/cli/main.py`, argparse)
- `peeka` → TUI (`peeka/tui/__init__.py`, requires textual)

## Code Style

### Imports: stdlib → third-party → local (blank line between groups, alphabetical within)

```python
import json
import threading
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

import textual  # third-party (when applicable)

from peeka.commands.base import BaseCommand
from peeka.core.agent import PeekaAgent
```

`typing` imports belong in the stdlib group. Third-party imports (e.g. `textual`, `pytest`) go between stdlib and local.

**Deferred imports**: Import inside methods to avoid circular deps (see `agent.py._register_handlers()`).

### TYPE_CHECKING for circular imports

```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from peeka.core.agent import PeekaAgent

class Command:
    def __init__(self, agent: "PeekaAgent"):  # String literal annotation
        self.agent = agent
```

### Type Hints: REQUIRED on all function signatures

Use `typing` module types (`Dict`, `Optional`, `Any`, `Callable`), not PEP 604 `X | None`.

### Docstrings: Google style (Args, Returns, Raises) on public non-trivial methods

### Naming: Classes=PascalCase, functions=snake_case, private=`_prefix`, constants=UPPER_SNAKE

### Error Handling (layered pattern)

```python
# Core modules: RAISE exceptions
if target_info is None:
    raise ValueError(f"Cannot find target: {pattern}")

# Commands: CATCH and return structured dicts
def execute(self, params: dict) -> dict:
    try:
        return {"status": "success", "data": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Agent: wraps command execution, adds traceback to error responses
# Best-effort restoration: swallow exceptions to protect target process
```

### Thread Safety

Use `threading.Lock` for shared mutable state in agent/injector/TUI views. Keep critical sections small.
TUI streaming views use double-checked locking for lazy client initialization (`_ensure_stream_client()`).

### Logging

- **Injected agent code**: `print("[peeka Agent] ...")` — no logging module, minimal footprint
- **CLI output**: `OutputFormatter` from `peeka/core/output.py` for structured JSONL
- **Commands**: Python `logging` module where appropriate

## Architecture

```
peeka/
├── cli/main.py              # CLI entry point (argparse)
├── tui/
│   ├── app.py               # PeekaApp main
│   ├── completion.py         # CLI/TUI completion helper
│   ├── screens/             # process_selector, main, help
│   ├── views/               # dashboard, watch, stack, trace, monitor,
│   │                        #   memory, logger, inspect, thread, top
│   └── widgets/             # autocomplete_input
├── core/
│   ├── agent.py             # PeekaAgent - injected into target, Unix socket server
│   ├── attach.py            # Process attachment (PEP 768 + GDB fallback)
│   ├── injector.py          # DecoratorInjector - runtime function wrapping
│   ├── client.py            # AgentClient, StreamingAgentClient
│   ├── observer.py          # ObservationManager
│   ├── monitor.py           # Performance monitoring
│   ├── output.py            # OutputFormatter (JSONL)
│   └── safeeval/            # Safe expression evaluation (simpleeval)
├── commands/                # BaseCommand subclasses
│   ├── base.py              # ABC: execute() + validate_params()
│   ├── watch.py, stack.py, trace.py, monitor.py, memory.py
│   ├── logger.py, search.py, reset.py, vmtool.py
│   ├── thread.py, top.py
│   └── complete.py, detach.py
└── utils/
    ├── formatters.py        # Value formatting utilities
    └── patterns.py          # Pattern matching (wildcards)
```

### Adding a New Command

1. Create `peeka/commands/mycommand.py` extending `BaseCommand`
2. Implement `execute(self, params: Dict[str, Any]) -> Dict[str, Any]`
3. Register in `peeka/core/agent.py` → `_register_handlers()` (import inside method)
4. Add CLI subcommand in `peeka/cli/main.py`
5. Write tests in `tests/test_mycommand.py`

## Security — CRITICAL

**NEVER use `eval()` on user input.** Use `peeka.core.safeeval.simpleeval.SimpleEval` instead.

## TUI Patterns (Textual)

```python
worker = self.run_worker(self._stream_observations(watch_id), thread=True, exclusive=False)
self.app.call_from_thread(self._update_ui, data)  # From background thread
widget = app.screen.query_one("#widget-id", WidgetType)  # After push_screen
```

Streaming views (watch, trace, stack, monitor) create dedicated `StreamingAgentClient` connections
lazily via `_ensure_stream_client()` with thread-safe double-checked locking. Non-streaming views
(logger, memory, inspect, thread) share the main client.

## Testing Patterns

Tests use **classes** with pytest fixtures. Custom `MockAgent` classes (not unittest.mock).

```python
class MockAgent:
    def __init__(self):
        self._observations = []

    def _send_observation(self, observation):
        self._observations.append(observation)

class TestMyFeature:
    @pytest.fixture
    def mock_agent(self):
        return MockAgent()
    def test_basic(self, mock_agent):
        assert function_under_test() == expected
```

Dynamic test modules: insert into `sys.modules`, clean up in teardown.

### Test Markers

| Marker        | Meaning                 |
|---------------|-------------------------|
| `unit`        | Fast, no external deps  |
| `integration` | In-process agent/client |
| `e2e`         | Requires ptrace         |
| `container`   | Requires Docker         |
| `tui`         | Requires textual        |
| `slow`        | >10s runtime            |
| `py314`       | Requires Python 3.14+   |
| `gdb`         | Requires GDB            |

## Python Version Support

| Version  | Attach Mechanism          | Requirements                     |
|----------|---------------------------|----------------------------------|
| 3.14+    | PEP 768 `sys.remote_exec` | None                             |
| 3.8-3.13 | GDB + ptrace fallback     | GDB, python3-dbg, CAP_SYS_PTRACE |

## Docker Test Images

Two test images in `docker/` for testcontainers and manual verification. All require `--cap-add=SYS_PTRACE`.

| Image | Dockerfile | Python | Purpose |
|-------|------------|--------|---------|
| `peeka-test:gdb` | `Dockerfile.test-gdb` | 3.12 | GDB + ptrace attach testing |
| `peeka-test:py314` | `Dockerfile.test-py314` | 3.14 | PEP 768 native attach testing |

```bash
# Build (from project root) — --network=host required (see note below)
docker build --network=host -f docker/Dockerfile.test-gdb -t peeka-test:gdb .
docker build --network=host -f docker/Dockerfile.test-py314 -t peeka-test:py314 .

# Run container tests (testcontainers auto-manages images)
pytest tests/container/test_attach.py -v -m container --timeout=180
```

**Network note**: `--network=host` lets Docker route through host proxy (Clash on `127.0.0.1:7897`) to USTC mirrors. No proxy env vars in Dockerfiles.

**TUI in containers**: Test images have `TERM=xterm-256color` and `COLORTERM=truecolor` baked in. No manual terminal env setup needed.

## Key Files

- `peeka/core/injector.py` — Function wrapping, decorator injection, value formatting
- `peeka/core/agent.py` — Command registration, Unix socket server, injected into target
- `peeka/core/safeeval/simpleeval.py` — Expression security, safe AST evaluation
- `peeka/core/output.py` — OutputFormatter for structured JSONL CLI output
- `tests/e2e/conftest.py` — E2E fixtures (target process lifecycle, ptrace checks)

## Git Conventions

- **Commit style**: Semantic (`feat:`, `fix:`, `perf:`, `docs:`, `test:`, `refactor:`)
- **Scope**: Module name in parens — `fix(tui):`, `feat(cli):`, `test(tui):`
- **Language**: English
- **Commit after every completed task**: NEVER leave work as unstaged changes. After finishing any implementation (feature, fix, refactor), immediately commit. Uncommitted work is invisible to git and will be lost on branch switches, checkouts, or crashes.

## Python tool

You can use `uv` (from `uvtools`) to run commands in a consistent environment. It automatically activates the virtual environment and ensures dependencies are available.
