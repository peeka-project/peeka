# Peeka

[中文文档](README_ZH.md)

A runtime diagnostic tool for Python 3.9-3.14+ based on PEP 768 remote debugging protocol, providing non-invasive function observation capabilities similar to Java Arthas.

## Features

- **Non-invasive**: Observe function calls without modifying target code
- **Real-time**: Millisecond-level data transmission with streaming support
- **Production-ready**: <5% performance overhead with comprehensive error handling
- **Secure**: Safe expression evaluation using simpleeval (AST whitelist, prevents code injection)
- **Flexible filtering**: Filter observations by parameters, return values, execution time, etc.

## Quick Start

### Installation

```bash
pip install peeka
```

### Basic Usage

1. **Attach to target process**

```bash
peeka-cli attach <pid>
```

2. **Watch function calls**

```bash
# Watch 5 function calls
peeka-cli watch "module.Class.method" --times 5

# With condition filtering
peeka-cli watch "module.Class.method" --condition "len(params) > 2"

# Stream observations in real-time
peeka-cli watch "module.Class.method"
```

3. **Process output data**

```bash
# Extract results with jq
peeka-cli watch "module.func" | jq 'select(.type == "observation") | .data.result'

# Filter slow calls
peeka-cli watch "module.func" | jq 'select(.type == "observation" and .data.duration_ms > 1)'

# Save to file
peeka-cli watch "module.func" > observations.jsonl
```

## Output Format

Peeka outputs **JSONL format** (one JSON object per line). Each message includes a `type` field for identification.

### Message Types

| Type | Description | Example Command |
|------|-------------|----------------|
| `status` | Status/progress information | attach |
| `success` | Command completed successfully | attach, detach |
| `error` | Command failed with error details | all commands |
| `event` | Control events (started, stopped, etc.) | watch, stack, monitor |
| `observation` | Real-time observation data | watch, stack, monitor |
| `result` | Query results (non-streaming) | logger, memory, sc, sm |

### Example Output

**observation - Function call data**:
```json
{
  "type": "observation",
  "watch_id": "watch_001",
  "timestamp": 1705586200.123,
  "func_name": "demo.Calculator.add",
  "args": [1, 2],
  "kwargs": {},
  "result": 3,
  "success": true,
  "duration_ms": 0.123,
  "count": 1
}
```

## Commands

