---
layout: default
title: memory Command
parent: Command Reference
nav_order: 7
permalink: /commands/memory
---

# memory Command
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}


## Overview

The `memory` command is used to analyze **memory usage** in running Python processes, providing 10 diagnostic operations: memory overview, trace control, allocation analysis, snapshot management, snapshot comparison, reference chain queries, snapshot export, and GC statistics. This is Peeka's core memory diagnostic tool, suitable for memory leak troubleshooting and performance optimization in production environments.



## TUI Usage

In TUI mode, press **`6`** key to switch to **Memory View**, providing 4 tabs and rich interactive features:

#### Overview Tab (Memory Overview)

- Process RSS (physical memory) display in MB
- RSS trend Sparkline chart (last 100 sample points)
- tracemalloc current tracked memory / peak memory
- GC three-generation counts (gen0, gen1, gen2)
- **Top Objects by Size** table: type, count, Δcount, size, Δsize
  - Auto-calculated deltas on each refresh (red = growth, green = decrease)
  - Sortable column headers

#### Allocations Tab (Allocation Hotspots)

- Requires Track to be started first
- Shows Top N memory allocations: Rank, Size, Count, Location (file:line)
- Syncs with auto-refresh updates

#### Diff Tab (Snapshot Comparison)

- **Snap button**: Take tracemalloc snapshot (max 2, FIFO)
- **Diff button**: Compare two snapshots, table shows Location, Size Δ, New, Old, Count Δ
- Delta data color-coded (red = growth, green = decrease)

#### References Tab (Reference Chain Analysis)

- Enter type name (e.g., `dict`, `MyClass`)
- **Referrers button**: Tree view of who references objects of that type (find leak root cause)
- **Referents button**: Tree view of what objects of that type reference (analyze object structure)

#### Controls and Keybindings

| Control | Keybinding | Function |
|---------|:----------:|----------|
| Refresh | `r` | Manual refresh overview + allocations |
| Track | `T` | Start/stop tracemalloc tracing |
| GC | `g` | Trigger GC statistics refresh |
| Dump | — | Export snapshot file to disk |
| Auto | `a` | Auto-refresh (5-second interval) |
| nframe input | — | Set tracemalloc stack depth (1-50) |
| limit input | — | Set GC/allocation display count (1-100) |
**CLI Equivalent Commands**: All examples below use CLI commands for demonstration. TUI provides the same functionality with a graphical interface.
## Use Cases

- **Memory leak diagnosis**: View which code locations allocate the most memory
- **Performance optimization**: Identify memory allocation hotspots, optimize memory usage
- **GC analysis**: Count object type quantities, discover abnormal object counts
- **Snapshot comparison**: Export multiple snapshots for offline comparison of memory growth
- **RSS monitoring**: View process physical memory (RSS) usage

## Command Format

```bash
peeka-cli memory <pid> [options]
```

### Parameters

| Parameter | Description | Default | Example |
|-----------|-------------|---------|---------|
| `pid` | Target process ID | - | `12345` |
| `--action` | Memory operation type | `overview` | `--action start` |
| `--nframe` | tracemalloc call stack depth | `25` | `--nframe 50` |
| `--group-by` | Allocation grouping method | `lineno` | `--group-by filename` |
| `--limit` | Result count limit | `20` | `--limit 50` |
| `--filename` | Snapshot file name | Auto-generated | `--filename snapshot1` |
| `--type-name` | Type name (for referrers/referents) | - | `--type-name dict` |
| `--max-depth` | Reference chain recursion depth | `2` | `--max-depth 3` |
| `--max-per-level` | Max entries per level | `10` | `--max-per-level 20` |

### action Operation Types

