---
name: peeka-diagnostics
description: >
  Runtime Python diagnostics using peeka-cli. Use when debugging Python processes,
  diagnosing slow performance, finding memory leaks, tracing function calls,
  watching variables at runtime, analyzing thread issues, or any runtime Python
  debugging task. Triggers: debug python, diagnose python, slow app, memory leak,
  trace function, watch expression, runtime debugging, peeka, profile python,
  thread deadlock, function not called, high CPU python
---

# Peeka Diagnostics Skill

Runtime diagnostic reference for AI agents using `peeka-cli` to diagnose live Python applications. All output is JSONL — pipe through `jq` for structured analysis.

## Quick Reference

| Command | Category | Purpose | Key Flags |
|---------|----------|---------|-----------|
| `attach` | Session | Attach to Python process | `<pid>` |
| `detach` | Session | Detach from process | — |
| `reset` | Session | Remove injected enhancements | `-l/--list`, `[pattern]` |
| `watch` | Streaming | Observe function calls (args, return, timing) | `-n`, `-x`, `-b/-s/-e/-f`, `--condition` |
| `trace` | Streaming | Trace call tree with timing breakdown | `-n`, `-d`, `--min-duration`, `--condition` |
| `stack` | Streaming | Capture call stack at function entry | `-n`, `--depth`, `--condition` |
| `monitor` | Streaming | Periodic aggregated performance stats | `-c/--cycles`, `--interval` |
| `top` | Streaming | Function-level sampling profiler | `-c/--cycles`, `-i/--interval`, `--sort` |
| `sc` | Query | Search classes by pattern | `-d/--detail`, `--limit` |
| `sm` | Query | Search methods in a class | `--method-pattern`, `-d/--detail` |
| `memory` | Query | Memory analysis (tracemalloc, gc, refs) | `--action` |
| `inspect` | Query | Runtime object inspection on heap | `--action`, `--target`, `--type` |
| `logger` | Query | View/modify log levels at runtime | `--action`, `--logger`, `--level` |
| `thread` | Query | List threads and inspect stacks | `--tid`, `--state`, `--sort-by` |

**Streaming commands** produce continuous output — ALWAYS use `-n`/`--times` (watch, trace, stack) or `-c`/`--cycles` (monitor, top) to bound execution.

## `run` — Observe Short-Lived Scripts

For scripts that exit quickly (before you could attach manually), use `peeka-cli run` to bootstrap and observe from startup:

```bash
peeka-cli run <script> [script-args...] -- <command> [command-args...]
```

The `run` command:
1. Pre-imports the user script (so all functions/classes exist)
2. Attaches peeka and sets up the observation command
3. Then executes the script — all calls are captured

### Flags

| Flag | Description |
|------|-------------|
| `--output-file <path>` | Write peeka JSONL output to file instead of stdout |

### Examples

```bash
# Watch a function in a script that runs and exits
peeka-cli run myscript.py -- watch "myscript.process_data" -n 10

# Pass arguments to the script
peeka-cli run myscript.py arg1 arg2 -- watch "myscript.main" -n 5

# Trace call tree of a short-lived script
peeka-cli run myscript.py -- trace "myscript.run" -d 3 -n 1

# Redirect peeka output to a file (best practice for AI agents)
peeka-cli run myscript.py --output-file /tmp/peeka_run_output.jsonl -- watch "myscript.func" -n 5
```

### Best Practice for AI Agents

Redirect peeka output to a temp file, then read results from that file:

```bash
peeka-cli run target_script.py --output-file /tmp/peeka_run_output.jsonl -- watch "module.func" -n 5
# After script exits, read observations:
cat /tmp/peeka_run_output.jsonl | jq 'select(.type == "observation")'
```

Supported observation commands after `--`: `watch`, `trace`, `stack`, `monitor`, `top`.

## Prerequisites Check

Before diagnosing, verify the environment:

