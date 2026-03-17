---
layout: default
title: Troubleshooting
nav_order: 9
permalink: /troubleshooting
---

# Troubleshooting
{: .no_toc }

Common issues and their solutions.
{: .fs-6 .fw-300 }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Attachment Issues

### Error: Operation not permitted

**Symptom**:
```
Error: Operation not permitted: ptrace access denied
```

**Cause**: Insufficient permissions to attach to the target process.

**Solutions**:

#### Solution 1: Use Same User

```bash
# Confirm target process owner
ps -o user= -p <pid>

# Run Peeka with the same user
peeka-cli attach <pid>
```

#### Solution 2: Use sudo

```bash
sudo peeka-cli attach <pid>
```

#### Solution 3: Adjust ptrace_scope

```bash
# Check current setting
cat /proc/sys/kernel/yama/ptrace_scope

# Temporary modification (for testing)
echo 1 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# Permanent modification
echo "kernel.yama.ptrace_scope = 1" | sudo tee /etc/sysctl.d/10-ptrace.conf
sudo sysctl -p /etc/sysctl.d/10-ptrace.conf
```

#### Solution 4: SELinux Configuration (RHEL/Fedora)

```bash
# Check SELinux status
getenforce

# Temporarily allow ptrace
sudo setsebool -P deny_ptrace off

# Or create SELinux policy
```

### Error: Process not found

**Symptom**:
```
Error: Process 12345 not found
```

**Cause**: PID doesn't exist or process has exited.

**Solution**:

```bash
# Confirm process exists
ps -p 12345

# Re-find PID
ps aux | grep "your_app"
pgrep -f "your_app.py"
```

### Error: Python debugging symbols not found (Python < 3.14)

**Symptom**:
```
Error: Python debugging symbols not found. Install python3-dbg.
```

**Cause**: Python debugging symbols not installed (required for GDB fallback).

**Solution**:

```bash
# Debian/Ubuntu
sudo apt-get update
sudo apt-get install python3-dbg

# RHEL/CentOS/Fedora
sudo yum install python3-debuginfo

# Verify installation
python3 -c "import sys; print(hasattr(sys, 'gettotalrefcount'))"
# Should output True
```

### Error: GDB not found (Python < 3.14)

**Symptom**:
```
Error: GDB not found. Please install GDB.
```

**Cause**: GDB is not installed.

**Solution**:

```bash
# Debian/Ubuntu
sudo apt-get install gdb

# RHEL/CentOS
sudo yum install gdb

# macOS
brew install gdb

# Verify version (requires 7.3+)
gdb --version
```

### Error: Timeout attaching to process

**Symptom**:
```
Error: Timeout attaching to process after 30 seconds
```

**Cause**:
1. Target process is hung or unresponsive
2. Attach timeout too short
3. High system load

**Solution**:

```bash
# Solution 1: Increase timeout
peeka-cli attach <pid> --timeout 60

# Solution 2: Check process status
ps -p <pid> -o stat=
# D: Uninterruptible sleep (possibly hung)
# R/S: Normal running

# Solution 3: Check system load
top
uptime
```

---

## Observation Issues

### No Observation Data

**Symptom**: watch command starts but no observation data is output.

**Cause**:
1. Function name spelling error
2. Function not being called
3. Condition expression too strict
4. Observation count limit reached

**Solutions**:

#### Check Function Name

```bash
# Use sc/sm to search for correct function name
peeka-cli sc "Calculator"
peeka-cli sm "add"

# Use fully qualified name
peeka-cli watch "demo.Calculator.add"  # ✅
peeka-cli watch "Calculator.add"        # ❌
```

#### Confirm Function is Called

```bash
# Check if target process is running
ps -p <pid>

# Check process logs
tail -f /var/log/your_app.log
```

#### Simplify Condition Expression

```bash
# First observe without conditions
peeka-cli watch "demo.func" --times 5

# After confirming data, add conditions
peeka-cli watch "demo.func" --condition "cost > 100" --times 5
```

#### Increase Observation Count

```bash
# Default -1 (infinite)
peeka-cli watch "demo.func"

# Or explicitly specify
peeka-cli watch "demo.func" --times 100
```

### Incomplete Observation Data

**Symptom**: Observed parameters or return values show as `<truncated>` or incomplete.

**Cause**: Output depth limit.

**Solution**:

```bash
# Increase output depth (default 2)
peeka-cli watch "demo.func" --depth 5

# Depth explanation:
# 1: Only show type
# 2: Show one layer of structure
# 5+: Show deep nesting
```

### Condition Expression Error

**Symptom**:
```
Error: Invalid condition expression: name 'invalid_var' is not defined
```

**Cause**: Condition expression uses non-existent variables or unsafe functions.

**Solutions**:

#### Available Variables

```bash
# ✅ Correct variables
params      # Parameter list
kwargs      # Keyword arguments
returnObj   # Return value
throwExp    # Exception object
cost        # Execution time (milliseconds)
target      # Target object (instance method)
```

#### Safe Functions

```bash
# ✅ Allowed functions
len(), str(), int(), float(), bool()
type(), isinstance()
min(), max(), sum()

# ❌ Disallowed functions
eval(), exec(), compile()
open(), read(), write()
__import__()
```

#### Examples

```bash
# ✅ Correct
--condition "len(params) > 2"
--condition "params[0] > 100 and cost > 50"
--condition "returnObj is not None"

# ❌ Incorrect
--condition "my_var > 100"           # my_var doesn't exist
--condition "eval('1+1')"            # eval not allowed
--condition "open('/etc/passwd')"    # open not allowed
```

---

## Performance Issues

### Target Process Slows Down