| Action | Description | Requires start | Main Purpose |
|--------|-------------|----------------|--------------|
| **overview** | Memory overview | ❌ No | View RSS, GC status, tracemalloc status |
| **start** | Start tracing | - | Enable tracemalloc memory tracing |
| **stop** | Stop tracing | ❌ No | Close tracemalloc, release tracing overhead |
| **top** | Top N allocations | ✅ Yes | View memory allocation hotspots (by code location) |
| **dump** | Export snapshot | ✅ Yes | Save snapshot for offline analysis |
| **gc** | GC statistics | ❌ No | Count object type quantities |
| **snapshot** | Memory snapshot | ✅ Yes | Save in-memory snapshot (FIFO, max 2) |
| **diff** | Snapshot comparison | ✅ Yes | Compare latest two snapshots for memory change |
| **referrers** | Referrer query | ❌ No | Find who holds objects of specified type (leak investigation) |
| **referents** | Referent query | ❌ No | Find what objects of specified type reference (structure analysis) |

## Basic Usage

### 1. Memory Overview (overview)

View current memory state of process, **no need to start tracing**.

```bash
# View memory overview (default action)
peeka-cli memory --action overview

# Or use other action
peeka-cli memory --action start
```

**Output Example**:

```json
{
  "status": "success",
  "action": "overview",
  "timestamp": 1738328400.0,
  "pid": 12345,
  "rss_bytes": 524288000,
  "rss_source": "procfs",
  "tracemalloc": {
    "enabled": false,
    "current_bytes": null,
    "peak_bytes": null
  },
  "gc": {
    "enabled": true,
    "counts": [150, 10, 2],
    "stats": [
      {"collections": 45, "collected": 1234, "uncollectable": 0},
      {"collections": 4, "collected": 89, "uncollectable": 0},
      {"collections": 0, "collected": 0, "uncollectable": 0}
    ]
  }
}
```

**Field Descriptions**:

| Field | Description | Example Value |
|-------|-------------|---------------|
| `rss_bytes` | Process physical memory (bytes) | `524288000` (500 MB) |
| `rss_source` | RSS source | `"procfs"` or `"resource_maxrss"` |
| `tracemalloc.enabled` | Whether tracemalloc is running | `true` / `false` |
| `tracemalloc.current_bytes` | Currently tracked memory (only when tracing) | `123456789` |
| `tracemalloc.peak_bytes` | Peak memory (only when tracing) | `234567890` |
| `gc.enabled` | Whether GC is enabled | `true` / `false` |
| `gc.counts` | GC counters (gen0, gen1, gen2) | `[150, 10, 2]` |
| `gc.stats` | Per-generation GC statistics | See table below |

**GC stats Fields**:

| Field | Description |
|-------|-------------|
| `collections` | Number of GC runs for this generation |
| `collected` | Number of objects collected |
| `uncollectable` | Number of uncollectable objects (warning: possible leak) |

### 2. Start Memory Tracing (start)

Enable Python's `tracemalloc` module to begin tracking memory allocations.

```bash
# Use default depth (25 call stack levels)
peeka-cli memory --action start

# Custom call stack depth (1-50)
peeka-cli memory --action start --nframe 50
```

**Output Example**:

```json
{
  "status": "success",
  "action": "start",
  "message": "tracemalloc started successfully",
  "nframe": 25
}
```

**Parameter Description**:

- `--nframe`: Call stack depth (1-50), default 25
  - Greater depth = more detailed tracking but higher overhead
  - Recommended: production 25, development/debugging 50

**Idempotency**:

If tracemalloc is already running, calling `start` again will not error:

```json
{
  "status": "success",
  "action": "start",
  "message": "tracemalloc is already running",
  "was_already_running": true
}
```

**Performance Impact**:

- **Overhead**: approximately 5-10% performance and memory overhead
- **Recommendation**: Start during off-peak hours, or enable only briefly

### 3. Stop Memory Tracing (stop)

Close `tracemalloc` and release tracing overhead.

```bash
peeka-cli memory --action stop
```

**Output Example**:

```json
{
  "status": "success",
  "action": "stop",
  "message": "tracemalloc stopped successfully",
  "was_running": true
}
```

**Important Notes**:

- ⚠️ **Data loss after stop**: stop clears all tracing data
- 📝 **Export before stopping**: if you need to preserve data, run `dump` first
- ✅ **Idempotent operation**: stop doesn't error even if not running

