---
layout: default
title: Peeka Monitor Command Reference
parent: Command Reference
nav_order: 5
permalink: /commands/monitor
---

# Peeka Monitor Command Reference
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Command Overview

The `monitor` command periodically collects and outputs function performance statistics, including call counts, success/failure rates, response times, and other key metrics. This is a lightweight performance monitoring tool suitable for long-term production environment operation.

**Core Features**:
- Periodic output of function performance statistics (default every 60 seconds)
- Statistics on call counts, success/failure rates
- Statistics on response times (average, minimum, maximum)
- Lightweight design (does not record detailed observation data, only statistics)
- Supports monitoring multiple functions simultaneously
- Configurable monitoring cycle and duration

**Difference from watch command**:
- `watch`: Records **detailed information for each call** (arguments, return values, call stacks, etc.)
- `monitor`: Only records **statistical data** (call counts, response times, etc.), outputs periodic summaries

## TUI Usage

In TUI mode, press **`5`** to switch to **Monitor view**, which provides the following interactive features:

- **Pattern Input**: Supports function name autocomplete (fetched from target process in real-time)
- **Parameter Configuration**: Visual configuration for output interval, monitoring cycle count
- **Statistics Display**: Real-time display of performance metrics
  - Call counts (total, success, fail)
  - Failure rate (fail_rate), response times (avg/min/max)
  - Cycle counter and interval time
- **Keyboard Shortcuts**:
  - Enter after entering pattern to start monitoring
  - Press `s` to stop monitoring
  - Press `c` to clear statistics

**CLI Equivalent**: All examples below use CLI commands for demonstration; TUI provides the same functionality with a graphical interface.
---

## Use Cases

### 1. Production Environment Performance Monitoring

**Scenario**: Long-term monitoring of critical function performance metrics, timely detection of performance degradation.

```bash
# Output statistics once every 60 seconds, continuous operation
peeka-cli monitor "myapp.api.handle_request" --interval 60
```

**Output Example**:
```json
{
  "watch_id": "monitor_a1b2c3d4",
  "cycle": 1,
  "total": 1234,
  "success": 1200,
  "fail": 34,
  "fail_rate": 0.0275,
  "rt_avg": 45.678,
  "rt_min": 5.123,
  "rt_max": 234.567
}
```

**Interpretation**:
- 1234 calls total within 1 minute
- 1200 successful, 34 failed (failure rate 2.75%)
- Average response time 45.678 milliseconds
- Fastest 5.123 milliseconds, slowest 234.567 milliseconds

### 2. Service Health Checks

**Scenario**: Monitor core function failure rate, alert when threshold exceeded.

```bash
# Output once every 30 seconds, continue for 10 times (5 minutes)
peeka-cli monitor "myapp.payment.process" \
  --interval 30 -c 10 | \
  jq -r 'select(.fail_rate > 0.05) | "ALERT: Fail rate \(.fail_rate*100)%"'
```

**Effect**: Outputs alert information when failure rate exceeds 5%.

### 3. Establishing Performance Baseline

**Scenario**: Establish performance baseline under normal load for subsequent performance comparison.

```bash
# Monitor for 1 hour (60 times, once per minute)
peeka-cli monitor "myapp.db.execute_query" \
  --interval 60 -c 60 > baseline.jsonl

# Analyze data
jq -s '{
  avg_rt: (map(.rt_avg) | add / length),
  avg_total: (map(.total) | add / length),
  max_fail_rate: (map(.fail_rate) | max)
}' baseline.jsonl
```

**Output**:
```json
{
  "avg_rt": 12.345,
  "avg_total": 567,
  "max_fail_rate": 0.0123
}
```

### 4. Multi-Function Comparison Monitoring

**Scenario**: Monitor multiple functions simultaneously, compare performance differences.

```bash
# Terminal 1: Monitor API v1
peeka-cli monitor "myapp.api.v1.handler" --interval 30 > api_v1.jsonl

# Terminal 2: Monitor API v2
peeka-cli monitor "myapp.api.v2.handler" --interval 30 > api_v2.jsonl

# Terminal 3: Real-time comparison
while true; do
  v1=$(tail -1 api_v1.jsonl | jq -r '.rt_avg')
  v2=$(tail -1 api_v2.jsonl | jq -r '.rt_avg')
  echo "v1: ${v1}ms, v2: ${v2}ms"
  sleep 30
done
```

