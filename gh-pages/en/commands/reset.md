---
layout: default
title: reset Command
parent: Command Reference
nav_order: 10
permalink: /commands/reset
---

# reset Command
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}


## Overview

The `reset` command is used to **restore enhanced methods to their original state**, removing observation logic injected by commands like `watch` and `stack`. This is a cleanup command that can selectively reset all enhancements or only those matching specific patterns.



## TUI Usage

**Note**: The reset command has **no dedicated view in TUI**, but can be executed through the command input box:

- Press `:` in the TUI main interface to enter command mode
- Enter `reset` command to execute

**Common Operations**:
- List all enhancements: `: reset --list` or `: reset -l`
- Reset all enhancements: `: reset`
- Reset specific pattern: `: reset "myapp.service.*"`

**Shortcuts**: Each view typically has an independent "Stop" button, no need to manually enter reset command.

**CLI Equivalent Commands**: All examples below use CLI commands for demonstration.
## Use Cases

- **Cleanup after diagnostics**: Remove all injected observation logic after completing troubleshooting
- **Reconfigure observations**: Reset existing enhancements before re-observing with different parameters
- **Selective cleanup**: Remove only specific module or class enhancements while preserving others
- **View current state**: List all currently active enhancements to understand system state
- **Performance restoration**: Remove observation logic to eliminate performance overhead

## Command Format

```bash
peeka-cli reset [pattern] [options]
```

**Prerequisites**: Must first use `peeka-cli attach <pid>` to attach to the target process

### Parameters

| Parameter | Description | Default | Example |
|-----------|-------------|---------|---------|
| `pattern` | Optional matching pattern (supports wildcards) | None | `"myapp.service.*"` |
| `-l, --list` | List current enhancements without resetting them | - | `--list` |

### Pattern Matching Rules

The `pattern` parameter supports Unix shell-style wildcards (based on fnmatch):

| Wildcard | Meaning | Example | Matches |
|---------|---------|---------|---------|
| `*` | Match any characters | `myapp.service.*` | `myapp.service.UserService` |
| `?` | Match single character | `myapp.?.query` | `myapp.a.query`, `myapp.b.query` |
| None | Exact match | `myapp.service.UserService.query` | Only exact pattern match |

**Note**: Pattern matching is performed against **stored patterns**, not function names.

## Output Format

### reset Operation Response

```json
{
  "status": "success",
  "action": "reset",
  "affected": [
    {
      "watch_id": "watch_a1b2c3d4",
      "pattern": "myapp.service.UserService.query"
    },
    {
      "watch_id": "watch_e5f6g7h8",
      "pattern": "myapp.service.UserService.update"
    }
  ],
  "count": 2
}
```

**Field Descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Operation status (`success`/`error`) |
| `action` | string | Operation type (`reset`) |
| `affected` | array | List of reset enhancements |
| `count` | int | Number of successful resets |

**affected Array Elements**:

| Field | Type | Description |
|-------|------|-------------|
| `watch_id` | string | Observation session ID |
| `pattern` | string | Original function matching pattern |
| `error` | string | (Optional) Error on reset failure |

### list Operation Response

```json
{
  "status": "success",
  "action": "list",
  "enhanced": [
    {
      "watch_id": "watch_a1b2c3d4",
      "pattern": "myapp.service.UserService.query",
      "command": "watch",
      "count": 42
    },
    {
      "watch_id": "stack_i9j0k1l2",
      "pattern": "myapp.handler.process",
      "command": "stack",
      "count": 15
    }
  ],
  "total": 2
}
```

**Field Descriptions**:

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | Operation status |
| `action` | string | Operation type (`list`) |
| `enhanced` | array | Current enhancement list |
| `total` | int | Total enhancement count |

**enhanced Array Elements**:

| Field | Type | Description |
|-------|------|-------------|
| `watch_id` | string | Observation session ID |
| `pattern` | string | Function matching pattern |
| `command` | string | Command that created enhancement (`watch`/`stack`) |
| `count` | int | Number of observations captured |

## Usage Examples

### Example 1: Reset All Enhancements

```bash
# Reset all enhancements
peeka-cli reset
```

**Output**:

```json
{
  "status": "success",
  "action": "reset",
  "affected": [
    {"watch_id": "watch_001", "pattern": "myapp.service.query"},
    {"watch_id": "watch_002", "pattern": "myapp.handler.process"},
    {"watch_id": "stack_003", "pattern": "myapp.api.handle"}
  ],
  "count": 3
}
```

**Use Cases**:
- Complete cleanup after diagnostics
- Restore system to non-observation state
- Eliminate all performance overhead

### Example 2: Reset by Pattern