```bash
# Correct flow: export first, then stop
peeka-cli memory --action dump --filename production_snapshot
peeka-cli memory --action stop
```

### 4. View Top N Memory Allocations (top)

Display code locations with highest memory usage (**requires start first**).

```bash
# View top 20 allocations (default grouping by line number)
peeka-cli memory --action top

# View top 50 allocations
peeka-cli memory --action top --limit 50

# Group by filename (see which module uses most)
peeka-cli memory --action top --group-by filename --limit 30
```

**Output Example** (grouped by line number):

```json
{
  "status": "success",
  "action": "top",
  "group_by": "lineno",
  "limit": 20,
  "total_size_bytes": 245760000,
  "allocations": [
    {
      "rank": 1,
      "size_bytes": 24641536,
      "count": 1024,
      "traceback": [
        {"filename": "/app/models.py", "lineno": 145}
      ]
    },
    {
      "rank": 2,
      "size_bytes": 15925248,
      "count": 512,
      "traceback": [
        {"filename": "/app/cache.py", "lineno": 89}
      ]
    }
  ]
}
```

**Field Descriptions**:

| Field | Description |
|-------|-------------|
| `rank` | Rank (descending by size_bytes) |
| `size_bytes` | Total bytes used by this allocation point |
| `count` | Number of allocation blocks |
| `traceback` | Call stack (array, oldest first) |

**group-by Mode Comparison**:

| Mode | Description | Use Case |
|------|-------------|----------|
| `lineno` | Group by code line | Locate specific code lines |
| `filename` | Group by file | Locate problem modules |

**Example** (grouped by filename):

```bash
peeka-cli memory --action top --group-by filename --limit 10
```

```json
{
  "allocations": [
    {
      "rank": 1,
      "size_bytes": 104857600,
      "count": 5120,
      "traceback": [
        {"filename": "/app/models.py", "lineno": 1}
      ]
    }
  ]
}
```

> Note: When grouping by filename, `lineno` field is 1 (no actual meaning)

**Error Handling**:

If `top` is called without starting tracing:

```json
{
  "status": "error",
  "action": "top",
  "error": "tracemalloc is not running. Run 'memory start' first."
}
```

### 5. Export Memory Snapshot (dump)

Save current memory snapshot to file (**requires start first**).

```bash
# Auto-generate filename (timestamp)
peeka-cli memory --action dump

# Specify filename
peeka-cli memory --action dump --filename my_snapshot

# With path traversal protection (auto-extracts basename)
peeka-cli memory --action dump --filename "../etc/passwd"
# Actually saved as: /tmp/passwd.snapshot
```

**Output Example**:

```json
{
  "status": "success",
  "action": "dump",
  "file_path": "/tmp/peeka_dump_20260131_165420.snapshot",
  "size_bytes": 1048576
}
```

**File Format**:

- **Format**: Python tracemalloc binary snapshot (`.snapshot`)
- **Loading**: Use `tracemalloc.Snapshot.load()` to load
- **Location**: Directory specified by `PEEKA_DUMP_DIR` environment variable, default `/tmp`

**Snapshot Contents**:

- ✅ All currently live memory allocations
- ✅ Call stack for each allocation point
- ✅ Allocation sizes and counts
- ❌ **Not incremental**: complete snapshot at current moment

**Offline Analysis Example**:

```python
import tracemalloc

# Load snapshot
snapshot = tracemalloc.Snapshot.load('/tmp/peeka_dump_20260131_165420.snapshot')

# Group by line number, view top 10
stats = snapshot.statistics('lineno')
for stat in stats[:10]:
    print(f"{stat.size / 1024 / 1024:.1f} MB - {stat.count} blocks")
    print(f"  {stat.traceback[0].filename}:{stat.traceback[0].lineno}")
```

**Snapshot Comparison** (incremental analysis):

