---
layout: default
title: Comparison with Arthas
nav_order: 7
permalink: /comparison
---

# Comparison with Arthas
{: .no_toc }

Peeka's design is deeply inspired by [Alibaba Arthas](https://github.com/alibaba/arthas), bringing similar diagnostic capabilities to the Python ecosystem.
{: .fs-6 .fw-300 }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Design Philosophy Comparison

| Dimension | Peeka | Arthas |
|------|-------|--------|
| **Target Language** | Python | Java |
| **Attach Mechanism** | PEP 768 / GDB + ptrace | Java Attach API |
| **Communication Protocol** | Unix Domain Socket | Netty + HTTP |
| **Command Interface** | CLI + TUI | CLI + Web UI |
| **Output Format** | JSONL | Text + JSON |
| **Security Mechanism** | simpleeval | OGNL + sandbox |

---

## Feature Comparison

### ✅ Implemented Arthas Features

| Feature | Peeka | Arthas | Description |
|------|-------|--------|------|
| **watch command** | ✅ | ✅ | Observe function calls, parameters, return values |
| Observation point control | `-b/-e/-s/-f` | `-b/-e/-s/-f` | AtEnter/AtExit/AtExceptionExit |
| Conditional filtering | `--condition` | `--condition` | Support expression filtering |
| Cost filtering | `cost > 100` | `#cost>100` | Based on execution time filtering |
| Output fields | `params/returnObj/throwExp/cost` | Same | Arthas-compatible field names |
| **trace command** | ✅ | ✅ | Trace function call chain and timing |
| Call tree display | ✅ Tree structure | ✅ Tree structure | Visualize call relationships |
| Depth limit | `-d, --depth` | `-n` | Control trace depth |
| Skip built-ins | `--skip-builtin` | `--skipJDKMethod` | Reduce output noise |
| Min duration | `--min-duration` | - | Filter low-cost calls |
| **stack command** | ✅ | ✅ | Capture function call stack |
| Conditional filtering | ✅ | ✅ | Support conditional expressions |
| **monitor command** | ✅ | ✅ | Performance statistics monitoring |
| Periodic statistics | ✅ | ✅ | Periodically output statistics |
| **logger command** | ✅ | ✅ | Dynamically adjust log levels |
| View loggers | ✅ | ✅ | List all loggers |
| Modify level | ✅ | ✅ | Modify log level at runtime |
| **sc/sm commands** | ✅ | ✅ | Search classes and methods |
| Pattern matching | ✅ | ✅ | Support wildcard search |
| **memory command** | ✅ | ✅ | Memory analysis |
| Memory overview | ✅ | ✅ | Show memory usage |
| **inspect command** | ✅ | ✅ (ognl) | Runtime object inspection |

### ✅ Fully Implemented Features

| Feature | Peeka | Arthas | Description |
|------|-------|--------|------|
| **attach command** | ✅ | ✅ | Attach to target process |
| **watch command** | ✅ | ✅ | Observe function calls, parameters, return values |
| Observation point control | `-b/-e/-s/-f` | `-b/-e/-s/-f` | AtEnter/AtExit/AtExceptionExit |
| Conditional filtering | `--condition` | `--condition` | Support expression filtering |
| Cost filtering | `cost > 100` | `#cost>100` | Based on execution time filtering |
| Output fields | `params/returnObj/throwExp/cost` | Same | Arthas-compatible field names |
| **trace command** | ✅ | ✅ | Trace function call chain and timing |
| Call tree display | ✅ Tree structure | ✅ Tree structure | Visualize call relationships |
| Depth limit | `-d, --depth` | `-n` | Control trace depth |
| Skip built-ins | `--skip-builtin` | `--skipJDKMethod` | Reduce output noise |
| Min duration | `--min-duration` | - | Filter low-cost calls |
| **stack command** | ✅ | ✅ | Capture function call stack |
| Conditional filtering | ✅ | ✅ | Support conditional expressions |
| **monitor command** | ✅ | ✅ | Performance statistics monitoring |
| Periodic statistics | ✅ | ✅ | Periodically output statistics |
| **logger command** | ✅ | ✅ | Dynamically adjust log levels |
| View loggers | ✅ | ✅ | List all loggers |
| Modify level | ✅ | ✅ | Modify log level at runtime |
| **sc/sm commands** | ✅ | ✅ | Search classes and methods |
| Pattern matching | ✅ | ✅ | Support wildcard search |
| **memory command** | ✅ | ✅ | Memory analysis |
| Memory overview | ✅ | ✅ | Show memory usage |
| **inspect command** | ✅ | ✅ (ognl) | Runtime object inspection |
| **reset command** | ✅ | ✅ (stop) | Reset enhancement, restore original function |
| **thread command** | ✅ | ✅ (jstack) | Thread analysis and thread stack |
| **top command** | ✅ | ✅ (profiler) | Function-level performance sampling |
| **detach command** | ✅ | ✅ (quit/exit) | Safely disconnect session |

