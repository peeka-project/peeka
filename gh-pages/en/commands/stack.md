---
layout: default
title: Peeka Stack Command Reference
parent: Command Reference
nav_order: 4
permalink: /commands/stack
---

# Peeka Stack Command Reference
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Command Overview

The `stack` command captures the complete call stack when a function is invoked, helping developers trace the function's call path. This is a powerful debugging tool, especially useful for analyzing complex call chains and locating the root cause of issues.

**Core Features**:
- Captures the complete call stack when a function is called
- Displays file names, line numbers, function names, and code snippets in the call chain
- Supports conditional filtering (capture only under specific conditions)
- Configurable stack depth (avoids excessive output)
- Real-time streaming output (JSON format)

**Difference from watch command**:
- `watch`: Observes function **arguments, return values, execution time**
- `stack`: Observes function **call path** (where it was called from)

## TUI Usage

In TUI mode, press **`4`** to switch to **Stack view**, which provides the following interactive features:

- **Pattern Input**: Supports function name autocomplete (fetched from target process in real-time)
- **Parameter Configuration**: Visual configuration for capture count, condition expressions, stack depth
- **Call Stack Visualization**: Real-time display of call stacks in table format
  - Shows file names, line numbers, function names, code snippets
  - Each capture displays complete call chain (from innermost to outermost)
- **Keyboard Shortcuts**:
  - Enter after entering pattern to start capturing
  - Press `c` to clear capture records
  - Press Delete to remove selected record
  - Up/Down arrow keys to browse stack levels

**CLI Equivalent**: All examples below use CLI commands for demonstration; TUI provides the same functionality with a graphical interface.
---

## Use Cases

### 1. Tracing Call Origins

**Scenario**: A function is called from multiple places, need to locate specific call paths.

```bash
# View where process_order function is called from
peeka-cli stack "myapp.orders.process_order"
```

**Output Example**:
```json
{
  "location": "AtEnter",
  "pattern": "myapp.orders.process_order",
  "params": [{"order_id": 12345}],
  "stack": [
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 156,
      "function": "create_order_view",
      "code_context": "result = process_order(order_data)"
    },
    {
      "filename": "/app/myapp/middleware/auth.py",
      "lineno": 45,
      "function": "check_permissions",
      "code_context": "return handler(request)"
    },
    {
      "filename": "/usr/lib/python3.14/http/server.py",
      "lineno": 89,
      "function": "handle_request",
      "code_context": "self.handle_one_request()"
    }
  ],
  "thread_id": 140234567890,
  "thread_name": "Thread-5"
}
```

### 2. Analyzing Recursive Calls

**Scenario**: Recursive function causes stack overflow, need to analyze recursion depth and patterns.

```bash
# Limit stack depth to 20 levels to avoid excessive output
peeka-cli stack "myapp.utils.recursive_func" --depth 20
```

### 3. Locating Exception Call Paths

**Scenario**: Function errors under specific conditions, need to trace the call chain when error occurs.

```bash
# Only capture stack when user_id is 999
peeka-cli stack "myapp.auth.check_permission" \
  --condition "params[0] == 999"
```

### 4. Analyzing Hot Call Paths

**Scenario**: Performance analysis, finding which paths most frequently call a function.

```bash
# Capture first 100 calls, then analyze path distribution
peeka-cli stack "myapp.db.execute_query" -n 100 | \
  jq -r '.stack[0] | "\(.filename):\(.lineno)"' | \
  sort | uniq -c | sort -rn
```

### 5. Cross-Module Call Tracing

**Scenario**: In microservices architecture, trace request propagation across modules.

```bash
# Trace API entry function call chain
peeka-cli stack "myapp.api.handle_request"
```

---

## Command Format

```bash
peeka-cli stack [--pid PID | --name NAME] <pattern> [options]
```

**Required Parameters**:
- `--pid, -p`: Target process PID (choose one: `--pid` or `--name`)
- `--name`: Target process name (choose one: `--pid` or `--name`)
- `pattern`: Target function pattern (e.g., `module.Class.method`)