```python
# Load two snapshots
snapshot1 = tracemalloc.Snapshot.load('before.snapshot')
snapshot2 = tracemalloc.Snapshot.load('after.snapshot')

# Calculate difference
diff = snapshot2.compare_to(snapshot1, 'lineno')

# View memory growth
for stat in diff[:10]:
    print(f"{stat.size_diff / 1024 / 1024:+.1f} MB - {stat.filename}:{stat.lineno}")
```

**Security Protection**:

- ✅ **Path traversal protection**: Auto-uses `os.path.basename()` to extract filename
- ✅ **Directory restriction**: Can only write to `PEEKA_DUMP_DIR` or `/tmp`
- ✅ **Auto extension**: Filename automatically gets `.snapshot` suffix

### 6. GC Object Statistics (gc)

Count quantities of each object type (**no need for start**).

```bash
# View top 20 object types (default)
peeka-cli memory --action gc

# View top 50 object types
peeka-cli memory --action gc --limit 50
```

**Output Example**:

```json
{
  "status": "success",
  "action": "gc",
  "limit": 20,
  "total_objects": 1523891,
  "objects_by_type": [
    {"rank": 1, "type": "dict", "count": 345612},
    {"rank": 2, "type": "list", "count": 198234},
    {"rank": 3, "type": "tuple", "count": 156789},
    {"rank": 4, "type": "str", "count": 123456},
    {"rank": 5, "type": "function", "count": 89012},
    {"rank": 6, "type": "User", "count": 50000}
  ]
}
```

**Field Descriptions**:

| Field | Description |
|-------|-------------|
| `total_objects` | Total GC-tracked objects |
| `objects_by_type` | Object type list sorted by count |
| `rank` | Rank (descending by count, ascending by type if tied) |
| `type` | Object type name (`type(obj).__name__`) |
| `count` | Number of objects of this type |

**Use Cases**:

- **Memory leak troubleshooting**: Discover abnormal object count growth
  ```bash
  # Example: Found 50000 User objects (possibly unreleased)
  ```
- **Object lifecycle analysis**: Observe object creation and destruction
- **Cache monitoring**: Check if cache objects are excessive

**Performance Note**:

- ⚠️ **Higher overhead**: `gc.get_objects()` returns all objects (possibly millions)
- 📊 **Use carefully in production**: Recommend during off-peak or low-traffic times
- ✅ **Has hard limit**: Returns maximum 100 items (prevents excessive output)

**Difference from top**:

| Dimension | `top` Command | `gc` Command |
|-----------|---------------|--------------|
| **Requires start** | ✅ Yes | ❌ No |
| **Shows** | Memory allocation **locations** (code lines) | Object **type** quantities |
| **What it tells** | Which code line allocated how much memory | How many objects of each type exist |
| **What it doesn't tell** | Object types | How much memory each object uses |
| **Data source** | `tracemalloc` | `gc.get_objects()` |


### 7. Memory Snapshot (snapshot)

Save a tracemalloc snapshot in memory for subsequent diff comparison (**requires start first**).

```bash
# Take a snapshot (max 2 stored, FIFO)
peeka-cli memory --action snapshot
```

**Output Example**:

```json
{
  "status": "success",
  "action": "snapshot",
  "snapshot_count": 1,
  "timestamp": 1738328400.0
}
```

**Usage Notes**:

- Snapshots are stored in Agent memory (not written to disk), max 2 stored
- When exceeding 2, the oldest snapshot is automatically discarded (FIFO)
- Used with `diff` to analyze memory changes over a period of time
- To persist snapshots to disk, use `dump` instead

### 8. Snapshot Comparison (diff)

Compare memory changes between the latest two snapshots (**requires at least 2 snapshots taken first**).

```bash
# Take two snapshots first
peeka-cli memory --action snapshot
# ... wait some time ...
peeka-cli memory --action snapshot

# Compare differences
peeka-cli memory --action diff
```

**Output Example**:

```json
{
  "status": "success",
  "action": "diff",
  "diffs": [
    {
      "location": "/app/models.py:145",
      "size_diff": 1048576,
      "size_new": 2097152,
      "size_old": 1048576,
      "count_diff": 512,
      "count_new": 1024,
      "count_old": 512
    },
    {
      "location": "/app/cache.py:89",
      "size_diff": -524288,
      "size_new": 524288,
      "size_old": 1048576,
      "count_diff": -256,
      "count_new": 256,
      "count_old": 512
    }
  ]
}
```

