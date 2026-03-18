---
layout: default
title: 架构设计
nav_order: 8
---

# 架构设计
{: .no_toc }

深入了解 Peeka 的设计理念、架构和实现细节。
{: .fs-6 .fw-300 }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 设计目标

Peeka Agent 的设计遵循以下核心目标：

### 低侵入性

Agent 的运行不显著影响目标进程的性能和功能。根据业界经验，生产环境诊断工具的性能开销应控制在 **5% 以内**。Peeka 通过精心设计的装饰器注入机制和观测数据缓冲策略，确保诊断操作对目标进程的影响最小化。

### 高可靠性

Agent 必须在各种异常情况下保持稳定运行，不因自身错误导致目标进程崩溃或异常。设计时特别关注资源管理问题，包括内存使用、文件描述符、线程等系统资源的正确释放，避免资源泄漏导致的长期稳定性问题。

### 实时性

诊断数据能够实时传输到客户端，使开发者立即观察到目标进程的行为变化。这对于定位间歇性问题尤为重要。Peeka 采用基于 Unix Domain Socket 的流式通信协议，实现了**毫秒级**的数据传输延迟。

### 可扩展性

Agent 架构能够方便地支持新的诊断命令和功能扩展，而不需要大规模重构现有代码。采用模块化设计，将通信、命令执行、观测等关注点分离，通过清晰定义的接口进行交互。

---

## 整体架构

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
│  ┌─────────────────┐                 │ ┌──────────┐ │       │
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

## 核心组件

### 1. 进程附加（attach.py）

负责将 Agent 代码注入到目标进程。

#### Python 3.14+

使用 PEP 768 的 `sys.remote_exec()` API：

```python
import sys

# 注入并执行 Agent 代码
sys.remote_exec(pid, agent_script_path)
```

**优势**：
- 官方支持，安全可靠
- 无需外部依赖（GDB）
- 跨平台兼容

#### Python 3.9-3.13

使用 GDB + ptrace 降级方案：

```python
# 1. GDB 附加到进程
gdb -p <pid>

# 2. 获取 GIL
call PyGILState_Ensure()

# 3. 执行 Python 代码
call PyRun_SimpleString("exec(open('/path/agent.py').read())")

# 4. 释放 GIL
call PyGILState_Release(gil_state)

# 5. 分离
detach
quit
```

**要求**：
- GDB 7.3+
- Python 调试符号
- CAP_SYS_PTRACE 权限

### 2. Agent 核心（agent.py）

注入到目标进程的核心代码，负责：

#### Socket 服务器

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
        # 在后台线程中运行，不阻塞主线程
        thread = threading.Thread(target=self._serve, daemon=True)
        thread.start()
```

#### 命令分发

```python
def _handle_command(self, command: dict) -> dict:
    cmd_type = command.get("command")
    handler = self.handlers.get(cmd_type)

    if handler:
        return handler.execute(command.get("params", {}))
    else:
        return {"status": "error", "error": f"Unknown command: {cmd_type}"}
```

#### 资源管理

- 固定大小的观测数据缓冲（默认 10000 条）
- 自动清理过期观测
- 优雅的线程关闭

### 3. 装饰器注入器（injector.py）

动态包装目标函数，添加观测逻辑。

#### 函数包装

```python
class DecoratorInjector:
    def inject_function(self, func, observer):
        original_func = func

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 入口观测
            if observer.at_enter:
                observer.on_enter(args, kwargs)

            try:
                # 执行原函数
                result = original_func(*args, **kwargs)

                # 成功观测
                if observer.at_exit:
                    observer.on_exit(result)

                return result
            except Exception as e:
                # 异常观测
                if observer.at_exception:
                    observer.on_exception(e)
                raise

        return wrapper
```

#### 安全恢复

```python
def restore_function(self, target):
    # 恢复原始函数
    if hasattr(target, '__wrapped__'):
        original = target.__wrapped__
        # 安全替换（处理各种边界情况）
        ...
```

### 4. 客户端（client.py）

与 Agent 通信的客户端库。

#### 同步客户端

```python
class AgentClient:
    def send_command(self, command: dict) -> dict:
        # 发送命令（长度前缀 + JSON）
        msg = json.dumps(command).encode()
        self.sock.sendall(len(msg).to_bytes(4, 'big') + msg)

        # 接收响应
        length = int.from_bytes(self.sock.recv(4), 'big')
        response = self.sock.recv(length)
        return json.loads(response)
```

#### 流式客户端

```python
class StreamingAgentClient(AgentClient):
    def stream_observations(self):
        # 生成器，实时流式接收观测数据
        while True:
            msg = self._recv_message()
            if msg.get("type") == "observation":
                yield msg
            elif msg.get("type") == "event":
                if msg["event"] == "watch_stopped":
                    break
