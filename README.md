<p align="center">
  <img src="gh-pages/assets/images/logo.png" alt="" width="48" align="middle">&nbsp;
  <strong style="font-size:2em;">Peeka</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/peeka/"><img src="https://img.shields.io/pypi/v/peeka?color=2888a8" alt="PyPI"></a>
  <a href="https://github.com/wwulfric/peeka/releases/latest"><img src="https://img.shields.io/github/v/release/wwulfric/peeka?color=2888a8" alt="Release"></a>
  <a href="https://github.com/wwulfric/peeka/actions"><img src="https://img.shields.io/github/actions/workflow/status/wwulfric/peeka/e2e-tests.yml?label=tests" alt="Tests"></a>
  <a href="https://github.com/wwulfric/peeka/blob/master/LICENSE"><img src="https://img.shields.io/github/license/wwulfric/peeka?color=2888a8" alt="License"></a>
</p>

<p align="center">
  <a href="README.zh-CN.md">中文</a> | <strong>English</strong>
</p>

> *Peek-a-boo!* — The name comes from the children's game. A diagnostic tool finding a hidden bug feels just like that moment of surprise when someone is found in hide-and-seek.

Runtime diagnostic tool for Python applications, inspired by [Alibaba Arthas](https://github.com/alibaba/arthas). Non-invasive function observation with zero code changes.

Uses [PEP 768](https://peps.python.org/pep-0768/) (`sys.remote_exec`) on Python 3.14+, with debugger-based fallback for Python 3.8–3.13 (GDB on Linux, LLDB on macOS).

## Key Features

- **Non-invasive** — Inject observation logic at runtime, fully restored on detach
- **Real-time streaming** — Millisecond-latency data via Unix domain sockets
- **Production-safe** — < 5% overhead, fixed-size memory buffers, graceful error recovery
- **Secure filtering** — [simpleeval](https://github.com/danthedeckie/simpleeval)-based condition expressions, blocks all code injection
- **Dual interface** — CLI (JSONL output, pipe-friendly) and interactive TUI

## Quick Start

### Install

```bash
pip install peeka          # CLI only (Python 3.8+)
pip install peeka[tui]     # CLI + TUI (Python 3.9+)
```

### Basic Usage

```bash
# 1. Attach to a running Python process
peeka-cli attach <pid>

# 2. Watch function calls
peeka-cli watch "module.Class.method" -n 5

# 3. Watch with condition filter
peeka-cli watch "module.func" --condition "params[0] > 100"

# 4. Trace call tree with timing
peeka-cli trace "module.func" -d 3

# 5. Capture call stack
peeka-cli stack "module.func" -n 3

# 6. Launch TUI
peeka
```

### Pipe-Friendly Output (JSONL)

All CLI output is JSONL — one JSON object per line with a `type` field:

```bash
# Filter observations with jq
peeka-cli watch "module.func" | jq 'select(.type == "observation")'

# Find slow calls
peeka-cli watch "module.func" | jq 'select(.type == "observation" and .data.duration_ms > 100)'

# Save to file
peeka-cli watch "module.func" > observations.jsonl
```

## Commands

| Command   | Description                                 |
|-----------|---------------------------------------------|
| `attach`  | Attach to a running Python process          |
| `watch`   | Observe function calls (args, return, time) |
| `trace`   | Trace call tree with timing breakdown       |
| `stack`   | Capture call stack at function entry        |
| `monitor` | Periodic performance statistics             |
| `logger`  | Adjust log levels at runtime                |
| `memory`  | Memory usage analysis                       |
| `inspect` | Runtime object inspection                   |
| `sc`/`sm` | Search classes / search methods             |
| `thread`  | Thread analysis and diagnostics             |
| `top`     | Function-level performance sampling         |
| `reset`   | Remove all injected enhancements            |
| `detach`  | Detach from target process                  |
| `run`     | Run a script with Peeka injected from startup |

### watch

```bash
peeka-cli watch <pattern> [options]
```

| Option             | Description                             | Default |
|--------------------|-----------------------------------------|---------|
| `-x, --depth`      | Output depth for nested objects          | 2       |
| `-n, --times`      | Number of observations (-1 = infinite)  | -1      |
| `--condition`       | Filter expression (e.g. `params[0] > 100`, `cost > 50`) | —       |
| `-b, --before`      | Observe at function entry               | false   |
| `-s, --success`     | Observe on success only                 | false   |
| `-e, --exception`   | Observe on exception only               | false   |
| `-f, --finish`      | Observe on finish (success or exception) | true    |

**Pattern format**: `module.Class.method` or `module.function`

### trace

```bash
peeka-cli trace <pattern> [options]
```

| Option             | Description                                | Default |
|--------------------|--------------------------------------------|---------|
| `-d, --depth`      | Max call tree depth                        | 3       |
| `-n, --times`      | Number of observations (-1 = infinite)     | -1      |
| `--condition`       | Filter expression (e.g. `cost > 50`)       | —       |
| `--skip-builtin`    | Skip stdlib/built-in functions             | true    |
| `--min-duration`    | Minimum duration filter (ms)               | 0       |

**Output example:**

```
`---[125.3ms] calculator.Calculator.calculate()
    +---[2.1ms] calculator.Calculator._validate()
    +---[98.2ms] calculator.Calculator._compute()
    |   `---[95.1ms] math.sqrt()
    `---[15.7ms] calculator.Logger.info()
```

### stack

```bash
peeka-cli stack <pattern> [options]
```

| Option             | Description                                | Default |
|--------------------|--------------------------------------------|---------|
| `-n, --times`      | Number of captures (-1 = infinite)         | -1      |
| `--condition`       | Filter expression                          | —       |
| `--depth`           | Stack depth limit                          | 10      |

### reset

```bash
peeka-cli reset [pattern] [options]
```

| Option        | Description                              | Default |
|---------------|------------------------------------------|---------|
| `-l, --list`  | List current enhancements without reset  | false   |
| `pattern`     | Optional glob pattern to filter targets  | —       |

```bash
peeka-cli reset                    # Reset all enhancements
peeka-cli reset "mymodule.*"       # Reset matching functions only
peeka-cli reset --list             # List active enhancements
```

### run

Run a Python script with Peeka injected from startup — useful when you need to observe code that runs at import time or in short-lived scripts.

```bash
peeka-cli run <script> [script_args] -- <command> [command_options]
```

```bash
peeka-cli run myscript.py -- watch "mymodule.func"
peeka-cli run myscript.py arg1 arg2 -- trace "mymodule.func" -d 3
peeka-cli run myscript.py -- watch "mymodule.func" --output-file out.jsonl
```

| Option          | Description                                    | Default |
|-----------------|------------------------------------------------|---------|
| `--output-file` | Write JSONL output to file instead of stdout   | —       |

## Condition Expressions

Powered by [simpleeval](https://github.com/danthedeckie/simpleeval) for safe evaluation:

```python
params[0] > 100              # Positional argument check
len(params) > 2              # Argument count
kwargs.get('debug') == True  # Keyword argument check
cost > 50                    # Execution time in ms (watch/trace only)
str(x).startswith('prefix')  # String operations
x + y > 10                   # Arithmetic
```

Available variables: `params` (positional args list), `kwargs` (keyword args dict), `result` (return value, finish only), `cost` (duration ms, watch/trace only).

**Security**: Only safe operations (comparisons, arithmetic, logic) are allowed. `eval`, `exec`, `__import__`, `open`, `compile` and reflection via `__class__`/`__subclasses__` are all blocked.

## Output Format

Every line is a JSON object with a `type` field:

| Type          | Description                         | Commands               |
|---------------|-------------------------------------|------------------------|
| `status`      | Progress/info messages              | attach                 |
| `success`     | Command completed successfully      | attach, detach         |
| `error`       | Command failed                      | all                    |
| `event`       | Control events (started/stopped)    | watch, stack, monitor  |
| `observation` | Real-time observation data          | watch, stack, monitor  |
| `result`      | Query results (non-streaming)       | logger, memory, sc, sm |

<details>
<summary>Output examples</summary>

```json
{"type": "status", "level": "info", "message": "Attaching to process 12345"}
{"type": "success", "command": "attach", "data": {"pid": 12345, "socket": "/tmp/peeka_xxx.sock"}}
{"type": "event", "event": "watch_started", "data": {"watch_id": "watch_001", "pattern": "module.func"}}
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
{"type": "error", "command": "watch", "error": "Cannot find target: invalid.pattern"}
```

</details>

## Python Version Support

| Python Version | CLI | TUI | Attach Mechanism              | Requirements                                    |
|----------------|:---:|:---:|-------------------------------|------------------------------------------------|
| 3.14+          | ✅  | ✅  | PEP 768 `sys.remote_exec()`  | Same UID or `CAP_SYS_PTRACE`                   |
| 3.9–3.13       | ✅  | ✅  | GDB (Linux) / LLDB (macOS)    | **Linux**: GDB 7.3+, ptrace ≤ 1<br>**macOS**: Xcode Command Line Tools |
| 3.8            | ✅  | ❌  | GDB (Linux) / LLDB (macOS)    | **Linux**: GDB 7.3+, ptrace ≤ 1<br>**macOS**: Xcode Command Line Tools |

TUI requires [Textual](https://github.com/Textualize/textual) which needs Python ≥ 3.9.

### Python < 3.14 Setup

#### Linux

GDB is required. Debug symbols are **strongly recommended** — some distros include them by default, but if GDB reports "no symbol" errors, install them:

```bash
# Debian/Ubuntu
sudo apt-get install gdb python3-dbg

# RHEL/Fedora
sudo yum install gdb python3-debuginfo

# Arch
sudo pacman -S gdb
```

#### macOS

LLDB is used instead of GDB. Install Xcode Command Line Tools if not already installed:

```bash
xcode-select --install
```

LLDB is included by default. No additional debug symbols are required.

### Docker

```bash
docker run --cap-add=SYS_PTRACE your-image
```

### ptrace Restrictions (Linux)

```bash
# Check current setting
cat /proc/sys/kernel/yama/ptrace_scope

# Temporarily allow (for testing)
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# SELinux (Fedora/RHEL)
sudo setsebool -P deny_ptrace=off
```

**Note**: macOS does not have ptrace_scope restrictions. System Integrity Protection (SIP) may prevent debugging some system processes, but user processes can be debugged normally.


## Troubleshooting

### Attach fails (permission denied)

- Ensure same UID or `CAP_SYS_PTRACE`
- **Linux**: Check `ptrace_scope` (see above)
- **Linux**: Install debug symbols if GDB reports "no symbol" errors
- **macOS**: Ensure Xcode Command Line Tools are installed (`xcode-select --install`)

### No observation data

- Verify function name (use fully qualified name: `module.Class.method`)
- Confirm the function is actually being called
- Check if condition expression is too restrictive

### Target process behaving abnormally

```bash
# Remove observation on specific function
peeka-cli reset "module.func"

# Remove all injected enhancements
peeka-cli reset

# If issues persist, detach and restart target process
peeka-cli detach <pid>
```

## Architecture

```
CLI/TUI  →  AgentClient  →  Unix Socket  →  PeekaAgent (injected in target)
                                              ├─ _register_handlers() → BaseCommand subclasses
                                              ├─ DecoratorInjector (function wrapping)
                                              └─ ObservationManager (buffered streaming)
```

- **Attach**: PEP 768 `sys.remote_exec()` on 3.14+, GDB (Linux) or LLDB (macOS) on 3.8–3.13
- **Observe**: Decorator injection wraps target functions, captures args/return/exceptions/timing
- **Stream**: Real-time observation data via Unix domain socket (length-prefixed JSON)
- **Commands**: Modular `BaseCommand` subclasses, registered in `PeekaAgent._register_handlers()`

## License

Apache License 2.0

## Acknowledgments

- Inspired by [Alibaba Arthas](https://github.com/alibaba/arthas)
- Safe evaluation: [simpleeval](https://github.com/danthedeckie/simpleeval)
- Remote debugging protocol: [PEP 768](https://peps.python.org/pep-0768/)