**Optional Parameters**:
- `-n, --times`: Number of captures (-1 for unlimited, default -1)
- `--condition`: Condition expression (capture only when condition is met)
- `--depth`: Stack depth limit (default 10)

---

## Parameter Reference

### pattern - Function Pattern

Specifies the target function to trace, supports the following formats:

| Format | Description | Example |
|--------|-------------|---------|
| `module.function` | Module-level function | `myapp.utils.calculate` |
| `module.Class.method` | Class method | `myapp.models.User.save` |
| `module.Class.static_method` | Static method | `myapp.utils.Helper.validate` |

**Notes**:
- Must use fully qualified name (starting from module root)
- Wildcards not supported (same as `watch` command)
- Target function must be loaded into memory

### --times, -n - Number of Captures

Controls the number of captures to avoid generating massive amounts of data.

| Value | Behavior | Use Case |
|-------|----------|----------|
| `-1` (default) | Unlimited capture | Continuous monitoring, production troubleshooting |
| `1` | Capture once then stop | Only need to see the call stack once |
| `N` | Capture N times then stop | Sampling analysis, path distribution statistics |

**Examples**:
```bash
# Only capture first invocation
peeka-cli stack "myapp.func" -n 1

# Capture 50 samples
peeka-cli stack "myapp.func" -n 50
```

### --condition - Condition Expression

Captures stack only when condition is met, avoiding irrelevant data.

**Available Variables**:
- `params`: Function's positional arguments (tuple)
- `kwargs`: Function's keyword arguments (dict)
- `target`: The `self` object for instance methods

**Supported Operators**:
- Comparison: `==`, `!=`, `>`, `<`, `>=`, `<=`
- Logical: `and`, `or`, `not`
- Membership: `in`, `not in`
- String: `str(x).startswith()`, `str(x).endswith()`
- Length: `len(params)`, `len(kwargs)`
- Index access: `params[0]`, `kwargs.get('key')`

**Examples**:
```bash
# Only capture when first argument is greater than 100
peeka-cli stack "myapp.func" --condition "params[0] > 100"

# Only capture when number of parameters is greater than 2
peeka-cli stack "myapp.func" --condition "len(params) > 2"

# Only capture when user ID is specified value
peeka-cli stack "myapp.check_permission" \
  --condition "kwargs.get('user_id') == 999"

# Compound condition
peeka-cli stack "myapp.process" \
  --condition "params[0] > 10 and len(params) < 5"
```

**Security**:
- Implemented based on `simpleeval` library, all dangerous operations disabled
- Disallowed: `eval`, `exec`, `__import__`, `open`, `compile`
- Disallowed access to: `__class__`, `__subclasses__`
- Only supports whitelisted safe operations

### --depth - Stack Depth Limit

Controls the number of call stack levels captured to avoid excessive output.

| Value | Description | Use Case |
|-------|-------------|----------|
| `10` (default) | 10 stack levels | General debugging scenarios |
| `5` | 5 stack levels | Only care about recent few levels |
| `20` | 20 stack levels | Deep recursion analysis |
| `50` | 50 stack levels | Extreme scenarios (not recommended) |

**Notes**:
- Stack depth starts counting from the target function's **caller** (excludes the target function itself)
- Greater depth = larger output data volume
- Recommend setting reasonable depth based on actual needs (5-20 levels)

**Examples**:
```bash
# Only view the 3 most recent caller levels
peeka-cli stack "myapp.func" --depth 3

# Deep recursion analysis (up to 30 levels)
peeka-cli stack "myapp.recursive_func" --depth 30
```

---

## Output Format

The `stack` command outputs JSON Lines format (one JSON object per line), facilitating streaming processing and tool integration.

### Complete Output Example

