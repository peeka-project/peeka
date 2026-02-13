# watch - Observe Function Calls

The `watch` command observes function calls, capturing arguments, return values, and execution time.

## Usage

```bash
peeka-cli watch <pattern> [options]
```

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pattern` | string | Required | Function pattern (module.Class.method) |
| `--depth, -x` | integer | 2 | Output depth for nested objects |
| `--times, -n` | integer | -1 | Number of observations (-1 = unlimited) |
| `--condition-express` | string | None | Filter condition expression |
| `-b, --before` | flag | false | Observe at function entry (AtEnter) |
| `-s, --success` | flag | false | Observe only on success (AtExit) |
| `-e, --exception` | flag | false | Observe only on exception (AtExceptionExit) |
| `-f, --finish` | flag | true | Observe both success and exception (default) |

## Pattern Format

```
module.Class.method   # Class method
module.function       # Module-level function
package.module.func   # Package function
```

## Examples

### Basic observation

```bash
# Watch 5 function calls
peeka-cli watch "demo.Calculator.add" --times 5
```

### Observation points

```bash
# Before function execution
peeka-cli watch "module.func" -b

# Only on success
peeka-cli watch "module.func" -s

# Only on exception
peeka-cli watch "module.func" -e

# Both success and exception (default)
peeka-cli watch "module.func" -f
```

### Conditional filtering

```bash
# Filter by parameter value
peeka-cli watch "module.func" --condition "params[0] > 100"

# Filter by parameter count
peeka-cli watch "module.func" --condition "len(params) > 2"

# Filter by execution time
peeka-cli watch "module.func" --condition "cost > 10"

# Filter by keyword argument
peeka-cli watch "module.func" --condition "kwargs.get('debug') == True"
```

### Control output depth

```bash
# Shallow output (depth 1)
peeka-cli watch "module.func" --depth 1

# Deep output (depth 5)
peeka-cli watch "module.func" --depth 5
```

## Output Format

### Observation message

```json
{
  "type": "observation",
  "watch_id": "watch_001",
  "timestamp": 1705586200.123,
  "func_name": "demo.Calculator.add",
  "location": "AtExit",
  "args": [1, 2],
  "kwargs": {},
  "result": 3,
  "success": true,
  "duration_ms": 0.123,
  "count": 1
}
```

### Field descriptions

| Field | Type | Description |
|-------|------|-------------|
| `type` | string | Always "observation" |
| `watch_id` | string | Unique watch identifier |
| `timestamp` | float | Unix timestamp |
| `func_name` | string | Fully qualified function name |
| `location` | string | Observation point (AtEnter/AtExit/AtExceptionExit) |
| `args` | array | Function arguments |
| `kwargs` | object | Keyword arguments |
| `result` | any | Return value (null for AtEnter) |
| `success` | boolean | Whether function succeeded |
| `duration_ms` | float | Execution duration in milliseconds |
| `count` | integer | Observation sequence number |

## Arthas-Compatible Fields

Peeka also provides Arthas-compatible field names:

| Arthas Field | Peeka Equivalent | Description |
|--------------|------------------|-------------|
| `params` | `args` | Function arguments |
| `returnObj` | `result` | Return value |
| `throwExp` | `error` | Exception message |
| `cost` | `duration_ms` | Execution time |
| `target` | `self` | Object instance (for methods) |

## Condition Expression Syntax

Available variables in conditions:

- `params`: Function arguments tuple
- `kwargs`: Keyword arguments dict
- `target`: Self object for methods
- `cost`: Execution duration (only available after execution)

Allowed operations:
- Comparison: `>`, `<`, `>=`, `<=`, `==`, `!=`
- Arithmetic: `+`, `-`, `*`, `/`, `%`
- Logical: `and`, `or`, `not`
- Functions: `len()`, `str()`, `int()`, `float()`
- Methods: `.startswith()`, `.endswith()`, `.get()`

Blocked operations (security):
- `__import__`, `eval`, `exec`, `compile`
- `open`, `file`, `input`
- Attribute access to `__class__`, `__subclasses__`, etc.

## Processing Output

### Extract specific fields with jq

```bash
# Get return values
peeka-cli watch "module.func" | jq 'select(.type == "observation") | .result'

# Get execution times
peeka-cli watch "module.func" | jq 'select(.type == "observation") | .duration_ms'
```

### Filter observations

```bash
# Only slow calls (>10ms)
peeka-cli watch "module.func" | jq 'select(.type == "observation" and .duration_ms > 10)'

# Only failed calls
peeka-cli watch "module.func" | jq 'select(.type == "observation" and .success == false)'
```

### Statistics

```bash
# Count observations
peeka-cli watch "module.func" --times 100 | jq 'select(.type == "observation")' | wc -l

# Average execution time
peeka-cli watch "module.func" --times 100 | \
  jq 'select(.type == "observation") | .duration_ms' | \
  awk '{sum+=$1; count++} END {print "Average:", sum/count, "ms"}'
```

## See Also

- [trace](trace.md) - Trace call chains
- [stack](stack.md) - Capture call stacks
- [monitor](monitor.md) - Performance statistics