**Field Descriptions**:

| Field | Description |
|-------|-------------|
| `location` | Code location (filename:lineno) |
| `size_diff` | Memory size change (positive = growth, negative = decrease) |
| `size_new` | Memory size in the new snapshot |
| `size_old` | Memory size in the old snapshot |
| `count_diff` | Allocation block count change |
| `count_new` | Allocation block count in the new snapshot |
| `count_old` | Allocation block count in the old snapshot |

**Important Notes**:

- Results are grouped by `lineno`, max 50 entries returned
- `size_diff > 0` indicates memory growth — key focus for leak investigation
- Unlike `dump` offline comparison, `diff` completes online without exporting files

### 9. Referrer Query (referrers)

Find who holds objects of the specified type (**no need for start**). Useful for tracing object references when investigating memory leaks.

```bash
# Find who references dict type objects
peeka-cli memory --action referrers --type-name dict

# Increase recursion depth and per-level count
peeka-cli memory --action referrers --type-name MyClass --max-depth 3 --max-per-level 15
```

**Output Example**:

```json
{
  "status": "success",
  "action": "referrers",
  "target": {
    "type": "MyClass",
    "repr_short": "<MyClass object at 0x7f...>",
    "count": 500
  },
  "referrers": [
    {
      "type": "dict",
      "repr_short": "{'user': <MyClass object at 0x7f...>, ...}",
      "referrers": [
        {
          "type": "list",
          "repr_short": "[{'user': <MyClass ...>}, ...] (len=500)"
        }
      ]
    }
  ]
}
```

**Parameter Descriptions**:

| Parameter | Description | Range | Default |
|-----------|-------------|-------|---------|
| `--type-name` | Target object type name | Any type name | **Required** |
| `--max-depth` | Recursive search depth | 1-3 | 2 |
| `--max-per-level` | Max referrers per level | 1-20 | 10 |

**Use Cases**:

- After discovering abnormal object count growth, use `referrers` to trace who holds those objects
- Use with `gc` command: first use `gc` to find abnormal types, then use `referrers` to trace the reference chain

### 10. Referent Query (referents)

Find what objects of the specified type reference (**no need for start**). Useful for analyzing internal object structure and holdings.

```bash
# Find what dict type objects reference
peeka-cli memory --action referents --type-name dict

# Custom depth
peeka-cli memory --action referents --type-name MyCache --max-depth 3
```

**Output Example**:

```json
{
  "status": "success",
  "action": "referents",
  "target": {
    "type": "MyCache",
    "repr_short": "<MyCache object at 0x7f...>",
    "count": 1
  },
  "referents": [
    {
      "type": "dict",
      "repr_short": "{'items': [...], 'max_size': 10000}",
      "referents": [
        {
          "type": "list",
          "repr_short": "[<Item ...>, <Item ...>, ...] (len=9500)"
        }
      ]
    }
  ]
}
```

**Difference from referrers**:

| Dimension | `referrers` | `referents` |
|-----------|-------------|-------------|
| **Direction** | Upward: who references me | Downward: what I reference |
| **Purpose** | Investigate leak root cause | Analyze object structure |
| **Typical Question** | Why isn't this object collected? | What does this object hold internally? |
## Complete Diagnostic Workflow

### Scenario 1: Memory Leak Troubleshooting

