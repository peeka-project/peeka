---
layout: default
title: 首页
nav_order: 1
description: "Peeka - Python 运行时诊断工具，提供非侵入式函数观测能力"
permalink: /
---

# Peeka
{: .fs-9 }

> *Peek-a-boo!* — 名字取自躲猫猫游戏。诊断工具发现隐藏 bug 的那一刻，像极了捉迷藏时突然现身的惊喜。

基于 Python 3.14 远程调试协议（PEP 768）的运行时诊断工具，提供非侵入式函数观测能力。
{: .fs-6 .fw-300 }

[快速开始](#快速开始){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[在 GitHub 上查看](https://github.com/wwulfric/peeka){: .btn .fs-5 .mb-4 .mb-md-0 }

---

{: .note }
> 🌐 **Language / 语言**: This documentation is also available in [English](/peeka/en/).
>
> 本文档也提供[英文版本](/peeka/en/)。

---

## 什么是 Peeka？

Peeka 是一个为 Python 开发者提供生产环境实时诊断能力的工具。它可以在**不修改目标代码**的情况下，动态观测和诊断运行中的 Python 应用。

### 为什么需要 Peeka？

传统的 Python 调试方法在生产环境面临诸多挑战：

- **不能停止服务** - 断点调试会阻塞进程
- **间歇性问题** - 需要在真实负载下观测
- **代码修改困难** - 生产环境无法随意部署

Peeka 专为解决这些生产环境诊断难题而设计。

---

## 核心特性

### 🔍 非侵入式观测
{: .text-delta }

- 无需修改目标代码
- 运行时动态注入观测逻辑
- 诊断结束后完全恢复原状

### ⚡ 实时诊断
{: .text-delta }

- 毫秒级数据传输延迟
- 流式观测数据推送
- 支持 JSON 格式输出，便于与其他工具集成

### 🛡️ 生产可用
{: .text-delta }

- 性能开销 < 5%
- 完善的异常捕获和恢复机制
- 固定内存缓冲，防止内存膨胀

### 🎯 条件过滤
{: .text-delta }

- 支持安全的表达式过滤（基于 simpleeval）
- 灵活的过滤语法（参数、返回值、执行时间等）
- 阻止所有代码注入攻击（`__import__`、`eval`、`exec` 等）

---

## 快速开始

### 安装

```bash
pip install peeka
```

### 基本使用

#### 1. 附加到目标进程

```bash
peeka-cli attach <pid>
```

#### 2. 观测函数调用

```bash
# 观测 5 次调用
peeka-cli watch "module.Class.method" --times 5

# 条件过滤
peeka-cli watch "module.Class.method" --condition "len(params) > 2"

# 实时流式观测
peeka-cli watch "module.Class.method"
```

#### 3. 数据处理

```bash
# 使用 jq 提取结果
peeka-cli watch "module.func" | jq 'select(.type == "observation") | .data.result'

# 筛选慢调用
peeka-cli watch "module.func" | jq 'select(.type == "observation" and .data.duration_ms > 1)'
```

---

## 主要功能

| 命令 | 功能 | 状态 |
|------|------|------|
| `attach` | 附加到目标进程 | ✅ |
| `watch` | 观测函数调用（参数、返回值、执行时间） | ✅ |
| `trace` | 追踪函数调用链和执行耗时 | ✅ |
| `stack` | 追踪函数调用栈 | ✅ |
| `monitor` | 性能统计监控 | ✅ |
| `logger` | 动态调整日志级别 | ✅ |
| `memory` | 内存分析 | ✅ |
| `inspect` | 运行时对象检查 | ✅ |
| `sc/sm` | 搜索类和方法 | ✅ |
| `reset` | 重置增强 | ✅ |
| `thread` | 线程分析 | ✅ |
| `top` | 函数级性能采样 | ✅ |
| `detach` | 安全断开连接 | ✅ |

[查看完整命令参考]({% link commands/index.md %}){: .btn .btn-outline }

### 🎨 TUI 交互式界面
{: .text-delta }

除了 CLI 命令行工具，Peeka 还提供功能完整的 TUI（文本用户界面）：

- **进程选择器** - 自动显示系统进程列表，支持搜索过滤
- **10 个专用视图** - Dashboard、Watch、Trace、Stack、Monitor、Logger、Memory、Inspect、Threads、Top
- **实时数据流** - 流式显示观测数据，支持暂停/继续/清屏
- **自动补全** - 动态获取目标进程的类和方法列表
- **主题支持** - 内置多种配色主题

```bash
# 启动 TUI
peeka

# 使用数字键切换视图
# 1/2/3/4/5/6/7/8/9/0
```

[查看 TUI 完整使用指南]({% link tui.md %}){: .btn .btn-outline }

---

---

## 技术亮点

### Python 3.14 远程调试协议（PEP 768）

核心的 `sys.remote_exec(pid, script_path)` 函数是整个系统运作的关键，它封装了复杂的进程附加、代码注入和执行调度逻辑。

**Python < 3.14 降级方案**：对于旧版本 Python，使用 GDB + ptrace 机制（参考 pyrasite）。

### Unix Domain Socket

采用 Unix Domain Socket 作为进程间通信的主要机制：

- 更高传输效率 - 不需要经过网络协议栈
- 更强安全性 - 仅限本地进程使用
- 简单可靠 - 长度前缀 + JSON 格式

### 安全的条件表达式评估

基于 simpleeval 库实现安全的条件过滤：

- AST 白名单 - 只允许安全操作
- 属性保护 - 阻止反射攻击
- 函数黑名单 - 禁用危险函数

[了解架构设计]({% link architecture.md %}){: .btn .btn-outline }

---

## 支持的 Python 版本

| Python 版本 | 附加机制 | 要求 |
|------------|---------|------|
| 3.14+ | PEP 768 `sys.remote_exec` | 无 |
| 3.9-3.13 | GDB + ptrace 降级方案 | GDB, python3-dbg, CAP_SYS_PTRACE |

---

## 开源协议

Peeka 基于 [Apache License 2.0](https://github.com/wwulfric/peeka/blob/main/LICENSE) 开源。

---

## 致谢

- 安全评估：[simpleeval](https://github.com/danthedeckie/simpleeval)
- 安全评估：[simpleeval](https://github.com/danthedeckie/simpleeval)
- 远程调试协议：[PEP 768](https://peps.python.org/pep-0768/)