### 5. Monitoring During Load Testing

**Scenario**: Real-time monitoring of function performance during load testing, observe system behavior.

```bash
# Monitor core function, output once every 10 seconds
peeka-cli monitor "myapp.process" --interval 10 | \
  jq -r '"\(.cycle): \(.total) calls, \(.rt_avg)ms avg, \(.fail_rate*100)% fail"'
```

**Output**:
```
1: 123 calls, 45.67ms avg, 1.2% fail
2: 234 calls, 67.89ms avg, 2.3% fail
3: 345 calls, 89.01ms avg, 3.4% fail
...
```

---

## Command Format

```bash
peeka-cli monitor [--pid PID | --name NAME] <pattern> [options]
```

**Required Parameters**:
- `--pid, -p`: Target process PID (choose one: `--pid` or `--name`)
- `--name`: Target process name (choose one: `--pid` or `--name`)
- `pattern`: Target function pattern (e.g., `module.Class.method`)

**Optional Parameters**:
- `--interval`: Output interval (seconds, default 60)
- `-c, --cycles`: Number of monitoring cycles (-1 for unlimited, default -1)

---

## Parameter Reference

### pattern - Function Pattern

Specifies the target function to monitor, format same as `watch` command.

| Format | Description | Example |
|--------|-------------|---------|
| `module.function` | Module-level function | `myapp.utils.calculate` |
| `module.Class.method` | Class method | `myapp.models.User.save` |
| `module.Class.static_method` | Static method | `myapp.utils.Helper.validate` |

**Notes**:
- Must use fully qualified name (starting from module root)
- Wildcards not supported
- Target function must be loaded into memory

### --interval - Output Interval

Controls the output frequency of statistical data (unit: seconds).

| Value | Description | Use Case |
|-------|-------------|----------|
| `10` | Output once every 10 seconds | Load testing, real-time monitoring |
| `30` | Output once every 30 seconds | High-frequency monitoring |
| `60` (default) | Output once every 60 seconds | Production environment regular monitoring |
| `300` | Output once every 5 minutes | Long-term trend analysis |

**Examples**:
```bash
# High-frequency monitoring (every 10 seconds)
peeka-cli monitor "myapp.api.handler" --interval 10

# Long-term monitoring (every 5 minutes)
peeka-cli monitor "myapp.batch.process" --interval 300
```

**Notes**:
- Shorter interval = more frequent output data (recommend setting based on function call frequency)
- Too short interval may result in too few calls per cycle, limiting statistical significance
- Too long interval may miss important performance changes

### -c, --cycles - Number of Monitoring Cycles

Controls the number of cycles the monitoring continues.

| Value | Description | Use Case |
|-------|-------------|----------|
| `-1` (default) | Unlimited monitoring | Production environment continuous monitoring |
| `1` | Monitor 1 cycle then stop | Quick view of current state |
| `10` | Monitor 10 cycles then stop | Fixed duration monitoring |
| `60` | Monitor 60 cycles then stop | 1 hour monitoring (interval=60) |

**Examples**:
```bash
# Monitor once then stop (view statistics for current 1 minute)
peeka-cli monitor "myapp.func" --interval 60 -c 1

# Monitor for 10 minutes (10 times, once per minute)
peeka-cli monitor "myapp.func" --interval 60 -c 10

# Continuous monitoring (until manually stopped)
peeka-cli monitor "myapp.func" --interval 60
```

**Calculating Total Duration**:
- Total duration = `interval` × `cycles`
- Example: `--interval 60 -c 10` = 10 minutes
- Example: `--interval 30 -c 120` = 1 hour

---

## Metrics Description

### Basic Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `total` | int | Total call count in current cycle |
| `success` | int | Successful call count (no exception thrown) |
| `fail` | int | Failed call count (exception thrown) |

### Derived Metrics

| Metric | Type | Formula | Description |
|--------|------|---------|-------------|
| `fail_rate` | float | `fail / total` | Failure rate (0-1, 4 decimal places) |
| `rt_avg` | float | `sum(duration) / total` | Average response time (milliseconds, 3 decimal places) |
| `rt_min` | float | `min(duration)` | Minimum response time (milliseconds, 3 decimal places) |
| `rt_max` | float | `max(duration)` | Maximum response time (milliseconds, 3 decimal places) |

### Metadata

