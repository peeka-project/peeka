<p align="center">
  <img src="https://peeka-project.github.io/assets/images/logo.png" alt="" width="48" align="middle">&nbsp;
  <strong style="font-size:2em;">Peeka</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/peeka/"><img src="https://img.shields.io/pypi/v/peeka?color=2888a8" alt="PyPI"></a>
  <a href="https://github.com/peeka-project/peeka/releases/latest"><img src="https://img.shields.io/github/v/release/peeka-project/peeka?color=2888a8" alt="Release"></a>
  <a href="https://github.com/peeka-project/peeka/actions"><img src="https://img.shields.io/github/actions/workflow/status/peeka-project/peeka/e2e-tests.yml?label=tests" alt="Tests"></a>
  <a href="https://github.com/peeka-project/peeka/blob/master/LICENSE"><img src="https://img.shields.io/github/license/peeka-project/peeka?color=2888a8" alt="License"></a>
  <a href="https://peeka-project.github.io/"><img src="https://img.shields.io/badge/docs-peeka--project.github.io-2888a8" alt="Docs"></a>
</p>

<p align="center">
  <strong>中文</strong> | <a href="README.md">English</a>
</p>

Peeka 是面向 Python 应用的运行时诊断工具。它可以附加到正在运行的 Python 进程，在不修改业务代码的情况下观察函数调用、调用链、调用栈、日志、内存、线程和热点函数。

Python 3.14+ 使用 [PEP 768](https://peps.python.org/pep-0768/)，Python 3.8.1-3.13 使用调试器降级方案。

## 截图

| Dashboard | Watch | Trace |
|-----------|-------|-------|
| <img src="docs/assets/screenshots/peeka-dashboard.png" alt="Peeka dashboard 视图" width="320"> | <img src="docs/assets/screenshots/peeka-watch.png" alt="Peeka watch 视图" width="320"> | <img src="docs/assets/screenshots/peeka-trace.png" alt="Peeka trace 视图" width="320"> |

## 核心特性

- **非侵入式** - 运行时注入观测逻辑，detach 或 reset 时恢复原函数。
- **实时流式** - 通过 Unix Domain Socket 低延迟传输观测数据。
- **生产友好** - 使用固定大小缓冲和异常恢复机制控制运行时影响。
- **安全过滤** - 使用 `simpleeval` 求值条件表达式，不直接执行 Python `eval`。
- **双界面** - CLI 输出 JSONL 给 agent 和自动化使用，TUI 给人交互式探索。

## 适用场景

- 在线服务出问题时，日志和指标不够定位，需要直接观察运行中的函数。
- 实时查看函数入参、返回值、异常和耗时。
- 追踪一次请求或任务内部的调用链，找出耗时位置。
- 捕获调用栈、线程状态、内存摘要、日志器和运行时对象。

## 双界面

Peeka 面向两类不同的操作者：

| 界面 | 面向对象 | 存在价值 |
|------|----------|----------|
| CLI | Agent 和自动化脚本 | 稳定命令 + JSONL 输出，适合脚本、流水线和编码 agent 解析 |
| TUI | 人类使用者 | 交互式终端工作台，适合不写管道时直接探索运行时诊断数据 |

## 安装

```bash
# 仅安装 CLI：适合 agent、脚本和无头环境。
pip install peeka

# 安装 CLI + TUI：适合人类交互式排查。
pip install "peeka[tui]"
```

Peeka 支持 Python 3.8.1+。TUI 需要 Python 3.9+。

Python 3.8.1-3.13 需要调试器支持：Linux 使用 GDB，macOS 使用 LLDB。Linux 上还需要目标进程允许 ptrace 附加。

## Python 支持

| Python 版本 | CLI | TUI | 附加机制 | 主要依赖 |
|-------------|:---:|:---:|----------|----------|
| 3.14+ | 是 | 是 | PEP 768 `sys.remote_exec()` | 相同 UID 或 `CAP_SYS_PTRACE` |
| 3.9-3.13 | 是 | 是 | Linux 使用 GDB，macOS 使用 LLDB | 调试器支持和附加权限 |
| 3.8.1-3.8.x | 是 | 否 | Linux 使用 GDB，macOS 使用 LLDB | 调试器支持和附加权限 |

平台相关的安装和故障排查见 [项目文档](https://peeka-project.github.io/)。

## 快速开始

### 给 agent 和自动化使用的 CLI

```bash
# 附加到正在运行的 Python 进程
peeka-cli attach <pid>

# 观察函数调用
peeka-cli watch "module.Class.method" -n 5

# 追踪调用链
peeka-cli trace "module.func"
```

CLI 输出结构化 JSONL，agent 和脚本可以稳定解析、过滤和保存观测结果。

### 给人使用的 TUI

```bash
# 启动 TUI
peeka
```

TUI 提供交互式 dashboard，用于浏览 watch、trace、stack、memory、thread、logger 等运行时视图。

函数匹配使用完整限定名，例如 `module.function` 或 `module.Class.method`。

## 核心命令

| 命令 | 用途 |
|------|------|
| `attach` / `detach` | 连接或分离目标进程 |
| `watch` | 观察函数参数、返回值、异常和耗时 |
| `trace` | 追踪嵌套调用和耗时分布 |
| `stack` | 捕获函数入口调用栈 |
| `monitor` / `top` | 查看周期性指标和热点函数 |
| `memory` / `thread` / `logger` | 查看内存、线程和日志器 |
| `inspect` / `sc` / `sm` | 检查对象，搜索类或方法 |
| `reset` | 移除注入的观测逻辑，恢复包装函数 |
| `run` | 从脚本启动时即注入 Peeka |

## 继续阅读

- [项目文档](https://peeka-project.github.io/) - 命令参考、TUI 用法、安装细节和故障排查。
- [场景案例](docs/scenarios.md) - 面向实际问题的诊断案例教程。
- [Demo 指南](docs/demo-guide.md) - 基于 demo 应用的逐命令示例。
- [附加机制解析](docs/python-process-attach-internals.md) - Peeka 如何向运行中的 Python 解释器注入诊断能力。
- [路线图](ROADMAP.zh-CN.md) - 后续计划和产品方向。

## 许可证

Apache License 2.0

## 致谢

- 灵感来源：[Alibaba Arthas](https://github.com/alibaba/arthas)
- 安全表达式求值：[simpleeval](https://github.com/danthedeckie/simpleeval)
- Python 3.14+ 附加机制基于 [PEP 768](https://peps.python.org/pep-0768/)
