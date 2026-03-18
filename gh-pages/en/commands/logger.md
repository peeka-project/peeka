---
layout: default
title: Peeka Logger Command Guide
parent: Command Reference
nav_order: 6
permalink: /commands/logger
---

# Peeka Logger Command Guide
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Command Overview

The `logger` command allows you to dynamically view and adjust Python application log levels at runtime, without restarting the process or modifying configuration files. This is a powerful tool for troubleshooting issues in production environments.

**Core Features**:
- List all loggers and their current log levels
- Query configuration information for specific loggers
- Dynamically modify logger log levels
- Support wildcard pattern matching for multiple loggers
- Changes take effect immediately without process restart

**Typical Scenarios**:
- Temporarily enable DEBUG logging in production to troubleshoot issues
- Suppress verbose logs from third-party libraries
- Dynamically adjust log levels for performance optimization
- Diagnose missing logs (check logger configuration)

---

## Use Cases

### 1. Temporarily Enable Debug Logging in Production

**Scenario**: Production environment has issues that require temporarily enabling DEBUG logs for troubleshooting, but the service cannot be restarted.

```bash
# Step 1: Check current log level
peeka-cli logger --action get --logger myapp.payment

# Output:
# {"status": "success", "name": "myapp.payment", "level": "INFO", "level_num": 20}

# Step 2: Temporarily enable DEBUG level
peeka-cli logger --action set --logger myapp.payment --level DEBUG

# Output:
# {"status": "success", "name": "myapp.payment", "old_level": "INFO", "new_level": "DEBUG"}

# Step 3: Restore original level after troubleshooting
peeka-cli logger --action set --logger myapp.payment --level INFO
```

**Effect**: Takes effect immediately without process restart, log file starts outputting detailed debug information.

### 2. Suppress Verbose Logs from Third-Party Libraries

**Scenario**: Third-party libraries (like urllib3, boto3) output excessive DEBUG logs that drown out application logs.

```bash
# View all loggers containing "urllib3"
peeka-cli logger --action list --pattern "urllib3*"

# Suppress urllib3 debug logs
peeka-cli logger --action set --logger urllib3 --level WARNING

# Do the same for boto3
peeka-cli logger --action set --logger botocore --level WARNING
```

**Effect**: Third-party libraries only output WARNING and above level logs, making application logs clearly visible.

### 3. Diagnose Missing Logs

**Scenario**: Logs from a certain module are not being output, suspecting logger configuration issues.

```bash
# Step 1: Check if logger exists
peeka-cli logger --action get --logger myapp.missing_logs

# If output is "Logger not found", the logger has not been initialized
# If output level is ERROR, the log level is set too high

# Step 2: View all loggers to find potentially related ones
peeka-cli logger --action list --pattern "myapp.*"

# Step 3: Lower level or create logger (set action will auto-create)
peeka-cli logger --action set --logger myapp.missing_logs --level DEBUG
```

### 4. Batch View Module Log Levels

**Scenario**: Check if log configuration for all application modules meets expectations.

```bash
# View all application loggers (assuming all start with "myapp")
peeka-cli logger --action list --pattern "myapp.*" | jq .

# Output formatted logger list for easy configuration review
```

### 5. Performance Optimization: Disable Unnecessary Logging

**Scenario**: Production environment finds log I/O becoming a performance bottleneck, need to temporarily disable some logs.

```bash
# Raise log level to WARNING for all non-core modules
peeka-cli logger --action set --logger myapp.analytics --level WARNING
peeka-cli logger --action set --logger myapp.reporting --level WARNING
peeka-cli logger --action set --logger myapp.metrics --level WARNING
```

---

## TUI Usage

In TUI mode, press **`7`** key to switch to **Logger View**, providing the following interactive features:

- **Logger List Display**: Automatically loads and displays all loggers and their current levels
  - Sorted by logger name
  - Shows logger name, current level, level number
  - Real-time Refresh button