| Field | Type | Description |
|-------|------|-------------|
| `watch_id` | string | Unique identifier for monitoring task |
| `cycle` | int | Current cycle number (starts from 1) |

---

## Output Format

The `monitor` command outputs JSON Lines format (one line per cycle), facilitating streaming processing.

### Complete Output Example

```json
{
  "watch_id": "monitor_a1b2c3d4",
  "cycle": 1,
  "total": 1234,
  "success": 1200,
  "fail": 34,
  "fail_rate": 0.0275,
  "rt_avg": 45.678,
  "rt_min": 5.123,
  "rt_max": 234.567
}
```

### Field Descriptions

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `watch_id` | string | Unique identifier for monitoring task | `"monitor_a1b2c3d4"` |
| `cycle` | int | Cycle number (starts from 1) | `1`, `2`, `3`... |
| `total` | int | Total call count in current cycle | `1234` |
| `success` | int | Successful call count | `1200` |
| `fail` | int | Failed call count | `34` |
| `fail_rate` | float | Failure rate (0-1) | `0.0275` (2.75%) |
| `rt_avg` | float | Average response time (milliseconds) | `45.678` |
| `rt_min` | float | Minimum response time (milliseconds) | `5.123` |
| `rt_max` | float | Maximum response time (milliseconds) | `234.567` |

### Statistical Cycle Description

**Important**: Statistical data for each cycle is **cumulative** (from monitoring start to current moment).

```json
// Cycle 1 (0-60 seconds)
{"cycle": 1, "total": 100, "rt_avg": 50}

// Cycle 2 (0-120 seconds, cumulative)
{"cycle": 2, "total": 250, "rt_avg": 55}

// Cycle 3 (0-180 seconds, cumulative)
{"cycle": 3, "total": 400, "rt_avg": 53}
```

**To calculate single cycle data**:
```bash
# Calculate new calls added in cycle 2
total_cycle2 - total_cycle1 = 250 - 100 = 150
```

---

## Usage Examples

### Example 1: Basic Monitoring

**Scenario**: Monitor API entry function, output statistics once per minute.

```bash
peeka-cli monitor "myapp.api.handle_request" --interval 60
```

**Output**:
```json
{"watch_id":"monitor_a1b2c3d4","cycle":1,"total":1234,"success":1200,"fail":34,"fail_rate":0.0275,"rt_avg":45.678,"rt_min":5.123,"rt_max":234.567}
{"watch_id":"monitor_a1b2c3d4","cycle":2,"total":2456,"success":2400,"fail":56,"fail_rate":0.0228,"rt_avg":48.123,"rt_min":5.123,"rt_max":345.678}
{"watch_id":"monitor_a1b2c3d4","cycle":3,"total":3678,"success":3600,"fail":78,"fail_rate":0.0212,"rt_avg":46.890,"rt_min":5.123,"rt_max":345.678}
...
```

### Example 2: Fixed Duration Monitoring

**Scenario**: Monitor for 5 minutes (5 times, once per minute).

```bash
peeka-cli monitor "myapp.payment.charge" --interval 60 -c 5
```

**Behavior**:
- Outputs 5 statistical data
- Automatically stops after 5th output
- Total monitoring duration: 5 minutes

### Example 3: Real-time Monitoring (High Frequency)

**Scenario**: Real-time monitoring during load testing, output once every 10 seconds.

```bash
peeka-cli monitor "myapp.process" --interval 10 | \
  jq -r '"\(.cycle): \(.total) calls, \(.rt_avg)ms avg, \(.fail) fails"'
```

**Output**:
```
1: 123 calls, 45.67ms avg, 2 fails
2: 278 calls, 52.34ms avg, 5 fails
3: 456 calls, 58.90ms avg, 8 fails
...
```

### Example 4: Failure Rate Alert

**Scenario**: Monitor failure rate, issue alert when exceeding 5%.

```bash
peeka-cli monitor "myapp.critical_func" --interval 30 | \
  jq -r 'if .fail_rate > 0.05 then
           "⚠️  ALERT: Fail rate \(.fail_rate * 100)% at cycle \(.cycle)"
         else
           "✅  Healthy: \(.fail_rate * 100)% fail rate"
         end'
```

**Output**:
```
✅  Healthy: 1.2% fail rate
✅  Healthy: 2.3% fail rate
⚠️  ALERT: Fail rate 6.7% at cycle 3
```