```bash
# 1. Find target PID
pgrep -af "python.*myapp"
# or: ps aux | grep python

# 2. Check Python version (determines attach mechanism)
python3 --version
# 3.14+: PEP 768 native attach (no extra deps)
# 3.8-3.13: GDB + ptrace required

# 3. For Python < 3.14 — verify GDB, ptrace, and debug symbols
which gdb
cat /proc/sys/kernel/yama/ptrace_scope  # Must be 0 or 1
# Verify debug symbols match Python version
gdb -batch -ex "py print PyGILState_Ensure" -ex quit
# Must succeed (output is an integer, doesn't matter what value)
# If fails → install python3-dbg that exactly matches your Python version
# Docker: container must have --cap-add=SYS_PTRACE

# 4. Check jq availability (for JSONL parsing)
which jq || echo "jq not found — use Python fallback below"
```

## Process Discovery

Find the target Python process PID before attaching:

```bash
# By script name
pgrep -af "python.*myapp.py"

# By module
pgrep -af "python.*-m mypackage"

# All Python processes
ps aux | grep "[p]ython"

# Inside Docker container: typically PID 1
ps aux
```

## Pattern Discovery (CRITICAL — Always Do First)

Before using `watch`, `trace`, `stack`, or `monitor`, discover the correct fully-qualified function pattern using `sc` and `sm`:

```bash
# Attach first
peeka-cli attach <pid>

# List all loaded classes
peeka-cli sc "*" | jq -r '.data.classes[]'

# Find a specific class
peeka-cli sc "Calculator" | jq '.data'

# List methods of a class (all methods)
peeka-cli sm "calculator.Calculator" | jq -r '.data.methods[]'

# List specific methods
peeka-cli sm "calculator.Calculator" --method-pattern "add" | jq '.data'
```

**Pattern format**: `module.Class.method` or `module.function` (fully qualified with module path).

## Diagnostic Decision Tree

Match the observed symptom to the right peeka command sequence:

| Symptom | First Command | Then | Goal |
|---------|---------------|------|------|
| **Slow response / high latency** | `watch` with `--condition "cost > N"` | `trace` for call tree breakdown | Find which sub-call is slow |
| **Wrong return value / logic bug** | `watch` the suspect function, examine `returnObj` | Add `--condition` to filter specific inputs | Correlate inputs → outputs |
| **Exception / unexpected error** | `watch` with `-e` (exception-only) | `stack` for call context | Find where and why exception occurs |
| **High memory / memory leak** | `memory --action overview` → `start` → `snapshot` × 2 → `diff` | `memory --action top`, then `referrers` | Find what allocates and holds memory |
| **High CPU** | `top` to find hotspot functions | `trace` the hot function for breakdown | Find CPU-intensive code path |
| **Deadlock / hang / stuck thread** | `thread` to list thread states | `stack` on the stuck function | Find lock contention point |
| **Function never called** | `watch` with `-n 1` + short wait — no output means not called | Verify pattern with `sc`/`sm` | Confirm function is reachable |
| **Log level too low / too high** | `logger --action list` to see current levels | `logger --action set --logger <name> --level DEBUG` | Adjust runtime log verbosity |

## Command Reference

### Session Commands

#### attach

Attach to a running Python process. Must be called before any other command.

```bash
peeka-cli attach <pid>
```

Output: `success` with `{"pid": <pid>, "socket": "/tmp/peeka_xxx.sock"}`

#### detach

Detach from the current process. Cleans up session files.

```bash
peeka-cli detach
```

#### reset

Remove injected enhancements and restore original functions.

```bash
# Reset all enhancements
peeka-cli reset

# Reset specific pattern only
peeka-cli reset "module.Class.method"

# List current enhancements without resetting
peeka-cli reset -l
```

### Streaming Commands

#### watch

Observe function calls with arguments, return values, timing, and exceptions.

