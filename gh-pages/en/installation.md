---
layout: default
title: Installation Guide
nav_order: 2
permalink: /installation
---

# Installation Guide
{: .no_toc }

This guide will help you install and configure Peeka in different environments.
{: .fs-6 .fw-300 }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## System Requirements

### Basic Requirements

- **Python Version**: Python 3.9 or higher
- **Operating System**: Linux (recommended), macOS
- **Permissions**: Permission to attach to target processes (same UID or CAP_SYS_PTRACE)

### Python Version Comparison

| Python Version | Attach Mechanism | Additional Requirements |
|------------|---------|---------|
| **3.14+** | PEP 768 `sys.remote_exec` | None |
| **3.9-3.13** | GDB + ptrace fallback | GDB, python3-dbg, CAP_SYS_PTRACE |

---

## Installation Methods

### Install with pip (Recommended)

#### Basic Version (CLI Only)

```bash
pip install peeka
```

#### Full Version (with TUI)

```bash
pip install peeka[tui]
```
### Install with uv

```bash
# Basic version
uv pip install peeka

# Full version (with TUI)
uv pip install "peeka[tui]"

# Development environment (from source)
uv sync --dev
```

### Install from Source

```bash
# Clone the repository
git clone https://github.com/wwulfric/peeka.git
cd peeka

# Install (basic version)
uv pip install -e .

# Install (with TUI)
uv pip install -e ".[tui]"

# Development environment (full dependencies)
uv sync --dev
```

---

## Additional Configuration for Python < 3.14

For Python 3.9-3.13, you need to install GDB and Python debugging symbols.

### Debian/Ubuntu

```bash
sudo apt-get update
sudo apt-get install gdb python3-dbg
```

### RHEL/CentOS/Fedora

```bash
sudo yum install gdb python3-debuginfo
```

### macOS

```bash
brew install gdb

# First-time use requires GDB authorization
# See: https://sourceware.org/gdb/wiki/PermissionsDarwin
```

---

## Permission Configuration

### Linux Systems

#### Temporarily Relax ptrace Restrictions (Testing Only)

```bash
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

#### Permanent Configuration (Recommended for Production)

Edit `/etc/sysctl.d/10-ptrace.conf`:

```
kernel.yama.ptrace_scope = 1
```

Then apply the configuration:

```bash
sudo sysctl -p /etc/sysctl.d/10-ptrace.conf
```

#### SELinux Systems (Fedora/RHEL)

```bash
# Check SELinux status
getenforce

# Temporarily allow ptrace
sudo setsebool -P deny_ptrace off

# Or create SELinux policy for specific processes
```

### Docker Containers

Add `--cap-add=SYS_PTRACE` parameter when running Docker containers:

```bash
docker run --cap-add=SYS_PTRACE your-image
```

Or configure in docker-compose.yml:

```yaml
services:
  app:
    image: your-image
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
```

---

## Verify Installation

### Check Version

```bash
peeka-cli --version
```

### Run Tests

```bash
# Start demo application
python -m peeka.examples.demo --mode loop

# Test attachment in another terminal
peeka-cli attach <pid>
```

### Check Dependencies

```bash
# Check Python version
python --version

# Check GDB (Python < 3.14)
gdb --version

# Check Python debugging symbols (Python < 3.14)
python -c "import sys; print(hasattr(sys, 'gettotalrefcount'))"
```

---

## Common Issues

### Attachment Failed: Insufficient Permissions

**Error Message**:
```
Error: Operation not permitted
```

**Solution**:
1. Ensure you have the same UID as the target process, or use sudo
2. Check ptrace_scope settings
3. For Docker, ensure CAP_SYS_PTRACE is added

### Python < 3.14: Debugging Symbols Not Found

**Error Message**:
```
Error: Python debugging symbols not found
```

**Solution**:
```bash
# Debian/Ubuntu
sudo apt-get install python3-dbg

# RHEL/CentOS
sudo yum install python3-debuginfo
```

### GDB Version Too Old

**Error Message**:
```
Error: GDB version 7.3+ required
```

**Solution**:
```bash
# Update GDB
sudo apt-get update
sudo apt-get install --only-upgrade gdb

# Or compile the latest version from source
```

### macOS: GDB Requires Authorization

**Error Message**:
```
Error: Unable to find Mach task port for process-id
```

**Solution**:
Refer to [GDB on macOS](https://sourceware.org/gdb/wiki/PermissionsDarwin) for code signing authorization.

---

## Next Steps

After installation, you can:

- [Quick Start]({% link quickstart.md %}) - Learn basic usage
- [Command Reference]({% link commands/index.md %}) - View all available commands
- [Examples]({% link examples.md %}) - Real-world application scenarios

---

## Getting Help

If you encounter problems during installation:

1. Check [Troubleshooting]({% link troubleshooting.md %})
2. Ask questions on [GitHub Issues](https://github.com/wwulfric/peeka/issues)
