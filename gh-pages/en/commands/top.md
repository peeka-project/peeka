---
layout: default
title: top Command
parent: Command Reference
nav_order: 12
permalink: /commands/top
---

# top Command
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}


## Overview

The `top` command is a function-level sampling profiler, similar to Linux's `top` command and `py-spy top`. It periodically samples the call stacks of all threads to gather CPU usage statistics for each function, helping developers quickly identify performance bottlenecks.

**Design Features**:
- **Low Overhead**: Sampling mode with performance impact < 5%
- **Real-time Statistics**: Streaming performance data output, supports live monitoring
- **Function Granularity**: Precise to function level, showing own time and total time
- **Automatic Filtering**: Filters Peeka's own threads by default to avoid interference

## Use Cases

- **Performance Bottleneck Identification**: Find functions with highest CPU usage
- **Hot Function Analysis**: Statistics on function call frequency and time distribution
- **Real-time Monitoring**: Continuous sampling to observe program performance changes
- **Optimization Verification**: Compare performance data before and after optimization

## Command Format

```bash
peeka-cli attach <pid>    # First attach to the target process
peeka-cli top [options]
```

### Parameters

| Parameter         | Description                                       | Default | Example                                   |
|-------------------|---------------------------------------------------|---------|-------------------------------------------|
| `-i, --interval`  | Sampling interval (seconds)                       | `0.01`  | `-i 0.02` (sample every 20ms)            |
| `-c, --cycles`    | Number of display cycles (-1 for infinite)        | `-1`    | `-c 10` (auto-stop after 10 displays)    |
| `--sort`          | Sort column (own / total / own-time / total-time) | `own`   | `--sort total`                            |
| `--no-filter-peeka` | Disable Peeka thread filtering (enabled by default) | `false` | `--no-filter-peeka` (show all threads)    |

### Performance Metrics

