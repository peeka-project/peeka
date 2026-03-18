---
layout: default
title: thread Command
parent: Command Reference
nav_order: 11
permalink: /commands/thread
---

# thread Command
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}


## Overview

The `thread` command is used to list all threads in the target process and inspect call stack information for specific threads. This command helps developers quickly locate thread states, diagnose deadlock issues, analyze thread blocking causes, and more.



## Use Cases

- **Thread Enumeration**: Quickly list all threads in a process and their states
- **State Filtering**: Filter threads by state (RUNNABLE/WAITING/TIMED_WAITING)
- **Stack Inspection**: View complete call stack for specific threads to locate code execution position
- **Deadlock Diagnosis**: Analyze thread states to discover potential deadlocks or blocking issues
- **Concurrency Debugging**: Understand multi-threaded program running state and thread distribution

## Command Format

```bash
peeka-cli attach <pid>    # First attach to target process
peeka-cli thread [options]
```

### Parameters

| Parameter    | Description                                                     | Default | Example               |
|--------------|----------------------------------------------------------------|---------|----------------------|
| `--tid`      | Thread ID for viewing specific thread stack details            | None    | `--tid 123456`       |
| `--state`    | Filter threads by state (RUNNABLE / WAITING / TIMED_WAITING)   | None    | `--state WAITING`    |
| `--sort-by`  | Sort field (tid / name / state)                                | `tid`   | `--sort-by name`     |
| `--depth`    | Stack depth limit (only for detail view)                       | `50`    | `--depth 30`         |

### Thread State Explanation

Peeka automatically infers thread state by analyzing the current call stack:

| State            | Description                           | Typical Scenarios              |
|------------------|---------------------------------------|--------------------------------|
| `RUNNABLE`       | Thread is running or in runnable state | Normal code execution          |
| `WAITING`        | Thread is waiting (indefinitely)       | `wait()`, `join()`, `lock`, etc. |
| `TIMED_WAITING`  | Thread is in timed wait                | `sleep()`, `poll()`, etc.      |

**State Inference Algorithm**: Checks the top 3 call frames of the thread stack and matches blocking patterns based on function names and module names (such as `select`, `poll`, `wait`, `sleep`, etc.).

## Basic Usage

### 1. List All Threads

```bash
# First attach to target process
peeka-cli attach 12345

# List all threads
peeka-cli thread
```

**Output Example**:

```json
{
  "status": "success",
  "action": "list",
  "total": 10,
  "threads": [
    {
      "tid": 140234567890,
      "native_id": 12345,
      "name": "MainThread",
      "daemon": false,
      "alive": true,
      "state": "RUNNABLE",
      "stack_depth": 15,
      "top_frame": {
        "filename": "/app/main.py",
        "lineno": 42,
        "funcname": "process_request"
      }
    },
    {
      "tid": 140234567891,
      "native_id": 12346,
      "name": "WorkerThread-1",
      "daemon": true,
      "alive": true,
      "state": "WAITING",
      "stack_depth": 8,
      "top_frame": {
        "filename": "/usr/lib/python3.12/threading.py",
        "lineno": 629,
        "funcname": "wait"
      }
    }
  ]
}
```

**Field Descriptions**:

| Field          | Description                                          | Example Value             |
|----------------|------------------------------------------------------|--------------------------|
| `tid`          | Thread ID (Python ident)                             | `140234567890`           |
| `native_id`    | Native thread ID (Python 3.8+, may be None)          | `12345`                  |
| `name`         | Thread name                                          | `"MainThread"`           |
| `daemon`       | Whether thread is daemon                             | `false`                  |
| `alive`        | Whether thread is alive                              | `true`                   |
| `state`        | Inferred thread state                                | `"RUNNABLE"`             |
| `stack_depth`  | Call stack depth                                     | `15`                     |
| `top_frame`    | Top frame info (filename / lineno / funcname)        | `{"filename": "...", ...}` |

### 2. Filter Threads by State

```bash
# Show only waiting threads
peeka-cli thread --state WAITING

# Show only sleeping threads
peeka-cli thread --state TIMED_WAITING

# Show only running threads
peeka-cli thread --state RUNNABLE
```

