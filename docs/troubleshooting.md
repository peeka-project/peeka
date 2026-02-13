# Troubleshooting

This guide helps you resolve common issues when using Peeka.

## Process Attachment Issues

### Error: Permission denied when attaching

**Symptom**: `peeka-cli attach <pid>` fails with permission error

**Cause**: Insufficient privileges to attach to target process

**Solutions**:

1. **Check if you own the process**:
```bash
ps -p <pid> -o user=
# Should match your username
```

2. **For Python 3.14+**: Requires CAP_SYS_PTRACE or same UID
```bash
# Check capabilities
getcap $(which python3)

# Or run with sudo (not recommended for production)
sudo peeka-cli attach <pid>
```

3. **For Python < 3.14**: Install debug symbols
```bash
# Debian/Ubuntu
sudo apt-get install gdb python3-dbg

# RHEL/Fedora
sudo yum install gdb python3-debuginfo

# Arch Linux
sudo pacman -S gdb python-debug
```

4. **Check ptrace_scope** (Linux):
```bash
# Check current setting
cat /proc/sys/kernel/yama/ptrace_scope

# 0 = no restrictions
# 1 = restricted to child processes
# 2 = admin only
# 3 = no ptrace allowed

# Temporarily allow ptrace (testing only)
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

5. **SELinux systems** (Fedora/RHEL):
```bash
# Check if SELinux is blocking
sudo ausearch -m avc -ts recent | grep ptrace

# Temporarily allow (testing only)
sudo setsebool -P deny_ptrace=off
```

### Error: GDB not found

**Symptom**: `gdb: command not found` (Python < 3.14)

**Solution**: Install GDB
```bash
# Debian/Ubuntu
sudo apt-get install gdb

# RHEL/Fedora
sudo yum install gdb

# macOS
brew install gdb
```

### Error: Target process crashed after attachment

**Cause**: Incompatible Python version or corrupted state

**Solutions**:
1. Verify Python version compatibility (3.9-3.14+)
2. Check if process is in healthy state before attaching
3. Try attaching to a fresh process instance

## Observation Issues

### No observation data received

**Symptom**: `watch` command runs but no observations appear

**Possible causes and solutions**:

1. **Incorrect function pattern**:
```bash
# Wrong: Missing module or incorrect name
peeka-cli watch "Calculator.add"

# Correct: Use fully qualified name
peeka-cli watch "demo.Calculator.add"

# Verify pattern with search commands
peeka-cli sc "Calculator"
peeka-cli sm "add"
```

2. **Function not being called**:
```bash
# Verify the function is actually being invoked
# Check application logs or add temporary logging
```

3. **Condition too strict**:
```bash
# If using conditions, try without first
peeka-cli watch "module.func"  # Without condition

# Then add condition gradually
peeka-cli watch "module.func" --condition "len(params) > 0"
```

4. **Times limit reached**:
```bash
# Check if observation already stopped
# Try without times limit
peeka-cli watch "module.func"  # Unlimited observations
```

### Observation data incomplete

**Symptom**: Missing fields or truncated output

**Causes and solutions**:

1. **Depth limit too low**:
```bash
# Increase output depth
peeka-cli watch "module.func" --depth 5
```

2. **Large objects truncated**:
```bash
# Expected behavior for performance
# Objects are automatically truncated to prevent memory issues
# Use --depth to control nested object display
```

## Performance Issues

### High CPU usage

**Symptom**: Target process CPU usage increases significantly

**Causes and solutions**:

1. **Too many observations**:
```bash
# Limit observation count
peeka-cli watch "module.func" --times 100

# Add condition to reduce observation frequency
peeka-cli watch "module.func" --condition "params[0] > 100"
```

2. **Deep output depth**:
```bash
# Reduce depth
peeka-cli watch "module.func" --depth 1
```

3. **High-frequency function**:
```bash
# Use monitor instead for statistics
peeka-cli monitor "module.func" --interval 5
```

### Target process becomes slow

**Symptom**: Application response time increases

**Solutions**:
```bash
# 1. Stop active observations
peeka-cli watch --action stop <watch_id>

# 2. Reset all instrumentation
peeka-cli reset --pattern "*"

# 3. If issues persist, detach completely
peeka-cli detach

# 4. Restart target process if necessary
```

## Connection Issues

### Error: Socket connection failed

**Symptom**: Cannot connect to agent socket

**Causes and solutions**:

1. **Agent not started**:
```bash
# First attach to process
peeka-cli attach <pid>

# Then run other commands
peeka-cli watch "module.func"
```

2. **Socket file removed**:
```bash
# Check socket directory
ls -la $PEEKA_SOCKET_DIR/peeka_*.sock

# Try reattaching
peeka-cli attach <pid>
```

3. **Permission issue on socket**:
```bash
# Check socket permissions
ls -la /tmp/peeka_*.sock

# Should be owned by your user
```

### Error: Connection timeout

**Symptom**: Commands hang or timeout

**Solutions**:
```bash
# Increase timeout
export PEEKA_TIMEOUT=60

# Check if target process is responsive
ps -p <pid>

# Check system load
uptime
```

## Expression Evaluation Issues

### Error: Invalid condition expression

**Symptom**: Condition parsing fails

**Causes and solutions**:

1. **Syntax error**:
```bash
# Wrong: Using disallowed operations
peeka-cli watch "module.func" --condition "import os"

# Correct: Use allowed operations
peeka-cli watch "module.func" --condition "params[0] > 10"
```

2. **Unsupported features**:
```bash
# Not allowed: eval, exec, __import__
# Allowed: comparison, arithmetic, logical operations, len(), str()

# See simpleeval documentation for allowed operations
```

3. **Variable names**:
```bash
# Available variables in conditions:
# - params: function arguments (tuple)
# - kwargs: keyword arguments (dict)
# - target: self object (for methods)
# - cost: execution duration (only after execution)

# Examples:
peeka-cli watch "module.func" --condition "len(params) > 2"
peeka-cli watch "module.func" --condition "kwargs.get('debug') == True"
peeka-cli watch "module.func" --condition "cost > 100"
```

## Docker/Container Issues

### Error: Operation not permitted in container

**Symptom**: Cannot attach to process in Docker container

**Solution**: Add SYS_PTRACE capability
```bash
# Run container with capability
docker run --cap-add=SYS_PTRACE your-image

# Or in docker-compose.yml
services:
  app:
    cap_add:
      - SYS_PTRACE
```

### GDB not available in container

**Solution**: Install GDB in container image
```dockerfile
# Debian/Ubuntu based images
RUN apt-get update && apt-get install -y gdb python3-dbg

# Alpine based images
RUN apk add --no-cache gdb python3-dev
```

## Getting Help

If you encounter issues not covered here:

1. **Check verbose output**:
```bash
# Enable debug logging (if available)
PEEKA_DEBUG=1 peeka-cli attach <pid>
```

2. **Review logs**:
```bash
# Check application logs
# Check system logs: /var/log/syslog or journalctl
```

3. **Report an issue**:
- GitHub: https://github.com/wwulfric/peeka/issues
- Include: Peeka version, Python version, OS, error messages
- Provide: Minimal reproduction steps

4. **Community support**:
- Check existing issues and discussions
- Search documentation for keywords