| Metric        | Description                                   | Calculation                        |
|---------------|-----------------------------------------------|------------------------------------|
| `own_pct`     | Own CPU percentage (function's own time)      | `own_count / total_samples * 100`  |
| `total_pct`   | Total CPU percentage (including sub-functions) | `total_count / total_samples * 100` |
| `own_time`    | Own time (seconds)                            | `own_count * interval`             |
| `total_time`  | Total time (seconds, including sub-functions) | `total_count * interval`           |
| `own_count`   | Own sample count (stack top at this function) | Direct count                       |
| `total_count` | Total sample count (function in call stack)   | Deduplicated count                 |

## Basic Usage

### 1. Start Performance Profiling

```bash
# First attach to the target process
peeka-cli attach 12345

# Start top command (default 10ms sampling interval)
peeka-cli top
```

**Output Example** (streaming output, updated every second):

```json
{
  "type": "top_snapshot",
  "top_id": "top_a1b2c3d4",
  "total_samples": 1000,
  "sample_interval": 0.01,
  "functions": [
    {
      "name": "compute_matrix",
      "filename": "/app/algorithm.py",
      "line": 156,
      "own_pct": 45.3,
      "total_pct": 58.7,
      "own_time": 0.453,
      "total_time": 0.587,
      "own_count": 453,
      "total_count": 587
    },
    {
      "name": "multiply",
      "filename": "/app/math_utils.py",
      "line": 42,
      "own_pct": 12.8,
      "total_pct": 13.4,
      "own_time": 0.128,
      "total_time": 0.134,
      "own_count": 128,
      "total_count": 134
    },
    {
      "name": "log_result",
      "filename": "/app/logger.py",
      "line": 89,
      "own_pct": 8.2,
      "total_pct": 8.9,
      "own_time": 0.082,
      "total_time": 0.089,
      "own_count": 82,
      "total_count": 89
    }
  ]
}
```

### 2. Adjust Sampling Interval

```bash
# 20ms sampling interval (lower overhead, reduced precision)
peeka-cli top -i 0.02

# 5ms sampling interval (higher precision, increased overhead)
peeka-cli top -i 0.005
```

**Sampling Interval Selection Recommendations**:
- **Production Environment**: 10-20ms (default 10ms), performance impact < 5%
- **Development Environment**: 5-10ms, higher precision
- **Long-term Monitoring**: 20-50ms, reduced overhead

### 3. Limit Display Cycles

```bash
# Auto-stop after 10 displays
peeka-cli top -c 10

# Auto-stop after 60 displays (approximately 1 minute)
peeka-cli top -c 60
```

### 4. Sort by Different Fields

```bash
# Sort by own CPU percentage (default)
peeka-cli top --sort own

# Sort by total CPU percentage
peeka-cli top --sort total

# Sort by own time
peeka-cli top --sort own-time

# Sort by total time
peeka-cli top --sort total-time
```

### 5. Include Peeka Threads

```bash
# Show all threads, including Peeka itself
peeka-cli top --no-filter-peeka
```

**Note**: Enabling `--no-filter-peeka` will display Peeka Agent and sampling threads themselves, typically used for debugging Peeka or verifying filtering logic.

## Output Format

### Streaming Output (One Snapshot Per Second)

```json
{
  "type": "top_snapshot",
  "top_id": "top_a1b2c3d4",
  "total_samples": 1000,
  "sample_interval": 0.01,
  "functions": [
    {
      "name": "compute_matrix",
      "filename": "/app/algorithm.py",
      "line": 156,
      "own_pct": 45.3,
      "total_pct": 58.7,
      "own_time": 0.453,
      "total_time": 0.587,
      "own_count": 453,
      "total_count": 587
    }
  ]
}
```

**Field Descriptions**:

| Field             | Description                               | Example Value        |
|-------------------|-------------------------------------------|----------------------|
| `top_id`          | Performance profiling session ID          | `"top_a1b2c3d4"`     |
| `total_samples`   | Total sample count                        | `1000`               |
| `sample_interval` | Sampling interval (seconds)               | `0.01`               |
| `functions`       | Function statistics list (sorted by own_pct desc) | `[...]`              |

**functions Array Elements**:

| Field         | Description                             | Example Value        |
|---------------|-----------------------------------------|----------------------|
| `name`        | Function name                           | `"compute_matrix"`   |
| `filename`    | Source file path                        | `"/app/algorithm.py"` |
| `line`        | Function definition line number         | `156`                |
| `own_pct`     | Own CPU percentage                      | `45.3`               |
| `total_pct`   | Total CPU percentage (including sub-functions) | `58.7`               |
| `own_time`    | Own time (seconds)                      | `0.453`              |
| `total_time`  | Total time (seconds, including sub-functions) | `0.587`              |
| `own_count`   | Own sample count                        | `453`                |
| `total_count` | Total sample count (deduplicated)       | `587`                |

## Real-time Monitoring Examples

### Filter Top 5 Hot Functions with jq

```bash
peeka-cli top | jq 'select(.type == "top_snapshot") | .functions[:5]'
```

### Count CPU Usage for Specific Modules

```bash
peeka-cli top | jq '
  select(.type == "top_snapshot") |
  .functions[] |
  select(.filename | contains("/app/")) |
  {name, own_pct}
'
```

### Export Performance Data to File

```bash
# Collect 100 snapshots then stop, save to file
peeka-cli top -c 100 > performance.jsonl
```

## TUI Usage

In TUI mode, the `top` command provides a visual performance profiling interface:

1. Start TUI:
   ```bash
   peeka  # or python -m peeka.tui
   ```

2. Connect to the target process (enter PID or select process)

3. Press **`0`** key to switch to **Top View**

4. Features:
   - Real-time display of function performance rankings
   - Support sorting by own_pct / total_pct / own_time / total_time
   - Color coding: red (high CPU), yellow (medium), green (low)
   - Display sampling statistics (total_samples, interval)
   - Support pause/resume sampling

5. Shortcuts:
   - `r`: Refresh data
   - `s`: Switch sort field
   - `Enter`: Start performance profiling
   - `Delete`: Stop performance profiling
   - `c`: Clear statistics data (reset)

## How It Works

### Sampling Flow

1. **Start Sampling Thread**: Run a background thread at specified interval (default 10ms)
2. **Get Thread Snapshot**: Call `sys._current_frames()` to get current stack frames of all threads
3. **Filter Threads**: Exclude Peeka's own threads (unless `--no-filter-peeka`)
4. **Traverse Call Stack**: Count from stack top (leaf frame) to stack bottom (root frame) frame by frame
5. **Update Statistics**:
   - Stack top frame: `own_count += 1` (function's own execution)
   - All frames: `total_count += 1` (deduplicated, includes call chain)
6. **Generate Snapshot**: Generate and push a snapshot to the client every second

### Filtering Strategy

By default, filter the following threads (disabled by `--no-filter-peeka`):
- Threads with names starting with `peeka-`
- Threads executing code within the Peeka package directory
- The sampling thread itself

### Statistical Metric Calculation

```python
# Own percentage
own_pct = (own_count / total_samples) * 100

# Total percentage
total_pct = (total_count / total_samples) * 100

# Own time
own_time = own_count * sample_interval

# Total time
total_time = total_count * sample_interval
```

## Notes

1. **Sampling Precision**:
   - Sampling mode cannot capture all function calls, only counts stack frames at sampling moments
   - Short-lived functions may be missed
   - Suitable for long-running performance profiling, not for microbenchmarks

2. **Performance Overhead**:
   - Default 10ms interval: performance impact < 5%
   - 5ms interval: performance impact approximately 5-10%
   - 1ms interval: performance impact 10-20% (not recommended)

3. **Thread Filtering**:
   - Filters Peeka threads by default to avoid data pollution
   - Use `--no-filter-peeka` to view all threads (including Peeka)

4. **Output Frequency**:
   - CLI mode: Outputs one snapshot per second (fixed)
   - Sampling interval and output frequency are independent

5. **Stop Methods**:
   - Ctrl+C: Normal stop, outputs final snapshot
   - `--cycles` parameter: Auto-stop
   - TUI mode: Press `Delete` key to stop

6. **Difference from trace Command**:
   - `top`: Sampling mode, low overhead, suitable for long-term monitoring
   - `trace`: Instrumentation mode, high precision, suitable for short-term call chain analysis
   - `top` counts all functions, `trace` only tracks specified functions

7. **Permission Requirements**:
   - Must use `attach` command to attach to the target process first
   - For attach permission requirements, see [attach command documentation](attach.html)