```json
{
  "watch_id": "watch_20260131_001",
  "timestamp": 1738339200.123456,
  "location": "AtEnter",
  "pattern": "myapp.orders.process_order",
  "params": [
    {"order_id": 12345, "amount": 99.99}
  ],
  "kwargs": {
    "priority": "high"
  },
  "target": {
    "__attrs__": {
      "user_id": 999,
      "session": "<Session object>"
    }
  },
  "stack": [
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 156,
      "function": "create_order_view",
      "code_context": "result = process_order(order_data)"
    },
    {
      "filename": "/app/myapp/middleware/rate_limiter.py",
      "lineno": 78,
      "function": "rate_limit_decorator",
      "code_context": "return func(*args, **kwargs)"
    },
    {
      "filename": "/app/myapp/middleware/auth.py",
      "lineno": 45,
      "function": "check_permissions",
      "code_context": "return handler(request)"
    }
  ],
  "thread_id": 140234567890,
  "thread_name": "ThreadPoolExecutor-3",
  "cost": 0.0
}
```

### Field Descriptions

| Field | Type | Description |
|-------|------|-------------|
| `watch_id` | string | Unique identifier for the observation task |
| `timestamp` | float | Unix timestamp (seconds, with decimals) |
| `location` | string | Observation point location (`AtEnter` indicates function entry) |
| `pattern` | string | Target function pattern |
| `params` | array | Function's positional arguments |
| `kwargs` | object | Function's keyword arguments |
| `target` | object | The `self` object for instance methods (class methods only) |
| `stack` | array | Array of call stack frames (most important field) |
| `thread_id` | int | Thread ID |
| `thread_name` | string | Thread name |
| `cost` | float | Execution time (milliseconds, 0.0 at `AtEnter`) |

### Stack Array Elements

Each stack frame contains the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `filename` | string | Absolute path to source code file |
| `lineno` | int | Source code line number |
| `function` | string | Function/method name |
| `code_context` | string | Source code content of that line (trimmed) |

**Stack Frame Order**:
- `stack[0]`: **Most recent caller** (location that directly called the target function)
- `stack[1]`: Caller's caller
- `stack[n]`: Later entries are closer to the root of the call chain

---

## Usage Examples

### Example 1: Basic Call Stack Tracing

**Scenario**: View where `calculate_price` function is called from.

```bash
peeka-cli stack "myapp.pricing.calculate_price"
```

**Output**:
```json
{
  "watch_id": "watch_001",
  "timestamp": 1738339200.123,
  "location": "AtEnter",
  "pattern": "myapp.pricing.calculate_price",
  "params": [{"product_id": 789, "quantity": 5}],
  "stack": [
    {
      "filename": "/app/myapp/api/cart.py",
      "lineno": 234,
      "function": "checkout",
      "code_context": "total = calculate_price(cart_items)"
    },
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 89,
      "function": "checkout_view",
      "code_context": "result = cart.checkout()"
    }
  ],
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**Interpretation**:
- `calculate_price` was called by `checkout` function at `cart.py:234`
- `checkout` was called by `checkout_view` at `views.py:89`

### Example 2: Conditional Filtering

**Scenario**: Only trace calls with negative arguments (possible exception cases).

```bash
peeka-cli stack "myapp.utils.process_value" \
  --condition "params[0] < 0" \
  -n 10
```

**Output** (only outputs when argument is negative):
```json
{
  "watch_id": "watch_002",
  "timestamp": 1738339201.456,
  "location": "AtEnter",
  "pattern": "myapp.utils.process_value",
  "params": [-5],
  "stack": [
    {
      "filename": "/app/myapp/data/processor.py",
      "lineno": 67,
      "function": "validate_input",
      "code_context": "result = process_value(user_input)"
    }
  ],
  "thread_id": 140234567891,
  "thread_name": "WorkerThread-2"
}
```

**Use**: Quickly locate the source of abnormal input.

### Example 3: Limiting Stack Depth

**Scenario**: Only care about the 3 most recent caller levels.

```bash
peeka-cli stack "myapp.db.execute_query" --depth 3
```

**Output**:
```json
{
  "watch_id": "watch_003",
  "timestamp": 1738339202.789,
  "location": "AtEnter",
  "pattern": "myapp.db.execute_query",
  "params": ["SELECT * FROM users WHERE id = ?", [999]],
  "stack": [
    {
      "filename": "/app/myapp/models/user.py",
      "lineno": 123,
      "function": "get_by_id",
      "code_context": "return db.execute_query(sql, params)"
    },
    {
      "filename": "/app/myapp/api/users.py",
      "lineno": 45,
      "function": "get_user",
      "code_context": "user = User.get_by_id(user_id)"
    },
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 78,
      "function": "user_profile_view",
      "code_context": "return get_user(request.user_id)"
    }
  ]
}
```

### Example 4: Capture Once and Stop

**Scenario**: Only need to see the call stack once to confirm the call path.

```bash
peeka-cli stack "myapp.cache.get" -n 1
```

**Behavior**: Automatically stops tracing after capturing the first invocation, no further output.

### Example 5: Combined with jq Analysis

**Scenario**: Extract all call origins, analyze which file most frequently calls the target function.

```bash
peeka-cli stack "myapp.logger.log" -n 100 | \
  jq -r '.stack[0] | "\(.filename):\(.lineno)"' | \
  sort | uniq -c | sort -rn | head -10
