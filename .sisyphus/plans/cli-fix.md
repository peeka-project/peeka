# CLI Fix & Test Alignment

## Context

### Original Request
Fix the CLI (`peeka/cli.py`) to work with the current core API and fix broken test files.

### Interview Summary
**Key Discussions**:
- CLI imports non-existent modules (`attachment`, `watcher`) - need to use `ProcessAttacher` and `AgentClient`
- User wants full Arthas flag support: `-b`, `-e`, `-s`, `-f`, `-x`, `-n`, `--condition-express`
- User wants JSONL output format for streaming observations
- Test files have wrong imports and outdated API calls
- Verification via `pytest tests/`

**Research Findings**:
- `DecoratorInjector.inject(pattern, watch_config)` takes config dict
- `WatchCommand` expects `PeekaAgent` as constructor arg
- 4 tests currently fail in test_injector.py due to field name mismatches
- `target` self-capture has a bug (checks `hasattr(func, "__self__")` which is always False for unbound methods)

### Metis Review
**Identified Gaps** (addressed):
- No detach functionality exists → Will stub with "not supported" message
- Test field names inconsistent → Will update to Arthas-compatible names
- Interactive mode complexity → Keep minimal
- target self-capture bug → Will fix in injector

---

## Work Objectives

### Core Objective
Make the CLI functional with the current core API and ensure all tests pass.

### Concrete Deliverables
- Working `peeka watch <pid> "pattern" [flags]` command
- Working `peeka attach <pid>` command with interactive mode
- All tests in `tests/` passing (0 failures)
- Arthas-compatible CLI flags

### Definition of Done
- [ ] `uv run pytest tests/` → 0 failures
- [ ] `peeka watch --help` shows Arthas flags (-b, -e, -s, -f, -x, -n)
- [ ] CLI can attach to a test process and stream observations

### Must Have
- Fix CLI imports to use `ProcessAttacher`, `AgentClient`, `StreamingAgentClient`
- Add Arthas CLI flags: `-b`, `-e`, `-s`, `-f`, `-x`, `-n`, `--condition-express`
- JSONL output format for observations
- Graceful Ctrl+C handling
- All 25 tests in test_injector.py passing

### Must NOT Have (Guardrails)
- DO NOT add new features beyond what core already supports
- DO NOT modify the communication protocol
- DO NOT add new dependencies beyond what's in pyproject.toml
- DO NOT implement detach (agent runs until target process exits)
- DO NOT change Arthas-compatible field names in injector

---

## Verification Strategy (MANDATORY)

### Test Decision
- **Infrastructure exists**: YES (pytest configured in pyproject.toml)
- **User wants tests**: YES (run pytest after changes)
- **Framework**: pytest

### Verification Commands
```bash
# Primary verification - all tests must pass
uv run pytest tests/ -v

# Quick smoke test for CLI
python -c "from peeka.cli import create_parser; p = create_parser(); print(p.format_help())"
```

---

## Task Flow

```
Task 1 (Fix injector bug) → Task 2 (Fix test_injector.py) → Task 6 (Verify)
                                                         ↗
Task 3 (Fix test_compatibility.py) ─────────────────────
                                                         ↗
Task 4 (Fix manual_test.py) ────────────────────────────
                                                         ↗
Task 5 (Rewrite CLI) ───────────────────────────────────
```

## Parallelization

| Group | Tasks | Reason |
|-------|-------|--------|
| A | 3, 4, 5 | Independent files after Task 1-2 complete |

| Task | Depends On | Reason |
|------|------------|--------|
| 2 | 1 | test_injector.py tests will fail until injector bug is fixed |
| 3, 4, 5 | 1, 2 | Can run in parallel once core tests pass |
| 6 | All | Final verification |

---

## TODOs

- [x] 1. Fix target self-capture bug in injector

  **What to do**:
  - In `peeka/core/injector.py`, line 319, the condition `hasattr(func, "__self__")` is always False for unbound methods
  - Change detection logic to check if first argument is an instance of a class that has this method
  - Alternative: Check if `func` was resolved from a class (not module) during `_resolve_target`

  **Must NOT do**:
  - Do not change the observation field names
  - Do not modify the wrapper signature

  **Parallelizable**: NO (dependency for Task 2)

  **References**:
  - `peeka/core/injector.py:318-319` - Current buggy detection: `target_self = args[0] if args and hasattr(func, "__self__") else None`
  - `peeka/core/injector.py:155-180` - `_resolve_target()` method that knows if target is from a class
  - `tests/test_injector.py:510-539` - Test case `test_target_self_capture` that expects `target` to be captured

  **Acceptance Criteria**:
  - [x] `uv run pytest tests/test_injector.py::TestArthasCompatibility::test_target_self_capture -v` → PASS
  - [x] When watching `module.Class.method`, observations include `target` with class instance attributes

  **Commit**: YES
  - Message: `fix(injector): correctly capture self for instance methods`
  - Files: `peeka/core/injector.py`
  - Pre-commit: `uv run pytest tests/test_injector.py::TestArthasCompatibility::test_target_self_capture -v`

