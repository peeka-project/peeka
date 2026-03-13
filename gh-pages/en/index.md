---
layout: default
title: Home
nav_order: 1
description: "Peeka - Python Runtime Diagnostic Tool with Non-Invasive Function Observation based on PEP 768"
permalink: /
---

# Peeka
{: .fs-9 }

A runtime diagnostic tool based on Python 3.14 remote debugging protocol (PEP 768), providing non-invasive function observation capabilities similar to Java Arthas.
{: .fs-6 .fw-300 }

[Quick Start](#quick-start){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View on GitHub](https://github.com/wwulfric/peeka){: .btn .fs-5 .mb-4 .mb-md-0 }

---

{: .note }
> 🌐 **Language / 语言**: This documentation is also available in [Chinese (中文)](/peeka/).
>
> 本文档也提供[中文版本](/peeka/)。

---

## What is Peeka?

Peeka is a tool that provides real-time diagnostic capabilities for Python developers in production environments. It can dynamically observe and diagnose running Python applications **without modifying target code**.

### Why Peeka?

Traditional Python debugging methods face many challenges in production environments:

- **Cannot stop service** - Breakpoint debugging blocks the process
- **Intermittent issues** - Need to observe under real load
- **Code modification difficulties** - Cannot deploy freely in production

Peeka is designed specifically to solve these production environment diagnostic challenges.

---

## Core Features

### 🔍 Non-Invasive Observation
{: .text-delta }

- No need to modify target code
- Runtime dynamic injection of observation logic
- Complete restoration after diagnosis

### ⚡ Real-Time Diagnosis
{: .text-delta }

- Millisecond-level data transmission latency
- Streaming observation data push
- JSON format output for easy integration with other tools

### 🛡️ Production-Ready
{: .text-delta }

- Performance overhead < 5%
- Complete exception capture and recovery mechanisms
- Fixed memory buffer to prevent memory expansion

### 🎯 Conditional Filtering
{: .text-delta }

- Safe expression filtering (based on simpleeval)
- Flexible filtering syntax (parameters, return values, execution time, etc.)
- Blocks all code injection attacks (`__import__`, `eval`, `exec`, etc.)

---

## Quick Start

### Installation

```bash
pip install peeka
```

### Basic Usage

#### 1. Attach to Target Process

```bash
peeka-cli attach <pid>
```

#### 2. Observe Function Calls

```bash
# Observe 5 calls
peeka-cli watch "module.Class.method" --times 5

# Conditional filtering
peeka-cli watch "module.Class.method" --condition "len(params) > 2"

# Real-time streaming observation
peeka-cli watch "module.Class.method"
```

#### 3. Data Processing

```bash
# Extract results with jq
peeka-cli watch "module.func" | jq 'select(.type == "observation") | .data.result'

# Filter slow calls
peeka-cli watch "module.func" | jq 'select(.type == "observation" and .data.duration_ms > 1)'
```

---

## Main Features

| Command | Function | Status |
|---------|----------|--------|
| `attach` | Attach to target process | ✅ |
| `watch` | Observe function calls (params, return, time) | ✅ |
| `trace` | Trace call chain and execution time | ✅ |
| `stack` | Trace call stack | ✅ |
| `monitor` | Performance statistics monitoring | ✅ |
| `logger` | Dynamically adjust log level | ✅ |
| `memory` | Memory analysis | ✅ |
| `inspect` | Runtime object inspection | ✅ |
| `sc/sm` | Search classes and methods | ✅ |
| `reset` | Reset enhancements | ✅ |
| `thread` | Thread analysis | ✅ |
| `top` | Function-level performance sampling | ✅ |
| `detach` | Safely exit diagnostic session | ✅ |

[View Complete Command Reference]({{ site.baseurl }}{% link commands/index.md %}){: .btn .btn-outline }

### 🎨 Interactive TUI Interface
{: .text-delta }

In addition to CLI commands, Peeka also provides a feature-complete TUI (Text User Interface):

- **Process Selector** - Automatically displays system process list with search filtering
- **10 Dedicated Views** - Dashboard, Watch, Trace, Stack, Monitor, Logger, Memory, Inspect, Threads, Top
- **Real-Time Data Stream** - Streaming observation data with pause/resume/clear support
- **Auto-Completion** - Dynamically retrieve classes and methods from target process
- **Theme Support** - Multiple built-in color themes

```bash
# Launch TUI
peeka

# Use shortcuts to switch views
# d/w/t/s/m/l/e/i/h/F8
```

[View Complete TUI Usage Guide]({{ site.baseurl }}{% link tui.md %}){: .btn .btn-outline }

---

## Comparison with Arthas

Peeka's design is deeply inspired by [Alibaba Arthas](https://github.com/alibaba/arthas), bringing similar diagnostic capabilities to the Python ecosystem.

### Python-Specific Advantages

- **Native JSON Output** - All commands output JSONL format for easy automation integration
- **simpleeval Security Sandbox** - Conditional expressions use AST whitelist, fully defending against code injection
- **Python 3.12+ Performance Optimization** - trace command uses `sys.monitoring` API with < 5% overhead
- **Lightweight Deployment** - No Java runtime required, one-click pip installation

[Detailed Feature Comparison]({{ site.baseurl }}{% link comparison.md %}){: .btn .btn-outline }

---

## Technical Highlights

### Python 3.14 Remote Debugging Protocol (PEP 768)

The core `sys.remote_exec(pid, script_path)` function is the key to the entire system's operation, encapsulating complex process attachment, code injection, and execution scheduling logic.

**Fallback for Python < 3.14**: For older Python versions, uses GDB + ptrace mechanism (reference: pyrasite).

### Unix Domain Socket

Uses Unix Domain Socket as the main inter-process communication mechanism:

- Higher transmission efficiency - No need for network protocol stack
- Stronger security - Only local processes can use
- Simple and reliable - Length prefix + JSON format

### Safe Conditional Expression Evaluation

Implements safe conditional filtering based on simpleeval library:

- AST whitelist - Only allows safe operations
- Attribute protection - Blocks reflection attacks
- Function blacklist - Disables dangerous functions

[Learn Architecture Design]({{ site.baseurl }}{% link architecture.md %}){: .btn .btn-outline }

---

## Supported Python Versions

| Python Version | Attachment Mechanism | Requirements |
|----------------|---------------------|--------------|
| 3.14+ | PEP 768 `sys.remote_exec` | None |
| 3.9-3.13 | GDB + ptrace fallback | GDB, python3-dbg, CAP_SYS_PTRACE |

---

## License

Peeka is open source under [MIT License](https://github.com/wwulfric/peeka/blob/main/LICENSE).

---

## Acknowledgments

- Inspiration: [Alibaba Arthas](https://github.com/alibaba/arthas)
- Security evaluation: [simpleeval](https://github.com/danthedeckie/simpleeval)
- Remote debugging protocol: [PEP 768](https://peps.python.org/pep-0768/)
