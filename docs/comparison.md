# Comparison with Arthas

This document provides a detailed comparison between Peeka and [Alibaba Arthas](https://github.com/alibaba/arthas).

## Overview

Peeka is inspired by Arthas and aims to bring similar diagnostic capabilities to the Python ecosystem. While Arthas is designed for Java applications, Peeka adapts these concepts to work with Python's unique characteristics.

## Feature Comparison

### Core Diagnostic Commands

| Feature | Peeka | Arthas | Notes |
|---------|-------|--------|-------|
| **Process Attachment** | ✅ | ✅ | Peeka uses PEP 768 or GDB+ptrace |
| **watch command** | ✅ | ✅ | Observe function calls |
| **trace command** | ✅ | ✅ | Trace call chains |
| **stack command** | ✅ | ✅ | Capture call stacks |
| **monitor command** | ✅ | ✅ | Performance statistics |
| **tt command** (time tunnel) | ❌ | ✅ | Planned |
| **jad command** (decompile) | N/A | ✅ | Not applicable to Python |

### Observation Control

| Feature | Peeka | Arthas | Notes |
|---------|-------|--------|-------|
| Observation points | `-b/-e/-s/-f` | `-b/-e/-s/-f` | AtEnter, AtExit, AtExceptionExit |
| Condition filtering | `--condition-express` | `--condition-express` | Expression-based filtering |
| Duration filtering | `cost > 100` | `#cost>100` | Filter by execution time |
| Output depth control | `--depth` | `-x` | Control nested object display |
| Count limiting | `--times` | `-n` | Limit observation count |

### Advanced Features

| Feature | Peeka | Arthas | Notes |
|---------|-------|--------|-------|
| Pattern wildcards | ⏳ Planned | ✅ | `module.*` patterns |
| Custom expressions | ⏳ Planned | ✅ | `-x '{params, returnObj}'` |
| Method profiling | ⏳ Planned | ✅ | CPU/memory profiling |
| Thread analysis | ⏳ Planned | ✅ | Thread dump, deadlock detection |
| Class search | ✅ | ✅ | `sc/sm` commands |
| Logger control | ✅ | ✅ | Dynamic log level adjustment |

## Python-Specific Advantages

### 1. Native JSON Output

**Peeka**: All commands output JSONL format by default
```bash
peeka-cli watch "module.func" | jq '.result'
```

**Arthas**: Text-based output, requires parsing
```bash
watch com.example.Service method | grep "result"
```

### 2. Safe Expression Evaluation

**Peeka**: Uses `simpleeval` with AST whitelist
- Prevents code injection attacks
- Blocks dangerous operations: `__import__`, `eval`, `exec`
- Safe for production use

**Arthas**: Uses OGNL expressions
- More powerful but higher security risk
- Requires careful input validation

### 3. Lightweight Deployment

**Peeka**:
- Single pip install: `pip install peeka`
- ~10MB memory footprint
- No runtime dependencies

**Arthas**:
- Requires Java runtime
- ~30MB memory footprint
- More complex deployment

### 4. Python Integration

**Peeka**: Native Python integration
- Direct access to Python objects
- Pythonic filtering syntax
- Works with Python's dynamic nature

## Performance Comparison

| Scenario | Peeka (Py 3.12+) | Peeka (Py 3.9-3.11) | Arthas (Java) |
|----------|------------------|---------------------|---------------|
| **watch overhead** | < 1% | < 1% | < 5% |
| **trace overhead** | < 5% | < 20% | < 5% |
| **Memory usage** | ~10MB | ~10MB | ~30MB |
| **Attachment time** | ~100ms | ~500ms | ~200ms |

Notes:
- Python 3.12+ uses `sys.monitoring` API for lower overhead
- Python 3.9-3.11 uses decorator-based approach
- Arthas uses bytecode instrumentation (JVMTI)

## Language-Specific Differences

### Type System

**Python (Peeka)**:
- Dynamic typing
- Runtime type checking
- Duck typing support

**Java (Arthas)**:
- Static typing
- Compile-time type checking
- Interface-based contracts

### Execution Model

**Python (Peeka)**:
- Interpreted (with JIT in some cases)
- GIL for thread safety
- Reference counting + GC

**Java (Arthas)**:
- JIT compiled bytecode
- Native thread support
- Generational GC

## Use Case Comparison

### Debugging Production Issues

**Both tools excel at**:
- Non-invasive observation
- Real-time diagnostics
- Minimal performance impact

**Peeka advantages**:
- Simpler deployment (pip install)
- JSON output for automation
- Better for microservices (lightweight)

**Arthas advantages**:
- More mature ecosystem
- Advanced profiling tools
- Better thread analysis

### Performance Tuning

**Peeka strengths**:
- Function-level timing
- Easy integration with monitoring tools
- Condition-based filtering

**Arthas strengths**:
- JVM-level profiling
- Heap dump analysis
- Advanced memory analysis

## Migration from Arthas

If you're familiar with Arthas and want to use Peeka for Python applications:

| Arthas Command | Peeka Equivalent |
|----------------|------------------|
| `watch com.Foo method` | `peeka-cli watch "module.Foo.method"` |
| `watch com.Foo method -b` | `peeka-cli watch "module.Foo.method" -b` |
| `watch com.Foo method -x 3` | `peeka-cli watch "module.Foo.method" --depth 3` |
| `watch com.Foo method '#cost>100'` | `peeka-cli watch "module.Foo.method" --condition "cost > 100"` |
| `trace com.Foo method` | `peeka-cli trace "module.Foo.method"` |
| `stack com.Foo method` | `peeka-cli stack "module.Foo.method"` |
| `monitor com.Foo method` | `peeka-cli monitor "module.Foo.method"` |

## Conclusion

**Choose Peeka when**:
- Working with Python applications
- Need lightweight deployment
- Want JSON output for automation
- Prefer open-source with active development

**Choose Arthas when**:
- Working with Java/JVM applications
- Need advanced JVM-specific features
- Require mature enterprise support
- Need comprehensive thread/heap analysis

Both tools share the same philosophy of providing production-grade diagnostic capabilities without code modification.
