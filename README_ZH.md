# Peeka

[English Documentation](README.md)

基于 Python 3.14 远程调试协议（PEP 768）的运行时诊断工具，提供类似 Java Arthas 的非侵入式函数观测能力。

## 核心特性

- **非侵入式**：无需修改目标代码，运行时动态注入观测逻辑
- **实时诊断**：毫秒级数据传输延迟，流式观测数据推送
- **生产可用**：性能开销 < 5%，完善的异常捕获和恢复机制
- **安全可靠**：基于 simpleeval 的安全表达式过滤（AST 白名单，阻止代码注入）
- **条件过滤**：灵活的过滤语法（参数、返回值、执行时间等）

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
peeka-cli watch "module.Class.method" --times 5

# 条件过滤
peeka-cli watch "module.Class.method" --condition "len(params) > 2"

# 实时流式观测
peeka-cli watch "module.Class.method"
```

3. **数据处理**

```bash
# 使用 jq 提取结果
peeka-cli watch "module.func" | jq 'select(.type == "observation") | .data.result'

# 筛选慢调用
peeka-cli watch "module.func" | jq 'select(.type == "observation" and .data.duration_ms > 1)'

# 保存到文件
peeka-cli watch "module.func" > observations.jsonl
```

## 输出格式

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

### 输出示例

**observation - 观测数据**:
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

## 命令参考

| 命令 | 功能 | 文档链接 |
|------|------|----------|
| `attach` | 附加到目标进程 | [📖 文档](https://wwulfric.github.io/peeka/commands/attach.html) |
| `watch` | 观测函数调用（参数、返回值、执行时间） | [📖 文档](https://wwulfric.github.io/peeka/commands/watch.html) |
| `trace` | 追踪函数调用链和执行耗时 | [📖 文档](https://wwulfric.github.io/peeka/commands/trace.html) |
| `stack` | 追踪函数调用栈 | [📖 文档](https://wwulfric.github.io/peeka/commands/stack.html) |
| `reset` | 重置增强恢复原函数 | [📖 文档](https://wwulfric.github.io/peeka/commands/reset.html) |
| `logger` | 动态调整日志级别 | [📖 文档](https://wwulfric.github.io/peeka/commands/logger.html) |
| `monitor` | 性能统计监控 | [📖 文档](https://wwulfric.github.io/peeka/commands/monitor.html) |
| `memory` | 内存分析 | [📖 文档](https://wwulfric.github.io/peeka/commands/memory.html) |
| `inspect` | 运行时对象检查 | [📖 文档](https://wwulfric.github.io/peeka/commands/inspect.html) |
| `sc` | 搜索类 | [📖 文档](https://wwulfric.github.io/peeka/commands/search.html) |
| `sm` | 搜索方法 | [📖 文档](https://wwulfric.github.io/peeka/commands/search.html) |

详细命令使用见 [命令参考文档](https://wwulfric.github.io/peeka/commands/)。

## 技术基础

### Python 3.14 远程调试协议（PEP 768）

核心的 `sys.remote_exec(pid, script_path)` 函数实现安全的进程代码注入。

**Python < 3.14 降级方案**：使用 GDB + ptrace 机制：
- 要求 GDB 7.3+，Python 调试符号（python3-dbg 或 python3-debuginfo）
- 要求 CAP_SYS_PTRACE 或相同 UID
- ptrace_scope 必须 <= 1

### 通信机制

- **Unix Domain Socket**：高效、安全的本地进程间通信
- **消息格式**：长度前缀 + JSON，结构化、可扩展

### 安全设计

- **安全表达式评估**：使用 simpleeval，AST 白名单
- **阻止代码注入**：禁止 `__import__`、`eval`、`exec` 等
- **资源限制**：固定内存缓冲，连接超时

## Python 版本支持

| 版本  | 附加机制          | 要求                     |
|----------|---------------------------|----------------------------------|
| 3.14+    | PEP 768 `sys.remote_exec` | 无                             |
| 3.9-3.13 | GDB + ptrace 降级方案     | GDB, python3-dbg, CAP_SYS_PTRACE |

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

## 与 Arthas 功能对比

Peeka 的设计深受 [Alibaba Arthas](https://github.com/alibaba/arthas) 启发，为 Python 生态系统带来了类似的诊断能力。

### 已实现的功能

| 功能 | Peeka | Arthas |
|------|-------|--------|
| **watch 命令** | ✅ | ✅ |
| 观测点控制 | `-b/-e/-s/-f` | `-b/-e/-s/-f` |
| 条件过滤 | `--condition-express` | `--condition-express` |
| 耗时过滤 | `cost > 100` | `#cost>100` |
| **trace 命令** | ✅ | ✅ |
| 调用树展示 | ✅ | ✅ |
| **stack 命令** | ✅ | ✅ |
| **monitor 命令** | ✅ | ✅ |
| **logger 命令** | ✅ | ✅ |
| **sc/sm 命令** | ✅ | ✅ |

### Python 特有优势

- **原生 JSON 输出**：所有命令输出 JSONL 格式，便于自动化集成
- **simpleeval 安全沙箱**：AST 白名单，完全防御代码注入
- **Python 3.12+ 性能优化**：使用 `sys.monitoring` API，性能开销 < 5%
- **轻量级部署**：无需 Java 运行时，pip 一键安装

详细对比见 [docs/comparison.md](docs/comparison.md)。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `PEEKA_SOCKET_DIR` | 套接字文件目录 | `/tmp` |
| `PEEKA_TIMEOUT` | 命令超时（秒） | `30` |
| `PEEKA_BUFFER_SIZE` | 观测数据缓冲大小 | `10000` |

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

更多故障排除技巧见 [docs/troubleshooting.md](docs/troubleshooting.md)。

## 文档

- [📚 完整文档](https://wwulfric.github.io/peeka/) - 完整的文档站点
- [架构设计](docs/ARCHITECTURE.md) - 系统架构和设计
- [使用示例](docs/examples.md) - 实际使用示例
- [与 Arthas 对比](docs/comparison.md) - 功能对比
- [故障排除](docs/troubleshooting.md) - 常见问题和解决方案
- [开发指南](AGENTS.md) - 开发者指南

## 许可证

MIT License

## 致谢

- 灵感来源：[Alibaba Arthas](https://github.com/alibaba/arthas)
- 安全评估：[simpleeval](https://github.com/danthedeckie/simpleeval)
- 远程调试协议：[PEP 768](https://peps.python.org/pep-0768/)