```bash
# 1. View current memory state
peeka-cli memory --action overview

# 2. Check object counts for anomalies with GC stats
peeka-cli memory --action gc --limit 50

# 3. Start tracing
peeka-cli memory --action start --nframe 50

# 4. Wait some time (let issue reproduce)
sleep 300  # 5 minutes

# 5. Take first memory snapshot
peeka-cli memory --action snapshot

# 6. Continue waiting
sleep 300

# 7. Take second memory snapshot
peeka-cli memory --action snapshot

# 8. Online comparison of two snapshots (no file export needed)
peeka-cli memory --action diff

# 9. View top allocation hotspots
peeka-cli memory --action top --limit 30

# 10. Trace reference chain for suspicious types
peeka-cli memory --action referrers --type-name MyClass --max-depth 3

# 11. Export snapshot for offline analysis (optional)
peeka-cli memory --action dump --filename snapshot_leak

# 12. Stop tracing
peeka-cli memory --action stop
```

### Scenario 2: Performance Optimization

```bash
# 1. Start tracing
peeka-cli memory --action start

# 2. Run performance test
# ... trigger business operations ...

# 3. View memory hotspots (grouped by file)
peeka-cli memory --action top --group-by filename --limit 20

# 4. View specific code lines (grouped by line number)
peeka-cli memory --action top --group-by lineno --limit 50

# 5. Stop tracing
peeka-cli memory --action stop
```

### Scenario 3: Periodic Monitoring

```bash
#!/bin/bash
# Scheduled memory snapshot script

PID=12345
SNAPSHOT_DIR="/data/memory_snapshots"

# Start tracing (first time)
peeka-cli memory --action start

# Export snapshot every hour
while true; do
  timestamp=$(date +%Y%m%d_%H%M%S)
  peeka-cli memory --action dump --filename "snapshot_$timestamp"
  sleep 3600
done
```

## Output Format

All actions return JSON format with fields including:

### Common Fields

| Field | Type | Description |
|-------|------|-------------|
| `status` | string | `"success"` or `"error"` |
| `action` | string | Executed operation type |
| `error` | string | Error message (only on failure) |

### Error Response Example

```json
{
  "status": "error",
  "action": "top",
  "error": "tracemalloc is not running. Run 'memory start' first."
}
```

## Performance Impact

### tracemalloc Overhead

| Scenario | Overhead | Notes |
|----------|----------|-------|
| **tracemalloc not started** | 0% | overview/gc have no extra overhead |
| **Start tracemalloc (nframe=25)** | 5-8% | Tracks memory allocations and call stacks |
| **Start tracemalloc (nframe=50)** | 8-12% | Deeper call stacks have higher overhead |
| **dump operation** | < 1% | Snapshot export momentary overhead |
| **gc operation** | 2-5% | Traverse all objects, momentary overhead |

### Best Practices

1. **Start on demand**:
   ```bash
   # ❌ Wrong: keep tracing on long-term
   peeka-cli memory --action start
   # ... run permanently ...

   # ✅ Correct: start briefly, stop immediately after diagnosis
   peeka-cli memory --action start
   sleep 300  # 5 minutes
   peeka-cli memory --action dump --filename snapshot
   peeka-cli memory --action stop
   ```

2. **Choose appropriate nframe**:
   ```bash
   # Production: use default 25
   peeka-cli memory --action start

   # Development/debugging: use deeper call stacks
   peeka-cli memory --action start --nframe 50
   ```

3. **Use gc during off-peak**:
   ```bash
   # gc operation has higher overhead, recommend off-peak execution
   peeka-cli memory --action gc --limit 30
   ```

4. **Export snapshots periodically**:
   ```bash
   # Export every 1 hour for trend analysis
   while true; do
     peeka-cli memory --action dump --filename "snapshot_$(date +%H)"
     sleep 3600
   done
   ```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PEEKA_DUMP_DIR` | `/tmp` | Snapshot file save directory |

**Example**:

```bash
# Custom snapshot directory
export PEEKA_DUMP_DIR=/data/peeka_dumps
peeka-cli memory --action dump
# File saved to: /data/peeka_dumps/peeka_dump_*.snapshot
```

## Common Issues

### 1. dump fails: "tracemalloc is not running"

**Cause**: dump executed without starting tracemalloc.

**Solution**:

```bash
# Start tracing first
peeka-cli memory --action start