| Command | Description | Documentation |
|---------|-------------|---------------|
| `attach` | Attach to target process | [📖 Documentation](https://wwulfric.github.io/peeka/en/commands/attach.html) |
| `watch` | Observe function calls (args, return, duration) | [📖 Documentation](https://wwulfric.github.io/peeka/en/commands/watch.html) |
| `trace` | Trace function call chains with timing | [📖 Documentation](https://wwulfric.github.io/peeka/en/commands/trace.html) |
| `stack` | Capture function call stacks | [📖 Documentation](https://wwulfric.github.io/peeka/en/commands/stack.html) |
| `reset` | Reset instrumentation to restore original functions | [📖 Documentation](https://wwulfric.github.io/peeka/en/commands/reset.html) |
| `logger` | Dynamically adjust log levels | [📖 Documentation](https://wwulfric.github.io/peeka/en/commands/logger.html) |
| `monitor` | Performance monitoring and statistics | [📖 Documentation](https://wwulfric.github.io/peeka/en/commands/monitor.html) |
| `memory` | Memory analysis | [📖 Documentation](https://wwulfric.github.io/peeka/en/commands/memory.html) |
| `inspect` | Runtime object inspection | [📖 Documentation](https://wwulfric.github.io/peeka/en/commands/inspect.html) |
| `sc` | Search for classes | [📖 Documentation](https://wwulfric.github.io/peeka/en/commands/search.html) |
| `sm` | Search for methods | [📖 Documentation](https://wwulfric.github.io/peeka/en/commands/search.html) |

For detailed command usage, see [Command Reference](https://wwulfric.github.io/peeka/en/commands/).

## Technical Foundation

### Python 3.14 Remote Debugging (PEP 768)

Uses `sys.remote_exec(pid, script_path)` for safe code injection into target processes.

**For Python < 3.14**: Falls back to GDB + ptrace mechanism:
- Requires GDB 7.3+, Python debug symbols (python3-dbg or python3-debuginfo)
- Requires CAP_SYS_PTRACE or same UID
- ptrace_scope must be <= 1

### Communication

- **Unix Domain Socket**: Efficient local IPC with high security
- **Message Format**: Length-prefixed JSON for structured, extensible communication

### Security

- **Safe Expression Evaluation**: Uses simpleeval with AST whitelist
- **Blocks code injection**: Prevents `__import__`, `eval`, `exec`, etc.
- **Resource limits**: Fixed buffer size, connection timeouts

## Python Version Support

| Version  | Attach Mechanism          | Requirements                     |
|----------|---------------------------|----------------------------------|
| 3.14+    | PEP 768 `sys.remote_exec` | None                             |
| 3.9-3.13 | GDB + ptrace fallback     | GDB, python3-dbg, CAP_SYS_PTRACE |

## Security Considerations

### Process Attachment Permissions

**Python 3.14+**:
- Uses PEP 768 `sys.remote_exec()`
- Requires same UID or CAP_SYS_PTRACE

**Python < 3.14**:
- Uses GDB + ptrace fallback
- Requires GDB and Python debug symbols
- Requires same UID or CAP_SYS_PTRACE
- ptrace_scope must be <= 1

**Docker containers**:
```bash
docker run --cap-add=SYS_PTRACE your-image
```

**Temporarily relax ptrace restrictions** (for testing):
```bash
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

## Comparison with Arthas

Peeka is inspired by [Alibaba Arthas](https://github.com/alibaba/arthas) and brings similar diagnostic capabilities to the Python ecosystem.

### Implemented Features

| Feature | Peeka | Arthas |
|---------|-------|--------|
| **watch command** | ✅ | ✅ |
| Observation points | `-b/-e/-s/-f` | `-b/-e/-s/-f` |
| Condition filtering | `--condition-express` | `--condition-express` |
| Duration filtering | `cost > 100` | `#cost>100` |
| **trace command** | ✅ | ✅ |
| Call tree visualization | ✅ | ✅ |
| **stack command** | ✅ | ✅ |
| **monitor command** | ✅ | ✅ |
| **logger command** | ✅ | ✅ |
| **sc/sm commands** | ✅ | ✅ |

### Python-Specific Advantages

- **Native JSON output**: All commands output JSONL format for easy integration
- **simpleeval security**: AST whitelist prevents code injection
- **Python 3.12+ optimization**: Uses `sys.monitoring` API for <5% overhead
- **Lightweight deployment**: No Java runtime required, pip install only

For detailed comparison, see [docs/comparison.md](docs/comparison.md).

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PEEKA_SOCKET_DIR` | Socket file directory | `/tmp` |
| `PEEKA_TIMEOUT` | Command timeout (seconds) | `30` |
| `PEEKA_BUFFER_SIZE` | Observation data buffer size | `10000` |

## Troubleshooting

### Attachment fails (permission denied)

```bash
# For Python < 3.14, install debug symbols
# Debian/Ubuntu
sudo apt-get install gdb python3-dbg

# RHEL/Fedora
sudo yum install gdb python3-debuginfo

# Temporarily relax ptrace restrictions
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# For SELinux systems (Fedora/RHEL)
sudo setsebool -P deny_ptrace=off
```

### No observation data

- Check if function name is correct (use fully qualified name)
- Verify function is being called
- Check if condition expression is too strict

### Target process behaves abnormally

```bash
# Stop observation
peeka-cli watch --action stop <watch_id>

# If issues persist, restart target process
```

For more troubleshooting tips, see [docs/troubleshooting.md](docs/troubleshooting.md).

## Documentation

- [📚 Full Documentation](https://wwulfric.github.io/peeka/en/) - Complete documentation site
- [Architecture](docs/ARCHITECTURE.md) - System architecture and design
- [Examples](docs/examples.md) - Practical usage examples
- [Comparison with Arthas](docs/comparison.md) - Feature comparison
- [Troubleshooting](docs/troubleshooting.md) - Common issues and solutions
- [Development](AGENTS.md) - Developer guide for contributors

## License

MIT License

## Acknowledgments

- Inspired by: [Alibaba Arthas](https://github.com/alibaba/arthas)
- Safe evaluation: [simpleeval](https://github.com/danthedeckie/simpleeval)
- Remote debugging protocol: [PEP 768](https://peps.python.org/pep-0768/)
