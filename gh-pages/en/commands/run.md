---
layout: default
title: run Command
parent: Command Reference
nav_order: 14
permalink: /en/commands/run
---

# run Command
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}


## Overview

The `run` command **launches a Python script with Peeka injected from startup** — no need for the process to already be running. It is designed for observing **import-time code**, **initialization logic**, or **short-lived scripts** where attaching after-the-fact is impossible.

Unlike the `attach` workflow, `run` gives you full diagnostic capability from the very first line of the script.


## Use Cases

- **Import-time observation**: Capture module loading, class initialization, and other one-time startup code
- **Short-lived scripts**: Processes that finish too quickly to attach manually
- **Batch jobs**: Diagnose cron tasks, data pipelines, and one-shot scripts
- **CI/CD debugging**: Capture function behavior in automated pipelines without modifying code
- **Reproduce startup bugs**: Control startup conditions precisely to reproduce issues that only appear at launch

## Command Format

```bash
peeka-cli run <script> [script_args] -- <command> [command_options]
```

`--` is the required separator — everything to its left is the script and its arguments; everything to the right is the Peeka command and its options.

### Parameters

| Parameter          | Description                                    | Default |
|--------------------|------------------------------------------------|---------|
| `script`           | Path to the Python script to run               | —       |
| `script_args`      | Arguments passed to the script (optional)      | —       |
| `--`               | Required separator                             | —       |
| `command`          | Peeka command (watch / trace / stack)          | —       |
| `command_options`  | Options for the Peeka command                  | —       |
| `--output-file`    | Write JSONL output to file instead of stdout   | —       |

### Supported Sub-commands

The Peeka command after `--` supports all the same options as when used standalone:

| Sub-command | Purpose                                            |
|-------------|----------------------------------------------------|
| `watch`     | Observe function calls (args, return value, timing)|
| `trace`     | Trace call tree with timing breakdown              |
| `stack`     | Capture call stack at function entry               |

## Examples

### Example 1: Simplest usage

```bash
peeka-cli run myscript.py -- watch "mymodule.MyClass.init_db"
```

Observes `init_db` from the moment the script starts.

### Example 2: Passing script arguments

```bash
peeka-cli run myscript.py --env production --config /etc/app.yml -- watch "mymodule.func"
```

`--env` and `--config` go to the script; `watch "mymodule.func"` is the Peeka command.

### Example 3: Trace call tree

```bash
peeka-cli run myscript.py -- trace "mymodule.func" -d 3
```

Traces the call tree of `mymodule.func` up to 3 levels deep.

### Example 4: Conditional filtering

```bash
peeka-cli run myscript.py -- watch "mymodule.func" --condition "params[0] > 100"
```

Only captures calls where the first argument is greater than 100.

### Example 5: Output to file

```bash
peeka-cli run myscript.py -- watch "mymodule.func" --output-file observations.jsonl
```

Writes all observation data to `observations.jsonl`. The script's own stdout is unaffected.

### Example 6: Limit observation count

```bash
peeka-cli run myscript.py -- watch "mymodule.func" -n 10
```

Automatically stops observing after 10 captures.

### Example 7: Capture call stack

```bash
peeka-cli run myscript.py -- stack "mymodule.func" -n 3
```

Captures the call stack at `mymodule.func` entry, 3 times.

## Output Format

Output format is identical to `watch`/`trace`/`stack` — one JSON object per line (JSONL) with a `type` field:

```json
{"type": "event", "event": "watch_started", "data": {"watch_id": "watch_001", "pattern": "mymodule.func"}}
{
  "type": "observation",
  "watch_id": "watch_001",
  "timestamp": 1705586200.123,
  "func_name": "mymodule.MyClass.func",
  "args": ["hello", 42],
  "kwargs": {},
  "result": true,
  "success": true,
  "duration_ms": 1.23,
  "count": 1
}
{"type": "event", "event": "watch_stopped", "data": {"watch_id": "watch_001"}}
```

### Processing with jq

```bash
# Show only observation data
peeka-cli run myscript.py -- watch "mymodule.func" | jq 'select(.type == "observation")'

# Find slow calls
peeka-cli run myscript.py -- watch "mymodule.func" | jq 'select(.type == "observation" and .data.duration_ms > 100)'

# Save and analyze
peeka-cli run myscript.py -- watch "mymodule.func" --output-file out.jsonl
jq '.args' out.jsonl
```

## run vs attach

| Feature              | `run`                           | `attach`                        |
|----------------------|---------------------------------|---------------------------------|
| Process state        | Launched by Peeka               | Already running                 |
| Observation window   | From the very first line        | From the moment of attach       |
| Best for             | Short-lived scripts, init logic | Long-running services           |
| How to start         | `peeka-cli run script.py -- …`  | `peeka-cli attach <pid>`        |
| Requires ptrace/PEP768 | No (direct injection)         | Yes                             |

**Recommendation**:
- Production services, daemons → use `attach`
- Scripts, batch jobs, startup-phase diagnostics → use `run`

## Notes

### ⚠️ The `--` separator is required

```bash
# ✅ Correct: -- separates script args from Peeka command
peeka-cli run myscript.py arg1 -- watch "mymodule.func"

# ❌ Wrong: missing -- causes parse errors
peeka-cli run myscript.py arg1 watch "mymodule.func"
```

### ⚠️ Observation ends when the script exits

When the script finishes (normally or with an error), observation stops automatically. For continuous observation, use `attach` with a long-running process.

### ⚠️ --output-file only affects Peeka output

`--output-file` redirects Peeka's JSONL diagnostic data to the specified file. The script's own stdout/stderr is unaffected.

```bash
# Script's print() goes to terminal; Peeka data goes to file
peeka-cli run myscript.py -- watch "mymodule.func" --output-file peeka.jsonl
```

## Typical Workflows

### Diagnosing a batch script

```bash
# 1. Run script and observe key functions
peeka-cli run batch_job.py --date 2024-01-15 -- watch "etl.transform" --output-file etl_obs.jsonl

# 2. Analyze results
jq 'select(.type == "observation")' etl_obs.jsonl | jq -s 'sort_by(.data.duration_ms) | reverse | .[0:5]'

# 3. Find slow calls
jq 'select(.type == "observation" and .data.duration_ms > 500)' etl_obs.jsonl
```

### Observing initialization logic

```bash
# Observe database connection pool setup at startup
peeka-cli run app.py -- watch "db.DatabasePool.connect" -n 5

# Trace configuration loading call tree
peeka-cli run app.py -- trace "config.load_settings" -d 4
```

## Related Commands

- [`attach`](attach.md) - Attach to an already-running process
- [`watch`](watch.md) - Observe function calls
- [`trace`](trace.md) - Trace call tree
- [`stack`](stack.md) - Capture call stack

## Changelog

| Version | Date       | Changes              |
|---------|------------|----------------------|
| 0.1.8   | 2025-04-28 | Added run command documentation |