```

**Output**:
```
     45 /app/myapp/api/views.py:123
     23 /app/myapp/middleware/auth.py:67
     12 /app/myapp/utils/helper.py:234
     ...
```

**Interpretation**: `views.py:123` is the most frequent call origin (45 times).

### Example 6: Tracing Multi-threaded Calls

**Scenario**: Analyze which threads called the target function.

```bash
peeka-cli stack "myapp.shared.resource.access" -n 50 | \
  jq -r '.thread_name' | sort | uniq -c
```

**Output**:
```
     30 WorkerThread-1
     15 WorkerThread-2
      5 MainThread
```

---

## Complete Diagnostic Workflows

### Workflow 1: Locating Exception Call Paths

**Problem**: A function throws exceptions under specific circumstances, need to find which call path triggers it.

```bash
# Step 1: Start tracing (only capture calls with exception parameters)
peeka-cli stack "myapp.payment.charge" \
  --condition "params[0] <= 0" \
  -n 20

# Step 2: Wait for issue reproduction (continuous output to file)
peeka-cli stack "myapp.payment.charge" \
  --condition "params[0] <= 0" > stack_trace.jsonl

# Step 3: Analyze call paths
jq -r '.stack[] | "\(.filename):\(.lineno) - \(.function)"' stack_trace.jsonl

# Step 4: Find most frequent exception sources
jq -r '.stack[0] | "\(.filename):\(.lineno)"' stack_trace.jsonl | \
  sort | uniq -c | sort -rn
```

**Result Example**:
```
     12 /app/myapp/api/refund.py:89
      3 /app/myapp/jobs/reconcile.py:234
```

**Conclusion**: `refund.py:89` is the main problem source, check input validation logic there.

### Workflow 2: Performance Hotspot Path Analysis

**Problem**: A database query function is frequently called, need to find which paths are most time-consuming.

```bash
# Step 1: Capture 200 invocations' call stacks
peeka-cli stack "myapp.db.query" -n 200 > query_stacks.jsonl

# Step 2: Analyze call path distribution
jq -r '.stack[0:3] | map("\(.filename):\(.lineno)") | join(" -> ")' \
  query_stacks.jsonl | sort | uniq -c | sort -rn | head -10

# Step 3: Optimize high-frequency paths (e.g., add caching)
```

**Output Example**:
```
     89 /app/myapp/api/list.py:123 -> /app/myapp/models/user.py:45
     34 /app/myapp/api/search.py:67 -> /app/myapp/models/user.py:45
     12 /app/myapp/jobs/sync.py:234 -> /app/myapp/models/user.py:45
```

**Conclusion**: `list.py:123` path has the highest proportion (89 times), prioritize optimizing this path.

### Workflow 3: Recursion Depth Analysis

**Problem**: Recursive function causes stack overflow, need to analyze recursion depth.

```bash
# Step 1: Capture deep call stacks (depth set to 50)
peeka-cli stack "myapp.tree.traverse" --depth 50 -n 10 > recursion.jsonl