```bash
peeka-cli watch <pattern> [options]
```

| Flag | Description | Default |
|------|-------------|---------|
| `-n, --times` | Number of observations (`-1` = infinite) | `-1` |
| `-x, --depth` | Output depth for nested objects | `2` |
| `-b, --before` | Observe at function entry (before execution) | `false` |
| `-s, --success` | Observe on successful return only | `false` |
| `-e, --exception` | Observe on exception only | `false` |
| `-f, --finish` | Observe on finish (both success and exception) | `true` (default) |
| `--condition` | Filter expression (e.g., `"cost > 50"`) | — |

```bash
# Watch 5 calls with full depth
peeka-cli watch "myapp.service.UserService.get_user" -n 5 -x 3

# Watch only slow calls (>100ms)
peeka-cli watch "myapp.api.handler" -n 10 --condition "cost > 100"

# Watch only exceptions
peeka-cli watch "myapp.service.process" -n 5 -e

# Watch before execution (see args before function runs)
peeka-cli watch "myapp.db.query" -n 3 -b

# Parse: extract function, cost, and return value
peeka-cli watch "myapp.func" -n 10 | jq --unbuffered 'select(.type == "observation") | {func: .func_name, cost: .cost, result: .returnObj}'
```

#### trace

Trace the full call tree of a function with timing breakdown per sub-call.

```bash
peeka-cli trace <pattern> [options]
```

| Flag | Description | Default |
|------|-------------|---------|
| `-n, --times` | Number of traces | `-1` |
| `-d, --depth` | Max call tree depth | `3` |
| `--condition` | Filter expression | — |
| `--skip-builtin` | Skip stdlib/built-in functions | `true` |
| `--min-duration` | Minimum duration in ms to record | `0` |

```bash
# Trace call tree 2 times, depth 5
peeka-cli trace "myapp.service.process_order" -n 2 -d 5

# Only show calls taking >10ms
peeka-cli trace "myapp.handler" -n 3 --min-duration 10

# Include built-in calls
peeka-cli trace "myapp.compute" -n 1 --skip-builtin false
```

#### stack

Capture the call stack at the point a function is entered.

```bash
peeka-cli stack <pattern> [options]
```

| Flag | Description | Default |
|------|-------------|---------|
| `-n, --times` | Number of captures | `-1` |
| `--depth` | Stack frame depth limit | `10` |
| `--condition` | Filter expression | — |

```bash
# Capture stack 3 times with 20-frame depth
peeka-cli stack "myapp.db.execute_query" -n 3 --depth 20
```

#### monitor

Collect periodic aggregated statistics (call count, avg/max/min duration) for a function.

```bash
peeka-cli monitor <pattern> [options]
```

| Flag | Description | Default |
|------|-------------|---------|
| `--interval` | Seconds between outputs | `60` |
| `-c, --cycles` | Number of reporting cycles (`-1` = infinite) | `-1` |

```bash
# Monitor every 5 seconds for 12 cycles (1 minute total)
peeka-cli monitor "myapp.api.handle_request" --interval 5 -c 12

# Parse monitor output for trends
peeka-cli monitor "myapp.api.handle_request" --interval 10 -c 6 | jq --unbuffered 'select(.type == "observation") | {ts: .timestamp, count: .count, avg: .avg_cost}'
```

**Note**: `monitor` does NOT have a `--condition` flag.

#### top

Function-level sampling profiler — identifies CPU hotspot functions.

```bash
peeka-cli top [options]
```

| Flag | Description | Default |
|------|-------------|---------|
| `-i, --interval` | Sampling interval in seconds | `0.01` |
| `-c, --cycles` | Number of display cycles (`-1` = infinite) | `-1` |
| `--sort` | Sort column: `own`, `total`, `own-time`, `total-time` | `own` |
| `--no-filter-peeka` | Include peeka's own threads in output | `false` |

