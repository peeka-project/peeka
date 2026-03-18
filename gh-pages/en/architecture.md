---
layout: default
title: Architecture
nav_order: 8
permalink: /architecture
---

# Architecture
{: .no_toc }

Deep dive into Peeka's design philosophy, architecture, and implementation details.
{: .fs-6 .fw-300 }

## Table of Contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Design Goals

Peeka Agent's design follows these core goals:

### Low Intrusion

The agent runs without significantly affecting the target process's performance and functionality. Based on industry experience, the performance overhead of production diagnostic tools should be kept **within 5%**. Peeka ensures minimal impact on the target process through carefully designed decorator injection mechanisms and observation data buffering strategies.

### High Reliability

The agent must remain stable under various exceptional circumstances and not cause the target process to crash or behave abnormally due to its own errors. Special attention is paid to resource management issues, including proper release of system resources such as memory usage, file descriptors, and threads, to avoid long-term stability issues caused by resource leaks.

### Real-Time Performance

Diagnostic data can be transmitted to the client in real-time, allowing developers to immediately observe behavioral changes in the target process. This is particularly important for locating intermittent problems. Peeka uses a stream-based communication protocol over Unix Domain Socket, achieving **millisecond-level** data transmission latency.

### Extensibility

The agent architecture can easily support new diagnostic commands and feature extensions without requiring large-scale refactoring of existing code. A modular design separates concerns such as communication, command execution, and observation, interacting through clearly defined interfaces.

---

## Overall Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Space                            │
│                                                               │
│  ┌──────────────┐                    ┌──────────────┐       │
│  │  CLI/TUI     │                    │ Target       │       │
│  │              │                    │ Process      │       │
│  │  - peeka-cli │                    │              │       │
│  │  - peeka     │                    │ ┌──────────┐ │       │
│  └──────┬───────┘                    │ │  Agent   │ │       │
│         │                            │ │ (injected)│ │       │
│         │ Unix Domain Socket         │ └────┬─────┘ │       │
│         │ /tmp/peeka_<pid>.sock      │      │       │       │
│         └────────────────────────────┼──────┘       │       │
│                                      │              │       │
│  │ AgentClient     │←────JSON────────┤ │ Commands │ │       │
│  │                 │                 │ │          │ │       │
│  │ - send_command  │                 │ │ - watch  │ │       │
│  │ - recv_response │                 │ │ - trace  │ │       │
│  └─────────────────┘                 │ │ - stack  │ │       │
│                                      │ │ - monitor│ │       │
│                                      │ │ - logger │ │       │
│                                      │ │ - memory │ │       │
│                                      │ │ - inspect│ │       │
│                                      │ │ - thread │ │       │
│                                      │ │ - top    │ │       │
│                                      │ │ - sc/sm  │ │       │
│                                      │ │ - reset  │ │       │
│                                      │ │ - detach │ │       │
│                                      │ └──────────┘ │       │
│                                      │              │       │
│                                      │ ┌──────────┐ │       │
│                                      │ │ Injector │ │       │
│                                      │ │          │ │       │
│                                      │ │ Function │ │       │
│                                      │ │ Wrapping │ │       │
│                                      │ └──────────┘ │       │
│                                      └──────────────┘       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      Kernel Space                            │
│                                                               │
│  ┌──────────────────────────────────────────┐               │
│  │  Process Attachment                       │               │
│  │                                           │               │
│  │  Python 3.14+:  sys.remote_exec()        │               │
│  │  Python < 3.14: GDB + ptrace             │               │
│  └──────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Process Attachment (attach.py)

Responsible for injecting Agent code into the target process.

#### Python 3.14+

Uses PEP 768's `sys.remote_exec()` API:

```python
import sys

# Inject and execute Agent code
sys.remote_exec(pid, agent_script_path)
```

**Advantages**:
- Official support, safe and reliable
- No external dependencies (GDB)
- Cross-platform compatibility

#### Python 3.9-3.13

Uses GDB + ptrace fallback:

```python
# 1. GDB attaches to process
gdb -p <pid>

# 2. Acquire GIL
call PyGILState_Ensure()

# 3. Execute Python code
call PyRun_SimpleString("exec(open('/path/agent.py').read())")

# 4. Release GIL
call PyGILState_Release(gil_state)

# 5. Detach
detach
quit
```

**Requirements**:
- GDB 7.3+
- Python debugging symbols
- CAP_SYS_PTRACE permission

### 2. Agent Core (agent.py)

Core code injected into the target process, responsible for:

#### Socket Server

```python
import socket
import threading

class PeekaAgent:
    def __init__(self):
        self.socket_path = f"/tmp/peeka_{os.getpid()}.sock"
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(self.socket_path)
        self.server.listen(1)

    def start(self):
        # Run in background thread, doesn't block main thread
        thread = threading.Thread(target=self._serve, daemon=True)
        thread.start()
```

#### Command Dispatching

```python
def _handle_command(self, command: dict) -> dict:
    cmd_type = command.get("command")
    handler = self.handlers.get(cmd_type)

    if handler:
        return handler.execute(command.get("params", {}))
    else:
        return {"status": "error", "error": f"Unknown command: {cmd_type}"}
```

#### Resource Management

- Fixed-size observation data buffer (default 10000 entries)
- Automatic cleanup of expired observations
- Graceful thread shutdown

### 3. Decorator Injector (injector.py)

Dynamically wraps target functions, adding observation logic.

#### Function Wrapping

```python
class DecoratorInjector:
    def inject_function(self, func, observer):
        original_func = func

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Entry observation
            if observer.at_enter:
                observer.on_enter(args, kwargs)

            try:
                # Execute original function
                result = original_func(*args, **kwargs)

                # Success observation
                if observer.at_exit:
                    observer.on_exit(result)

                return result
            except Exception as e:
                # Exception observation
                if observer.at_exception:
                    observer.on_exception(e)
                raise

        return wrapper
```

#### Safe Restoration

```python
def restore_function(self, target):
    # Restore original function
    if hasattr(target, '__wrapped__'):
        original = target.__wrapped__
        # Safe replacement (handles various edge cases)
        ...
```

### 4. Client (client.py)

Client library for communicating with the Agent.

#### Synchronous Client

```python
class AgentClient:
    def send_command(self, command: dict) -> dict:
        # Send command (length prefix + JSON)
        msg = json.dumps(command).encode()
        self.sock.sendall(len(msg).to_bytes(4, 'big') + msg)

        # Receive response
        length = int.from_bytes(self.sock.recv(4), 'big')
        response = self.sock.recv(length)
        return json.loads(response)
```

#### Streaming Client

```python
class StreamingAgentClient(AgentClient):
    def stream_observations(self):
        # Generator, receives observation data in real-time
        while True:
            msg = self._recv_message()
            if msg.get("type") == "observation":
                yield msg
            elif msg.get("type") == "event":
                if msg["event"] == "watch_stopped":
                    break
```

### 5. Command System (commands/)

Modular command implementation.

#### Base Class

```python
class BaseCommand(ABC):
    def __init__(self, agent: "PeekaAgent"):
        self.agent = agent

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute command and return result"""
        pass
```

#### Command Registration

```python
def _register_handlers(self):
    from peeka.commands.watch import WatchCommand
    from peeka.commands.trace import TraceCommand
    # ... Lazy import to avoid circular dependencies

    self.handlers = {
        "watch": WatchCommand(self),
        "trace": TraceCommand(self),
        # ...
    }
```

---

## Communication Protocol

### Message Format

All messages use **length prefix + JSON** format:

```
┌─────────────┬─────────────────────────┐
│  Length     │   JSON Payload          │
│  (4 bytes)  │   (variable length)     │
└─────────────┴─────────────────────────┘
```

### Request Format

```json
{
  "command": "watch",
  "params": {
    "pattern": "module.func",
    "times": 10,
    "condition": "cost > 100"
  }
}
```

### Response Format

#### Success Response

```json
{
  "status": "success",
  "data": {
    "watch_id": "watch_001",
    "pattern": "module.func"
  }
}
```

#### Error Response

```json
{
  "status": "error",
  "error": "Cannot find target: invalid.pattern",
  "traceback": "..."
}
```