- **Level Modification**: Quickly adjust level for selected logger
  - Supports DEBUG, INFO, WARNING, ERROR, CRITICAL
  - Changes take effect immediately
- **Pattern Filtering**: Supports fnmatch wildcards (`*` and `?`) for filtering loggers
- **Quick Operations**:
  - Up/Down arrow keys to select logger
  - Press Enter to modify selected logger's level
  - Press `r` to refresh logger list

**CLI Equivalent Commands**: All examples below use CLI commands for demonstration. TUI provides the same functionality with a graphical interface.

## Command Format

```bash
peeka-cli logger [--action ACTION] [options]
```

**Required**:
- Must first attach to target process using `peeka-cli attach <pid>`

**Optional Parameters**:
- `--action`: Operation type (`list`, `get`, `set`, default `list`)
- `--logger`: Logger name (required for `get` and `set` actions)
- `--level`: Log level (required for `set` action)
- `--pattern`: Matching pattern (optional for `list` action)

---

## Actions

### 1. list - List All Loggers

**Purpose**: View all initialized loggers in the process and their current log levels.

**Syntax**:
```bash
peeka-cli logger --action list [--pattern <pattern>]
```

**Parameters**:
- `--pattern` (optional): fnmatch-style pattern (supports `*` and `?` wildcards)

**Examples**:
```bash
# List all loggers
peeka-cli logger --action list

# Only list loggers under myapp namespace
peeka-cli logger --action list --pattern "myapp.*"

# List all loggers containing "db"
peeka-cli logger --action list --pattern "*db*"
```

**Output**:
```json
{
  "status": "success",
  "loggers": [
    {"name": "myapp.auth", "level": "INFO", "level_num": 20},
    {"name": "myapp.db", "level": "WARNING", "level_num": 30},
    {"name": "myapp.api", "level": "DEBUG", "level_num": 10}
  ],
  "count": 3
}
```

### 2. get - Query Specific Logger

**Purpose**: View detailed configuration of a specific logger.

**Syntax**:
```bash
peeka-cli logger --action get --logger <name>
```

**Parameters**:
- `--logger` (required): Full logger name (wildcards not supported)

**Example**:
```bash
peeka-cli logger --action get --logger myapp.payment
```

**Output (Success)**:
```json
{
  "status": "success",
  "name": "myapp.payment",
  "level": "INFO",
  "level_num": 20
}
```

**Output (Failure)**:
```json
{
  "status": "error",
  "error": "Logger not found: myapp.payment"
}
```

### 3. set - Modify Logger Level

**Purpose**: Dynamically modify a logger's log level, takes effect immediately.

**Syntax**:
```bash
peeka-cli logger --action set --logger <name> --level <level>
```