```bash
# Profile for 5 cycles, sort by own time
peeka-cli top -c 5 --sort own-time

# Slower sampling (1s interval) for 10 cycles
peeka-cli top -i 1 -c 10

# Parse: find top functions by own-time
peeka-cli top -c 3 | jq --unbuffered 'select(.type == "observation") | .functions[:5]'
```

**Note**: `top` does NOT have a `-n/--times` flag. Use `-c/--cycles` to bound execution.

### Query Commands

#### sc (Search Classes)

```bash
peeka-cli sc <pattern> [-d/--detail] [--limit N]
```

```bash
# Find all classes matching pattern
peeka-cli sc "myapp.*" | jq '.data.classes'

# Detailed class info (methods, bases, module)
peeka-cli sc "myapp.models.User" -d

# Limit results
peeka-cli sc "*" --limit 100
```

#### sm (Search Methods)

```bash
peeka-cli sm <class_pattern> [--method-pattern PATTERN] [-d/--detail]
```

```bash
# All methods of a class
peeka-cli sm "myapp.models.User" | jq '.data.methods'

# Find specific method
peeka-cli sm "myapp.models.User" --method-pattern "save" -d
```

**Note**: `class_pattern` is positional (required). `--method-pattern` is an optional flag (defaults to `*`).

#### memory

Memory analysis using tracemalloc, garbage collector, and reference tracing.

```bash
peeka-cli memory --action <action> [options]
```

| Action | Purpose | Prerequisites |
|--------|---------|---------------|
| `overview` | General memory stats | None |
| `start` | Start tracemalloc tracking | None |
| `stop` | Stop tracemalloc tracking | `start` |
| `top` | Top memory allocations | `start` must be running |
| `snapshot` | Take allocation snapshot | `start` must be running |
| `diff` | Diff between last two snapshots | At least 2 `snapshot` calls |
| `dump` | Dump tracemalloc data to file | `start` must be running |
| `gc` | Force garbage collection, show stats | None |
| `referrers` | Show what references objects of a type | `--type-name` required |
| `referents` | Show what objects of a type reference | `--type-name` required |

Additional flags: `--nframe` (tracemalloc depth, default 25), `--group-by` (lineno/filename), `--limit`, `--filename` (for dump), `--type-name` (for referrers/referents), `--max-depth`, `--max-per-level`.

```bash
# Full memory investigation sequence
peeka-cli memory --action overview
peeka-cli memory --action start
peeka-cli memory --action snapshot
# ... let the app run ...
peeka-cli memory --action snapshot
peeka-cli memory --action diff | jq '.data'
peeka-cli memory --action top --limit 10 | jq '.data'
peeka-cli memory --action referrers --type-name "MyClass" | jq '.data'
peeka-cli memory --action stop
```

#### inspect

Runtime object inspection on the heap. CLI command is `inspect` (NOT `vmtool`).

```bash
peeka-cli inspect --action <action> [options]
```

| Action | Purpose | Required Flag |
|--------|---------|---------------|
| `get` | Get attribute value from module/object | `--target` |
| `instances` | Find live instances of a class | `--type` |
| `count` | Count live instances of a class | `--type` |

Additional flags: `--limit` (default 10), `--depth` (default 2), `--filter-express` (e.g., `"obj.value > 0"`), `--gc-first` (force GC before scanning).

```bash
# Get a module-level variable
peeka-cli inspect --action get --target "myapp.config.DEBUG"

# Find all instances of a class
peeka-cli inspect --action instances --type "myapp.models.User" --limit 5

# Count instances with GC first
peeka-cli inspect --action count --type "myapp.cache.CacheEntry" --gc-first

# Filter instances
peeka-cli inspect --action instances --type "myapp.models.Order" --filter-express "obj.total > 1000"
```

#### logger

View and modify log levels at runtime.

```bash
peeka-cli logger --action <action> [options]
```

