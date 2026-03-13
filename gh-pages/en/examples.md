---
layout: default
title: Examples
nav_order: 5
permalink: /examples
---

# Examples
{: .no_toc }

Learn how to use Peeka to diagnose and solve problems through real-world scenarios.
{: .fs-6 .fw-300 }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Scenario 1: Diagnose Slow API

### Problem Description

API endpoints occasionally respond very slowly (> 1 second), need to find the cause of slow calls.

### Solution Steps

#### 1. Attach to Process

```bash
# Find the API server process
ps aux | grep "api_server.py"
# Output: user 12345 ...

# Attach
peeka-cli attach 12345
```

#### 2. Monitor Overall Performance

```bash
# Collect statistics every 10 seconds
peeka-cli monitor "app.api.handle_request" --interval 10
```

Output:
```json
{"type":"observation","func_name":"app.api.handle_request","total":150,"success":148,"fail":2,"avg_rt":250.5,"min_rt":50.2,"max_rt":1850.3}
```

Found that `max_rt` is as high as 1850ms, indicating slow calls exist.

#### 3. Observe Slow Calls

```bash
# Only observe calls with execution time > 1000ms
peeka-cli watch "app.api.handle_request" \
  --condition "cost > 1000" \
  --times 10
```

Output:
```json
{"type":"observation","watch_id":"watch_001","func_name":"app.api.handle_request","args":[{"user_id": 12345}],"result":{"status": "ok"},"duration_ms":1850.3,"count":1}
```

Found that slow call parameter is `user_id=12345`.

#### 4. Trace Call Chain

```bash
# Trace complete call chain to find time-consuming parts
peeka-cli trace "app.api.handle_request" \
  --condition "cost > 1000" \
  --depth 5 \
  --times 1
```

Output:
```
`---[1850.3ms] app.api.handle_request()
    +---[5.2ms] app.auth.validate_token()
    +---[1800.1ms] app.db.query_user_data()  ← Slow
    |   +---[1795.5ms] sqlalchemy.query.all()
    |   `---[2.1ms] app.db._parse_results()
    `---[15.7ms] app.response.build()
```

**Conclusion**: Slow call is caused by `app.db.query_user_data()`, SQL query takes too long.

#### 5. Verify Fix

After optimizing SQL query, monitor again:

```bash
peeka-cli monitor "app.api.handle_request" --interval 10
```

Output:
```json
{"type":"observation","total":150,"avg_rt":120.5,"max_rt":450.3}
```

Performance significantly improved!

---

## Scenario 2: Locate Exception Causes

### Problem Description

Background task occasionally throws `ValueError`, but logs are incomplete, unable to locate the cause.

### Solution Steps

#### 1. Observe Exceptions

```bash
# Only observe calls that throw exceptions
peeka-cli watch "app.tasks.process_data" \
  --exception
```

Output:
```json
{
  "type":"observation",
  "func_name":"app.tasks.process_data",
  "args":[{"data": [1, 2, null]}],
  "success":false,
  "exception":"ValueError: invalid value",
  "duration_ms":5.2
}
```

Found that exception parameter contains `null`.

#### 2. View Call Stack

```bash
# Capture call stack when exception occurs
peeka-cli stack "app.tasks.process_data" \
  --condition "throwExp is not None" \
  --times 1
```

Output:
```
Thread: WorkerThread-1
  File "scheduler.py", line 45, in run
    self.execute_task(task)
  File "scheduler.py", line 78, in execute_task
    result = task.process_data(data)
  File "tasks.py", line 120, in process_data
    validated = self._validate(data)  ← Exception thrown here