### ⏳ Planned Features

| Feature | Peeka | Arthas | Priority | Description |
|------|-------|--------|--------|------|
| Wildcard matching | Planned | ✅ `module.*` | Medium | Support glob patterns |
| Custom output expressions | Planned | ✅ `-x '{params, returnObj}'` | Low | Flexible output format |
| tt command | Planned | ✅ | High | Time tunnel (record and replay) |
| profiler | Planned | ✅ | High | CPU/stack flame graphs |
| heapdump | Planned | ✅ | Medium | Heap dump analysis |

### ❌ Non-Applicable Features

| Feature | Arthas | Description |
|------|--------|------|
| **jvm command** | ✅ | Python has no JVM |
| **jad command** | ✅ | Python source code usually available |
| **mc/retransform** | ✅ | Python doesn't need bytecode compilation |
| **classloader** | ✅ | Python module system is different |

---

## Python-Specific Advantages

### 1. Native JSON Output

Peeka outputs standard JSONL format for all commands, making automation integration easy:

```bash
# Peeka - Direct JSON output
peeka-cli watch "module.func" | jq 'select(.type == "observation")'

# Arthas - Requires additional text processing
watch module.func -x 2 | grep "result" | awk '{print $3}'
```

### 2. simpleeval Security Sandbox

Conditional expressions use AST whitelist, completely defending against code injection:

```python
# ✅ Peeka - Safe evaluation
--condition "params[0] > 100 and cost > 50"

# ⚠️ Arthas - Potential OGNL security risks
--condition '#cost > 50'
```

### 3. Python 3.12+ Performance Optimization

trace command uses `sys.monitoring` API with minimal performance overhead:

| Python Version | Implementation | Overhead |
|------------|------|------|
| 3.12+ | `sys.monitoring` | < 5% |
| 3.9-3.11 | `sys.settrace` | < 20% |
| 3.14+ | PEP 768 attach | 0% (attach overhead) |

Compared to Arthas:
- Java Instrumentation API: < 5% overhead
- Similar performance level

### 4. Lightweight Deployment

```bash
# Peeka - One-click pip install
pip install peeka

# Arthas - Requires download and configuration
curl -O https://arthas.aliyun.com/arthas-boot.jar
java -jar arthas-boot.jar
```

### 5. Unix Domain Socket

- Higher transmission efficiency (no network protocol stack)
- Stronger security (local only)
- Simpler reliability (length prefix + JSON)

Compared to Arthas:
- Arthas uses Netty + HTTP (supports remote)
- Peeka focuses on local diagnostics (more secure)

---

## Performance Comparison

### watch Command Performance

| Scenario | Peeka (Python 3.12+) | Arthas (Java) |
|------|---------------------|---------------|
| Decorator injection overhead | < 1% | < 5% |
| Per observation overhead | ~0.1ms | ~0.05ms |
| Memory usage | ~10MB | ~30MB |
| Startup time | < 1s | ~3s |

