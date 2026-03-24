# Peeka Developer Guide (for AI Coding Agents)

Runtime diagnostic tool for Python 3.8-3.14+ using PEP 768 remote debugging.

## Build & Test Commands

This project uses **uv** as the package manager. Always prefix Python commands with `uv run` to ensure you're using the correct project environment:

```bash
uv pip install -e .                 # Core only
uv pip install -e ".[tui]"         # With TUI (textual)
uv sync --dev                      # Dev (pytest, textual, testcontainers, docker, pytest-cov, pytest-timeout)

uv run pytest tests/ -v                                          # All tests
uv run pytest tests/ -v -m "not e2e and not container"           # CI-safe (no ptrace/docker)
uv run pytest tests/test_injector.py -v                          # Single file
uv run pytest tests/test_injector.py::TestDecoratorInjector::test_inject_function -v  # Single test
uv run pytest tests/e2e/ -v                                      # E2E (requires ptrace)
uv run ruff check peeka/                                         # Lint (no enforced config)
```

**Rule**: Any Python command (pytest, ruff, python, etc.) should be run with `uv run <command>` to use the project's virtual environment.

Pytest config: `pytest.ini` (timeout=60s, filterwarnings ignores DeprecationWarning).

## Entry Points

- `peeka-cli` → CLI (`peeka/cli/main.py`, argparse)
- `peeka` → TUI (`peeka/tui/__init__.py`, requires textual)

## Code Style

### Imports: stdlib → third-party → local (blank line between groups, alphabetical within)

```python
import json
from typing import Any, Dict, Optional

import textual  # third-party

from peeka.core.agent import PeekaAgent
```

`typing` imports belong in the stdlib group. Use `TYPE_CHECKING` + string annotations for circular imports. Import inside methods when needed (see `agent.py._register_handlers()`).

### Type Hints & Docstrings

- **Required** on public and non-trivial function signatures; small private callbacks may omit
- Use `typing` module types (`Dict`, `Optional`, `Any`, `Callable`), not PEP 604 `X | None`
- Google-style docstrings (Args, Returns, Raises) on public non-trivial methods
- Naming: Classes=PascalCase, functions=snake_case, private=`_prefix`, constants=UPPER_SNAKE

### Error Handling (layered pattern)

- **Core modules**: RAISE exceptions (e.g. `raise ValueError(...)`)
- **Commands**: CATCH and return `{"status": "success"|"error", ...}` dicts
- **Agent**: wraps command execution, adds traceback; swallows exceptions for best-effort restoration

### Thread Safety & Logging

Use `threading.Lock` for shared mutable state in agent/injector/TUI views. Keep critical sections small.
TUI streaming views use double-checked locking for lazy client initialization (`_ensure_stream_client()`).

- **Injected agent code**: `print("[peeka Agent] ...")` — no logging module, minimal footprint
- **CLI output**: `OutputFormatter` from `peeka/core/output.py` for structured JSONL
- **Commands/TUI views**: Python `logging` module

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

### Security

**NEVER use `eval()` on user input.** Use `peeka.core.safeeval.simpleeval.SimpleEval` instead.

## TUI Patterns (Textual)

Streaming views (watch, trace, stack, monitor) create dedicated `StreamingAgentClient` connections
lazily via `_ensure_stream_client()` with thread-safe double-checked locking. Non-streaming views
(logger, memory, inspect, thread) share the main client. Use `self.app.call_from_thread()` for
UI updates from background threads.

## Testing Patterns

Most tests use **class-based** tests with pytest fixtures. Custom `MockAgent` / `MockStreamingAgentClient`
classes (not unittest.mock). Dynamic test modules insert into `sys.modules`, clean up in teardown.

### Test Markers (declared in pytest.ini)

| Marker        | Meaning                 | Usage                                        |
|---------------|-------------------------|----------------------------------------------|
| `tui`         | Requires textual        | Heavily used in `tests/tui/`                 |
| `unit`        | Fast, no external deps  | Sparsely applied                             |
| `e2e`         | Requires ptrace         | By directory (`tests/e2e/`) + conftest       |
| `container`   | Requires Docker         | By directory (`tests/container/`) + conftest |
| `py314`       | Requires Python 3.14+   | —                                            |
| `gdb`         | Requires GDB            | —                                            |

### Key Test Fixtures

- `tests/tui/conftest.py` — `MockStreamingAgentClient`, shared TUI test mocks
- `tests/e2e/conftest.py` — `has_ptrace_permission`, `has_pep768`, `has_gdb`, `target_process`
- `tests/container/conftest.py` — `gdb_container`, `py314_container`, `container_target`

## Python Version Support

| Version  | Attach Mechanism          | Requirements                     |
|----------|---------------------------|----------------------------------|
| 3.14+    | PEP 768 `sys.remote_exec` | None                             |
| 3.8-3.13 | GDB + ptrace fallback     | GDB, python3-dbg, CAP_SYS_PTRACE |

## Docker Test Images

Two test images in `docker/` for testcontainers and manual verification. All require `--cap-add=SYS_PTRACE`.

| Image | Dockerfile | Python | Purpose |
|-------|------------|--------|---------|
| `peeka-test:3.8` | `test.Dockerfile-3.8` | 3.8 | GDB + ptrace attach testing |
| `peeka-test:3.12` | `test.Dockerfile-3.12` | 3.12 | GDB + ptrace attach testing |
| `peeka-test:3.14` | `test.Dockerfile-3.14` | 3.14 | PEP 768 native attach testing |

Build with `--network=host` (for proxy routing). Run: `uv run pytest tests/container/test_attach.py -v -m container --timeout=180`

## Git Conventions

- **Commit style**: Semantic (`feat:`, `fix:`, `perf:`, `docs:`, `test:`, `refactor:`)
- **Scope**: Module name in parens — `fix(tui):`, `feat(cli):`, `test(tui):`
- **Language**: English
- **Commit after every completed task**: NEVER leave work as unstaged changes.