# Step 2: Calculate stack depth for each invocation
jq '.stack | length' recursion.jsonl

# Step 3: Find the deepest call
jq -s 'max_by(.stack | length)' recursion.jsonl > deepest.json

# Step 4: Analyze deepest call's path
jq '.stack[] | "\(.function) at \(.filename):\(.lineno)"' deepest.json
```

**Output Example**:
```
traverse at /app/myapp/tree.py:45
traverse at /app/myapp/tree.py:45
traverse at /app/myapp/tree.py:45
... (repeated 48 times)
process_tree at /app/myapp/api/views.py:123
```

**Conclusion**: Recursion depth reached 48 levels, need to optimize termination condition or switch to iterative implementation.

---

## Important Notes

### 1. Performance Impact

**Impact Degree**:
- **Capturing stack frames**: Each capture adds approximately 0.5-2ms overhead (depends on stack depth)
- **JSON serialization**: Approximately 0.2-0.5ms per capture
- **Network transmission**: Approximately 0.1-0.3ms per capture (Unix Domain Socket)

**Total Overhead**: Approximately 1-3ms per capture (high-frequency functions may accumulate to 5-10% CPU)

**Optimization Recommendations**:
- Use `--condition` to reduce capture frequency
- Set reasonable `--depth` (default 10 levels usually sufficient)
- Avoid tracing ultra-high frequency functions (e.g., functions called tens of thousands of times per second)
- Use `-n` to limit capture count (stop immediately after debugging)

### 2. Output Data Volume

**Data Volume Estimation**:
- Each stack frame approximately 200-300 bytes (JSON)
- 10-level call stack approximately 2-3 KB
- 1000 captures approximately 2-3 MB

**Management Recommendations**:
- Output to file: `peeka-cli stack ... > output.jsonl`
- Regularly clean output files
- Use streaming processing (`jq`) instead of loading all data at once

### 3. Thread Safety

**Notes**:
- In multi-threaded environments, call stacks from different threads will be interleaved in output
- Use `thread_id` and `thread_name` fields to distinguish threads
- Can filter specific threads with `jq`:
  ```bash
  peeka-cli stack "myapp.func" | \
    jq 'select(.thread_name == "WorkerThread-1")'
  ```

### 4. Condition Expression Limitations

**Limitations**:
- Does not support `cost` variable (because `stack` only captures at function entry, execution not yet completed)
- Does not support accessing return values (`returnObj` unavailable)
- Does not support complex object method calls (e.g., `params[0].some_method()`)

**Available Variables**: Only `params`, `kwargs`, `target`

### 5. Stack Frame Count Limit

**Limitations**:
- Default maximum 10 levels (adjustable via `--depth`)
- Python interpreter default maximum recursion depth is 1000 (`sys.getrecursionlimit()`)
- Not recommended to set `--depth` beyond 50 (excessive data volume)

---

## FAQ

### Q3: How to stop a running stack trace?

**Method 1**: Use Ctrl+C to interrupt the client (does not affect target process)


**Notes**:
- After stopping tracing, the target function returns to original state (no performance impact)
- Target process is unaffected

### Q4: Why is the code_context field None?

**Reasons**:
- Source code file is inaccessible (e.g., compiled `.pyc` code)
- Source code file has been deleted or moved
- Python built-in modules (C extensions)

**Solutions**:
- Ensure source code file exists and is accessible
- For C extension modules, source code content cannot be obtained (normal behavior)

### Q5: Can stack and watch commands be used simultaneously?

**Answer**: Yes, they can be used simultaneously.

**Example**:
```bash
# Terminal 1: Trace call stack
peeka-cli stack "myapp.func" > stack.jsonl

# Terminal 2: Observe arguments and return values
peeka-cli watch "myapp.func" > watch.jsonl
```

**Notes**:
- Both commands will inject two decorators (performance impact accumulates)
- Recommend using as needed, avoid excessive tracing

### Q6: How to trace standard library function call stacks?

**Answer**: Yes, but requires full module path.

**Examples**:
```bash
# Trace json.dumps call stack
peeka-cli stack "json.dumps" --depth 5