### Example 5: Response Time Trend

**Scenario**: Monitor response time changes, plot trend chart.

```bash
# Monitor for 30 minutes (30 times, once per minute)
peeka-cli monitor "myapp.db.query" --interval 60 -c 30 | \
  jq -r '"\(.cycle) \(.rt_avg)"' > rt_trend.dat

# Use gnuplot to plot trend (requires gnuplot installation)
gnuplot <<EOF
set terminal png size 800,600
set output 'rt_trend.png'
set xlabel 'Cycle'
set ylabel 'Response Time (ms)'
set title 'Response Time Trend'
plot 'rt_trend.dat' with lines
EOF
```

### Example 6: Combined with watch Command

**Scenario**: First use `monitor` to discover performance issues, then use `watch` for deep investigation.

```bash
# Step 1: Start monitoring, discover abnormal response time
peeka-cli monitor "myapp.process" --interval 60 | \
  jq -r 'select(.rt_avg > 100)'
# Output: {"cycle": 5, "rt_avg": 234.567, ...}

# Step 2: Use watch to view detailed call information
peeka-cli watch "myapp.process" -n 10
# Analyze arguments, return values, execution time

# Step 3: Stop monitoring after locating issue
# (Ctrl+C or use cycles parameter)
```

---

## Complete Monitoring Workflows

### Workflow 1: Establishing Production Performance Baseline

**Goal**: Establish performance baseline under normal load for subsequent performance comparison.

```bash
# Step 1: Monitor core function for 1 hour
peeka-cli monitor "myapp.api.handle_request" \
  --interval 60 -c 60 > baseline_$(date +%Y%m%d).jsonl

# Step 2: Calculate baseline statistics
jq -s '{
  avg_total: (map(.total) | add / length),
  avg_rt: (map(.rt_avg) | add / length),
  p50_rt: (map(.rt_avg) | sort)[30],
  p95_rt: (map(.rt_avg) | sort)[57],
  max_fail_rate: (map(.fail_rate) | max)
}' baseline_$(date +%Y%m%d).jsonl > baseline_summary.json

# Step 3: View baseline
cat baseline_summary.json
```

**Output**:
```json
{
  "avg_total": 567.8,
  "avg_rt": 45.678,
  "p50_rt": 44.123,
  "p95_rt": 67.890,
  "max_fail_rate": 0.0123
}
```

### Workflow 2: Performance Degradation Detection

**Goal**: Compare current performance with baseline, detect performance degradation.

```bash
# Step 1: Load baseline data
baseline_rt=$(jq -r '.avg_rt' baseline_summary.json)
echo "Baseline avg RT: ${baseline_rt}ms"

# Step 2: Real-time monitoring and comparison
peeka-cli monitor "myapp.api.handle_request" --interval 60 | \
  jq -r --arg baseline "$baseline_rt" '
    if .rt_avg > ($baseline | tonumber * 1.5) then
      "⚠️  DEGRADATION: \(.rt_avg)ms (baseline: \($baseline)ms)"
    else
      "✅  Normal: \(.rt_avg)ms"
    end
  '
```

**Output**:
```
✅  Normal: 47.123ms
✅  Normal: 48.567ms
⚠️  DEGRADATION: 89.012ms (baseline: 45.678ms)
```

### Workflow 3: Multi-Function Performance Comparison

**Goal**: Compare performance differences between different implementations (e.g., API v1 vs v2).

```bash
# Step 1: Monitor two functions simultaneously
peeka-cli monitor "myapp.api.v1.handler" --interval 30 > v1.jsonl &
peeka-cli monitor "myapp.api.v2.handler" --interval 30 > v2.jsonl &

# Step 2: Wait to collect data (10 minutes)
sleep 600

# Step 3: Stop monitoring
kill %1 %2

# Step 4: Comparative analysis
echo "API v1:"
jq -s 'map(.rt_avg) | add / length' v1.jsonl
echo "API v2:"
jq -s 'map(.rt_avg) | add / length' v2.jsonl
```

**Output**:
```
API v1:
67.890
API v2:
45.123
```

**Conclusion**: v2 performs better than v1 (33% faster on average).

### Workflow 4: Load Test Monitoring

**Goal**: Monitor system performance during load testing, observe performance curve.

