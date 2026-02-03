# Peeka

基于 Python 3.14 远程调试协议（PEP 768）的运行时诊断工具，提供类似 Java Arthas 的非侵入式函数观测能力。

## 项目背景

Peeka 是一个为 Python 开发者提供生产环境实时诊断能力的工具。传统的 Python 调试方法通常需要在代码中显式插入调试语句，或使用
IDE 断点调试，这些方法在开发环境有效，但在生产环境难以应用。

生产环境的诊断需求具有其特殊性：

- **不能停止服务**：避免影响用户体验和业务连续性
- **间歇性问题**：需要在真实生产负载下观测
- **高效诊断**：应对生产环境的高数据量和调用频率

Peeka 正是为解决这些生产环境诊断难题而设计，提供非侵入式诊断能力，在不修改目标代码的情况下实时观测和诊断应用行为。

## 核心特性

### 非侵入式观测

- 无需修改目标代码
- 运行时动态注入观测逻辑
- 诊断结束后完全恢复原状

### 实时诊断

- 毫秒级数据传输延迟
- 流式观测数据推送
- 支持 JSON 格式输出，便于与其他工具集成

### 生产可用

- 性能开销 < 5%
- 完善的异常捕获和恢复机制
- 固定内存缓冲，防止内存膨胀

### 条件过滤

- 支持安全的表达式过滤（基于 simpleeval）
- 灵活的过滤语法（参数、返回值、执行时间等）
- 阻止所有代码注入攻击（`__import__`、`eval`、`exec` 等）

## 设计目标

Peeka Agent 的设计遵循以下核心目标：

### 低侵入性

Agent 的运行不显著影响目标进程的性能和功能。根据业界经验，生产环境诊断工具的性能开销应控制在 5% 以内。Peeka
通过精心设计的装饰器注入机制和观测数据缓冲策略，确保诊断操作对目标进程的影响最小化。

### 高可靠性

Agent 必须在各种异常情况下保持稳定运行，不因自身错误导致目标进程崩溃或异常。设计时特别关注资源管理问题，包括内存使用、文件描述符、线程等系统资源的正确释放，避免资源泄漏导致的长期稳定性问题。

### 实时性

诊断数据能够实时传输到客户端，使开发者立即观察到目标进程的行为变化。这对于定位间歇性问题尤为重要。Peeka 采用基于 Unix
Domain Socket 的流式通信协议，实现了毫秒级的数据传输延迟。

### 可扩展性

Agent 架构能够方便地支持新的诊断命令和功能扩展，而不需要大规模重构现有代码。采用模块化设计，将通信、命令执行、观测等关注点分离，通过清晰定义的接口进行交互。

## 技术基础

### Python 3.14 远程调试协议（PEP 768）

核心的 `sys.remote_exec(pid, script_path)` 函数是整个系统运作的关键，它封装了复杂的进程附加、代码注入和执行调度逻辑。通过这一函数，Peeka
能够将 Agent 代码安全地注入到目标进程中，并启动监听服务准备接收诊断命令。

**Python < 3.14 降级方案**：对于旧版本 Python，使用 GDB + ptrace 机制（参考 pyrasite）：

1. GDB 通过 ptrace 附加到目标进程
2. 调用 `PyGILState_Ensure()` 获取 GIL
3. 调用 `PyRun_SimpleString()` 执行 Agent 代码
4. 调用 `PyGILState_Release()` 释放 GIL
5. GDB 分离，进程继续运行

**要求**：

- GDB 7.3+
- Python 调试符号（python3-dbg 或 python3-debuginfo）
- CAP_SYS_PTRACE 或相同 UID
- ptrace_scope <= 1

### Unix Domain Socket

采用 Unix Domain Socket 作为进程间通信的主要机制。相比网络套接字，Unix Domain Socket 具有：

- **更高传输效率**：不需要经过网络协议栈
- **更强安全性**：仅限本地进程使用
- **简单可靠**：长度前缀 + JSON 格式

### 安全的条件表达式评估

基于 simpleeval 库实现安全的条件过滤：

- **AST 白名单**：只允许安全操作（比较、算术、逻辑）
- **属性保护**：阻止 `__class__`、`__subclasses__` 等反射攻击
- **函数黑名单**：禁用 `eval`、`compile`、`open`、`exec`、`__import__`

## 快速开始

### 安装

```bash
pip install peeka
```

### 基本使用

1. **附加到目标进程**

```bash
peeka-cli attach <pid>
```

2. **观测函数调用**

```bash
# 观测 5 次调用
peeka-cli watch <pid> "module.Class.method" --times 5

# 条件过滤
peeka-cli watch <pid> "module.Class.method" --condition "len(params) > 2"

# 实时流式观测
peeka-cli watch <pid> "module.Class.method"
```

3. **数据处理**

```bash
# 使用 jq 提取结果
peeka-cli watch <pid> "module.func" | jq 'select(.type == "observation") | .data.result'

# 筛选慢调用
peeka-cli watch <pid> "module.func" | jq 'select(.type == "observation" and .data.duration_ms > 1)'

# 保存到文件
peeka-cli watch <pid> "module.func" > observations.jsonl
```