| Action | Purpose | Flags |
|--------|---------|-------|
| `list` | List all loggers | `--pattern` (fnmatch filter) |
| `get` | Get level of specific logger | `--logger <name>` |
| `set` | Set level of specific logger | `--logger <name>`, `--level <LEVEL>` |

```bash
# List all loggers
peeka-cli logger --action list | jq '.data'

# List loggers matching pattern
peeka-cli logger --action list --pattern "myapp.*"

# Get current level
peeka-cli logger --action get --logger "myapp.db"

# Set level to DEBUG
peeka-cli logger --action set --logger "myapp.db" --level DEBUG
```

#### thread

List threads and inspect individual thread stacks.

```bash
peeka-cli thread [options]
```

| Flag | Description | Default |
|------|-------------|---------|
| `--tid` | Thread ID for detailed stack trace | — |
| `--state` | Filter by state: `RUNNABLE`, `WAITING`, `TIMED_WAITING` | — |
| `--sort-by` | Sort by: `tid`, `name`, `state` | `tid` |
| `--depth` | Stack depth for detail view | `50` |

```bash
# List all threads
peeka-cli thread | jq '.data'

# Filter stuck threads
peeka-cli thread --state WAITING | jq '.data.threads[]'

# Get specific thread stack
peeka-cli thread --tid 12345 --depth 30
```

**Note**: If `--tid` is provided, shows detailed stack trace for that thread. Otherwise lists all threads.

## JSONL Output Format

Every line of CLI output is a JSON object with a `type` field. The 6 output types:

```
status:       {"type": "status", "level": "info", "message": "..."}
success:      {"type": "success", "command": "...", "data": {...}}
error:        {"type": "error", "command": "...", "error": "...", "suggestion": "..."}
event:        {"type": "event", "event": "...", "data": {...}}
observation:  {"type": "observation", "watch_id": "...", "func_name": "...", "params": [...], "kwargs": {}, "returnObj": ..., "cost": ..., "success": true/false, ...}
result:       {"type": "result", "command": "...", "data": {...}}
```

### jq Recipes

```bash
# Filter by type
peeka-cli watch "func" -n 10 | jq --unbuffered 'select(.type == "observation")'

# Extract specific fields from observations
... | jq --unbuffered 'select(.type == "observation") | {func: .func_name, cost: .cost, result: .returnObj}'

# Find slow calls (>100ms)
... | jq --unbuffered 'select(.type == "observation" and .cost > 100)'

# Find exceptions
... | jq --unbuffered 'select(.type == "observation" and .success == false)'

# Extract error messages
... | jq 'select(.type == "error") | .error'

# Get result data from query commands
peeka-cli sc "*" | jq 'select(.type == "result") | .data'

# Filter status/progress messages
peeka-cli attach <pid> | jq 'select(.type == "status") | .message'

# Check success confirmations
peeka-cli attach <pid> | jq 'select(.type == "success") | .data'

# Monitor control events (started/stopped)
peeka-cli watch "module.func" -n 5 | jq --unbuffered 'select(.type == "event") | {event: .event, data: .data}'

# Save observations to file while viewing
peeka-cli watch "func" -n 20 | tee observations.jsonl | jq --unbuffered 'select(.type == "observation") | .cost'
```

**IMPORTANT**: Use `jq --unbuffered` when piping streaming command output for real-time display.

### Python Fallback (when jq is unavailable)

```python
import json
import sys

for line in sys.stdin:
    line = line.strip()
    if not line or not line.startswith('{'):
        continue
    try:
        msg = json.loads(line)
        if msg.get('type') == 'observation':
            print(json.dumps({k: v for k, v in msg.items() if k != 'type'}, indent=2))
    except json.JSONDecodeError:
        continue
```

Usage: `peeka-cli watch "func" -n 10 | python3 filter.py`

## Condition Expression Reference

Condition expressions filter observations using sandboxed evaluation (simpleeval). Available variables depend on the observation timing flag:

| Variable | `-b` (before) | `-f` (finish, default) | `-s` (success) | `-e` (exception) |
|----------|:---:|:---:|:---:|:---:|
| `params` | Yes | Yes | Yes | Yes |
| `kwargs` | Yes | Yes | Yes | Yes |
| `target` | Yes | Yes | Yes | Yes |
| `cost` | — | Yes | Yes | Yes |

- `params`: Positional arguments as a list (e.g., `params[0]`)
- `kwargs`: Keyword arguments as a dict (e.g., `kwargs.get('user_id')`)
- `target`: The `self` reference for methods (access instance attributes: `target.name`)
- `cost`: Execution time in milliseconds (only available after function completes, not with `-b`)

**Note**: `returnObj` and `throwExp` appear in observation OUTPUT data but are NOT available in `--condition` expressions.

**Supported operators**: `>`, `<`, `>=`, `<=`, `==`, `!=`, `and`, `or`, `not`, `in`, `not in`
**Supported functions**: `len()`, `str()`, `int()`, `float()`, `bool()`

```bash
# Slow calls
--condition "cost > 50"

# Specific argument value
--condition "params[0] > 100"

# Combined conditions
--condition "cost > 100 and len(params) > 0"

# Multiple conditions
--condition "cost > 10 and len(params) > 2"

# Exception with cost filter
-e --condition "cost > 0"

# Instance attribute check
--condition "target.is_admin == True"
```

**Security**: Expressions are sandboxed. `eval`, `exec`, `__import__`, `open`, `compile`, and `__class__`/`__subclasses__` are all blocked.

## Diagnostic Playbooks

### Playbook A: Business Logic Debugging

**Goal**: Find why a function returns wrong results or behaves unexpectedly.

```bash
# 1. Attach
peeka-cli attach <pid>

# 2. Discover the function pattern
peeka-cli sc "MyModule" | jq '.data'
peeka-cli sm "mymodule.MyClass" --method-pattern "process*" | jq '.data'

# 3. Watch the function (observe args → return correlation)
peeka-cli watch "mymodule.MyClass.process" -n 10 -x 3 | \
  jq --unbuffered 'select(.type == "observation") | {args: .params, result: .returnObj, ok: .success}'

# 4. Narrow with condition on suspect inputs
peeka-cli watch "mymodule.MyClass.process" -n 5 --condition "params[0] == 'bad_input'" | \
  jq --unbuffered 'select(.type == "observation")'

# 5. Trace internal call tree for deeper investigation
peeka-cli trace "mymodule.MyClass.process" -n 2 -d 5

# 6. Cleanup
peeka-cli reset && peeka-cli detach
```

### Playbook B: Performance Diagnosis

**Goal**: Find why the application is slow.

```bash
# 1. Attach
peeka-cli attach <pid>

# 2. Profile with top — find hotspot functions
peeka-cli top -c 5 --sort own-time | \
  jq --unbuffered 'select(.type == "observation")'

# 3. Watch the slow function with cost filter
peeka-cli watch "myapp.hot_function" -n 10 --condition "cost > 100" | \
  jq --unbuffered 'select(.type == "observation") | {func: .func_name, cost: .cost}'

# 4. Trace the call tree to find slow sub-calls
peeka-cli trace "myapp.hot_function" -n 2 -d 5 --min-duration 10

# 5. Monitor trends over time (every 5s for 1 minute)
peeka-cli monitor "myapp.hot_function" --interval 5 -c 12 | \
  jq --unbuffered 'select(.type == "observation") | {count: .count, avg: .avg_cost, max: .max_cost}'

# 6. Cleanup
peeka-cli reset && peeka-cli detach
```

### Playbook C: Memory Leak Hunting

**Goal**: Find memory leaks and excessive memory usage.