# Then export snapshot
peeka-cli memory --action dump
```

### 2. top results empty

**Possible Causes**:

- Just started tracemalloc, haven't captured allocations yet
- Process has very few memory allocations

**Solution**:

```bash
# Wait some time then check
peeka-cli memory --action start
sleep 60
peeka-cli memory --action top
```

### 3. dump file too large

**Cause**: Traced too long, too many allocation records.

**Solution**:

- Reduce tracing time (stop promptly)
- Lower nframe depth
- Export periodically and clear (stop + start)

### 4. gc command very slow

**Cause**: `gc.get_objects()` needs to traverse all objects.

**Solution**:

- Execute during off-peak hours
- Reduce limit parameter
- Avoid high-frequency calls

### 5. RSS and tracemalloc values differ significantly

**Cause**:

- **RSS**: Physical memory occupied by process (includes code, stack, shared libraries)
- **tracemalloc**: Only tracks Python heap allocations

**Normal Situation**:

```
RSS: 500 MB
tracemalloc: 200 MB  # Only Python object memory
```

**Difference Sources**:

- Shared libraries (e.g., numpy, torch)
- Memory directly allocated by C extensions
- Interpreter's own memory
- Stack memory

### 6. Where is dump file?

**Default Location**: `/tmp/peeka_dump_*.snapshot`

**Find Method**:

```bash
# View latest dump file
ls -lt /tmp/peeka_dump_*.snapshot | head -1

# Custom directory
export PEEKA_DUMP_DIR=/data/dumps
peeka-cli memory --action dump
ls -lt /data/dumps/
```

## Advanced Tips

### 1. Automated Memory Monitoring Script

```bash
#!/bin/bash
# memory_monitor.sh - Automatic memory monitoring

PID=$1
ALERT_THRESHOLD=1000000000  # 1GB

peeka-cli memory --action overview | \
  jq -r '.rss_bytes' | \
  while read rss; do
    if [ $rss -gt $ALERT_THRESHOLD ]; then
      echo "Alert: RSS > 1GB, capturing snapshot..."
      peeka-cli memory --action start
      sleep 30
      peeka-cli memory --action dump --filename "alert_$(date +%s)"
      peeka-cli memory --action stop
    fi
  done
```

### 2. Memory Growth Rate Analysis

```python
# analyze_growth.py
import json
import sys

snapshots = sys.argv[1:]  # Multiple snapshot file paths

sizes = []
for snapshot in snapshots:
    data = json.load(open(snapshot))
    sizes.append(data['rss_bytes'])

# Calculate growth rate
for i in range(1, len(sizes)):
    growth = (sizes[i] - sizes[i-1]) / sizes[i-1] * 100
    print(f"Snapshot {i}: +{growth:.2f}%")
```

### 3. Integrate with Prometheus

```python
# prometheus_exporter.py
from prometheus_client import Gauge
import subprocess
import json
import time

rss_gauge = Gauge('process_rss_bytes', 'Process RSS memory', ['pid'])
tracemalloc_gauge = Gauge('tracemalloc_bytes', 'Tracemalloc memory', ['pid', 'type'])

def collect_metrics(pid):
    result = subprocess.check_output(['peeka', 'memory', '--pid', str(pid)])
    data = json.loads(result)

    rss_gauge.labels(pid=pid).set(data['rss_bytes'])

    if data['tracemalloc']['enabled']:
        tracemalloc_gauge.labels(pid=pid, type='current').set(
            data['tracemalloc']['current_bytes']
        )
        tracemalloc_gauge.labels(pid=pid, type='peak').set(
            data['tracemalloc']['peak_bytes']
        )

while True:
    collect_metrics(12345)
    time.sleep(15)
```

## References

- [Python tracemalloc Documentation](https://docs.python.org/3/library/tracemalloc.html)
- [Python gc Module Documentation](https://docs.python.org/3/library/gc.html)
- [Peeka Architecture Design](../ARCHITECTURE.md)
- [Peeka Developer Guide](../AGENTS.md)

## Changelog

| Version | Date | Updates |
|---------|------|---------|
| 0.1.0 | 2026-01 | Initial release, supports 10 memory operations |