## 输出格式规范

Peeka 所有命令均输出 **JSONL 格式**（每行一个 JSON 对象），每个对象包含 `type` 字段用于标识消息类型。

### 消息类型

| 类型 | 说明 | 示例命令 |
|------|------|----------|
| `status` | 状态/进度信息（非关键） | attach |
| `success` | 命令成功完成 | attach, detach |
| `error` | 命令失败，包含错误详情 | 所有命令 |
| `event` | 控制事件（started, stopped 等） | watch, stack, monitor |
| `observation` | 实时观测数据（函数调用） | watch, stack, monitor |
| `result` | 查询结果（非流式命令） | logger, memory, sc, sm, reset |

### 输出格式示例

#### status - 状态信息
```json
{"type": "status", "level": "info", "message": "Attaching to process 12345"}
```

#### success - 成功响应
```json
{"type": "success", "command": "attach", "data": {"pid": 12345, "socket": "/tmp/peeka_xxx.sock"}}
```

#### error - 错误响应
```json
{"type": "error", "command": "watch", "error": "Cannot find target: invalid.pattern"}
```

#### event - 控制事件
```json
{"type": "event", "event": "watch_started", "data": {"watch_id": "watch_001", "pattern": "module.func"}}
```

#### observation - 观测数据
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

#### result - 查询结果
```json
{"type": "result", "command": "logger", "data": {"status": "success", "loggers": [...]}}
```

### 解析输出示例

#### Python 解析
```python
import json
import subprocess

proc = subprocess.Popen(
    ["peeka", "watch", "12345", "module.func"],
    stdout=subprocess.PIPE,
    text=True
)

for line in proc.stdout:
    msg = json.loads(line)
    
    if msg["type"] == "observation":
        print(f"Call #{msg['count']}: {msg['func_name']} -> {msg.get('result')}")
    elif msg["type"] == "error":
        print(f"Error: {msg['error']}")
        break
```

#### Bash + jq 解析
```bash
# 只显示观测数据
peeka-cli watch 12345 "module.func" | jq 'select(.type == "observation")'

# 提取函数返回值
peeka-cli watch 12345 "module.func" | jq 'select(.type == "observation") | .result'

# 过滤慢调用（>10ms）
peeka-cli watch 12345 "module.func" | jq 'select(.type == "observation" and .duration_ms > 10)'

# 统计成功率
peeka-cli watch 12345 "module.func" | \
  jq -r 'select(.type == "observation") | if .success then "OK" else "ERROR" end' | \
  uniq -c

# 只显示错误信息
peeka-cli watch 12345 "module.func" | jq 'select(.type == "error")'
```

## 使用示例

### 观测函数调用

```bash
# 启动演示应用
$ python examples/demo.py --mode loop
当前进程 PID: 12345

# 在另一个终端观测
$ peeka-cli attach 12345
{"type":"status","level":"info","message":"Attaching to process 12345"}
{"type":"success","command":"attach","data":{"pid":12345,"socket":"/tmp/peeka_xxx.sock"}}

$ peeka-cli watch 12345 "demo.Calculator.add" --times 5
{"type":"event","event":"watch_started","data":{"watch_id":"watch_001","pattern":"demo.Calculator.add"}}
{"type":"observation","watch_id":"watch_001","timestamp":1705586200.123,"func_name":"demo.Calculator.add","args":[1,2],"result":3,"success":true,"duration_ms":0.123,"count":1}
{"type":"observation","watch_id":"watch_001","timestamp":1705586200.456,"func_name":"demo.Calculator.add","args":[3,4],"result":7,"success":true,"duration_ms":0.087,"count":2}
...
```

### 条件过滤

```bash
# 只观测第一个参数大于 100 的调用
$ peeka-cli watch 12345 "demo.Calculator.multiply" --condition "params[0] > 100"
```

支持的条件语法：

```python
len(params) > 2  # 参数数量
kwargs.get('debug') == True  # 关键字参数
x + y > 10  # 算术表达式
str(x).startswith('prefix')  # 字符串操作
params[0] == 'value'  # 索引访问
```

### 与其他工具集成

```bash
# 统计调用次数（只计算观测数据）
$ peeka-cli watch 12345 "module.func" | jq 'select(.type == "observation")' | wc -l

# 分析耗时分布
$ peeka-cli watch 12345 "module.func" | \
  jq 'select(.type == "observation") | .duration_ms' | \
  awk '{sum+=$1; count++} END {print "avg:", sum/count}'

# 实时监控错误率
$ peeka-cli watch 12345 "module.func" | \
  jq -r 'select(.type == "observation") | if .success then "OK" else "ERROR" end' | \
  uniq -c
```

## 命令参考

Peeka 提供多个强大的诊断命令，每个命令都有详细的使用文档。

### 命令概览