---

- [x] 2. Update test_injector.py field names to Arthas-compatible

  **What to do**:
  - Change `obs["args"]` → `obs["params"]` (lines 48, 74)
  - Change `obs["result"]` → `obs["returnObj"]` (line 49)
  - Change `obs["error"]` → `obs["throwExp"]` (line 190)
  
  **Must NOT do**:
  - Do not change tests that already use correct field names
  - Do not modify test logic, only field name references

  **Parallelizable**: NO (depends on Task 1)

  **References**:
  - `tests/test_injector.py:48-49` - `test_inject_function` uses old names
  - `tests/test_injector.py:74` - `test_inject_with_condition` uses old names
  - `tests/test_injector.py:190` - `test_captures_exceptions` uses old names
  - `tests/test_injector.py:316-317, 345, 385, 498-500` - Tests already using correct Arthas names (reference)
  - `peeka/core/injector.py:367-376` - Actual field names in observation output

  **Acceptance Criteria**:
  - [x] `uv run pytest tests/test_injector.py -v` → 25 passed, 0 failed

  **Commit**: YES
  - Message: `test(injector): update field names to Arthas-compatible format`
  - Files: `tests/test_injector.py`
  - Pre-commit: `uv run pytest tests/test_injector.py -v`

---

- [ ] 3. Fix test_compatibility.py imports and API

  **What to do**:
  - Change `from peeka.core.commands.watch import WatchCommand` → `from peeka.commands.watch import WatchCommand`
  - Create a MockAgent class similar to `tests/test_injector.py:6-11` that has required attributes
  - Update `WatchCommand(observer)` → `WatchCommand(mock_agent)` where mock_agent has `.injector` and `.observer`

  **Must NOT do**:
  - Do not remove any test cases
  - Do not add new dependencies

  **Parallelizable**: YES (with 4, 5)

  **References**:
  - `tests/test_compatibility.py:115-116, 160-164, 212-216` - Wrong import and constructor
  - `tests/test_injector.py:6-11` - MockAgent pattern to follow:
    ```python
    class MockAgent:
        def __init__(self):
            self._observations = []
        def _send_observation(self, obs):
            self._observations.append(obs)
    ```
  - `peeka/commands/watch.py:39-41` - WatchCommand expects agent with `.injector` and `.observer`

  **Acceptance Criteria**:
  - [ ] `uv run pytest tests/test_compatibility.py -v` → All tests pass or skip (attach tests may skip on CI)
  - [ ] No import errors on module load

  **Commit**: YES
  - Message: `test(compatibility): fix imports and use MockAgent pattern`
  - Files: `tests/test_compatibility.py`
  - Pre-commit: `uv run pytest tests/test_compatibility.py -v`

---