```

### 5. 命令系统（commands/）

模块化的命令实现。

#### 基类

```python
class BaseCommand(ABC):
    def __init__(self, agent: "PeekaAgent"):
        self.agent = agent

    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行命令并返回结果"""
        pass
```

#### 命令注册

```python
def _register_handlers(self):
    from peeka.commands.watch import WatchCommand
    from peeka.commands.trace import TraceCommand
    # ... 延迟导入避免循环依赖

    self.handlers = {
        "watch": WatchCommand(self),
        "trace": TraceCommand(self),
        # ...
    }
```

---

## 通信协议

### 消息格式

所有消息使用 **长度前缀 + JSON** 格式：

```
┌─────────────┬─────────────────────────┐
│  Length     │   JSON Payload          │
│  (4 bytes)  │   (variable length)     │
└─────────────┴─────────────────────────┘
```

### 请求格式

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

### 响应格式

#### 成功响应

```json
{
  "status": "success",
  "data": {
    "watch_id": "watch_001",
    "pattern": "module.func"
  }
}
```

#### 错误响应

```json
{
  "status": "error",
  "error": "Cannot find target: invalid.pattern",
  "traceback": "..."
}
```

#### 流式观测

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

## 安全机制

### 1. 表达式安全（safeeval/）

基于 `simpleeval` 库的安全表达式评估。

#### AST 白名单

只允许安全的 AST 节点：

```python
SAFE_NODES = {
    ast.Expression, ast.Compare, ast.BinOp, ast.UnaryOp,
    ast.Num, ast.Str, ast.NameConstant, ast.Name,
    ast.List, ast.Tuple, ast.Dict, ast.Subscript,
    # ... 其他安全节点
}
```

#### 属性保护

阻止危险属性访问：

```python
UNSAFE_ATTRS = {
    '__class__', '__subclasses__', '__bases__',
    '__import__', '__builtins__', '__globals__'
}
```

#### 函数黑名单

禁用危险函数：

```python
UNSAFE_FUNCTIONS = {
    'eval', 'exec', 'compile', 'open',
    '__import__', 'input', 'globals', 'locals'
}
```

### 2. 资源限制

#### 内存缓冲

```python
class ObservationManager:
    def __init__(self, max_size=10000):
        self.buffer = collections.deque(maxlen=max_size)
```

#### 超时控制

```python
@timeout(seconds=30)
def execute_command(command):
    # 命令执行有超时保护
    pass
```

### 3. 异常捕获

#### 三层防护

1. **核心模块**：抛出异常，快速失败
2. **命令层**：捕获并返回错误字典
3. **Agent 层**：最终防护，添加 traceback

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

## 性能优化

### 1. 装饰器注入

- 使用 `functools.wraps` 保留元数据
- 最小化包装开销（< 1%）
- 条件编译（仅在需要时注入）

### 2. sys.monitoring API（Python 3.12+）

trace 命令使用 `sys.monitoring` API：

```python
import sys

def trace_callback(code, instruction_offset, args):
    # 低开销的事件回调
    pass

sys.monitoring.use_tool_id(sys.monitoring.PROFILER_ID, "peeka")
sys.monitoring.register_callback(
    sys.monitoring.PROFILER_ID,
    sys.monitoring.events.CALL,
    trace_callback
)
```

**性能对比**：
- `sys.monitoring`: < 5% 开销
- `sys.settrace`: < 20% 开销（Python 3.9-3.11）

### 3. 流式传输

- 使用生成器避免内存积累
- Unix Domain Socket 低延迟传输
- JSON 流式解析

---

## 扩展开发

### 添加新命令

1. 创建命令类：

```python
# peeka/commands/mycommand.py
from peeka.commands.base import BaseCommand
from typing import Dict, Any

class MyCommand(BaseCommand):
    def execute(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # 实现命令逻辑
            result = self._do_work(params)
            return {"status": "success", "data": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}
```

2. 注册到 Agent：

```python
# peeka/core/agent.py
def _register_handlers(self):
    from peeka.commands.mycommand import MyCommand
    self.handlers["mycommand"] = MyCommand(self)
```

3. 添加 CLI 接口：

```python
# peeka/cli/main.py
parser.add_subcommand("mycommand", help="My new command")
```

### 添加 TUI 视图

1. 创建视图类：

```python
# peeka/tui/views/myview.py
from textual.widgets import Static

class MyView(Static):
    def compose(self):
        yield Label("My View")
```

2. 注册快捷键：

```python
# peeka/tui/screens/main.py
BINDINGS = [
    ("5", "show_myview", "My View"),
]
```

---

## 参考资料

- [PEP 768 - 安全外部调试器](https://peps.python.org/pep-0768/)
- [PEP 669 - 低开销监控](https://peps.python.org/pep-0669/)
- [simpleeval 文档](https://github.com/danthedeckie/simpleeval)
