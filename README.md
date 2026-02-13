# Peeka

[中文文档](README_ZH.md) | [📚 Full Documentation](https://wwulfric.github.io/peeka/en/)

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

```bash
# Attach to target process
peeka-cli attach <pid>

# Watch function calls
peeka-cli watch "module.Class.method" --times 5

# With condition filtering
peeka-cli watch "module.Class.method" --condition "len(params) > 2"
```

## Commands

| Command | Description | Documentation |
|---------|-------------|---------------|
| `attach` | Attach to target process | [📖 Docs](https://wwulfric.github.io/peeka/en/commands/attach.html) |
| `watch` | Observe function calls | [📖 Docs](https://wwulfric.github.io/peeka/en/commands/watch.html) |
| `trace` | Trace function call chains | [📖 Docs](https://wwulfric.github.io/peeka/en/commands/trace.html) |
| `stack` | Capture function call stacks | [📖 Docs](https://wwulfric.github.io/peeka/en/commands/stack.html) |
| `reset` | Reset instrumentation | [📖 Docs](https://wwulfric.github.io/peeka/en/commands/reset.html) |
| `logger` | Adjust log levels | [📖 Docs](https://wwulfric.github.io/peeka/en/commands/logger.html) |
| `monitor` | Performance monitoring | [📖 Docs](https://wwulfric.github.io/peeka/en/commands/monitor.html) |
| `memory` | Memory analysis | [📖 Docs](https://wwulfric.github.io/peeka/en/commands/memory.html) |
| `inspect` | Runtime object inspection | [📖 Docs](https://wwulfric.github.io/peeka/en/commands/inspect.html) |
| `sc` / `sm` | Search classes/methods | [📖 Docs](https://wwulfric.github.io/peeka/en/commands/search.html) |

For detailed command usage, see [Command Reference](https://wwulfric.github.io/peeka/en/commands/).

## Documentation

- [📚 Full Documentation](https://wwulfric.github.io/peeka/en/) - Complete documentation site
- [Quick Start Guide](https://wwulfric.github.io/peeka/en/quickstart.html) - Getting started
- [Architecture](docs/ARCHITECTURE.md) - System architecture and design
- [Examples](https://wwulfric.github.io/peeka/en/examples.html) - Usage examples
- [Comparison with Arthas](https://wwulfric.github.io/peeka/en/comparison.html) - Feature comparison
- [Troubleshooting](https://wwulfric.github.io/peeka/en/troubleshooting.html) - Common issues
- [Development Guide](AGENTS.md) - For contributors

## Python Version Support

| Version  | Attach Mechanism          | Requirements                     |
|----------|---------------------------|----------------------------------|
| 3.14+    | PEP 768 `sys.remote_exec` | None                             |
| 3.9-3.13 | GDB + ptrace fallback     | GDB, python3-dbg, CAP_SYS_PTRACE |

## License

MIT License

## Acknowledgments

- Inspired by: [Alibaba Arthas](https://github.com/alibaba/arthas)
- Safe evaluation: [simpleeval](https://github.com/danthedeckie/simpleeval)
- Remote debugging protocol: [PEP 768](https://peps.python.org/pep-0768/)