```bash
# Step 1: Start monitoring (high frequency, every 10 seconds)
peeka-cli monitor "myapp.process" --interval 10 > load_test.jsonl &

# Step 2: Start load test (another terminal)
# ab -n 10000 -c 100 http://localhost:8000/api/endpoint

# Step 3: Real-time observation of performance metrics
tail -f load_test.jsonl | \
  jq -r '"\(.cycle): \(.total) calls, \(.rt_avg)ms avg, \(.fail_rate*100)% fail"'

# Step 4: Stop monitoring after test ends
kill %1

# Step 5: Analyze performance curve
jq -r '"\(.cycle) \(.total) \(.rt_avg) \(.fail_rate)"' load_test.jsonl > metrics.dat
```

---

## Important Notes

### 1. Performance Impact

**Impact Degree**:
- **Statistical recording**: Each call adds approximately 0.1-0.2ms overhead
- **Statistical computation**: Each cycle approximately 0.01ms (negligible)
- **JSON output**: Each cycle approximately 0.1ms (negligible)

**Total Overhead**: Approximately 0.1-0.2ms per call (10 times lighter than `watch` command)

**Advantages**:
- Does not record detailed data, minimal memory usage
- Suitable for long-term operation, performance impact negligible
- Suitable for high-frequency function monitoring

### 2. Statistical Data is Cumulative

**Important**: `monitor` statistical data is **cumulative**, not per-cycle.

```json
// Cycle 1: Cumulative 0-60 seconds
{"cycle": 1, "total": 100}

// Cycle 2: Cumulative 0-120 seconds (not just the 2nd 60 seconds)
{"cycle": 2, "total": 250}
```

**Calculating Single Cycle Data**:
```bash
# Extract single cycle call count
jq -s '[.[0].total] + [range(1; length) |
  {cycle: .[.].cycle, calls: .[.].total - .[-1].total}]' monitor.jsonl
```

### 3. Response Time Statistics

**rt_avg Calculation Method**:
- Cumulative average: `sum(all call durations) / total`
- Not weighted moving average
- Not single cycle average

**Example**:
```json
// Cycle 1: 100 calls, average 50ms
{"cycle": 1, "total": 100, "rt_avg": 50}

// Cycle 2: 100 new calls, average 60ms
// Cumulative average = (100*50 + 100*60) / 200 = 55ms
{"cycle": 2, "total": 200, "rt_avg": 55}
```

### 4. Definition of Failure

**fail Count Rules**:
- Function throws exception → `fail` +1
- Function returns normally → `success` +1
- Even if returns `None` or error code, as long as no exception, counts as `success`

**Notes**:
- If application uses error codes instead of exceptions, `fail` count may be 0
- Recommend combining with business logic analysis for true `success` authenticity

### 5. Stopping Monitoring

**Method 1**: Use `-c` parameter to limit cycle count (automatic stop)
```bash
peeka-cli monitor "myapp.func" --interval 60 -c 10
```

**Method 2**: Manual Ctrl+C (does not affect target process)
```bash
peeka-cli monitor "myapp.func" --interval 60
# Press Ctrl+C to stop
```

**Important**:
- After stopping monitoring, target function returns to original state (no performance impact)
- Statistical data is not persisted (need to manually save output)
- Multiple monitoring tasks are independent

### 6. Multiple Monitoring Tasks

**Support**: Can start multiple `monitor` tasks to monitor different functions simultaneously.

```bash
# Terminal 1: Monitor API
peeka-cli monitor "myapp.api.handler" --interval 60

# Terminal 2: Monitor database
peeka-cli monitor "myapp.db.query" --interval 60

# Terminal 3: Monitor cache
peeka-cli monitor "myapp.cache.get" --interval 60
```

**Notes**:
- Each task collects statistics independently, no mutual interference
- More monitored functions = cumulative performance overhead
- Recommend monitoring no more than 10 functions

---

## FAQ

### Q1: How to view current monitoring tasks?

**Method 1**: Use `status` action (if CLI supports)
```bash
peeka-cli reset -l
```

**Method 2**: Check if process has corresponding client connections
```bash
ps aux | grep "peeka-cli monitor" | grep 12345
```

**Method 3**: View target process socket connections
```bash
lsof -p 12345 | grep peeka
```

### Q2: How to calculate call count for single cycle?

**Method**: Use `jq` to calculate difference between adjacent cycles.