### 3. View Stack Details for Specific Thread

```bash
# View complete stack for thread 140234567890
peeka-cli thread --tid 140234567890

# Limit stack depth to 30 levels
peeka-cli thread --tid 140234567890 --depth 30
```

**Output Example** (detail view):

```json
{
  "status": "success",
  "action": "detail",
  "thread": {
    "tid": 140234567890,
    "native_id": 12345,
    "name": "MainThread",
    "daemon": false,
    "alive": true,
    "state": "WAITING",
    "stack_depth": 8,
    "stack": [
      {
        "filename": "/usr/lib/python3.12/queue.py",
        "lineno": 171,
        "funcname": "get",
        "locals_keys": ["self", "block", "timeout"]
      },
      {
        "filename": "/app/worker.py",
        "lineno": 25,
        "funcname": "worker_loop",
        "locals_keys": ["queue", "item", "result"]
      },
      {
        "filename": "/app/main.py",
        "lineno": 100,
        "funcname": "run",
        "locals_keys": ["self", "config"]
      }
    ]
  }
}
```

**stack Field Descriptions**:

| Field          | Description                        | Example Value                     |
|----------------|------------------------------------|----------------------------------|
| `filename`     | Source file path                   | `"/app/worker.py"`               |
| `lineno`       | Line number                        | `25`                             |
| `funcname`     | Function name                      | `"worker_loop"`                  |
| `locals_keys`  | Local variable names (max 20)      | `["queue", "item", "result"]`    |

### 4. Sort by Field

```bash
# Sort by thread name
peeka-cli thread --sort-by name

# Sort by thread state
peeka-cli thread --sort-by state

# Sort by thread ID (default)
peeka-cli thread --sort-by tid
```

## Output Format

### list Output (List Mode)

```json
{
  "status": "success",
  "action": "list",
  "total": 10,
  "threads": [
    {
      "tid": 140234567890,
      "native_id": 12345,
      "name": "MainThread",
      "daemon": false,
      "alive": true,
      "state": "RUNNABLE",
      "stack_depth": 15,
      "top_frame": {
        "filename": "/app/main.py",
        "lineno": 42,
        "funcname": "process_request"
      }
    }
  ]
}
```

### detail Output (Detail Mode)

```json
{
  "status": "success",
  "action": "detail",
  "thread": {
    "tid": 140234567890,
    "native_id": 12345,
    "name": "MainThread",
    "daemon": false,
    "alive": true,
    "state": "WAITING",
    "stack_depth": 8,
    "stack": [
      {
        "filename": "/usr/lib/python3.12/queue.py",
        "lineno": 171,
        "funcname": "get",
        "locals_keys": ["self", "block", "timeout"]
      }
    ]
  }
}
```

## TUI Usage

In TUI mode, you can view thread information through the interactive interface:

1. Launch TUI:
   ```bash
   peeka  # or python -m peeka.tui
   ```

2. Connect to target process (enter PID or select process)

3. Press **`h`** key to switch to **Threads View**

4. Features:
   - Real-time display of all thread lists
   - Filter threads by state
   - Select thread to view stack details
   - Support sorting by name, state, ID

## Notes

1. **State Inference Accuracy**:
   - Thread state is inferred by analyzing call stack, may have false positives
   - Only checks top 3 frames, deep blocking may not be identified
   - RUNNABLE state includes both running and runnable situations

2. **native_id Availability**:
   - `native_id` field is only available in Python 3.8+
   - In older Python versions, this field is `null`

3. **Local Variable Limits**:
   - `locals_keys` field in detail view shows at most 20 local variable names
   - Variable values are not retrieved to avoid triggering side effects

4. **Performance Impact**:
   - Getting thread info uses `sys._current_frames()` and `threading.enumerate()`
   - Performance overhead is minimal, but may have delay with very large thread counts (>1000)

5. **Permission Requirements**:
   - Must first use `attach` command to attach to target process
   - For attachment permission requirements, see [attach command documentation](attach.html)