- [ ] 4. Fix manual_test.py API calls

  **What to do**:
  - Create MockAgent class for injector initialization
  - Change `DecoratorInjector(observer)` → `DecoratorInjector(mock_agent)`
  - Change `injector.inject(pattern, depth, times, condition)` → `injector.inject(pattern, {"depth": ..., "times": ..., "condition_express": ...})`
  - Change `injector.restore(pattern)` → `injector.uninject(watch_id)` (need to store watch_id from inject return)
  - Remove `injector.get_watch_id()` call (doesn't exist - use return value from inject)

  **Must NOT do**:
  - Do not change the test logic or coverage
  - Do not add pytest dependency (this is a standalone script)

  **Parallelizable**: YES (with 3, 5)

  **References**:
  - `tests/manual_test.py:47, 101, 163` - Wrong DecoratorInjector constructor
  - `tests/manual_test.py:57-61, 111-116, 183-186` - Wrong inject() signature
  - `tests/manual_test.py:76, 133` - `restore()` doesn't exist, use `uninject(watch_id)`
  - `tests/manual_test.py:122` - `get_watch_id()` doesn't exist
  - `peeka/core/injector.py:51-72` - Correct `inject(pattern, watch_config)` signature
  - `peeka/core/injector.py:103-123` - `uninject(watch_id)` signature

  **Acceptance Criteria**:
  - [ ] `python tests/manual_test.py` → All 4 tests pass
  - [ ] Output shows: "4/4 tests passed" with checkmarks

  **Commit**: YES
  - Message: `test(manual): update API calls to match current injector`
  - Files: `tests/manual_test.py`
  - Pre-commit: `python tests/manual_test.py`

---

- [ ] 5. Rewrite CLI to use current core API

  **What to do**:
  
  **5a. Fix imports**:
  - Remove: `from .core.attachment import attacher`
  - Remove: `from .core.watcher import watch_function, unwatch_function`
  - Add: `from peeka.core.attach import ProcessAttacher`
  - Add: `from peeka.core.client import AgentClient, StreamingAgentClient`
  
  **5b. Update argument parser** (`create_parser()`):
  - Add Arthas flags to watch subparser:
    - `-x, --depth` (int, default 2)
    - `-n, --times` (int, default -1)
    - `-b, --before` (flag)
    - `-e, --exception` (flag)
    - `-s, --success` (flag)
    - `-f, --finish` (flag, default True)
    - `--condition-express` (string)
  - Add `pid` positional argument to watch command
  - Remove old `--params`, `--return`, `--exceptions` flags (replaced by Arthas flags)
  
  **5c. Rewrite `execute_watch()`**:
  - Create `ProcessAttacher(pid)` and call `attach()`
  - Get socket path via `attacher.get_socket_path()`
  - Create `StreamingAgentClient(socket_path)`
  - Send watch command via `send_command({"type": "watch", "action": "start", ...})`
  - Stream observations via `stream_observations()` generator
  - Output each observation as JSONL (one JSON per line to stdout)
  - Handle KeyboardInterrupt: send stop command, disconnect, exit cleanly
  
  **5d. Rewrite `execute_attach()`**:
  - Create `ProcessAttacher(pid)` and call `attach()`
  - Keep interactive loop but use `AgentClient.send_command()` for commands
  - Parse watch commands in loop and translate to proper command dict
  
  **5e. Stub `execute_detach()` and `execute_unwatch()`**:
  - Print "Not supported - agent remains active until target process exits"

  **Must NOT do**:
  - Do not implement new features not in core
  - Do not change communication protocol
  - Do not add dependencies

  **Parallelizable**: YES (with 3, 4)

  **References**:
  - `peeka/cli.py` - Current broken CLI (entire file needs update)
  - `peeka/core/attach.py:18-81` - ProcessAttacher class and attach() method
  - `peeka/core/client.py:13-70` - AgentClient class
  - `peeka/core/client.py:73-220` - StreamingAgentClient class
  - `peeka/commands/watch.py:59-83` - Watch command protocol structure
  - `README.md` - CLI usage examples (should match after fix):
    ```
    peeka watch <pid> "module.Class.method" --times 5
    peeka watch <pid> "module.Class.method" --condition "len(params) > 2"
    ```

  **Acceptance Criteria**:
  - [ ] `python -c "from peeka.cli import main"` → No import errors
  - [ ] `python -m peeka.cli watch --help` → Shows -b, -e, -s, -f, -x, -n, --condition-express
  - [ ] Manual test: Start `examples/demo.py`, attach with peeka, see JSONL output

  **Commit**: YES
  - Message: `fix(cli): rewrite to use ProcessAttacher and AgentClient`
  - Files: `peeka/cli.py`
  - Pre-commit: `python -c "from peeka.cli import create_parser; p = create_parser(); print('OK')"`

---

- [ ] 6. Run full test suite and verify

  **What to do**:
  - Run `uv run pytest tests/ -v`
  - Ensure 0 failures
  - If any failures, debug and fix

  **Must NOT do**:
  - Do not skip failing tests
  - Do not disable tests

  **Parallelizable**: NO (depends on all previous tasks)

  **References**:
  - All test files in `tests/`
  - `pyproject.toml` - pytest configuration

  **Acceptance Criteria**:
  - [ ] `uv run pytest tests/ -v` → All tests pass (some may skip on CI due to attach permissions)
  - [ ] `uv run pytest tests/test_injector.py -v` → 25 passed, 0 failed

  **Commit**: NO (verification only)

---

## Commit Strategy

| After Task | Message | Files | Verification |
|------------|---------|-------|--------------|
| 1 | `fix(injector): correctly capture self for instance methods` | `peeka/core/injector.py` | `uv run pytest tests/test_injector.py::TestArthasCompatibility::test_target_self_capture -v` |
| 2 | `test(injector): update field names to Arthas-compatible format` | `tests/test_injector.py` | `uv run pytest tests/test_injector.py -v` |
| 3 | `test(compatibility): fix imports and use MockAgent pattern` | `tests/test_compatibility.py` | `uv run pytest tests/test_compatibility.py -v` |
| 4 | `test(manual): update API calls to match current injector` | `tests/manual_test.py` | `python tests/manual_test.py` |
| 5 | `fix(cli): rewrite to use ProcessAttacher and AgentClient` | `peeka/cli.py` | `python -c "from peeka.cli import create_parser"` |

---

## Success Criteria

### Verification Commands
```bash
# All tests pass
uv run pytest tests/ -v  # Expected: 0 failures

# CLI loads without errors
python -c "from peeka.cli import main"  # Expected: no output (success)

# CLI shows Arthas flags
python -m peeka.cli watch --help  # Expected: shows -b, -e, -s, -f, -x, -n
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All 25+ tests pass
- [ ] CLI imports resolve correctly
- [ ] Arthas flags available in CLI help