```bash
# Reset only myapp.service module enhancements
peeka-cli reset "myapp.service.*"

# Reset all methods of specific class
peeka-cli reset "myapp.service.UserService.*"

# Reset specific method
peeka-cli reset "myapp.service.UserService.query"
```

**Output** (matches 2 enhancements):

```json
{
  "status": "success",
  "action": "reset",
  "affected": [
    {"watch_id": "watch_001", "pattern": "myapp.service.UserService.query"},
    {"watch_id": "watch_002", "pattern": "myapp.service.UserService.update"}
  ],
  "count": 2
}
```

**Use Cases**:
- Selective cleanup of specific modules
- Preserve observations in other modules
- Reconfigure observation parameters for specific functions

### Example 3: No Matching Pattern

```bash
# Pattern doesn't match any enhancements
peeka-cli reset "nonexistent.*"
```

**Output**:

```json
{
  "status": "success",
  "action": "reset",
  "affected": [],
  "count": 0
}
```

### Example 4: List Current Enhancements

```bash
# View all active enhancements
peeka-cli reset --list
```

**Output**:

```json
{
  "status": "success",
  "action": "list",
  "enhanced": [
    {
      "watch_id": "watch_a1b2c3d4",
      "pattern": "myapp.service.UserService.query",
      "command": "watch",
      "count": 42
    },
    {
      "watch_id": "stack_i9j0k1l2",
      "pattern": "myapp.handler.process",
      "command": "stack",
      "count": 15
    }
  ],
  "total": 2
}
```

**Use Cases**:
- Understand current system state
- Verify if observations are still active
- Decide which enhancements need resetting

### Example 5: List Empty Enhancements

```bash
# When no active enhancements
peeka-cli reset --list
```

**Output**:

```json
{
  "status": "success",
  "action": "list",
  "enhanced": [],
  "total": 0
}
```

### Example 6: Using with jq

```bash
# Extract reset count
peeka-cli reset | jq '.count'
# Output: 3

# Extract affected pattern list
peeka-cli reset "myapp.*" | jq -r '.affected[].pattern'
# Output:
# myapp.service.query
# myapp.handler.process

# Count current enhancements
peeka-cli reset --list | jq '.total'
# Output: 5

# View enhancements from specific command
peeka-cli reset --list | jq '.enhanced[] | select(.command == "watch")'

# Sort by observation count
peeka-cli reset --list | jq '.enhanced | sort_by(.count) | reverse'
```

## Typical Workflows

### Workflow 1: Cleanup After Diagnostics

```bash
# 1. Start diagnostics
peeka-cli watch "myapp.service.query" -n 100

# 2. View observation data (automatically stops after 100 times)
# ... analyze data ...

# 3. Cleanup all enhancements after diagnostics
peeka-cli reset

# Verify
peeka-cli reset --list
# Output: {"total": 0}
```

### Workflow 2: Reconfigure Observations

```bash
# 1. Currently observing (depth 2)
peeka-cli watch "myapp.service.query" -x 2

# 2. Need deeper output (depth 3)
# First reset current observation
peeka-cli reset "myapp.service.query"

# 3. Re-observe with new parameters
peeka-cli watch "myapp.service.query" -x 3
```

### Workflow 3: Multi-Module Diagnostics

```bash
# 1. Observe multiple modules
peeka-cli watch "myapp.service.*" &
peeka-cli watch "myapp.handler.*" &
peeka-cli watch "myapp.api.*" &

# 2. After diagnosing service module, cleanup only service
peeka-cli reset "myapp.service.*"

# 3. Continue observing other modules
# handler and api observations continue running

# 4. Cleanup everything when finished
peeka-cli reset
```

### Workflow 4: Periodic Status Checks

```bash
#!/bin/bash
# check_enhancements.sh - Periodic enhancement status check

while true; do
  TOTAL=$(peeka-cli reset --list | jq '.total')
  echo "$(date): Active enhancements = $TOTAL"

  if [ "$TOTAL" -gt 10 ]; then
    echo "Warning: Too many enhancements, consider cleanup"
  fi

  sleep 300  # Check every 5 minutes
done
```

## Important Notes

### ⚠️ Monitor Command Not Affected

The `reset` command **only affects enhancements created by `watch` and `stack` commands**. The `monitor` command uses an independent tracking mechanism and won't be cleared by reset.

```bash
# monitor is not affected
peeka-cli monitor 12345 "myapp.service.query"  # Start monitoring

peeka-cli reset                        # Reset won't stop monitor

# Need to stop monitor separately
peeka-cli reset "myapp.service.*"
```

### ⚠️ Pattern Matching Rules

Patterns match against **stored patterns**, not function names:

```bash
# Assuming previously executed:
peeka-cli watch "myapp.service.UserService.query"

# ✅ Correct: Match stored pattern
peeka-cli reset "myapp.service.*"              # Match success
peeka-cli reset "myapp.service.UserService.*"  # Match success

# ❌ Wrong: Try to match class name (won't work)
peeka-cli reset "UserService.*"                # No match
```

### ⚠️ Reset is Irreversible

Reset operations immediately remove enhancement logic and **cannot be undone**. To continue observing, you must re-execute `watch` or `stack` commands.

```bash
# Need to re-observe after reset
peeka-cli reset "myapp.service.query"
peeka-cli watch "myapp.service.query" -n 100  # Re-start observation
```

### ⚠️ Performance Restoration

After reset, functions return to original state with immediate elimination of performance overhead:

| State | Performance Overhead |
|-------|---------------------|
| Before enhancement | 0% |
| During watch observation | 2-5% |
| After reset | 0% |

### ⚠️ Concurrency Safety

The reset command is thread-safe, but edge cases may occur in high-concurrency scenarios:

- During reset, ongoing observations may still produce data
- Calls immediately after reset will use the original function

## Common Questions

### Q1: What's the difference between reset and stopping observation streaming?

**A**:

- `reset`: Removes the injected decorator from the target function, permanently deletes the enhancement logic
- `Ctrl+C` (or close CLI): Stops the client-side data streaming, but the enhancement logic remains active in the target process

**Sequence Explanation**:

```
Ctrl+C stops streaming client: Observation data stops returning, but enhancement still runs
reset removes enhancement: Deletes the decorator from target process, fully restores original function
```

**Recommended Usage**:

- Temporary pause of observation: Use `Ctrl+C` (only disconnects client)
- Complete cleanup of enhancements: Use `reset` command (removes injected logic)
- Continue diagnostics on other functions: Use `reset` first, then restart other observations

```bash
# Method 1: Temporary pause (client disconnect)
# Ctrl+C

# Method 2: Complete cleanup (remove enhancement)
peeka-cli reset "myapp.service.*"
```

### Q2: How to reset specific watch_id?

**A**: reset doesn't directly support watch_id parameter, but can use exact pattern matching:

```bash
# 1. View pattern corresponding to watch_id
peeka-cli reset --list | jq '.enhanced[] | select(.watch_id == "watch_001")'
# Output: {"watch_id": "watch_001", "pattern": "myapp.service.query", ...}

# 2. Reset using exact pattern
peeka-cli reset "myapp.service.query"
```

**Or directly use watch stop**:

```bash
peeka-cli reset "watch_001"
```

### Q3: Will reset affect running functions?

**A**: No. Reset only replaces function references, won't interrupt executing calls.

**Sequence Explanation**:

```
Time T0: Function A starts executing (using enhanced version)
Time T1: Execute reset (replace function reference)
Time T2: Function A continues executing (still uses enhanced version, already entered)
Time T3: Function A ends (produces observation data)
Time T4: New Function A call (uses original version)
```

### Q4: Is no matching pattern an error?

**A**: Not an error, returns `count: 0`.

```bash
peeka-cli reset "nonexistent.*"
# Output: {"status": "success", "count": 0}
```

This is expected behavior, convenient for script usage (won't error on no match).

### Q5: How to reset all watch but keep stack?

**A**: Current version doesn't support filtering by command type, but can achieve indirectly through pattern matching:

```bash
# If watch and stack use different modules
peeka-cli reset "myapp.service.*"  # Assuming only watch observes this module
```

**Future Plan**: Support `--command watch` parameter for filtering.

### Q6: What if reset --list output is too much?

**A**: Use jq to filter:

```bash
# Only view watch command enhancements
peeka-cli reset --list | jq '.enhanced[] | select(.command == "watch")'

# Only view specific module enhancements
peeka-cli reset --list | jq '.enhanced[] | select(.pattern | startswith("myapp.service"))'

# Sort by observation count
peeka-cli reset --list | jq '.enhanced | sort_by(.count) | reverse'
```

## Summary

The `reset` command is a powerful tool for production environment enhancement management, particularly suitable for:
- Cleanup after diagnostics
- Reconfiguring observation parameters
- Selective module cleanup
- System state inspection

**Best Practices**:
- Record state before modification (for easy restoration)
- Immediately restore original level after debugging
- Use `--pattern` to filter loggers (improve efficiency)
- Combine with `jq` for powerful data analysis

**Next Steps**:
- Learn [`watch`](watch.md) command (observe function calls)
- Learn [`stack`](stack.md) command (trace call stacks)
- Learn [`monitor`](monitor.md) command (performance monitoring)
- Reference [AGENTS.md](../AGENTS.md) (developer guide)