```

**Conclusion**: Exception is caused by `null` data passed from `scheduler.py`.

#### 3. Verify Fix

After adding input validation, test again:

```bash
peeka-cli watch "app.tasks.process_data" --times 100
```

Observed 100 calls, no exceptions.

---

## Scenario 3: Verify Code Changes

### Problem Description

Modified caching logic, need to verify that cache is actually working.

### Solution Steps

#### 1. Observe Cache Function

```bash
# Observe cache hit status
peeka-cli watch "app.cache.get" --times 20
```

Output:
```json
{"type":"observation","func_name":"app.cache.get","args":["user_123"],"result":{"name":"Alice"},"from_cache":true}
{"type":"observation","func_name":"app.cache.get","args":["user_456"],"result":null,"from_cache":false}
{"type":"observation","func_name":"app.cache.get","args":["user_123"],"result":{"name":"Alice"},"from_cache":true}
```

#### 2. Calculate Hit Rate

```bash
peeka-cli watch "app.cache.get" --times 1000 | \
  jq 'select(.type == "observation") | .from_cache' | \
  awk '{if($1=="true") hit++; total++} END {print "Hit Rate:", (hit/total)*100, "%"}'
```

Output:
```
Hit Rate: 85.3 %
```

**Conclusion**: Cache hit rate is 85%, meets expectations.

---

## Scenario 4: Monitor Performance Regression

### Problem Description

After deploying a new version, worried about performance regression, need real-time monitoring.

### Solution Steps

#### 1. Establish Performance Baseline

Before deployment:
```bash
peeka-cli monitor "app.service.critical_func" --interval 5 -c 12 > baseline.jsonl
```

#### 2. Monitor After Deployment

```bash
peeka-cli monitor "app.service.critical_func" --interval 5 -c 12 > after_deploy.jsonl
```

#### 3. Comparison Analysis

```python
# compare.py
import json

def load_stats(file):
    stats = []
    with open(file) as f:
        for line in f:
            msg = json.loads(line)
            if msg.get("type") == "observation":
                stats.append(msg["avg_rt"])
    return sum(stats) / len(stats) if stats else 0

baseline = load_stats("baseline.jsonl")
after = load_stats("after_deploy.jsonl")

print(f"Baseline: {baseline:.2f}ms")
print(f"After Deploy: {after:.2f}ms")
print(f"Change: {((after - baseline) / baseline) * 100:.1f}%")
```

Output:
```
Baseline: 125.50ms
After Deploy: 130.20ms
Change: +3.7%
```

**Conclusion**: Performance slightly decreased by 3.7%, within acceptable range.

---

## Scenario 5: Debug Race Conditions

### Problem Description

Multi-threaded program occasionally has data inconsistency, suspected to be a race condition.

### Solution Steps

#### 1. Observe Key Function Call Order

```bash
# Observe two key functions
peeka-cli watch "app.data.read" --times 100 > read.jsonl &
peeka-cli watch "app.data.write" --times 100 > write.jsonl &
```

#### 2. Analyze Timestamps

```python
# analyze_race.py
import json
from collections import defaultdict

def load_calls(file):
    calls = []
    with open(file) as f:
        for line in f:
            msg = json.loads(line)
            if msg.get("type") == "observation":
                calls.append((msg["timestamp"], msg["func_name"]))
    return calls

reads = load_calls("read.jsonl")
writes = load_calls("write.jsonl")

# Merge and sort
all_calls = sorted(reads + writes, key=lambda x: x[0])

# Find suspicious patterns: read -> read (no write in between)
for i in range(len(all_calls) - 1):
    curr_func = all_calls[i][1]
    next_func = all_calls[i+1][1]
    if "read" in curr_func and "read" in next_func:
        print(f"Suspicious pattern at {all_calls[i][0]}")
```

#### 3. Verify Fix

After adding lock protection, test again:

```bash
peeka-cli watch "app.data.read" --times 100 | \
  jq 'select(.type == "observation") | .data_version' | \
  uniq -c