```bash
jq -s '
  [range(0; length)] | map({
    cycle: .[.].cycle,
    calls: (if . == 0 then .[0].total else .[.].total - .[.-1].total end),
    rt_avg: .[.].rt_avg
  })
' monitor.jsonl
```

**Output**:
```json
[
  {"cycle": 1, "calls": 100, "rt_avg": 50},
  {"cycle": 2, "calls": 150, "rt_avg": 55},
  {"cycle": 3, "calls": 200, "rt_avg": 53}
]
```

### Q3: Why did rt_avg suddenly drop?

**Possible Reasons**:
1. **New calls have faster response time**: Cumulative average pulled down
2. **Cache takes effect**: Subsequent calls hit cache
3. **Load decreased**: System resources sufficient, faster response

**Troubleshooting Method**:
```bash
# View changes in rt_min and rt_max
jq -r '"\(.cycle) \(.rt_min) \(.rt_avg) \(.rt_max)"' monitor.jsonl
```

**Example**:
```
1  5.123  50.000  234.567
2  5.123  48.000  234.567  ← rt_avg drops, but rt_min/max unchanged
3  2.456  35.000  234.567  ← rt_min drops, indicating new calls faster
```

### Q4: How to monitor async functions?

**Answer**: `monitor` command supports async functions (async def).

```bash
peeka-cli monitor "myapp.async_handler" --interval 60
```

**Notes**:
- Statistics reflect async function's **actual execution time** (excluding wait time)
- If function has `await` internally, wait time not included in `rt_avg`

### Q5: Why is total number large but output sparse?

**Reason**: `monitor` only outputs **periodic statistics**, not every call.

- `total` is cumulative call count
- Only outputs 1 statistic per `interval`
- If detailed information per call needed, use `watch` command

### Q6: Can I monitor standard library functions?

**Answer**: Yes, but be aware of performance impact.

```bash
# Monitor json.dumps (may have extremely high call frequency)
peeka-cli monitor "json.dumps" --interval 10 -c 6
```

**Warning**:
- Standard library functions usually have extremely high call frequency
- Even lightweight `monitor` may have noticeable cumulative overhead
- Recommend testing first with `--interval 10 -c 1`, observe `total` count

---

## Advanced Techniques

### 1. Real-time Performance Dashboard

**Scenario**: Use `watch` command (shell tool) to create real-time dashboard.

```bash
#!/bin/bash
# dashboard.sh

PID=12345
PATTERN="myapp.api.handler"
LOG="monitor.jsonl"

# Start monitoring (background)
peeka-cli monitor "$PATTERN" --interval 10 > $LOG &
MONITOR_PID=$!

# Real-time display dashboard
while kill -0 $MONITOR_PID 2>/dev/null; do
  clear
  echo "=== Performance Dashboard ==="
  echo ""
  tail -1 $LOG | jq -r '
    "Cycle: \(.cycle)",
    "Total Calls: \(.total)",
    "Success Rate: \((1 - .fail_rate) * 100)%",
    "Fail Rate: \(.fail_rate * 100)%",
    "Avg RT: \(.rt_avg)ms",
    "Min RT: \(.rt_min)ms",
    "Max RT: \(.rt_max)ms"
  '
  sleep 10
done
```

### 2. Prometheus Integration

**Scenario**: Export monitoring data to Prometheus.

```bash
#!/bin/bash
# export_to_prometheus.sh

PID=12345
PATTERN="myapp.api.handler"
METRICS_FILE="/var/lib/node_exporter/textfile_collector/peeka.prom"

peeka-cli monitor "$PATTERN" --interval 60 | \
  jq -r '
    "peeka_calls_total{pattern=\"\($PATTERN)\"} \(.total)",
    "peeka_success_total{pattern=\"\($PATTERN)\"} \(.success)",
    "peeka_fail_total{pattern=\"\($PATTERN)\"} \(.fail)",
    "peeka_fail_rate{pattern=\"\($PATTERN)\"} \(.fail_rate)",
    "peeka_rt_avg_ms{pattern=\"\($PATTERN)\"} \(.rt_avg)",
    "peeka_rt_min_ms{pattern=\"\($PATTERN)\"} \(.rt_min)",
    "peeka_rt_max_ms{pattern=\"\($PATTERN)\"} \(.rt_max)"
  ' > $METRICS_FILE
```

