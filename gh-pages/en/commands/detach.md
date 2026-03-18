---
layout: default
title: detach Command
parent: Command Reference
nav_order: 13
permalink: /commands/detach
---

# detach Command
{: .no_toc }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}


## Overview

The `detach` command is used to detach the Peeka Agent from the target process, stop all diagnostic activities, and restore the target process to its original state. This command cleans up all injected observation logic, shuts down the Agent service, deletes temporary files, and ensures the target process is not affected.

## Use Cases

- **Complete Diagnostics**: Clean exit after diagnostic work is finished
- **Avoid Resource Occupation**: Release memory and file descriptors occupied by Agent
- **Restore Original State**: Remove all function enhancements and observation logic
- **Switch Target Process**: Detach from current process to prepare for attaching to another

## Command Format

```bash
peeka-cli attach <pid>    # First attach to the target process
# ... Execute diagnostic commands ...
peeka-cli detach          # Detach when finished
```

**Note**: The `detach` command has no parameters.

## Detachment Process

The `detach` command performs the following cleanup operations:

1. **Stop All Active Observations**:
   - Stop all `watch` observations
   - Stop all `trace` tracing
   - Stop all `stack` captures
   - Stop all `monitor` monitoring
   - Stop `top` performance profiling

2. **Restore Enhanced Functions**:
   - Call `injector.uninject_all()` to remove all decorators
   - Restore functions to original state (remove `__peeka_original__` wrapper)

3. **Clean Observation Data**:
   - Clear observation buffers
   - Unregister all watch IDs

4. **Shutdown Agent Service**:
   - Close Unix Domain Socket
   - Stop Agent listening thread
   - Delete socket file (`/tmp/peeka_<pid>.sock`)

5. **Release Resources**:
   - Clean memory buffers
   - Close file descriptors
   - Stop background threads

## Basic Usage

### 1. Normal Detachment

```bash
# First attach to the target process
peeka-cli attach 12345

# Execute diagnostic commands
peeka-cli watch "mymodule.func" -n 10
peeka-cli monitor "mymodule.func" --interval 1 -c 5

# Detach when finished
peeka-cli detach
```

**Output Example**:

```json
{
  "type": "success",
  "command": "detach",
  "data": {
    "pid": 12345,
    "message": "Detached from process 12345"
  }
}
```

### 2. Detachment Failure

If an error occurs during the detachment process:

```json
{
  "type": "error",
  "command": "detach",
  "error": "Failed to restore function: mymodule.func"
}
```

**Handling**:
- If the error is non-critical (e.g., one function restoration fails), Agent will continue cleaning other resources
- If the error is critical (e.g., socket closure fails), restarting the target process is recommended

## TUI Usage

In TUI mode:

1. Start TUI:
   ```bash
   peeka  # or python -m peeka.tui
   ```

2. After connecting to the target process, press **`1`** key to return to Dashboard view

3. In Dashboard, enter command:
   ```
   detach
   ```

4. Or directly press **`q`** key to exit TUI (will automatically execute detach)

## Notes

1. **Automatic Cleanup**:
   - Peeka Agent will make best-effort attempts to cleanup on abnormal exit
   - But 100% restoration is not guaranteed; using the `detach` command for normal exit is recommended

2. **Function Restoration**:
   - In most cases, functions will be completely restored to their original state
   - In rare cases, if a function is simultaneously modified by other code, complete restoration may not be possible

3. **Observation Data Loss**:
   - After `detach`, all unconsumed observation data will be cleared
   - If data preservation is needed, ensure all data is saved before `detach`

4. **Socket File Cleanup**:
   - Socket file (`/tmp/peeka_<pid>.sock`) will be automatically deleted
   - If the process exits abnormally, manual cleanup may be required

5. **Performance Recovery**:
   - After `detach`, target process performance should immediately recover to original level
   - If performance issues persist, it may be a problem with the target process itself

6. **Re-attachment**:
   - After `detach`, you can `attach` to the same process again
   - Each `attach` creates a new socket file and Agent instance

7. **Process Termination**:
   - If the target process terminates before `detach`, Agent will automatically cleanup
   - Manual `detach` execution is not required

## Relationship with attach Command

`attach` and `detach` are paired operations:

```bash
# Lifecycle
peeka-cli attach <pid>    # Inject Agent, start service
# ... Diagnostic operations ...
peeka-cli detach          # Cleanup Agent, restore original state
```

**Resource Usage Comparison**:

| State       | Socket File | Memory Usage | Function Enhancement | Background Threads |
|-------------|-------------|--------------|----------------------|--------------------|
| Before attach | None        | 0            | None                 | 0                  |
| After attach  | Exists      | ~10MB        | Depends on commands  | 1-5                |
| After detach  | None        | 0            | None                 | 0                  |

## Troubleshooting

### 1. detach Command Not Responding

```bash
# Force terminate Agent (not recommended)
kill -9 <pid_of_agent_thread>
```

### 2. Socket File Not Cleaned

```bash
# Manually delete socket file
rm /tmp/peeka_<pid>.sock
```

### 3. Function Not Restored

If function behavior is abnormal after `detach`:

1. Check if other diagnostic tools are attached simultaneously
2. Restart the target process
3. Check if Peeka version is compatible with target Python version

### 4. Memory Not Released

If target process memory does not decrease after `detach`:

- This may be normal behavior of Python memory management
- Python interpreter does not immediately release memory to the operating system
- You can manually trigger garbage collection: `peeka-cli memory --action gc` (before detach)

## Permission Requirements

The `detach` command requires:
- Successfully `attach`ed to the target process
- Maintained connection with the target process (socket available)

**No additional permissions** are needed because cleanup operations execute within the target process.
