# Examples

This document provides practical examples of using Peeka for common diagnostic scenarios.

## Basic Function Observation

### Example 1: Monitoring a Calculator

Start the demo application:

```bash
python examples/demo.py --mode loop
```

In another terminal, attach and observe:

```bash
# Attach to the process
peeka-cli attach <pid>

# Watch 5 function calls
peeka-cli watch "demo.Calculator.add" --times 5
```

Output:
```json
{"type":"event","event":"watch_started","data":{"watch_id":"watch_001","pattern":"demo.Calculator.add"}}
{"type":"observation","watch_id":"watch_001","timestamp":1705586200.123,"func_name":"demo.Calculator.add","args":[1,2],"result":3,"success":true,"duration_ms":0.123,"count":1}
{"type":"observation","watch_id":"watch_001","timestamp":1705586200.456,"func_name":"demo.Calculator.add","args":[3,4],"result":7,"success":true,"duration_ms":0.087,"count":2}
```

## Conditional Filtering

### Example 2: Filter by Parameter Value

Only observe calls where the first parameter is greater than 100:

```bash
peeka-cli watch "demo.Calculator.multiply" --condition "params[0] > 100"
```

### Example 3: Filter by Execution Time

Only observe slow calls (>10ms):

```bash
peeka-cli watch "module.slow_function" --condition "cost > 10"
```

## Data Processing with jq

### Example 4: Extract Return Values

```bash
# Get only the return values
peeka-cli watch "module.func" | jq 'select(.type == "observation") | .result'
```

### Example 5: Calculate Average Duration

```bash
# Calculate average execution time
peeka-cli watch "module.func" --times 100 | \
  jq 'select(.type == "observation") | .duration_ms' | \
  awk '{sum+=$1; count++} END {print "Average:", sum/count, "ms"}'
```

### Example 6: Monitor Error Rate

```bash
# Count successful vs failed calls
peeka-cli watch "module.func" | \
  jq -r 'select(.type == "observation") | if .success then "OK" else "ERROR" end' | \
  sort | uniq -c
```

## Integration Examples

### Example 7: Save to File for Later Analysis

```bash
# Save observations to file
peeka-cli watch "module.func" --times 1000 > observations.jsonl

# Later, analyze the file
cat observations.jsonl | jq 'select(.type == "observation" and .duration_ms > 10)'
```

### Example 8: Real-time Monitoring Dashboard

```bash
# Filter and format for dashboard display
peeka-cli watch "api.handler" | \
  jq -r 'select(.type == "observation") |
    "\(.timestamp | strftime("%H:%M:%S")) | \(.func_name) | \(.duration_ms)ms | \(if .success then "✓" else "✗" end)"'
```

## Advanced Usage

### Example 9: Observe Multiple Functions

```bash
# In separate terminals or using tmux
peeka-cli watch "module.func1" > func1.jsonl &
peeka-cli watch "module.func2" > func2.jsonl &
```

### Example 10: Trace Call Chains

```bash
# Trace function execution with call tree
peeka-cli trace "module.Calculator.calculate" --depth 3
```

## Production Scenarios

### Example 11: Debugging Intermittent Issues

```bash
# Stream observations and filter for specific conditions
peeka-cli watch "payment.process" --condition "params[0].amount > 1000" | \
  jq 'select(.type == "observation" and (.success == false or .duration_ms > 1000))'
```

### Example 12: Performance Analysis

```bash
# Monitor performance statistics
peeka-cli monitor "api.endpoint" --interval 5

# Output shows aggregated stats every 5 seconds
```

For more examples and use cases, refer to the specific command documentation.
