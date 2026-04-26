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

**Before ANY diagnostic session, complete Steps 0–3 in order. Do NOT skip.**

---

## Section 1: Environment Detection (Step 0)

Determine how to invoke `peeka-cli` based on the user's Python environment. Run the detection script if available, otherwise detect manually.

### Option A: Run detection script

```bash
sh .agents/skills/peeka-diagnostics/scripts/detect-env.sh --project-dir .
```

The script outputs `ENV_TYPE`, `PEEKA_PREFIX`, and `PEEKA_CMD`. Use `PEEKA_CMD` for all subsequent commands.

### Option B: Manual detection (fallback)

Check workspace markers in this priority order:

| Check | Condition | `PEEKA_CMD` value |
|-------|-----------|-------------------|
| `pyproject.toml` contains `[tool.uv]` | uv project | `uv run peeka-cli` |
| `pyproject.toml` contains `[tool.poetry]` | poetry project | `poetry run peeka-cli` |
| `$CONDA_DEFAULT_ENV` is set OR `environment.yml` exists | conda env | `conda run --no-banner -n <env> peeka-cli` |
| `.venv/bin/activate` or `venv/bin/activate` exists | venv | `. .venv/bin/activate && peeka-cli` |
| None of the above | system Python | `peeka-cli` |

### Set the command variable

After detection, define `PEEKA_CMD` for all examples below. For instance:

```bash
PEEKA_CMD="uv run peeka-cli"
```

> **Important**: The target process may use a DIFFERENT Python environment than peeka. `PEEKA_CMD` is for invoking peeka-cli, not for the target process.

---

## Section 2: OS Compatibility Check (Step 1)

Check the user's operating system and Python version BEFORE proceeding.

| OS | Support Level | Attach Mechanisms | Notes |
|----|--------------|-------------------|-------|
| **Linux** | FULL | PEP 768 (3.14+) + GDB+ptrace (3.8–3.13) | All features available |
| **macOS** | PEP 768 ONLY | PEP 768 (3.14+) | GDB path NOT RECOMMENDED (requires codesign, impractical). No `ptrace_scope` check needed. |
| **Windows** | NOT SUPPORTED | — | AF_UNIX sockets and ptrace/GDB absent. Recommend WSL2 or Linux container. |

### Stop conditions (MUST check)

- **macOS AND target Python < 3.14**: **STOP.** Tell the user peeka requires Python 3.14+ on macOS, or suggest using a Linux container/VM.
- **Windows**: **STOP.** Tell the user peeka is not supported on Windows. Recommend WSL2 or a Linux container.

### macOS-specific notes