# Trace logging module's info method
peeka-cli stack "logging.Logger.info" --depth 3
```

**Notes**:
- Standard library functions usually have extremely high call frequency, recommend using condition filtering and count limits
- Some C extension functions cannot be traced (e.g., `time.sleep`)

---

## Advanced Techniques

### 1. Call Path Deduplication and Sorting

**Scenario**: Analyze all different call paths, sorted by frequency.

```bash
peeka-cli stack "myapp.db.query" -n 500 | \
  jq -r '.stack[0:3] | map("\(.filename):\(.lineno)") | join(" -> ")' | \
  sort | uniq -c | sort -rn > call_paths.txt
```

**Output Example**:
```
    123 /app/api/users.py:45 -> /app/models/user.py:78
     67 /app/api/orders.py:123 -> /app/models/order.py:56
     34 /app/jobs/sync.py:234 -> /app/models/user.py:78
```

### 2. Visualizing Call Trees

**Scenario**: Generate call tree diagrams (requires additional tools like `graphviz`).

```bash
# Step 1: Extract call relationships
peeka-cli stack "myapp.func" -n 100 | \
  jq -r '.stack[] | "\(.function) -> \(.filename):\(.lineno)"' > edges.txt

# Step 2: Use graphviz to generate diagram (need to write custom script)
# Or use online tools like https://dreampuf.github.io/GraphvizOnline/
```

### 3. Real-time Call Frequency Monitoring

**Scenario**: Display call count per second in real-time.

```bash
peeka-cli stack "myapp.api.handle_request" | \
  jq -r .timestamp | \
  awk '{
    sec = int($1)
    count[sec]++
  } END {
    for (s in count) print s, count[s]
  }'
```

### 4. Filtering Third-Party Library Stack Frames

**Scenario**: Only care about application code, ignore third-party libraries (e.g., Django, Flask).

```bash
peeka-cli stack "myapp.views.index" --depth 20 | \
  jq '.stack |= map(select(.filename | startswith("/app/myapp")))'
```

### 5. Cross-Process Call Chain Analysis

**Scenario**: Combine with logs to trace cross-process call chains.

**Method**:
1. Start `stack` tracing in each service
2. Use unified `trace_id` (extract from `params` or `kwargs`)
3. Merge outputs from different services, group by `trace_id`

```bash
# Service A
peeka-cli stack "service_a.process" | \
  jq --arg service "A" '. + {service: $service}' > trace_a.jsonl

# Service B
peeka-cli stack "service_b.handle" | \
  jq --arg service "B" '. + {service: $service}' > trace_b.jsonl

# Merge and analyze
cat trace_a.jsonl trace_b.jsonl | \
  jq -s 'group_by(.params[0].trace_id)'
```

### 6. Prometheus Integration

**Scenario**: Export call path statistics to Prometheus monitoring.

```bash
# Script example (requires custom implementation)
peeka-cli stack "myapp.api.endpoint" -n 1000 | \
  jq -r '.stack[0] | "\(.filename):\(.lineno)"' | \
  sort | uniq -c | \
  awk '{print "call_path_count{path=\""$2"\"} "$1}' > metrics.prom
```

**Output Example** (Prometheus format):
```
call_path_count{path="/app/api/users.py:45"} 123
call_path_count{path="/app/api/orders.py:67"} 78
```

---


## Summary

The `stack` command is a powerful tool for tracing function call paths, especially suitable for:
- Locating exception call origins
- Analyzing complex call chains
- Performance hotspot path analysis
- Recursion depth diagnostics

**Best Practices**:
- Use condition filtering to reduce irrelevant data
- Set reasonable stack depth (5-20 levels)
- Limit capture count (avoid generating massive data)
- Combine with `jq` for powerful data analysis
- Stop tracing promptly after debugging

**Next Steps**:
- Learn about [`watch`](watch) command (observing arguments and return values)
- Learn about [`memory`](memory) command (memory analysis)
- Refer to [AGENTS.md](../AGENTS) (developer guide)