```bash
# 1. Attach
peeka-cli attach <pid>

# 2. Get baseline memory overview
peeka-cli memory --action overview | jq '.data'

# 3. Start tracemalloc tracking
peeka-cli memory --action start

# 4. Take first snapshot
peeka-cli memory --action snapshot

# 5. Wait for allocations (let the app handle some requests)
sleep 30  # or trigger the suspect workflow

# 6. Take second snapshot
peeka-cli memory --action snapshot

# 7. Diff snapshots — find what grew
peeka-cli memory --action diff | jq '.data'

# 8. Find top allocators
peeka-cli memory --action top --limit 10 | jq '.data'

# 9. Trace references for suspect type
peeka-cli memory --action referrers --type-name "MyLeakyClass" | jq '.data'

# 10. Optional: force GC and check if objects are collected
peeka-cli memory --action gc | jq '.data'

# 11. Cleanup
peeka-cli memory --action stop
peeka-cli reset && peeka-cli detach
```

### Playbook D: Thread Analysis

**Goal**: Debug deadlocks, hangs, or thread contention.

```bash
# 1. Attach
peeka-cli attach <pid>

# 2. List all threads — look for WAITING/TIMED_WAITING states
peeka-cli thread | jq '.data.threads[] | {tid: .tid, name: .name, state: .state}'

# 3. Filter stuck threads
peeka-cli thread --state WAITING | jq '.data.threads[]'

# 4. Get stack trace of suspect thread
peeka-cli thread --tid <tid> --depth 30

# 5. Watch the contended function to see if it ever completes
peeka-cli watch "myapp.lock_handler.acquire" -n 5

# 6. Cleanup
peeka-cli reset && peeka-cli detach
```

## Safety Protocol

**MANDATORY for every diagnostic session**:

1. **Always bound streaming commands**: Use `-n/--times` (watch, trace, stack) or `-c/--cycles` (monitor, top). Never run unbounded in automated workflows.

2. **Always reset before detach**: Restores all instrumented functions to their original state.
   ```bash
   peeka-cli reset && peeka-cli detach
   ```

3. **One session at a time**: Only one peeka agent can be attached to a process. If another session exists, detach it first.

4. **Recovery from stale sessions**: If a previous session wasn't cleaned up properly:
   ```bash
   # Attempt to detach the stale session
   peeka-cli detach
   # If detach fails, re-attach first then detach cleanly
   peeka-cli attach <pid> && peeka-cli reset && peeka-cli detach
   ```

5. **Don't watch hot loops without `-n`**: Functions called thousands of times per second will produce massive output and impact performance without a bound.

6. **Condition expressions are sandboxed**: No `eval`, `exec`, `open`, `import` — safe to use freely. No risk of code injection.

7. **Production impact**: peeka adds <5% overhead per instrumented function. Minimize the number of concurrent watch/trace targets.

## Common Errors and Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `"Not attached to any process"` | No active peeka session | Run `peeka-cli attach <pid>` first |
| `"Cannot find target: <pattern>"` | Wrong function pattern | Use `peeka-cli sc` and `peeka-cli sm` to find the correct pattern |
| Permission denied / ptrace error | Missing ptrace permissions | Check `ptrace_scope`, use `--cap-add=SYS_PTRACE` in Docker |
| **Timeout waiting for agent ready file (GDB path)** | Agent initialization never completes after GDB injection | See full troubleshooting below |
| No observations received | Function not being called, or wrong timing flag | Verify function is active; try without `--condition`; check timing flags |
| `"Already attached"` | Previous session not cleaned up | `peeka-cli detach`, then re-attach if needed |
| tracemalloc error on `memory --action top` | tracemalloc not started | Run `peeka-cli memory --action start` first |
| `memory --action diff` fails | Fewer than 2 snapshots | Take at least 2 snapshots with `memory --action snapshot` |
| `memory --action referrers` fails | Missing `--type-name` | Add `--type-name "ClassName"` flag |

---