```

Output shows consistent data version, no race condition.

---

## Scenario 6: Analyze Parameter Distribution

### Problem Description

Need to understand the distribution of function parameters to optimize caching strategy.

### Solution Steps

#### 1. Collect Parameter Data

```bash
peeka-cli watch "app.service.query" --times 1000 > params.jsonl
```

#### 2. Analyze Distribution

```bash
# Extract first parameter
cat params.jsonl | \
  jq 'select(.type == "observation") | .args[0]' | \
  sort | uniq -c | sort -rn | head -10
```

Output:
```
    245 "user_type_A"
    198 "user_type_B"
     87 "user_type_C"
     45 "user_type_D"
     ...
```

#### 3. Visualize

```python
# visualize.py
import json
from collections import Counter
import matplotlib.pyplot as plt

params = []
with open("params.jsonl") as f:
    for line in f:
        msg = json.loads(line)
        if msg.get("type") == "observation":
            params.append(msg["args"][0])

counter = Counter(params)
labels, values = zip(*counter.most_common(10))

plt.bar(labels, values)
plt.xlabel("Parameter Value")
plt.ylabel("Frequency")
plt.title("Parameter Distribution")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("param_dist.png")
```

**Conclusion**: `user_type_A` and `user_type_B` have the highest proportion, should be cached first.

---

## Scenario 7: Production Real-Time Alerts

### Problem Description

Need to monitor critical functions in production in real-time, with automatic alerts on anomalies.

### Solution Steps

#### 1. Write Monitoring Script

```bash
#!/bin/bash
# monitor_and_alert.sh

peeka-cli monitor "app.api.critical" --interval 10 | \
while read -r line; do
    # Parse JSON
    avg_rt=$(echo "$line" | jq -r '.avg_rt // 0')
    fail=$(echo "$line" | jq -r '.fail // 0')

    # Alert conditions
    if (( $(echo "$avg_rt > 500" | bc -l) )); then
        echo "ALERT: High latency detected: ${avg_rt}ms" | \
          mail -s "Peeka Alert" ops@example.com
    fi

    if (( fail > 0 )); then
        echo "ALERT: ${fail} failures detected" | \
          mail -s "Peeka Alert" ops@example.com
    fi
done
```

#### 2. Run in Background

```bash
nohup ./monitor_and_alert.sh > alert.log 2>&1 &
```

#### 3. Integrate with Monitoring Systems

```python
# prometheus_exporter.py
from prometheus_client import Gauge, start_http_server
import json
import subprocess

# Define metrics
api_latency = Gauge('api_critical_latency_ms', 'API critical latency')
api_failures = Gauge('api_critical_failures', 'API critical failures')

# Start HTTP server
start_http_server(8000)

# Read Peeka output
proc = subprocess.Popen(
    ['peeka-cli', 'monitor', 'app.api.critical', '--interval', '10'],
    stdout=subprocess.PIPE,
    text=True
)

for line in proc.stdout:
    msg = json.loads(line)
    if msg.get("type") == "observation":
        api_latency.set(msg.get("avg_rt", 0))
        api_failures.set(msg.get("fail", 0))
```

---

## Best Practices Summary

### 1. Gradually Narrow Down Scope

```bash
# From coarse to fine
monitor → watch → trace → stack
```

### 2. Use Conditional Filtering

```bash
# Avoid too much data
--condition "cost > 100"
--times 10
```

### 3. Save Observation Data

```bash
# For offline analysis
peeka-cli watch "func" > data.jsonl
```

### 4. Integrate with Tool Chain

```bash
# Make full use of Unix tools
peeka-cli watch "func" | jq | awk | gnuplot
```

### 5. Automation Integration

```python
# Integrate into CI/CD
python -m peeka.analyze --baseline baseline.jsonl --current current.jsonl
```

---

## More Resources

- [Command Reference]({% link commands/index.md %}) - Detailed command documentation
- [Architecture]({% link architecture.md %}) - Understand implementation principles
- [Troubleshooting]({% link troubleshooting.md %}) - Common problem solutions
