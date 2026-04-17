# Troubleshooting Guide

This guide helps diagnose and fix common issues with Peeka.

## PEP 768 Attach Failures (Python 3.14+)

### Symptoms

When attaching to a Python 3.14+ process, you see errors like:

```
ERROR: Attach failed: PyRuntime address lookup failed during debug offsets initialization
```

or

```
RuntimeError: Can't determine the Python version of the remote process
```

### Known Affected Tools

This is NOT a Peeka-specific issue. Other tools using PEP 768 also experience this:
- **memray** - Memory profiler
- Any tool using `sys.remote_exec()`

### Root Cause

This indicates your Python 3.14 binary has one of these issues:

1. **Missing `.pyruntime` ELF section** - Python was compiled without proper PEP 768 support
2. **Stripped binary** - Debug symbols/sections were removed during installation
3. **Incompatible build flags** - Python was compiled with flags that affect memory layout
4. **ASLR interference** - Address Space Layout Randomization may affect PyRuntime address lookup

This is most commonly seen with:
- **UV-managed Python installations**
- **Custom-compiled Python builds**
- **Pre-release Python 3.14** versions (PEP 768 is still stabilizing)

### Diagnostic Steps

#### 1. Run the Diagnostic Script

```bash
python diagnose_attach.py <target_pid>
```

This will check:
- Python version compatibility
- Whether `.pyruntime` section exists in the binary
- ASLR status
- Permissions and ptrace_scope
- Process state

#### 2. Check for `.pyruntime` Section Manually

```bash
readelf -S $(which python3) | grep pyruntime
```

If this returns nothing, your Python binary is missing the required section for PEP 768.

#### 3. Verify Python Installation

```bash
python3 --version
python3 -c "import sys; print(hasattr(sys, 'remote_exec'))"
```

The second command should print `True` for Python 3.14+.

### Solutions

#### Solution 1: Use GDB Fallback (Recommended)

Use Python 3.8-3.13 to run Peeka, which will automatically use the GDB fallback method:

```bash
# Install an older Python version
# On Ubuntu/Debian:
sudo apt install python3.12 python3.12-venv

# Create a venv with Python 3.12
python3.12 -m venv .venv-peeka
source .venv-peeka/bin/activate
pip install peeka[tui]

# Run Peeka
peeka
```

#### Solution 2: Use System Python 3.14 (Not UV)

If your system Python 3.14 works but UV's doesn't:

```bash
# Install Peeka with system Python
/usr/bin/python3.14 -m pip install --user peeka[tui]

# Run with system Python
/usr/bin/python3.14 -m peeka.tui
```

#### Solution 3: Report the Issue

Since this affects multiple tools, consider reporting:

1. **To UV** (if using UV-managed Python):
   - Check: https://github.com/astral-sh/uv/issues
   - Report Python 3.14 PEP 768 compatibility issue

2. **To CPython** (if using pre-release Python 3.14):
   - Check: https://github.com/python/cpython/issues
   - Report PEP 768 implementation issues

Include in your report:
- Python version: `python --version`
- Installation method: UV / compiled from source / package manager
- Output of: `readelf -S $(which python3) | grep -E "(pyruntime|debug)"`
- Which tools fail: Peeka, memray, etc.

### GDB Fallback Requirements

If using the GDB fallback method (Python < 3.14), ensure you have:

```bash
# Ubuntu/Debian
sudo apt install gdb python3-dbg

# RHEL/Fedora
sudo yum install gdb python3-debuginfo

# Arch
sudo pacman -S gdb
```

And check ptrace permissions:

```bash
cat /proc/sys/kernel/yama/ptrace_scope
# Should be 0 or 1. If 2+, run:
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

---

## Permission Errors

### Symptoms

```
PermissionError: No permission to access process <pid>
```

### Solutions

1. **Run as same user**:
   ```bash
   ps aux | grep <pid>  # Check process owner
   # Run Peeka as that user
   ```

2. **Check ptrace_scope** (Linux):
   ```bash
   cat /proc/sys/kernel/yama/ptrace_scope
   ```
   - `0` = No restrictions (best for development)
   - `1` = Restricted (can only attach to child processes)
   - `2` = Admin-only
   - `3` = Disabled

   To enable:
   ```bash
   echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
   ```

3. **Use CAP_SYS_PTRACE** (production):
   ```bash
   sudo setcap cap_sys_ptrace=eip $(which python3)
   ```

---

## Process Already Attached

### Symptoms

```
RuntimeError: Already attached to process <pid>. Please detach first
```

### Solution

```bash
peeka-cli detach
```

If the detach command doesn't work (agent crashed), manually clean up:

```bash
rm -f /tmp/peeka_*.sock /tmp/peeka_*.pid /tmp/peeka_*.ready
```

---

## Agent Timeout

### Symptoms

```
TimeoutError: Agent initialization timeout
```

### Common Causes

1. **Process is busy** - Target process is CPU-bound or holding the GIL
2. **Import lock contention** - Agent imports 13+ modules on startup
3. **Slow I/O** - `/tmp` filesystem is slow

### Solutions

1. **Increase timeout** - Modify `READY_TIMEOUT_PEP768` / `READY_TIMEOUT_GDB` in `peeka/core/attach.py`

2. **Check process state**:
   ```bash
   top -p <pid>  # Is it using 100% CPU?
   ```

3. **Check /tmp filesystem**:
   ```bash
   df -h /tmp
   ```

---

## Import Errors

### Symptoms

```
ImportError: No module named 'textual'
```

### Solution

Install TUI dependencies:

```bash
pip install peeka[tui]
```

Or just CLI:

```bash
pip install peeka
```

---

## Getting Help

If your issue isn't covered here:

1. Run the diagnostic script: `python diagnose_attach.py <pid>`
2. Check existing issues: https://github.com/wwulfric/peeka/issues
3. Open a new issue with:
   - Error message (full traceback)
   - Python version
   - Operating system
   - Installation method (pip, UV, source)
   - Output of diagnostic script