## Attach Failure Troubleshooting (GDB path - Python < 3.14)

If `peeka-cli attach <pid>` hangs and eventually times out waiting for the agent ready file, use this systematic troubleshooting:

### Step 1: Verify prerequisites
```bash
# 1. Check ptrace scope
cat /proc/sys/kernel/yama/ptrace_scope
# Must be 0 (allow any process to ptrace any other process)
# If it's 1: sudo sysctl -w kernel.yama.ptrace_scope=0

# 2. Check GDB installed
which gdb

# 3. VERIFY PYTHON DEBUG SYMBOLS (most common failure after ptrace)
gdb -batch -ex "py print PyGILState_Ensure" -ex quit
# ✓ Success: outputs an integer (doesn't matter what it is)
# ✗ Failure: "No symbol "PyGILState_Ensure" in current context"
#    → Debug symbols don't match your Python version
#    → Fix: install python3-dbg package that exactly matches your python version
#    → In Docker: use the base.Dockerfile-<version> to build a matched image

# 4. Check that GDB can actually execute Python code
docker exec peeka-test-<version> bash -c '
  gdb -batch -p $(pgrep -f demo.py) \
    -ex "call (int) PyGILState_Ensure()" \
    -ex "call (int) PyRun_SimpleString(\"open(\\\"/tmp/gdb-test\\\", \\\"w\\\").write(\\\"ok\\\")\")" \
    -ex "call (void) PyGILState_Release(\$1)" \
    -ex quit
'
ls -l /tmp/gdb-test
# ✓ Success: /tmp/gdb-test exists with content "ok"
# If this fails → GDB/python-dbg issue, fix symbols first
```

### Step 2: Diagnose the thread scheduling issue (Python <= 3.8)

If GDB works fine (Step 1 passes) but attach still times out:
```bash
# Manually test thread creation via GDB
docker exec peeka-test-<version> bash -c '
  gdb -batch -p $(pgrep -f demo.py) \
    -ex "call (int) PyGILState_Ensure()" \
    -ex "call (int) PyRun_SimpleString(\"import threading,time; print(\\\"starting thread\\\"); t=threading.Thread(target=lambda: time.sleep(30)); t.daemon=True; t.start(); print(\\\"thread started\\\")\")" \
    -ex "call (void) PyGILState_Release(\$1)" \
    -ex quit
'

# Check if thread actually scheduled
ps -T $(pgrep -f demo.py) | grep -E "PID|sleep"
# ✓ Success: you see the extra thread running
# ✗ Failure: thread exists but is in T (stopped) state → THIS IS THE BUG
#    → Root cause: On older Python <= 3.8, threads created via GDB while the
#    process is stopped never get scheduled after GDB detaches
#    → Fix: execute bootstrap directly without creating a new thread
```

### Step 3: Verify the fix

After applying the direct-execution fix:
```bash
# Test direct execution via GDB
docker exec peeka-test-<version> bash -c '
  gdb -batch -p $(pgrep -f demo.py) \
    -ex "call (int) PyGILState_Ensure()" \
    -ex "call (int) PyRun_SimpleString(\"open(\\\"/tmp/direct-exec-ok\\\", \\\"w\\\").write(\\\"done\\\")\")" \
    -ex "call (void) PyGILState_Release(\$1)" \
    -ex quit
'

ls -l /tmp/direct-exec-ok
# ✓ Success: file exists → direct execution works
# Now try full attach → should succeed
```

### Common Root Causes Ordered by Likelihood:

1. **ptrace_scope != 0** → 权限问题，fix ptrace_scope
2. **Debug symbols don't match Python version** → 最常见，GDB 找不到 Python C API 符号
3. **Missing --cap-add=SYS_PTRACE in Docker** → 容器没有权限
4. **Thread scheduling bug (Python <= 3.8)** → 这就是我们这次遇到的问题，必须直接执行不能创建线程