- Process discovery: use `pgrep -af "python"` (no `--name` flag — it's dead code)
- `ptrace_scope` check does NOT apply (no `/proc/sys/kernel/yama/`)
- Socket paths work (macOS supports AF_UNIX and `/tmp`)
- SIP (System Integrity Protection) may interfere with system Python — use user-installed Python (e.g., from Homebrew or python.org)

---

## Section 3: Permission Quick Fix (Step 2)

Based on OS + Python version, verify permissions before attaching.

### Linux + PEP 768 (Python 3.14+)

**Need**: Same UID as target process, OR `CAP_SYS_PTRACE`

```bash
# Check: who owns the target process?
ps -o user= -p <pid>

# Fix: grant ptrace capability to Python binary
sudo setcap cap_sys_ptrace=eip $(which python3.14)

# Or: run peeka as the same user as the target
sudo -u <target_user> ${PEEKA_CMD} attach <pid>
```

### Linux + GDB (Python 3.8–3.13)

**Need**: `ptrace_scope <= 1` AND same UID or root AND GDB AND python3-dbg

```bash
# Quick check sequence:
cat /proc/sys/kernel/yama/ptrace_scope  # Must be 0 or 1
which gdb                                # Must exist
gdb -batch -ex "python print('ok')" -ex quit  # Must print 'ok'

# Fix ptrace_scope (temporary):
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# Fix missing GDB + debug symbols:
# Debian/Ubuntu: sudo apt-get install gdb python3-dbg
# RHEL/Fedora:   sudo yum install gdb python3-debuginfo
# Arch:          sudo pacman -S gdb

# Docker: container MUST have --cap-add=SYS_PTRACE
# SELinux: sudo setsebool -P deny_ptrace=off
```

> **Encountering attach failures after permissions are correct?**
> Use the Read tool: `.agents/skills/peeka-diagnostics/refs/troubleshooting.md`

### macOS + PEP 768 (Python 3.14+)

**Need**: Same UID as target process

```bash
# Check: who owns the target process?
ps -o user= -p <pid>

# If permission denied: ensure peeka runs as same user as target
# SIP may interfere with system Python — use user-installed Python
```

---

## Section 4: Process Discovery (Step 3)

Find the target Python process PID before attaching.

```bash
# By script name
pgrep -af "python.*myapp.py"

# By module
pgrep -af "python.*-m mypackage"

# All Python processes
ps aux | grep "[p]ython"

# Inside Docker container (typically PID 1)
docker exec <container> ps aux | grep python
```

### Pattern discovery (find correct function names)

After attaching, discover fully-qualified function patterns with `sc` and `sm`:

```bash
${PEEKA_CMD} attach <pid>

# Find classes matching a pattern
${PEEKA_CMD} sc "MyModule*" | jq '.data.classes'

# Find methods in a class
${PEEKA_CMD} sm "mymodule.MyClass" | jq '.data.methods'
```

> **Need full sc/sm flag reference?**
> Use the Read tool: `.agents/skills/peeka-diagnostics/refs/commands.md`

---

## Section 5: Quick Reference Table

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

**Streaming commands** produce continuous output — ALWAYS use `-n/--times` (watch, trace, stack) or `-c/--cycles` (monitor, top) to bound execution.

**Pattern format**: `module.Class.method` or `module.function` (fully qualified with module path).

> **Need full command flags, options, and jq recipes?**
> Use the Read tool: `.agents/skills/peeka-diagnostics/refs/commands.md`

---

## Section 6: `run` Command — Observe Short-Lived Scripts

For scripts that exit quickly (before you could attach manually), use `run` to bootstrap and observe from startup:

```bash
${PEEKA_CMD} run <script> [script-args...] -- <command> [command-args...]
```

The `run` command:
1. Pre-imports the user script (so all functions/classes exist)
2. Attaches peeka and sets up the observation command
3. Then executes the script — all calls are captured

### Key flags

| Flag | Description |
|------|-------------|
| `--output-file <path>` | Write peeka JSONL output to file instead of stdout |

### Examples

```bash
# Watch a function in a short-lived script
${PEEKA_CMD} run myscript.py -- watch "myscript.process_data" -n 10

# Pass arguments to the script
${PEEKA_CMD} run myscript.py arg1 arg2 -- watch "myscript.main" -n 5

# Trace call tree of a short-lived script
${PEEKA_CMD} run myscript.py -- trace "myscript.run" -d 3 -n 1

# Best practice: redirect output to file, then read results
${PEEKA_CMD} run target_script.py --output-file /tmp/peeka_run_output.jsonl -- watch "module.func" -n 5
cat /tmp/peeka_run_output.jsonl | jq 'select(.type == "observation")'
```

Supported observation commands after `--`: `watch`, `trace`, `stack`, `monitor`, `top`.

---

## Section 7: Diagnostic Decision Tree

Match the observed symptom to the right peeka command sequence:

| Symptom | First Command | Then | Goal |
|---------|---------------|------|------|
| **Slow response / high latency** | `watch` with `--condition "cost > N"` | `trace` for call tree breakdown | Find which sub-call is slow |
| **Wrong return value / logic bug** | `watch` the suspect function, examine `returnObj` | Add `--condition` to filter specific inputs | Correlate inputs to outputs |
| **Exception / unexpected error** | `watch` with `-e` (exception-only) | `stack` for call context | Find where and why exception occurs |
| **High memory / memory leak** | `memory --action overview` then `start` then `snapshot` x2 then `diff` | `memory --action top`, then `referrers` | Find what allocates and holds memory |
| **High CPU** | `top` to find hotspot functions | `trace` the hot function for breakdown | Find CPU-intensive code path |
| **Deadlock / hang / stuck thread** | `thread` to list thread states | `stack` on the stuck function | Find lock contention point |
| **Function never called** | `watch` with `-n 1` + short wait — no output means not called | Verify pattern with `sc`/`sm` | Confirm function is reachable |
| **Log level too low / too high** | `logger --action list` to see current levels | `logger --action set --logger <name> --level DEBUG` | Adjust runtime log verbosity |

> **Need step-by-step diagnostic playbooks for each symptom?**
> Use the Read tool: `.agents/skills/peeka-diagnostics/refs/playbooks.md`

---

## Section 8: Condition Expressions (brief)

Use `--condition` to filter observations safely (sandboxed simpleeval). Common variable: `cost` (ms) is only available after the function finishes (not with `-b/--before`).

> **Need full variables + examples for `--condition`?**
> Use the Read tool: `.agents/skills/peeka-diagnostics/refs/commands.md`

---

## Section 9: Safety Protocol

**MANDATORY for every diagnostic session**:

1. **Always bound streaming commands**: Use `-n/--times` (watch, trace, stack) or `-c/--cycles` (monitor, top). Never run unbounded in automated workflows.

2. **Always reset before detach**: Restores all instrumented functions to their original state.
   ```bash
   ${PEEKA_CMD} reset && ${PEEKA_CMD} detach
   ```

3. **One session at a time**: Only one peeka agent can be attached to a process. If another session exists, detach it first.

4. **Recovery from stale sessions**: If a previous session wasn't cleaned up properly:
   ```bash
   # Attempt to detach the stale session
   ${PEEKA_CMD} detach
   # If detach fails, re-attach first then detach cleanly
   ${PEEKA_CMD} attach <pid> && ${PEEKA_CMD} reset && ${PEEKA_CMD} detach
   ```

5. **Don't watch hot loops without `-n`**: Functions called thousands of times per second will produce massive output and impact performance without a bound.

6. **Condition expressions are sandboxed**: No `eval`, `exec`, `open`, `import` — safe to use freely. No risk of code injection.

7. **Production impact**: peeka adds <5% overhead per instrumented function. Minimize the number of concurrent watch/trace targets.

8. **Use `jq --unbuffered`** when piping streaming command output for real-time display.

---

## Section 10: Progressive Disclosure — Load More Detail

This skill file provides the essentials. For deeper reference, instruct the agent to load these files:

> **Need full command flags, options, and jq recipes?**
> Use the Read tool: `.agents/skills/peeka-diagnostics/refs/commands.md`
>
> **Need step-by-step diagnostic playbooks?**
> Use the Read tool: `.agents/skills/peeka-diagnostics/refs/playbooks.md`
>
> **Encountering errors or attach failures?**
> Use the Read tool: `.agents/skills/peeka-diagnostics/refs/troubleshooting.md`
>
> **Need environment detection script source?**
> Use the Read tool: `.agents/skills/peeka-diagnostics/scripts/detect-env.sh`

### Output & parsing (JSONL)

Peeka CLI output is JSONL (one JSON object per line). For the full JSONL schema, jq recipes, and the Python fallback parser, use the Read tool: `.agents/skills/peeka-diagnostics/refs/commands.md`
