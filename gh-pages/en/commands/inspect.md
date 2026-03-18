---
layout: default
title: inspect Command
parent: Command Reference
nav_order: 8
permalink: /commands/inspect
---

# inspect Command
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Overview

The `inspect` command provides **runtime object inspection** capabilities, allowing you to view object states in running Python processes without modifying code. It supports three operations:

| Operation | Function | Typical Use |
|-----------|----------|-------------|
| **get** | Get module/class attribute values | View configs, constants, state variables |
| **instances** | Find type instances | Memory leak troubleshooting, object tracking |
| **count** | Count instance numbers | Quickly assess object count |



---

## TUI Usage

In TUI mode, press **`8`** key to switch to **Inspect View**, providing the following interactive features:

- **Operation Selection**: Visually switch between get/instances/count operations
- **get Operation**: Get module/class attribute values
  - Input target path (e.g., `sys.version`, `module.attr`)
  - Configure output depth
  - Display attribute value and type information
- **instances Operation**: Find type instances
  - Input class name (e.g., `myapp.User`)
  - Configure result count limit and filter expression
  - Display instance list and attributes
  - Support --gc-first (GC before execution)
- **count Operation**: Count instance numbers
  - Input class name (e.g., `list`, `dict`)
  - Quickly count instance numbers
- **Quick Operations**:
  - Press Enter after entering parameters to execute
  - Press `c` to clear results

**CLI Equivalent Commands**: All examples below use CLI commands for demonstration. TUI provides the same functionality with a graphical interface.

## Use Cases

### 1. Configuration Checking

View configuration values at runtime in production without restarting the process:

```bash
peeka inspect --action get --target "app.config.DEBUG"
```

### 2. Memory Leak Troubleshooting

Find all instances of a specific type to check for unreleased objects:

```bash
peeka inspect --action instances --type myapp.User --limit 10
```

### 3. Object Statistics

Quickly count objects of a type to assess memory usage:

```bash
peeka inspect --action count --type list
```

### 4. State Diagnosis

View runtime state variables to diagnose application behavior:

```bash
peeka inspect --action get --target "sys.path"
```

---

## Command Format

```bash
peeka inspect --action <action> [options]
```

### Basic Parameters

| Parameter | Description | Required | Default |
|-----------|-------------|----------|---------|
| `-p, --pid` | Target process PID | Yes | - |
| `--action` | Operation type | No | `get` |

### action Operation Types

| Action | Description | Required Parameters |
|--------|-------------|---------------------|
| **get** | Get attribute value | `--target` |
| **instances** | Find instances | `--type` |
| **count** | Count instances | `--type` |

---

## Parameter Descriptions

### get Operation Parameters

| Parameter | Description | Example |
|-----------|-------------|---------|
| `--target` | Target path (dot-separated) | `sys.version` |
| `--depth` | Output nesting depth | `--depth 3` |

**target Resolution Rules**:

- First segment must be a module in `sys.modules`
- Subsequent segments found through `getattr()` chaining
- **Does not support** dictionary key lookup (e.g., `config["debug"]`)

Examples:

- `sys.version` → `getattr(sys.modules["sys"], "version")`
- `myapp.Config.DEBUG` → `getattr(getattr(sys.modules["myapp"], "Config"), "DEBUG")`

### instances Operation Parameters

| Parameter | Description | Default | Range |
|-----------|-------------|---------|-------|
| `--type` | Type name | - | Required |
| `--limit` | Result count limit | `10` | 1-1000 |
| `--depth` | Output nesting depth | `2` | 0-10 |
| `--filter-express` | Filter expression | None | SimpleEval syntax |
| `--gc-first` | Run GC before scan | `False` | - |

**type Resolution Rules**:

- Built-in types: `str`, `int`, `list`, `dict`, `set`, `tuple`, `bytes`, `bool`, `float`
- Custom types: `module.ClassName` (module must be loaded)
- **Does not support** dynamic module imports

### count Operation Parameters

| Parameter | Description | Default |
|-----------|-------------|---------|
| `--type` | Type name | - |
| `--filter-express` | Filter expression | None |
| `--gc-first` | Run GC before scan | `False` |

