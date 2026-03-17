---
layout: default
title: Command Reference
nav_order: 4
has_children: true
permalink: /commands
---

# Command Reference
{: .no_toc }

Peeka provides a series of powerful diagnostic commands, each focused on specific diagnostic scenarios. This documentation covers 13 core commands.
{: .fs-6 .fw-300 }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Command Overview

| Command | Function | Use Case |
|---------|----------|----------|
| attach | Attach to target process | First step for all scenarios |
| watch | Observe function calls | View params, return values, execution time |
| trace | Trace call chain | Analyze function call relationships and time distribution |
| stack | Trace call stack | Track who calls the function |
| monitor | Performance statistics | Real-time monitoring of function performance metrics |
| logger | Log management | Dynamically adjust log level |
| memory | Memory analysis | Analyze memory usage and leaks |
| inspect | Object inspection | Runtime object property inspection |
| search (sc/sm) | Search classes and methods | Code exploration and discovery |
| reset | Reset enhancements | Restore observed functions |
| thread | Thread analysis | Enumerate threads and view thread stacks |
| top | Function profiling | Function-level performance hotspot analysis |
| detach | Disconnect | Safely exit diagnostic session |

---

## Common Parameters

All commands share the following parameter format:

### Pattern Format

Used to specify target function patterns:

```bash
# Class method
module.ClassName.method_name

# Module function
module.function_name

# Wildcard support
module.ClassName.*
module.*
*.method_name
```

### Output Format

All commands output JSONL (JSON Lines) format, one JSON object per line:

```json
{"type":"status","level":"info","message":"..."}
{"type":"success","command":"attach","data":{...}}
{"type":"observation","watch_id":"...","data":{...}}
```

### Message Types

| Type | Description |
|------|-------------|
| `status` | Status information (non-critical) |
| `success` | Command success |
| `error` | Command failure |
| `event` | Control events (started, stopped) |
| `observation` | Observation data |
| `result` | Query results |

---

## Command Usage Flow

### Standard Diagnostic Flow

```bash
# 1. Attach to process
peeka-cli attach <pid>

# 2. Use specific diagnostic commands
peeka-cli watch "module.func"

# 3. Analyze results
peeka-cli watch "module.func" | jq 'select(.type == "observation")'

# 4. (Optional) Reset enhancements
peeka-cli reset "module.func"
```

### TUI Interactive Flow

```bash
# Launch TUI
peeka

# Use number keys to switch views
# 1 - Dashboard
# 2 - Watch view
# 3 - Trace view
# 4 - Stack view
# 5 - Monitor view
# 6 - Memory view
# 7 - Logger view
# 8 - Inspect view
# 9 - Threads view
# 0 - Top view
```

See [TUI Usage Guide]({% link tui.md %}) for details.


---

## Conditional Expressions

Many commands support `--condition` parameter for filtering observation results.

### Available Variables

| Variable | Description | Type |
|----------|-------------|------|
| `params` | Function parameter list | list |
| `kwargs` | Keyword argument dictionary | dict |
| `returnObj` | Return value | any |
| `throwExp` | Exception object | Exception or None |
| `cost` | Execution time (milliseconds) | float |
| `target` | Target object (instance methods) | object |

### Condition Examples

```bash
# Parameter filtering
--condition "params[0] > 100"
--condition "len(params) > 2"
--condition "kwargs.get('debug') == True"

# Return value filtering
--condition "returnObj is not None"
--condition "len(returnObj) > 10"

# Execution time filtering
--condition "cost > 100"  # Over 100ms
--condition "cost > 10 and cost < 100"  # 10-100ms

# Exception filtering
--condition "throwExp is not None"
--condition "type(throwExp).__name__ == 'ValueError'"

# Combined conditions
--condition "params[0] > 100 and cost > 50"
--condition "len(params) > 2 or returnObj is None"
```

### Security Restrictions

Conditional expressions use `simpleeval` library for safe evaluation, not supporting:

- ❌ `__import__`, `eval`, `exec` and other dangerous functions
- ❌ File operations (`open`, `read`, `write`)
- ❌ Reflection operations (`__class__`, `__subclasses__`)
- ✅ Arithmetic, comparison, logical operations
- ✅ String operations, list indexing
- ✅ Safe built-in functions (`len`, `str`, `int`, etc.)

---

## Performance Impact

| Command | Performance Overhead | Notes |
|---------|---------------------|-------|
| `watch` | < 1% | Decorator injection, minimal overhead |
| `trace` | < 5% (3.12+) | Uses sys.monitoring API |
| `trace` | < 20% (3.9-3.11) | Uses sys.settrace |
| `stack` | < 1% | Only captures call stack |
| `monitor` | < 1% | Periodic statistics |
| `logger` | 0% | No performance impact |
| `memory` | Configurable | Depends on sampling frequency |

---

## Next Steps


Select the command you need for detailed documentation:

- [attach - Attach to target process]({% link commands/attach.md %})
- [watch - Observe function calls]({% link commands/watch.md %})
- [trace - Trace call chain]({% link commands/trace.md %})
- [stack - Trace call stack]({% link commands/stack.md %})
- [monitor - Performance monitoring]({% link commands/monitor.md %})
- [logger - Log management]({% link commands/logger.md %})
- [memory - Memory analysis]({% link commands/memory.md %})
- [inspect - Object inspection]({% link commands/inspect.md %})
- [search - Search classes and methods]({% link commands/search.md %})
- [reset - Reset enhancements]({% link commands/reset.md %})
- [thread - Thread analysis]({% link commands/thread.md %})
- [top - Function profiling]({% link commands/top.md %})
- [detach - Disconnect]({% link commands/detach.md %})

> **Note**: Detailed English documentation for individual commands is being prepared. Currently, command documentation is available in Chinese. Please refer to the Chinese version for complete command documentation.

Or view [Quick Start]({% link quickstart.md %}) to learn basic usage methods.
