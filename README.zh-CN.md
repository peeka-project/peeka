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
  <strong>中文</strong> | <a href="README.md">English</a>
</p>

<p align="center">
  路线图：<strong>中文</strong> | <a href="ROADMAP.md">English</a>
</p>

> *Peek-a-boo!* — 名字取自躲猫猫游戏。诊断工具发现隐藏 bug 的那一刻，像极了捉迷藏时突然现身的惊喜。

Python 应用运行时诊断工具，灵感来源于 [Alibaba Arthas](https://github.com/alibaba/arthas)。无需修改代码，即可非侵入式观测函数行为。

Python 3.14+ 使用 [PEP 768](https://peps.python.org/pep-0768/)（`sys.remote_exec`），Python 3.8–3.13 使用调试器降级方案（Linux 用 GDB，macOS 用 LLDB）。

## 核心特性

- **非侵入式** — 运行时注入观测逻辑，退出时完全恢复原状
- **实时流式** — 基于 Unix Domain Socket，毫秒级数据传输延迟
- **生产可用** — 性能开销 < 5%，固定内存缓冲，完善的异常恢复机制
- **安全过滤** — 基于 [simpleeval](https://github.com/danthedeckie/simpleeval) 的条件表达式，阻止所有代码注入攻击
- **双重界面** — CLI（JSONL 输出，管道友好）和交互式 TUI

## 快速开始

### 安装

```bash
pip install peeka          # 仅 CLI（Python 3.8+）
pip install peeka[tui]     # CLI + TUI（Python 3.9+）
```

### 基本使用

```bash
# 1. 附加到目标进程
peeka-cli attach <pid>

# 2. 观测函数调用
peeka-cli watch "module.Class.method" -n 5

# 3. 条件过滤
peeka-cli watch "module.func" --condition "params[0] > 100"

# 4. 追踪调用链
peeka-cli trace "module.func" -d 3

# 5. 捕获调用栈
peeka-cli stack "module.func" -n 3

# 6. 启动 TUI
peeka
```

### 管道友好输出（JSONL）

所有 CLI 输出均为 JSONL 格式——每行一个 JSON 对象，包含 `type` 字段：

```bash
# 用 jq 过滤观测数据
peeka-cli watch "module.func" | jq 'select(.type == "observation")'

# 筛选慢调用
peeka-cli watch "module.func" | jq 'select(.type == "observation" and .data.duration_ms > 100)'

# 保存到文件
peeka-cli watch "module.func" > observations.jsonl
```

## 命令参考

| 命令      | 功能                          |
|-----------|-------------------------------|
| `attach`  | 附加到目标 Python 进程         |
| `watch`   | 观测函数调用（参数、返回值、耗时） |
| `trace`   | 追踪调用链及耗时分布           |
| `stack`   | 捕获函数入口调用栈             |
| `monitor` | 定期输出性能统计               |
| `logger`  | 运行时调整日志级别             |
| `memory`  | 内存使用分析                   |
| `inspect` | 运行时对象检查                 |
| `sc`/`sm` | 搜索类 / 搜索方法              |
| `thread`  | 线程分析与诊断                 |
| `top`     | 函数级性能采样                 |
| `reset`   | 移除所有注入的增强              |
| `detach`  | 从目标进程分离                 |
| `run`     | 从启动时注入并运行脚本          |

### watch

```bash
peeka-cli watch <pattern> [options]
```

| 参数               | 说明                            | 默认值 |
|--------------------|---------------------------------|--------|
| `-x, --depth`      | 嵌套对象输出深度                 | 2      |
| `-n, --times`      | 观测次数（-1 为无限）            | -1     |
| `--condition`       | 条件表达式（如 `params[0] > 100`、`cost > 50`） | —      |
| `-b, --before`      | 在函数入口观测                   | false  |
| `-s, --success`     | 仅在成功时观测                   | false  |
| `-e, --exception`   | 仅在异常时观测                   | false  |
| `-f, --finish`      | 观测完成时（成功或异常）          | true   |

**pattern 格式**：`module.Class.method` 或 `module.function`

### trace

```bash
peeka-cli trace <pattern> [options]
```

| 参数               | 说明                            | 默认值 |
|--------------------|---------------------------------|--------|
| `-d, --depth`      | 追踪深度（最大调用层数）          | 3      |
| `-n, --times`      | 观测次数（-1 为无限）            | -1     |
| `--condition`       | 条件表达式（如 `cost > 50`）     | —      |
| `--skip-builtin`    | 跳过内置函数和标准库              | true   |
| `--min-duration`    | 最小耗时过滤（毫秒）             | 0      |

**输出示例：**

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

| 参数               | 说明                            | 默认值 |
|--------------------|---------------------------------|--------|
| `-n, --times`      | 捕获次数（-1 为无限）            | -1     |
| `--condition`       | 条件表达式                       | —      |
| `--depth`           | 调用栈深度限制                   | 10     |

### reset

```bash
peeka-cli reset [pattern] [options]
```

| 参数          | 说明                              | 默认值 |
|---------------|-----------------------------------|--------|
| `-l, --list`  | 列出当前增强项，不执行重置         | false  |
| `pattern`     | 可选 glob 模式，过滤目标函数       | —      |

```bash
peeka-cli reset                    # 重置所有增强
peeka-cli reset "mymodule.*"       # 仅重置匹配的函数
peeka-cli reset --list             # 列出当前活跃的增强项
```

### run

从脚本启动时即注入 Peeka——适用于需要观测导入期代码或短生命周期脚本的场景。

```bash
peeka-cli run <script> [script_args] -- <command> [command_options]
```

```bash
peeka-cli run myscript.py -- watch "mymodule.func"
peeka-cli run myscript.py arg1 arg2 -- trace "mymodule.func" -d 3
peeka-cli run myscript.py -- watch "mymodule.func" --output-file out.jsonl
```

| 参数            | 说明                              | 默认值 |
|-----------------|-----------------------------------|--------|
| `--output-file` | 将 JSONL 输出写入文件而非 stdout   | —      |

## 条件表达式

基于 [simpleeval](https://github.com/danthedeckie/simpleeval) 实现安全求值：

```python
params[0] > 100              # 位置参数检查
len(params) > 2              # 参数数量
kwargs.get('debug') == True  # 关键字参数检查
cost > 50                    # 执行耗时（毫秒，仅 watch/trace 支持）
str(x).startswith('prefix')  # 字符串操作
x + y > 10                   # 算术表达式
```

可用变量：`params`（位置参数列表）、`kwargs`（关键字参数字典）、`result`（返回值，仅 finish 时）、`cost`（耗时毫秒，仅 watch/trace）。

**安全机制**：仅允许安全操作（比较、算术、逻辑），`eval`、`exec`、`__import__`、`open`、`compile` 以及 `__class__`/`__subclasses__` 等反射操作均被阻止。

## 输出格式

每行输出为一个 JSON 对象，包含 `type` 字段标识消息类型：

| 类型          | 说明                 | 相关命令                |
|---------------|----------------------|------------------------|
| `status`      | 状态/进度信息         | attach                 |
| `success`     | 命令执行成功          | attach, detach         |
| `error`       | 命令执行失败          | 所有命令                |
| `event`       | 控制事件（启动/停止）  | watch, stack, monitor  |
| `observation` | 实时观测数据          | watch, stack, monitor  |
| `result`      | 查询结果（非流式）     | logger, memory, sc, sm |

<details>
<summary>输出示例</summary>

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

## Python 版本支持

| Python 版本  | CLI | TUI | 附加机制                        | 要求                                                  |
|-------------|:---:|:---:|--------------------------------|------------------------------------------------------|
| 3.14+       | ✅  | ✅  | PEP 768 `sys.remote_exec()`   | 相同 UID 或 `CAP_SYS_PTRACE`                         |
| 3.9–3.13    | ✅  | ✅  | GDB (Linux) / LLDB (macOS)    | **Linux**: GDB 7.3+，ptrace ≤ 1<br>**macOS**: Xcode 命令行工具 |
| 3.8         | ✅  | ❌  | GDB (Linux) / LLDB (macOS)    | **Linux**: GDB 7.3+，ptrace ≤ 1<br>**macOS**: Xcode 命令行工具 |

TUI 依赖 [Textual](https://github.com/Textualize/textual)，需要 Python ≥ 3.9。

### Python < 3.14 配置

#### Linux

需要 GDB。**强烈建议安装调试符号**——部分发行版默认已包含足够的符号信息，但如果 GDB 报告 "no symbol" 错误，需要手动安装：

```bash
# Debian/Ubuntu
sudo apt-get install gdb python3-dbg

# RHEL/Fedora
sudo yum install gdb python3-debuginfo

# Arch
sudo pacman -S gdb
```

#### macOS

使用 LLDB 代替 GDB。如果尚未安装，请安装 Xcode 命令行工具：

```bash
xcode-select --install
```

LLDB 已默认包含，无需额外安装调试符号。

### Docker

```bash
docker run --cap-add=SYS_PTRACE your-image
```

### ptrace 限制（Linux）

```bash
# 查看当前设置
cat /proc/sys/kernel/yama/ptrace_scope

# 临时放宽（测试用）
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope

# SELinux 系统（Fedora/RHEL）
sudo setsebool -P deny_ptrace=off
```

**注意**：macOS 没有 ptrace_scope 限制。系统完整性保护（SIP）可能会阻止调试某些系统进程，但用户进程可以正常调试。


## 故障排除

### 附加失败（权限不足）

- 确保相同 UID 或拥有 `CAP_SYS_PTRACE`
- **Linux**：检查 `ptrace_scope`（见上文）
- **Linux**：如果 GDB 报告 "no symbol" 错误，安装调试符号
- **macOS**：确保已安装 Xcode 命令行工具（`xcode-select --install`）

### 没有观测数据

- 检查函数名是否正确（使用完整限定名：`module.Class.method`）
- 确认函数是否被调用
- 检查条件表达式是否过于严格

### 目标进程行为异常

```bash
# 移除特定函数的观测
peeka-cli reset "module.func"

# 移除所有注入的增强
peeka-cli reset

# 如果持续异常，断开连接并重启目标进程
peeka-cli detach <pid>
```

## 架构概览

```
CLI/TUI  →  AgentClient  →  Unix Socket  →  PeekaAgent（注入到目标进程）
                                              ├─ _register_handlers() → BaseCommand 子类
                                              ├─ 装饰器注入器（函数包装）
                                              └─ 观测管理器（缓冲流式传输）
```

- **进程附加**：Python 3.14+ 使用 PEP 768 `sys.remote_exec()`，3.8–3.13 使用 GDB（Linux）或 LLDB（macOS）
- **观测机制**：装饰器注入包装目标函数，捕获参数/返回值/异常/耗时
- **数据传输**：通过 Unix Domain Socket 实时流式传输观测数据（长度前缀 + JSON）
- **命令系统**：模块化 `BaseCommand` 子类，在 `PeekaAgent._register_handlers()` 中注册

## 许可证

Apache License 2.0

## 致谢

- 灵感来源：[Alibaba Arthas](https://github.com/alibaba/arthas)
- 安全评估：[simpleeval](https://github.com/danthedeckie/simpleeval)
- 远程调试协议：[PEP 768](https://peps.python.org/pep-0768/)