**Prometheus Query Examples**:
```promql
# Failure rate alert
rate(peeka_fail_total[5m]) / rate(peeka_calls_total[5m]) > 0.05

# Response time trend
peeka_rt_avg_ms{pattern="myapp.api.handler"}
```

### 3. Performance Regression Detection

**Scenario**: Automatically detect performance degradation after each deployment.

```bash
#!/bin/bash
# regression_test.sh

PID=12345
PATTERN="myapp.api.handler"
BASELINE="baseline_rt.txt"

# Read baseline
baseline_rt=$(cat $BASELINE)

# Monitor for 5 minutes
current_rt=$(peeka-cli monitor "$PATTERN" --interval 60 -c 5 | \
  jq -s 'map(.rt_avg) | add / length')

# Compare
if (( $(echo "$current_rt > $baseline_rt * 1.2" | bc -l) )); then
  echo "❌ REGRESSION: $current_rt ms (baseline: $baseline_rt ms)"
  exit 1
else
  echo "✅ PASS: $current_rt ms (baseline: $baseline_rt ms)"
  exit 0
fi
```

### 4. Multi-Function Aggregated Statistics

**Scenario**: Monitor multiple functions, aggregate statistical data.

```bash
# Monitor 3 functions (parallel)
peeka-cli monitor "myapp.api.v1" --interval 60 -c 10 > v1.jsonl &
peeka-cli monitor "myapp.api.v2" --interval 60 -c 10 > v2.jsonl &
peeka-cli monitor "myapp.api.v3" --interval 60 -c 10 > v3.jsonl &

# Wait for completion
wait

# Aggregate statistics
jq -s '
  reduce .[] as $item ({};
    .total += $item.total |
    .success += $item.success |
    .fail += $item.fail
  ) |
  .fail_rate = .fail / .total
' v1.jsonl v2.jsonl v3.jsonl
```

### 5. Automatic Alert Script

**Scenario**: Automatically send alerts when anomalies detected (Slack, email, etc.).

```bash
#!/bin/bash
# alert_on_degradation.sh

PID=12345
PATTERN="myapp.critical"
THRESHOLD_RT=100      # Response time threshold (milliseconds)
THRESHOLD_FAIL=0.05   # Failure rate threshold (5%)

peeka-cli monitor "$PATTERN" --interval 60 | \
  jq -r --arg rt "$THRESHOLD_RT" --arg fail "$THRESHOLD_FAIL" '
    if .rt_avg > ($rt | tonumber) or .fail_rate > ($fail | tonumber) then
      "ALERT: cycle=\(.cycle), rt=\(.rt_avg)ms, fail=\(.fail_rate*100)%"
    else
      empty
    end
  ' | \
  while read line; do
    # Send alert (example: Slack)
    curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
      -H 'Content-Type: application/json' \
      -d "{\"text\": \"$line\"}"
  done
```

### 6. Historical Data Analysis

**Scenario**: Analyze historical monitoring data, find performance patterns.

```bash
# Collect 1 week of monitoring data
for day in {1..7}; do
  peeka-cli monitor "myapp.func" --interval 3600 -c 24 > \
    monitor_day${day}.jsonl
  sleep 86400  # 1 day
done

# Analyze performance at same time each day
for hour in {0..23}; do
  echo -n "Hour $hour: "
  jq -s --arg h "$hour" 'map(select(.cycle == ($h | tonumber + 1))) |
    map(.rt_avg) | add / length' monitor_day*.jsonl
done
```

---

## Summary

The `monitor` command is a powerful tool for production environment performance monitoring, especially suitable for:
- Long-term performance monitoring
- Establishing performance baselines
- Performance degradation detection
- Real-time monitoring during load testing
- Integration with monitoring systems like Prometheus

**Best Practices**:
- Choose appropriate `--interval` based on function call frequency (recommend 30-60 seconds)
- Use `-c` to limit cycle count (avoid forgetting to stop)
- Output to file (`> monitor.jsonl`) for subsequent analysis
- Combine with `jq` for powerful data analysis
- Use with `watch` command (first `monitor` to discover issues, then `watch` for deep investigation)

**Next Steps**:
- Learn about [`watch`](watch) command (observing function detailed information)
- Learn about [`stack`](stack) command (tracing call stacks)
- Learn about [`memory`](memory) command (memory analysis)
- Refer to [AGENTS.md](../AGENTS) (developer guide)
