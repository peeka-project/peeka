---
layout: default
title: attach
parent: Command Reference
nav_order: 1
permalink: /commands/attach
---

# attach - Attach to Target Process
{: .no_toc }

Inject Peeka Agent into a target Python process and establish a diagnostic channel.
{: .fs-6 .fw-300 }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Overview

The `attach` command is the first step in using Peeka. It injects Peeka Agent code into the target process and starts a Unix Domain Socket server, establishing a communication channel for subsequent diagnostic commands.

### How It Works

**Python 3.14+**:
- Uses PEP 768's `sys.remote_exec()` API
- Secure, efficient, officially supported

**Python 3.9-3.13**:
- Uses GDB + ptrace mechanism
- Compatibility fallback solution

---

## TUI Usage

**TUI Auto-Attach on Launch**: Running `peeka` command directly launches TUI and automatically shows process selector:

1. Run `peeka` (no arguments)
2. In process selector, choose target process
3. Press Enter to auto-attach and enter main interface

**TUI Features**:
- Real-time process list refresh
- Display process PID, command line, CPU/memory usage
- Support search/filter (type keywords to filter)
- Auto-validate permissions (show PEP 768 or GDB availability)

**CLI Equivalent Commands**: All examples below use CLI commands for demonstration. TUI provides the same functionality with a graphical interface.

## Syntax

```bash
peeka-cli attach <pid> [options]
```

### Parameters

| Parameter | Type | Required | Description |
|------|------|------|------|
| `pid` | int | ✅ | PID of the target process |

### Options

| Option | Description | Default |
|------|------|--------|
| `--timeout` | Attachment timeout (seconds) | 30 |
| `--socket-dir` | Socket file directory | `/tmp` |

---

## Usage Examples

### Basic Attachment

```bash
# Attach to process 12345
peeka-cli attach 12345
```

Output:
```json
{"type":"status","level":"info","message":"Attaching to process 12345"}
{"type":"status","level":"info","message":"Using PEP 768 remote_exec"}
{"type":"success","command":"attach","data":{"pid":12345,"socket":"/tmp/peeka_12345.sock"}}
```

### Finding Process PID

```bash
# Using ps
ps aux | grep python

# Using pgrep
pgrep -f "my_app.py"

# Using pidof
pidof python3
```

### Attach and Execute Command Immediately

```bash
# Attach then immediately observe
peeka-cli attach 12345 && peeka-cli watch "app.func"
```

---

## Permission Requirements

### Linux Systems

#### Same User

The simplest approach is to run Peeka as the same user:

```bash
# Both target process and Peeka run as user1
user1$ python my_app.py  # PID: 12345
user1$ peeka-cli attach 12345  # ✅ Success
```

#### Different Users (Requires sudo)

```bash
# Target process runs as user1, need sudo
user1$ python my_app.py  # PID: 12345
user2$ sudo peeka-cli attach 12345  # ✅ Success
```

#### ptrace_scope Configuration

Check current configuration:
```bash
cat /proc/sys/kernel/yama/ptrace_scope
```

| Value | Description | Peeka Availability |
|----|------|-------------|
| 0 | No restrictions (not recommended) | ✅ All users can attach |
| 1 | Only parent-child processes or CAP_SYS_PTRACE | ✅ Recommended setting |
| 2 | Only CAP_SYS_PTRACE | ✅ Requires sudo |
| 3 | Completely disabled | ❌ Cannot use |

Temporary modification (for testing):
```bash
echo 1 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

Permanent modification:
```bash
echo "kernel.yama.ptrace_scope = 1" | sudo tee /etc/sysctl.d/10-ptrace.conf
sudo sysctl -p /etc/sysctl.d/10-ptrace.conf
```

### Docker Containers

Need to add `SYS_PTRACE` capability:

```bash
# Add when running container
docker run --cap-add=SYS_PTRACE your-image

# docker-compose.yml
services:
  app:
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
```

### SELinux Systems

Check SELinux status:
```bash
getenforce  # Enforcing, Permissive, Disabled
```

Temporarily allow ptrace:
```bash
sudo setsebool -P deny_ptrace off
```

---

## Output Format

### Success Response

```json
{
  "type": "success",
  "command": "attach",
  "data": {
    "pid": 12345,
    "socket": "/tmp/peeka_12345.sock",
    "python_version": "3.12.0",
    "attach_method": "remote_exec"
  }
}
```

### Error Response

```json
{
  "type": "error",
  "command": "attach",
  "error": "Operation not permitted: ptrace access denied"
}
```

---

## Troubleshooting

### Error: Operation not permitted

**Cause**: Insufficient permissions

**Solutions**:
1. Use same user or sudo
2. Check ptrace_scope setting
3. Check SELinux configuration

```bash
# Check process owner
ps -o user= -p 12345

# Use sudo
sudo peeka-cli attach 12345

# Relax ptrace restrictions (for testing)
echo 1 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

### Error: Process not found

**Cause**: PID doesn't exist or has exited

**Solutions**:
```bash
# Confirm process exists
ps -p 12345

# Re-find PID
pgrep -f "my_app.py"
```

### Error: Python debugging symbols not found (Python < 3.14)

**Cause**: Missing Python debugging symbols

**Solutions**:
```bash
# Debian/Ubuntu
sudo apt-get install python3-dbg

# RHEL/CentOS
sudo yum install python3-debuginfo
```

### Error: GDB not found (Python < 3.14)

**Cause**: GDB not installed

**Solutions**:
```bash
# Debian/Ubuntu
sudo apt-get install gdb

# RHEL/CentOS
sudo yum install gdb
```

### Error: Timeout attaching to process

**Cause**: Attachment timeout (target process may be hung)

**Solutions**:
```bash
# Increase timeout
peeka-cli attach 12345 --timeout 60

# Check target process status
ps -p 12345 -o stat=
```

---

## Security Considerations

### Process Isolation

- Peeka can only attach to local processes
- Remote attachment not supported
- Unix Domain Socket limited to local access only

### Principle of Least Privilege

- Production environments should use same user
- Avoid using root privileges
- Detach promptly when diagnostics are no longer needed

### Code Injection Security

- Agent code only performs diagnostic functions
- Does not modify business logic
- All injections can be reverted via reset command

---

## Related Commands

- [detach]({% link commands/detach.md %}) - Detach from process
- [watch]({% link commands/watch.md %}) - Observe function calls
- [reset]({% link commands/reset.md %}) - Reset enhancements

---

## References

- [PEP 768 - Safe External Debugger](https://peps.python.org/pep-0768/)
- [Linux ptrace(2) Manual](https://man7.org/linux/man-pages/man2/ptrace.2.html)
- [Yama LSM Documentation](https://www.kernel.org/doc/html/latest/admin-guide/LSM/Yama.html)