**Symptom**: After attaching Peeka, target process response slows down.

**Cause**:
1. trace command overhead too high (Python < 3.12)
2. Observation frequency too high
3. Output depth too large

**Solutions**:

#### Use Python 3.12+

Python 3.12+ trace command uses `sys.monitoring` API with overhead < 5%.

#### Limit Observation Frequency

```bash
# ✅ Limit observation count
peeka-cli watch "func" --times 10

# ✅ Use conditional filtering
peeka-cli watch "func" --condition "cost > 100"

# ❌ Infinite observation of high-frequency function
peeka-cli watch "high_frequency_func"
```

#### Reduce Output Depth

```bash
# ✅ Use default depth
peeka-cli watch "func"  # depth=2

# ❌ Excessive depth
peeka-cli watch "func" --depth 10
```

#### Stop Unnecessary Observations

```bash
# Stop watch
peeka-cli reset "func"

# Or detach from process
peeka-cli detach <pid>
```

### Peeka Client Slow Response

**Symptom**: Peeka commands execute slowly, data transmission has high latency.

**Cause**:
1. Observation data volume too large
2. Unix Socket buffer full
3. High CPU load

**Solutions**:

```bash
# Reduce data volume
peeka-cli watch "func" --times 10 --condition "cost > 100"

# Check system resources
top
df -h

# Clean up old socket files
rm -f /tmp/peeka_*.sock
```

---

## Output Issues

### JSON Parsing Error

**Symptom**:
```
Error: Expecting value: line 1 column 1 (char 0)
```

**Cause**: Output contains non-JSON content (such as print statements).

**Solutions**:

```bash
# Extract only JSON lines
peeka-cli watch "func" | grep '^{' | jq

# Or use Python filter
peeka-cli watch "func" | python -c '
import sys, json
for line in sys.stdin:
    try:
        msg = json.loads(line)
        print(json.dumps(msg))
    except:
        pass
'
```

### Garbled Output

**Symptom**: Output contains garbled characters.

**Cause**: Encoding issue.

**Solutions**:

```bash
# Set correct locale
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# Or use Python processing
peeka-cli watch "func" | python -c '
import sys
for line in sys.stdin:
    print(line, end="")
' 2>&1 | tee output.log
```

---

## Docker Issues

### Unable to Attach in Docker Container

**Symptom**:
```
Error: Operation not permitted (Docker)
```

**Cause**: Container lacks SYS_PTRACE capability.

**Solutions**:

#### docker run

```bash
docker run --cap-add=SYS_PTRACE --security-opt seccomp=unconfined your-image
```

#### docker-compose.yml

```yaml
services:
  app:
    image: your-image
    cap_add:
      - SYS_PTRACE
    security_opt:
      - seccomp=unconfined
```

#### Kubernetes

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: app
    securityContext:
      capabilities:
        add: ["SYS_PTRACE"]
```

---

## TUI Issues

### TUI Display Abnormal

**Symptom**: TUI interface display garbled or cannot render properly.

**Cause**: Terminal compatibility issue.

**Solutions**:

```bash
# Check if terminal type supports 256 color
echo $TERM

# Or use CLI mode
peeka-cli watch "func"
```


### TUI Colors Broken in Docker Container

**Symptom**: After entering a container via `docker exec`, TUI colors are missing or Header/Footer are indistinguishable from the main body.

**Cause**: `docker exec` does not inherit host terminal environment variables (`TERM`, `COLORTERM`). The container defaults to `TERM=dumb`, and Textual cannot detect truecolor support.

**Solutions**:

Peeka test images have `TERM=xterm-256color` and `COLORTERM=truecolor` baked in. TUI works out of the box via `docker exec` — no manual env setup needed.

### TUI Freezes

**Symptom**: TUI interface unresponsive.

**Cause**:
1. Data flow too fast
2. Background thread blocking

**Solutions**:

```bash
# Use Ctrl+C to exit

# Use CLI instead
peeka-cli watch "func" --times 10
```

---

## Other Issues

### Socket File Conflict

**Symptom**:
```
Error: Address already in use: /tmp/peeka_12345.sock
```

**Cause**: Previous abnormal exit didn't clean up socket file.

**Solutions**:

```bash
# Delete old socket file
rm -f /tmp/peeka_12345.sock

# Or use different socket directory
peeka-cli attach 12345 --socket-dir /tmp/my_peeka
```

### High Memory Usage

**Symptom**: Peeka or target process has high memory usage.

**Cause**: Observation data buffer too large.

**Solutions**:

```bash
# Limit observation count
peeka-cli watch "func" --times 100

# Periodically reset observations
peeka-cli reset "func"

# Or detach from process
peeka-cli detach <pid>
```

### Module Not Found

**Symptom**:
```
Error: No module named 'peeka'
```

**Cause**: Installation issue.

**Solutions**:

```bash
# Reinstall
pip uninstall peeka
pip install peeka

# Or use uv
uv pip install peeka

# Verify installation
python -c "import peeka; print(peeka.__version__)"
```

---

## Getting Help

If none of the above solutions resolve your issue:

1. **View logs**:
   ```bash
   peeka-cli --verbose attach <pid>
   ```

2. **GitHub Issues**:
   [https://github.com/wwulfric/peeka/issues](https://github.com/wwulfric/peeka/issues)

3. **Provide information**:
   - Operating system and version
   - Python version
   - Peeka version
   - Complete error message
   - Reproduction steps

4. **Community discussion**:
   - GitHub Discussions
   - Stack Overflow (tag: `peeka`)

---

## Related Documentation

- [Installation Guide]({% link installation.md %})
- [Quick Start]({% link quickstart.md %})
- [Command Reference]({% link commands/index.md %})