**Special Note**: `count` operation **traverses all** objects (no limit constraint), only counts without storing objects, minimal memory overhead.

### Filter Expressions

Filter expressions use **SimpleEval** safe evaluator, supported syntax:

| Syntax | Description | Example |
|--------|-------------|---------|
| `obj.*` | Object attributes | `obj.value` |
| Comparison | `>`, `<`, `==`, `!=` | `obj.age > 18` |
| Logic | `and`, `or`, `not` | `obj.active and obj.age > 18` |
| Arithmetic | `+`, `-`, `*`, `/` | `obj.score * 2 > 100` |
| Functions | `len()`, `str()`, `int()`, `bool()` | `len(obj.items) > 0` |

**Safety Restrictions**:

- ❌ Forbidden: `eval()`, `exec()`, `compile()`
- ❌ Forbidden: `__import__`, `open()`, `__class__`
- ❌ Forbidden: accessing private attributes (`__*__`)

**Error Handling**:

- Syntax errors: **entire command fails**
- Runtime errors (e.g., attribute doesn't exist): **skip that object**

---

## Output Format

### get Response

```json
{
  "status": "success",
  "action": "get",
  "target": "sys.version",
  "type": "str",
  "value": "3.14.2 (main, Jan  1 2026, 10:00:00) [GCC 11.4.0]"
}
```

| Field | Description |
|-------|-------------|
| `status` | Status: `success` or `error` |
| `action` | Operation type |
| `target` | Queried target path |
| `type` | Value type name |
| `value` | Attribute value (depth limited) |

### instances Response

```json
{
  "status": "success",
  "action": "instances",
  "class_name": "list",
  "count": 5,
  "limit": 10,
  "truncated": false,
  "instances": [
    {
      "type": "list",
      "value": [
        1,
        2,
        3
      ]
    },
    {
      "type": "list",
      "value": [
        "a",
        "b"
      ]
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `class_name` | Queried type |
| `count` | Number of returned instances (`== len(instances)`) |
| `limit` | Requested limit |
| `truncated` | Whether more instances exist (`true`/`false`) |
| `instances` | Instance array (depth limited) |

**truncated Semantics**:

- `true`: More matching instances exist in heap (count unknown)
- `false`: All matching GC-tracked objects returned

### count Response

```json
{
  "status": "success",
  "action": "count",
  "class_name": "list",
  "count": 240
}
```

| Field | Description |
|-------|-------------|
| `class_name` | Queried type |
| `count` | Total GC-tracked instances |

### error Response

```json
{
  "status": "error",
  "action": "get",
  "error": "Cannot resolve target: Module 'nonexistent' not loaded in target process"
}
```

---

## Usage Examples

### Example 1: View System Information

```bash
# View Python version
peeka inspect --action get --target "sys.version"

# View sys.path
peeka inspect --action get --target "sys.path" --depth 3
```

**Output**:

```json
{
  "status": "success",
  "action": "get",
  "target": "sys.path",
  "type": "list",
  "value": [
    "/usr/lib/python3.14",
    "/home/user/project",
    "... (truncated)"
  ]
}
```

### Example 2: View Configuration Values

```bash
# View application config
peeka inspect --action get --target "myapp.config.DEBUG"

# View class constant
peeka inspect --action get --target "myapp.Database.POOL_SIZE"
```

### Example 3: Memory Leak Troubleshooting

```bash
# Find all User instances
peeka inspect --action instances --type myapp.User --limit 20

# Filter active users
peeka inspect --action instances --type myapp.User \
  --filter-express "obj.active == True" --limit 10

# Filter large objects
peeka inspect --action instances --type list \
  --filter-express "len(obj) > 100" --limit 5
```

**Output**:

```json
{
  "status": "success",
  "action": "instances",
  "class_name": "myapp.User",
  "count": 20,
  "limit": 20,
  "truncated": true,
  "instances": [
    {
      "type": "myapp.User",
      "value": "<User(id=1, name='Alice', active=True)>"
    }
  ]
}
```

### Example 4: Object Statistics

```bash
# Count all list instances
peeka inspect --action count --type list

# Count dict instances
peeka inspect --action count --type dict

# Count objects with specific conditions
peeka inspect --action count --type myapp.Connection \
  --filter-express "obj.closed == False"
```

**Output**:

```json
{
  "status": "success",
  "action": "count",
  "class_name": "list",
  "count": 240
}
```

### Example 5: Combine with jq

```bash
# Extract value field
peeka inspect --action get --target "sys.version" | jq -r '.value'

# Count instances
peeka inspect --action count --type list | jq '.count'

# Pretty print
peeka inspect --action instances --type dict --limit 3 | jq .
```

---

## Complete Diagnostic Workflow

### Scenario: Memory Leak Troubleshooting

**Problem**: Production memory continuously growing, suspect class instances not released.

**Step 1: Count Objects**

```bash
# Periodically count suspicious types
peeka inspect --action count --type myapp.Cache
# Output: {"count": 1500}

# Count again after 5 minutes
peeka inspect --action count --type myapp.Cache
# Output: {"count": 1800}  ← Continuously growing!
```

**Step 2: View Instance Samples**

```bash
# Get first 10 instances
peeka inspect --action instances --type myapp.Cache --limit 10 | jq .

# View large objects
peeka inspect --action instances --type myapp.Cache \
  --filter-express "len(obj.data) > 1000" --limit 5
```

**Step 3: Check Configuration**

```bash
# View cache config
peeka inspect --action get --target "myapp.cache_config.MAX_SIZE"
# Discovered MAX_SIZE not taking effect!
```

**Step 4: Verify Fix**

After fixing code and redeploying, count again:

```bash
peeka inspect --action count --type myapp.Cache
# Output: {"count": 100}  ← Back to normal
```

---

## Important Notes

### ⚠️ GC Tracked Object Limitations

`gc.get_objects()` **only returns GC-tracked objects**:

| Type | Tracked | instances/count Result |
|------|---------|------------------------|
| `list`, `dict`, `set`, `tuple` | ✅ Yes | Reliable |
| Custom class instances | ✅ Yes | Reliable |
| `str`, `int`, `float`, `bytes` | ❌ No | May be 0 or incomplete |

**Recommendations**:

- Memory leak troubleshooting: prioritize **container types** or **custom classes**
- String/integer counting: results **unreliable**, reference only

### ⚠️ Target Resolution Rules

`--target` parameter uses `getattr()` chain, **does not support dictionary keys**:

```bash
# ❌ Wrong: dictionary key syntax not supported
peeka inspect --action get --target 'config["debug"]'

# ✅ Correct: get dictionary first, view manually
peeka inspect --action get --target "config" | jq '.value.debug'
```

### ⚠️ Module Loading Limitations

`--type` parameter **does not dynamically import modules**:

```bash
# ❌ Wrong: query fails when myapp not loaded
peeka inspect --action instances --type myapp.User

# ✅ Correct: ensure target process has imported myapp module
# (target code must have import myapp)
```

### ⚠️ Performance Impact

| Operation | Heap Traversal | Performance Impact |
|-----------|----------------|-------------------|
| `get` | ❌ No | Very low (< 1ms) |
| `instances` | ✅ Partial (until limit) | Medium (10-100ms) |
| `count` | ✅ Full | High (50-500ms) |

**Recommendations**:

- `count` operation may take longer in large memory processes
- Use carefully in production, avoid frequent calls

### ⚠️ Filter Expression Safety

Filter expressions use **SimpleEval** to prevent code injection:

```bash
# ✅ Safe: SimpleEval allowed operations
peeka inspect --action instances --type myapp.User \
  --filter-express "obj.age > 18 and obj.active"

# ❌ Forbidden: code injection attack
peeka inspect --action instances --type myapp.User \
  --filter-express "__import__('os').system('rm -rf /')"
# Error: Invalid filter expression: __import__ not allowed
```

---

## Common Issues

### Q1: instances returns count: 0, but I'm sure objects exist

**A**: Possible reasons:

1. **Objects not GC-tracked** (like `str`, `int`)
   ```bash
   # str/int may be unreliable
   peeka inspect --action count --type str  # May be 0

   # Use container types instead
   peeka inspect --action count --type list  # Reliable
   ```

2. **Module not loaded**
   ```bash
   # Confirm module imported
   peeka inspect --action get --target "sys.modules.keys()" | grep myapp
   ```

3. **filter-express filtered out all objects**
   ```bash
   # Test without filter first
   peeka inspect --action instances --type myapp.User --limit 5
   ```

### Q2: target query fails "Module not loaded"

**A**: Target module not imported in process.

**Solution**:

```bash
# Check loaded modules
peeka inspect --action get --target "list(sys.modules.keys())" | grep myapp

# If module not loaded, add import to target code
```

### Q3: filter-express syntax error

**A**: SimpleEval only supports limited syntax.

**Common Errors**:

```bash
# ❌ List comprehension not supported
--filter-express "[x for x in obj.items]"

# ✅ Use len() instead
--filter-express "len(obj.items) > 0"

# ❌ Dictionary key syntax not supported
--filter-express "obj['key'] > 0"

# ✅ Use attribute syntax
--filter-express "obj.key > 0"
```

### Q4: count operation very slow

**A**: `count` traverses entire heap, slow with many objects.

**Optimization Suggestions**:

```bash
# Use instances instead (has limit)
peeka inspect --action instances --type list --limit 10

# Or run count during off-peak hours
```

### Q5: instances truncated always true

**A**: Matching objects exceed `limit`.

**Solution**:

```bash
# Increase limit (max 1000)
peeka inspect --action instances --type list --limit 1000

# Or use filter to narrow scope
peeka inspect --action instances --type list \
  --filter-express "len(obj) > 100" --limit 10
```

---

## Advanced Tips

### Tip 1: Periodically Monitor Object Count

```bash
#!/bin/bash
# monitor_objects.sh - Monitor object count changes

PID=12345
TYPE="myapp.Connection"

while true; do
  COUNT=$(peeka inspect --action count --type $TYPE | jq '.count')
  echo "$(date): $TYPE count = $COUNT"
  sleep 60
done
```

### Tip 2: Combine get and instances

```bash
# First query config
CONFIG=$(peeka inspect --action get --target "myapp.config.MAX_CONNECTIONS" | jq '.value')

# Then count actual connections
ACTUAL=$(peeka inspect --action count --type myapp.Connection | jq '.count')

# Compare
echo "Config: $CONFIG, Actual: $ACTUAL"
```

### Tip 3: Use gc-first for Accurate Count

```bash
# Before GC
peeka inspect --action count --type myapp.Cache
# Output: {"count": 1500}

# After forced GC
peeka inspect --action count --type myapp.Cache --gc-first
# Output: {"count": 1200}  ← Cleaned unreferenced objects
```

### Tip 4: Complex Filter Expressions

```bash
# Multi-condition filter
peeka inspect --action instances --type myapp.User \
  --filter-express "obj.age > 18 and obj.active and len(obj.name) > 0" \
  --limit 10

# Arithmetic operations
peeka inspect --action instances --type myapp.Score \
  --filter-express "obj.math + obj.english > 180" \
  --limit 5
```

### Tip 5: Export for Analysis

```bash
# Export instances to file
peeka inspect --action instances --type myapp.User --limit 100 > users.json

# Offline analysis
jq '.instances | map(.value.age) | add / length' users.json  # Average age
jq '.instances | map(select(.value.active == true)) | length' users.json  # Active users
```

---


## Summary

### Core Features

| Operation | Purpose | Performance | Heap Traversal |
|-----------|---------|-------------|----------------|
| **get** | View attributes/config | Very fast | ❌ |
| **instances** | Memory troubleshooting | Medium | Partial |
| **count** | Object statistics | Slower | Full |

### Typical Workflow

1. **Quick check**: `get` to view config and state
2. **Quantity assessment**: `count` to count objects
3. **Detailed analysis**: `instances` to get instance samples
4. **Filter refinement**: `--filter-express` to narrow scope

### Best Practices

✅ **Recommended**:

- Use container types (list, dict) for instances/count
- Combine with jq to process JSON output
- Periodically monitor key object counts
- Use filter expressions to precisely locate issues

❌ **Avoid**:

- Frequent count execution (performance impact)
- Using instances on str/int (unreliable)
- Complex logic in filter expressions
- Forgetting to check if module loaded

### Related Commands

- `memory` - Memory analysis and tracking
- `sc` - Search classes
- `sm` - Search methods