### trace Command Performance

| Scenario | Peeka (Python 3.12+) | Peeka (3.9-3.11) | Arthas (Java) |
|------|---------------------|------------------|---------------|
| Tracing overhead | < 5% | < 20% | < 5% |
| Depth 5 | ~0.5ms | ~2ms | ~0.3ms |
| Depth 10 | ~1ms | ~5ms | ~0.5ms |

### monitor Command Performance

| Metric | Peeka | Arthas |
|------|-------|--------|
| Statistics overhead | < 1% | < 1% |
| Periodic response latency | < 10ms | < 5ms |
| Memory usage | ~1MB | ~2MB |

---

## User Experience Comparison

### Command Comparison

#### watch command

**Peeka**:
```bash
peeka-cli watch "app.Calculator.add" \
  --condition "params[0] > 100" \
  --times 10
```

**Arthas**:
```bash
watch com.example.Calculator add \
  '#params[0] > 100' \
  -n 10
```

#### trace command

**Peeka**:
```bash
peeka-cli trace "app.service.process" \
  --depth 5 \
  --min-duration 10
```

**Arthas**:
```bash
trace com.example.Service process \
  -n 5 \
  '#cost > 10'
```

### Output Format Comparison

#### Peeka - JSONL

```json
{"type":"observation","func_name":"app.add","args":[1,2],"result":3,"duration_ms":0.123}
{"type":"observation","func_name":"app.add","args":[3,4],"result":7,"duration_ms":0.087}
```

**Advantages**:
- Machine-readable
- Easy to parse and filter
- Rich toolchain (jq, python, etc.)

#### Arthas - Text

```
watch result=@ArrayList[
    @Integer[3],
    @Integer[7],
]
cost=123.45ms
```

**Advantages**:
- Human-readable
- Intuitive display
- Suitable for terminal viewing

---

## Ecosystem Comparison

### Peeka Ecosystem

- **Integration tools**: jq, grep, awk, python
- **Visualization**: Textual TUI
- **Extensibility**: Python modular design
- **Community**: Python developer community

### Arthas Ecosystem

- **Integration tools**: Web UI, Arthas Tunnel
- **Visualization**: Web Dashboard
- **Extensibility**: Java plugin mechanism
- **Community**: Alibaba support, Java developer community

---

## Use Case Selection

### Choose Peeka When

1. **Python applications** - Native Python support
2. **Automation integration** - JSONL output for easy scripting
3. **Lightweight deployment** - pip install, no Java runtime needed
4. **Local diagnostics** - Unix Socket safe and reliable
5. **Modern Python** - Takes full advantage of Python 3.12+ features

### Choose Arthas When

1. **Java applications** - Designed specifically for Java
2. **Remote diagnostics** - Supports Arthas Tunnel
3. **Web UI** - Graphical interface
4. **Mature and stable** - Alibaba production-verified
5. **Rich features** - tt, profiler, heapdump and other advanced features

---

## Summary

| Dimension | Peeka | Arthas |
|------|-------|--------|
| **Target language** | Python | Java |
| **Core advantages** | Lightweight, JSON output, Python 3.12+ optimization | Mature, feature-rich, Web UI |
| **Performance** | < 5% (3.12+) | < 5% |
| **Security** | simpleeval (AST whitelist) | OGNL (sandbox) |
| **Deployment** | pip install | jar download |
| **Learning curve** | Medium | Medium |
| **Community activity** | Growing | Very active |

---

## References

- [Alibaba Arthas](https://github.com/alibaba/arthas)
- [Arthas User Documentation](https://arthas.aliyun.com/doc/)
- [Peeka GitHub](https://github.com/wwulfric/peeka)
- [PEP 768 - Safe External Debugger](https://peps.python.org/pep-0768/)
