# Command Reference

This document provides detailed reference for all Peeka commands.

## Command Overview

| Command | Description | Documentation |
|---------|-------------|---------------|
| `attach` | Attach to target process | [attach.md](attach.md) |
| `watch` | Observe function calls | [watch.md](watch.md) |
| `trace` | Trace function call chains | [trace.md](trace.md) |
| `stack` | Capture call stacks | [stack.md](stack.md) |
| `reset` | Reset instrumentation | [reset.md](reset.md) |
| `logger` | Adjust log levels | [logger.md](logger.md) |
| `monitor` | Performance monitoring | [monitor.md](monitor.md) |
| `memory` | Memory analysis | [memory.md](memory.md) |
| `inspect` | Object inspection | [inspect.md](inspect.md) |
| `sc/sm` | Search classes/methods | [search.md](search.md) |

## General Usage Pattern

All commands follow this general pattern:

```bash
peeka-cli <command> [options]
```

## Output Format

All commands output JSONL (JSON Lines) format:
- Each line is a valid JSON object
- Use `jq` for filtering and processing
- `type` field indicates message type

See individual command documentation for detailed usage and examples.