**Parameters**:
- `--logger` (required): Logger name (auto-created if doesn't exist)
- `--level` (required): New log level (see supported levels below)

**Supported Log Levels**:
| Level | Value | Description |
|------|------|------|
| `DEBUG` | 10 | Detailed debugging information |
| `INFO` | 20 | General informational messages |
| `WARNING` | 30 | Warning messages (default level) |
| `ERROR` | 40 | Error messages |
| `CRITICAL` | 50 | Critical errors |
| `NOTSET` | 0 | Not set (inherit from parent logger) |

**Examples**:
```bash
# Enable DEBUG logging
peeka-cli logger --action set --logger myapp.auth --level DEBUG

# Disable INFO level logging (keep only warnings and errors)
peeka-cli logger --action set --logger myapp.reporting --level WARNING

# Restore default level
peeka-cli logger --action set --logger myapp.auth --level INFO
```

**Output**:
```json
{
  "status": "success",
  "name": "myapp.auth",
  "old_level": "INFO",
  "new_level": "DEBUG",
  "old_level_num": 20,
  "new_level_num": 10
}
```

**Notes**:
- Logger names are case-insensitive (internally converted to uppercase)
- If logger doesn't exist, it will be auto-created (using `logging.getLogger(name)`)
- Changes take effect immediately without process restart
- Changes are not persistent (will revert to original config after process restart)

---

## Parameters

### --pattern - Matching Pattern

Used with `list` action to filter logger list.

**Supported Wildcards**:
- `*`: Matches any length of characters (including empty string)
- `?`: Matches single character
- `[seq]`: Matches any character in seq
- `[!seq]`: Matches any character not in seq

**Examples**:
| Pattern | Matches | Doesn't Match |
|------|----------|------------|
| `myapp.*` | `myapp.auth`, `myapp.db` | `myapp`, `webapp.auth` |
| `*db*` | `myapp.db`, `database`, `mongodb` | `myapp.cache` |
| `myapp.api.v?` | `myapp.api.v1`, `myapp.api.v2` | `myapp.api.v10` |
| `myapp.[ad]*` | `myapp.auth`, `myapp.db` | `myapp.cache` |

**Usage**:
```bash
# List all loggers under myapp namespace
peeka-cli logger --action list --pattern "myapp.*"

# List all database-related loggers
peeka-cli logger --action list --pattern "*db*"

# List all API version loggers
peeka-cli logger --action list --pattern "*.api.v?"
```

### --logger - Logger Name

Specifies the full name of the logger to operate on.

**Naming Convention**:
- Typically uses module path (like `myapp.module.submodule`)
- Python standard practice: `logger = logging.getLogger(__name__)`
- Third-party libraries typically use package name (like `urllib3`, `boto3`)

**Methods to Find Logger Names**:
```bash
# Method 1: List all loggers, find target
peeka-cli logger --action list | jq -r '.loggers[].name'

# Method 2: Use pattern matching to narrow scope
peeka-cli logger --action list --pattern "myapp.payment*"

# Method 3: Check getLogger calls in code
grep -r "getLogger" myapp/ | grep -v ".pyc"
```

### --level - Log Level

Specifies the new log level (only used for `set` action).

**Level Selection Recommendations**:
| Scenario | Recommended Level | Description |
|------|----------|------|
| Production normal operation | `INFO` | Record key business information |
| Production troubleshooting | `DEBUG` | Temporarily enable detailed logs |
| Performance optimization (reduce logging) | `WARNING` | Only record exceptional situations |
| Disable third-party library logs | `ERROR` or `CRITICAL` | Only record severe errors |
| Inherit parent logger config | `NOTSET` | Use parent logger's level |

**Level Inheritance Relationship**:
```
root logger (default WARNING)
  └─ myapp (INFO)
       ├─ myapp.auth (DEBUG) ← Uses own level
       └─ myapp.db (NOTSET)  ← Inherits myapp's INFO
```

---

## Output Format

### list Action Output

```json
{
  "status": "success",
  "loggers": [
    {
      "name": "myapp.auth",
      "level": "INFO",
      "level_num": 20
    },
    {
      "name": "myapp.db",
      "level": "DEBUG",
      "level_num": 10
    }
  ],
  "count": 2
}
```

**Field Descriptions**:
- `status`: Operation status (`success` or `error`)
- `loggers`: Logger list (sorted by name)
- `name`: Full logger name
- `level`: Log level name (like `INFO`)
- `level_num`: Log level numeric value (like `20`)
- `count`: Number of matched loggers

### get Action Output

**Success**:
```json
{
  "status": "success",
  "name": "myapp.payment",
  "level": "INFO",
  "level_num": 20
}
```

**Failure** (logger doesn't exist):
```json
{
  "status": "error",
  "error": "Logger not found: myapp.payment"
}
```

### set Action Output

**Success**:
```json
{
  "status": "success",
  "name": "myapp.auth",
  "old_level": "INFO",
  "new_level": "DEBUG",
  "old_level_num": 20,
  "new_level_num": 10
}
```

**Failure** (invalid level):
```json
{
  "status": "error",
  "error": "Invalid level: INVALID. Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL, NOTSET"
}
```

---

## Usage Examples

### Example 1: View All Logger Configurations

```bash
peeka-cli logger --action list | jq .
```

**Output**:
```json
{
  "status": "success",
  "loggers": [
    {"name": "root", "level": "WARNING", "level_num": 30},
    {"name": "myapp", "level": "INFO", "level_num": 20},
    {"name": "myapp.auth", "level": "INFO", "level_num": 20},
    {"name": "myapp.db", "level": "WARNING", "level_num": 30},
    {"name": "urllib3.connectionpool", "level": "WARNING", "level_num": 30}
  ],
  "count": 5
}
```

### Example 2: Temporarily Enable DEBUG Logging for Troubleshooting

```bash
# 1. Check current level
peeka-cli logger --action get --logger myapp.payment
# Output: {"status": "success", "name": "myapp.payment", "level": "INFO", ...}

# 2. Enable DEBUG
peeka-cli logger --action set --logger myapp.payment --level DEBUG
# Output: {"status": "success", "old_level": "INFO", "new_level": "DEBUG"}

# 3. Observe log file (another terminal)
tail -f /var/log/myapp.log | grep payment

# 4. Restore after troubleshooting
peeka-cli logger --action set --logger myapp.payment --level INFO
```

### Example 3: Suppress Verbose Third-Party Library Logs

```bash
# View all third-party library loggers
peeka-cli logger --action list --pattern "*" | \
  jq -r '.loggers[] | select(.level == "DEBUG") | .name'

# Batch disable (keep only WARNING and above)
for logger in urllib3 botocore requests; do
  peeka-cli logger --action set --logger "$logger" --level WARNING
done
```

### Example 4: Check if Logger Exists

```bash
# Method 1: Use get action
result=$(peeka-cli logger --action get --logger myapp.missing 2>&1)
echo "$result" | jq -r .status
# Output: error (if doesn't exist)

# Method 2: List all and search
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.name == "myapp.missing")'
# No output (if doesn't exist)
```

### Example 5: Create New Logger and Set Level

```bash
# set action will auto-create non-existent logger
peeka-cli logger --action set --logger myapp.new_module --level DEBUG

# Verify creation success
peeka-cli logger --action get --logger myapp.new_module
# Output: {"status": "success", "name": "myapp.new_module", "level": "DEBUG", ...}
```

### Example 6: Batch View Specific Module Configuration

```bash
# View log levels for all myapp.api submodules
peeka-cli logger --action list --pattern "myapp.api.*" | \
  jq -r '.loggers[] | "\(.name): \(.level)"'
```

**Output**:
```
myapp.api.v1: INFO
myapp.api.v2: DEBUG
myapp.api.auth: WARNING
```

---

## Complete Diagnostic Workflow

### Workflow 1: Production Issue Troubleshooting

**Scenario**: Production environment has payment failures, need to temporarily enable debug logging to locate issue.

```bash
# Step 1: Check current log level for payment module
peeka-cli logger --action get --logger myapp.payment
# Output: {"level": "INFO"}

# Step 2: Enable DEBUG logging
peeka-cli logger --action set --logger myapp.payment --level DEBUG

# Step 3: Monitor log file simultaneously
tail -f /var/log/myapp.log | grep -A 5 -B 5 "payment"

# Step 4: Reproduce issue (trigger payment flow)

# Step 5: Review debug logs to locate issue

# Step 6: Restore original level after resolving issue
peeka-cli logger --action set --logger myapp.payment --level INFO
```

### Workflow 2: Diagnose Missing Logs

**Scenario**: Logs from a certain module are completely missing, need to check the reason.

```bash
# Step 1: Check if logger exists
peeka-cli logger --action get --logger myapp.analytics
# If output is "Logger not found", it's not initialized

# Step 2: View parent logger level
peeka-cli logger --action get --logger myapp
# Output: {"level": "WARNING"}

# Step 3: Create logger and set to DEBUG
peeka-cli logger --action set --logger myapp.analytics --level DEBUG

# Step 4: Verify logs start outputting
tail -f /var/log/myapp.log | grep analytics
```

### Workflow 3: Performance Optimization - Reduce Log I/O

**Scenario**: System has high load, log I/O becomes bottleneck, need to temporarily disable some logs.

```bash
# Step 1: View all loggers at DEBUG level
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.level == "DEBUG") | .name'

# Output:
# myapp.api
# myapp.cache
# myapp.db
# myapp.reporting

# Step 2: Keep core modules (api, db) at DEBUG, disable others
peeka-cli logger --action set --logger myapp.cache --level WARNING
peeka-cli logger --action set --logger myapp.reporting --level WARNING

# Step 3: Observe system load changes
# (Use top, htop, or monitoring system)

# Step 4: Restore if needed
peeka-cli logger --action set --logger myapp.cache --level DEBUG
peeka-cli logger --action set --logger myapp.reporting --level DEBUG
```

### Workflow 4: Batch Adjust Third-Party Library Logs

**Scenario**: Multiple third-party libraries output excessive debug logs, need to batch disable them.

```bash
# Step 1: List all non-application loggers (typically third-party libraries)
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.name | startswith("myapp") | not) | .name'

# Output:
# urllib3
# urllib3.connectionpool
# botocore
# requests

# Step 2: Batch set to WARNING
cat <<'EOF' | bash
for logger in urllib3 urllib3.connectionpool botocore requests; do
  peeka-cli logger --action set --logger "$logger" --level WARNING
  echo "Set $logger to WARNING"
done
EOF

# Step 3: Verify
peeka-cli logger --action list --pattern "*" | \
  jq -r '.loggers[] | select(.name | startswith("myapp") | not) | "\(.name): \(.level)"'
```

---

## Important Notes

### 1. Temporary Nature of Changes

**Important**: Logger command changes **are not persistent**.

- Changes take effect immediately, but will revert to original config after process restart
- For permanent changes, update configuration files (like `logging.conf` or `logging.basicConfig()` in code)

### 2. Root Logger Impact

**root logger** is the default parent of all loggers:
- Default level is `WARNING`
- All loggers without explicitly set levels inherit from root logger
- Modifying root logger affects all child loggers (unless child loggers have explicit levels)

**Example**:
```bash
# View root logger
peeka-cli logger --action get --logger root

# Globally enable DEBUG (use with caution!)
peeka-cli logger --action set --logger root --level DEBUG
```

**Warning**: Modifying root logger can cause log explosion, only use when necessary.

### 3. Logger Creation Timing

**Note**: `list` and `get` only show **initialized** loggers.

- Loggers are created on first call to `logging.getLogger(name)`
- If code hasn't executed to relevant module, logger won't appear in list
- `set` action will auto-create non-existent loggers

### 4. Level Inheritance Mechanism

Python logging level inheritance rules:
```
root (WARNING)
  └─ myapp (INFO)
       ├─ myapp.auth (DEBUG)    ← Uses own level
       ├─ myapp.db (NOTSET)     ← Inherits myapp's INFO
       └─ myapp.cache (NOTSET)  ← Inherits myapp's INFO
```

**Actual Effective Levels**:
- `myapp.auth`: DEBUG (own level)
- `myapp.db`: INFO (inherited from myapp)
- `myapp.cache`: INFO (inherited from myapp)

### 5. Handler Impact

**Note**: Logger command only modifies logger **level**, not handler configuration.

- Even if logger level is DEBUG, if handler level is INFO, DEBUG logs still won't output
- Check handler configuration: `logger.handlers[0].level` (need to check in code)

### 6. Performance Impact

Modifying logger level itself has **no performance overhead**, but log level changes affect:
- **Lowering level** (like INFO → DEBUG): Log volume increases, I/O overhead rises
- **Raising level** (like DEBUG → WARNING): Log volume decreases, performance improves

**Recommendations**:
- Restore original level immediately after debugging
- Avoid keeping DEBUG level enabled for extended periods
- Regularly check log file sizes

---

## FAQ

### Q1: Why are logs still not outputting after changing logger level?

**Possible Reasons**:
1. **Handler level too high**: Logger level is DEBUG, but handler level is INFO
2. **Logs not flushed**: Some handlers have buffering, need to wait for flush
3. **Wrong logger name**: Actual logger name used differs from the one modified
4. **Parent logger level too high**: Even if child logger is DEBUG, parent logger filtered messages

**Diagnosis Method**:
```bash
# 1. Confirm logger level has changed
peeka-cli logger --action get --logger myapp.target

# 2. Check parent logger level
peeka-cli logger --action get --logger myapp

# 3. Check root logger level
peeka-cli logger --action get --logger root

# 4. View all loggers (confirm name is correct)
peeka-cli logger --action list --pattern "myapp.*"
```

### Q2: How to batch modify multiple loggers?

**Method 1**: Use shell loop
```bash
for logger in myapp.auth myapp.db myapp.cache; do
  peeka-cli logger --action set --logger "$logger" --level DEBUG
done
```

**Method 2**: Read from file
```bash
# loggers.txt file content:
# myapp.auth
# myapp.db
# myapp.cache

while read logger; do
  peeka-cli logger --action set --logger "$logger" --level DEBUG
done < loggers.txt
```

**Method 3**: Dynamic query then batch modify
```bash
# Change all INFO level loggers to DEBUG
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.level == "INFO") | .name' | \
  while read logger; do
    peeka-cli logger --action set --logger "$logger" --level DEBUG
  done
```

### Q3: Will changes affect other processes?

**Answer**: No.

- Each process has independent logger configuration
- Changes only affect the specified PID process
- Other processes' loggers are unaffected

### Q4: How to restore all loggers to original state?

**Method**: Restart process (logger configuration will reload).

**Note**: Logger command doesn't provide "restore snapshot" functionality, recommend:
1. Record original levels before changing
2. Or just restart process to restore configuration

**Example (record original levels)**:
```bash
# Save current configuration before changing
peeka-cli logger --action list > logger_backup.json

# Restore after changes
jq -r '.loggers[] | "\(.name) \(.level)"' logger_backup.json | \
  while read name level; do
    peeka-cli logger --action set --logger "$name" --level "$level"
  done
```

### Q5: Why doesn't pattern matching find loggers?

**Possible Reasons**:
1. **Pattern syntax error**: fnmatch doesn't support regex, only supports `*` and `?`
2. **Logger not initialized**: Code hasn't executed to that module yet
3. **Case sensitivity**: Logger names are case-sensitive

**Debug Method**:
```bash
# 1. List all loggers (without pattern)
peeka-cli logger --action list | jq -r '.loggers[].name'

# 2. Confirm exact name of target logger

# 3. Use correct pattern
peeka-cli logger --action list --pattern "myapp.*"
```

### Q6: Can non-existent loggers be created?

**Answer**: Yes, use `set` action.

```bash
# Create new logger and set level
peeka-cli logger --action set --logger myapp.new_logger --level DEBUG

# Verify
peeka-cli logger --action get --logger myapp.new_logger
# Output: {"status": "success", "name": "myapp.new_logger", "level": "DEBUG"}
```

**Note**:
- Newly created loggers won't auto-recreate after process restart
- Application code needs to explicitly call `logging.getLogger(name)` to use the logger

---

## Advanced Techniques

### 1. Dynamic Log Level Toggle Script

**Scenario**: Frequently enable/disable debug logging, write automation script.

```bash
#!/bin/bash
# toggle_debug.sh - Toggle log level for myapp.payment

PID=12345
LOGGER="myapp.payment"

current=$(peeka-cli logger --action get --logger $LOGGER | jq -r .level)

if [ "$current" == "DEBUG" ]; then
  echo "Disabling DEBUG..."
  peeka-cli logger --action set --logger $LOGGER --level INFO
else
  echo "Enabling DEBUG..."
  peeka-cli logger --action set --logger $LOGGER --level DEBUG
fi
```

### 2. Monitor Log Level Changes

**Scenario**: Regularly check logger configuration to ensure production environment hasn't accidentally enabled DEBUG.

```bash
#!/bin/bash
# check_debug_loggers.sh - Check all DEBUG level loggers

PID=12345

debug_loggers=$(peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.level == "DEBUG") | .name')

if [ -n "$debug_loggers" ]; then
  echo "WARNING: Found DEBUG loggers in production:"
  echo "$debug_loggers"
  # Send alert (like Slack, email, etc.)
else
  echo "All loggers are at safe levels."
fi
```

### 3. Integrate with Prometheus

**Scenario**: Export logger configuration to Prometheus monitoring.

```bash
#!/bin/bash
# export_logger_metrics.sh

PID=12345

peeka-cli logger --action list | \
  jq -r '.loggers[] | "logger_level{name=\"\(.name)\"} \(.level_num)"' \
  > /var/lib/node_exporter/textfile_collector/logger_levels.prom
```

**Prometheus Query**:
```promql
# Query all DEBUG level loggers
logger_level{level="10"}

# Alert rule (detect production DEBUG loggers)
ALERT ProductionDebugLogger
  IF logger_level{name=~"myapp.*", level="10"} > 0
  FOR 5m
  ANNOTATIONS {
    summary = "Production logger at DEBUG level",
    description = "Logger {{ $labels.name }} is at DEBUG level in production."
  }
```

### 4. Log Level Analysis

**Scenario**: Count distribution of logger levels in application.

```bash
peeka-cli logger --action list --pattern "myapp.*" | \
  jq -r '.loggers[] | .level' | sort | uniq -c
```

**Output**:
```
     12 DEBUG
     45 INFO
      8 WARNING
```

### 5. Temporary Log Redirection

**Scenario**: Temporarily adjust a module's log level and redirect output to separate file.

```bash
# 1. Enable DEBUG logging
peeka-cli logger --action set --logger myapp.payment --level DEBUG

# 2. Monitor logs in another terminal
tail -f /var/log/myapp.log | grep "payment" > payment_debug.log

# 3. Reproduce issue

# 4. Stop monitoring (Ctrl+C)

# 5. Restore log level
peeka-cli logger --action set --logger myapp.payment --level INFO
```

### 6. Auto-Restore Script

**Scenario**: Enable DEBUG then auto-restore after 5 minutes to avoid forgetting to disable.

```bash
#!/bin/bash
# temp_debug.sh - Temporarily enable DEBUG, auto-restore after 5 minutes

PID=$1
LOGGER=$2
DURATION=${3:-300}  # Default 5 minutes

# Save original level
original=$(peeka-cli logger --action get --logger $LOGGER | jq -r .level)
echo "Original level: $original"

# Enable DEBUG
peeka-cli logger --action set --logger $LOGGER --level DEBUG
echo "DEBUG enabled. Will auto-restore in $DURATION seconds..."

# Background wait then restore
(
  sleep $DURATION
  peeka-cli logger --action set --logger $LOGGER --level $original
  echo "Restored to $original"
) &
```

**Usage**:
```bash
./temp_debug.sh 12345 myapp.payment 300
```

---

## Summary

The `logger` command is a powerful tool for log diagnostics in production environments, especially suitable for:
- Temporarily enabling debug logs to troubleshoot issues
- Suppressing verbose logs from third-party libraries
- Dynamically adjusting log levels for performance optimization
- Diagnosing missing log issues

**Best Practices**:
- Record original levels before modification (for easy restoration)
- Restore original level immediately after debugging
- Avoid prolonged DEBUG level (log explosion)
- Use `--pattern` to filter loggers (improve efficiency)
- Combine with `jq` for powerful data analysis

**Next Steps**:
- Learn about [`watch`](watch.md) command (observe function calls)
- Learn about [`stack`](stack.md) command (trace call stacks)
- Learn about [`memory`](memory.md) command (memory analysis)
- Refer to [AGENTS.md](../AGENTS.md) (developer guide)