| 命令        | 功能                  | 文档链接                    |
|-----------|---------------------|-------------------------|
| `attach`  | 附加到目标进程             | 见下方                     |
| `watch`   | 观测函数调用（参数、返回值、执行时间） | [详细文档](docs/watch.md)   |
| `stack`   | 追踪函数调用栈             | [详细文档](docs/stack.md)   |
| `reset`   | 重置增强恢复原函数           | [详细文档](docs/reset.md)   |
| `logger`  | 动态调整日志级别            | [详细文档](docs/logger.md)  |
| `monitor` | 性能统计监控              | [详细文档](docs/monitor.md) |
| `memory`  | 内存分析                | [详细文档](docs/memory.md)  |
| `inspect` | 运行时对象检查             | [详细文档](docs/inspect.md) |
| `sc`      | 搜索类                 | [详细文档](docs/search.md)  |
| `sm`      | 搜索方法                | [详细文档](docs/search.md)  |

### attach - 附加到目标进程

```bash
peeka-cli attach <pid>
```

### watch - 观测函数调用

```bash
peeka-cli watch <pid> <pattern> [options]
```

**参数**：

| 参数            | 说明             | 默认值 |
|---------------|----------------|-----|
| `--depth, -x` | 输出深度           | 2   |
| `--times, -n` | 观测次数 (-1 表示无限) | -1  |
| `--condition` | 条件表达式          | 无   |
| `-b` | 在函数入口观测 | - |
| `-s` | 仅在成功时观测 | - |
| `-e` | 仅在异常时观测 | - |
| `-f` | 观测成功和异常（默认） | 是 |

**pattern 格式**：`module.Class.method` 或 `module.function`

**更多详情**：参见 [watch 命令详解](docs/watch.md)

### stack - 追踪调用栈

```bash
peeka-cli stack <pid> <pattern> [options]
```

捕获函数被调用时的完整调用栈，用于追踪调用来源。

**更多详情**：参见 [stack 命令详解](docs/stack.md)

### logger - 动态调整日志级别

```bash
peeka-cli logger <pid> [--action {list,get,set}] [options]
```

运行时查看和修改 logger 的日志级别，无需重启进程。

**更多详情**：参见 [logger 命令详解](docs/logger.md)

### monitor - 性能统计

```bash
peeka-cli monitor <pid> <pattern> [--interval SECONDS] [-c CYCLES]
```

定期输出函数性能统计（调用次数、成功率、响应时间）。

**更多详情**：参见 [monitor 命令详解](docs/monitor.md)

### memory - 内存分析

```bash
peeka-cli memory <pid> [--action {overview,start,stop,top,dump,gc}] [options]
```

分析进程内存使用情况和内存分配。

**更多详情**：参见 [memory 命令详解](docs/memory.md)

### sc / sm - 搜索类和方法

```bash
peeka-cli sc <pid> <pattern>  # 搜索类
peeka-cli sm <pid> <pattern>  # 搜索方法
```

在运行中的进程中搜索类和方法，用于代码探索。

**更多详情**：参见 [search 命令详解](docs/search.md)

## 环境变量

| 变量                  | 说明       | 默认值     |
|---------------------|----------|---------|
| `PEEKA_SOCKET_DIR`  | 套接字文件目录  | `/tmp`  |
| `PEEKA_TIMEOUT`     | 命令超时（秒）  | `30`    |
| `PEEKA_BUFFER_SIZE` | 观测数据缓冲大小 | `10000` |

## 安全考虑

### 进程附加权限

**Python 3.14+**:

- 使用 PEP 768 `sys.remote_exec()`
- 需要相同 UID 或 CAP_SYS_PTRACE

**Python < 3.14**:

- 使用 GDB + ptrace 降级方案
- 需要 GDB 和 Python 调试符号
- 需要相同 UID 或 CAP_SYS_PTRACE
- ptrace_scope 必须 <= 1

**Docker 容器**:

```bash
docker run --cap-add=SYS_PTRACE your-image
```

**临时放宽 ptrace 限制**（测试用）:
```bash
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

## 故障排除

### 附加失败（权限不足）

```bash
# Python < 3.14 使用 GDB 需要额外安装调试符号
# Debian/Ubuntu
sudo apt-get install gdb python3-dbg

# RHEL/Fedora
sudo yum install gdb python3-debuginfo

# 临时放宽 ptrace 限制
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# SELinux 系统（Fedora/RHEL）
sudo setsebool -P deny_ptrace=off
```

### 观测不到数据

- 检查函数名是否正确（使用完整限定名）
- 确认函数是否被调用
- 检查条件表达式是否过于严格

### 目标进程行为异常

```bash
# 停止观测
peeka-cli watch --action stop <watch_id>

# 如果持续异常，重启目标进程
```

## 架构文档

详细架构设计见 [AGENTS.md](AGENTS.md)

## 开发计划

- [ ] 线程诊断 (`ThreadCommand`)
- [ ] 内存分析 (`MemoryCommand`)
- [ ] 对象观测（跟踪对象生命周期）
- [ ] 火焰图生成
- [ ] Web UI

## 许可证

MIT License

## 致谢

- 灵感来源：[Alibaba Arthas](https://github.com/alibaba/arthas)
- 安全评估：[simpleeval](https://github.com/danthedeckie/simpleeval)
- 远程调试协议：[PEP 768](https://peps.python.org/pep-0768/)