#### Streaming Observation

```json
{
  "type": "observation",
  "watch_id": "watch_001",
  "timestamp": 1705586200.123,
  "func_name": "module.func",
  "args": [1, 2],
  "result": 3,
  "duration_ms": 0.123
}
```

---

## Security Mechanisms

### 1. Expression Safety (safeeval/)

Safe expression evaluation based on the `simpleeval` library.

#### AST Whitelist

Only safe AST nodes are allowed:

```python
SAFE_NODES = {
    ast.Expression, ast.Compare, ast.BinOp, ast.UnaryOp,
    ast.Num, ast.Str, ast.NameConstant, ast.Name,
    ast.List, ast.Tuple, ast.Dict, ast.Subscript,
    # ... Other safe nodes
}
```

#### Attribute Protection

Blocks dangerous attribute access:

```python
UNSAFE_ATTRS = {
    '__class__', '__subclasses__', '__bases__',
    '__import__', '__builtins__', '__globals__'
}
```

#### Function Blacklist

Disables dangerous functions:

```python
UNSAFE_FUNCTIONS = {
    'eval', 'exec', 'compile', 'open',
    '__import__', 'input', 'globals', 'locals'
}
```

### 2. Resource Limits

#### Memory Buffering

```python
class ObservationManager:
    def __init__(self, max_size=10000):
        self.buffer = collections.deque(maxlen=max_size)
```

#### Timeout Control

```python
@timeout(seconds=30)
def execute_command(command):
    # Command execution has timeout protection
    pass
```

### 3. Exception Catching

#### Three-Layer Protection

1. **Core modules**: Throw exceptions, fail fast
2. **Command layer**: Catch and return error dictionary
3. **Agent layer**: Final protection, add traceback

```python
try:
    result = command.execute(params)
except Exception as e:
    result = {
        "status": "error",
        "error": str(e),
        "traceback": traceback.format_exc()
    }
```

---

## Performance Optimization

### 1. Decorator Injection

- Uses `functools.wraps` to preserve metadata
- Minimizes wrapping overhead (< 1%)
- Conditional compilation (inject only when needed)

### 2. sys.monitoring API (Python 3.12+)

trace command uses `sys.monitoring` API:

```python
import sys

def trace_callback(code, instruction_offset, args):
    # Low overhead event callback
    pass

sys.monitoring.use_tool_id(sys.monitoring.PROFILER_ID, "peeka")
sys.monitoring.register_callback(
    sys.monitoring.PROFILER_ID,
    sys.monitoring.events.CALL,
    trace_callback
)
```

**Performance Comparison**:
- `sys.monitoring`: < 5% overhead
- `sys.settrace`: < 20% overhead (Python 3.9-3.11)

### 3. Streaming Transmission

- Uses generators to avoid memory accumulation
- Unix Domain Socket low-latency transmission
- JSON streaming parsing

---

## Extension Development

### Adding a New Command

1. Create command class:

```python
# peeka/commands/mycommand.py
from peeka.commands.base import BaseCommand
from typing import Dict, Any

class MyCommand(BaseCommand):
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Implement command logic
            result = self._do_work(params)
            return {"status": "success", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}
```

2. Register in Agent:

```python
# peeka/core/agent.py
def _register_handlers(self):
    from peeka.commands.mycommand import MyCommand
    self.handlers["mycommand"] = MyCommand(self)
```

3. Add CLI interface:

```python
# peeka/cli/main.py
parser.add_subcommand("mycommand", help="My new command")
```

### Adding a TUI View

1. Create view class:

```python
# peeka/tui/views/myview.py
from textual.widgets import Static

class MyView(Static):
    def compose(self):
        yield Label("My View")
```

2. Register shortcut:

```python
# peeka/tui/screens/main.py
BINDINGS = [
    ("5", "show_myview", "My View"),
]
```

---

## References

- [PEP 768 - Safe External Debugger](https://peps.python.org/pep-0768/)
- [PEP 669 - Low Overhead Monitoring](https://peps.python.org/pep-0669/)
- [simpleeval Documentation](https://github.com/danthedeckie/simpleeval)
