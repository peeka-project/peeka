# Trace 数据清理与 Gevent 运行时检测问题复盘

| 字段 | 值 |
|------|-----|
| **话题** | Trace 命令在复杂运行环境下的数据安全性与运行时策略降级 |
| **受影响组件** | commands/trace, core/instrumentation/trace |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 2 |
| **时间跨度** | 2026-06-08 至 2026-06-13 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#2](#事故-2trace-运行时无法感知延迟加载的-gevent) | Trace 运行时无法感知延迟加载的 Gevent | SEV-1 | 2026-06-13 |
| [#1](#事故-1trace-调用树包含不可序列化对象导致-json-损坏) | Trace 调用树包含不可序列化对象导致 JSON 损坏 | SEV-1 | 2026-06-08 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

`trace` 命令作为 Peeka 最复杂的诊断工具，直接操作 Python 的 `sys.settrace` 或 `sys.monitoring`。该话题涉及 trace 在两个维度上的鲁棒性：数据序列化安全（防止不可序列化对象破坏通信）和环境适应性（在 gevent 被延迟加载/打补丁后的动态策略调整）。

---

## 事故 #2：Trace 运行时无法感知延迟加载的 Gevent

> **Tag 范围**：`v0.1.16` → `v0.1.17` | **严重级别**：SEV-1 | **日期**：2026-06-13

### 概要

如果目标进程在 trace 命令启动**之后**才加载并启用 gevent（延迟加载场景），trace 后端依然会尝试使用 full recursive 模式，导致 `sys.settrace` 冲突甚至进程挂起。

### 根因分析

#### 类别
Logic Error

#### 分析
Peeka 的策略选择逻辑最初仅在命令启动（`execute` 阶段）执行一次检测。然而，Python 环境是动态的，gevent 可能会在任何时间点通过 `monkey.patch_all()` 修改运行时环境。如果 trace 已经在运行，原有的递归探测后端无法自动感知这种变化并降级。

修复方案在 `trace.py` 核心 wrapper 中引入了 `effective_backend` 逻辑，在每次调用时（或通过缓存）执行 `_is_gevent_patched_now()` 检查。一旦发现 gevent 已激活，立即将该次及后续观测降级为 `wrapper_only` 模式。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `53a8aa6` | lufeihaidao | 2026-06-08 | fix(trace): runtime gevent detection with monotonic cache in wrapper |

### 复现

#### 前置条件
- 启动一个不带 gevent 的目标进程。
- 启动 `trace` 观测某个函数。
- 在目标进程中通过代码或交互式方式执行 `gevent.monkey.patch_all()`。

#### 预期行为
Trace 命令应感知到 gevent 已打补丁，并上报降级元数据。

#### 实际行为
Trace 仍然尝试使用 `sys.settrace`（如果使用的是 legacy 后端），导致与 gevent 的内部 tracer 冲突。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`53a8aa6`](https://github.com/peeka-project/peeka/commit/53a8aa6) | lufeihaidao | 2026-06-08 | fix(trace): runtime gevent detection with monotonic cache in wrapper |

#### 变更内容
- 在 `TraceCommand` 中新增 `_runtime_meta_for_downgrade` 用于上报降级状态。
- 在 instrumentation wrapper 中引入 `effective_backend` 逻辑，实时检测 gevent 补丁状态。
- 使用单向（monotonic）缓存：一旦检测到 gevent 已补丁，永久保持该状态以减少开销。

---

## 事故 #1：Trace 调用树包含不可序列化对象导致 JSON 损坏

> **Tag 范围**：`v0.1.16` → `v0.1.17` | **严重级别**：SEV-1 | **日期**：2026-06-08

### 概要

`trace` 调用树的根节点意外包含了 `_result`（原始返回值）或 `_exception`（原始异常对象）。当这些对象不可 JSON 序列化时（如包含文件句柄或自定义 C 对象），会导致 Agent 编码失败并断开连接。

### 根因分析

#### 类别
Logic Error / Type Error

#### 分析
Trace 后端为了支持 wrapper 返回/抛出正确的值，会在调用树节点中暂存原始结果。然而，这些内部字段不应流向输出层。原实现未能在序列化前彻底清理这些字段。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`acc0f3c`](https://github.com/peeka-project/peeka/commit/acc0f3c) | lufeihaidao | 2026-06-08 | fix(trace): strip internal fields from observation call_tree |

#### 变更内容
- 引入 `_sanitize_call_tree_node` 函数，显式剥离 `_result`、`_exception` 和 `_code`。
- 将 `_exception` 转换为可序列化的字典（包含类型和消息）。
- 在观测数据入队前进行“浅拷贝+清理”操作。

#### 验证
- 新增 `tests/test_trace_observation_clean.py`，使用不可序列化对象（如 `threading.Lock()`）作为返回值进行测试。

### 经验教训

#### 做得好的方面
- 在剥离原始异常的同时，保留了其类型和消息，确保了诊断信息的完整性。
- 通过浅拷贝隔离了内部状态与输出数据，避免了竞态条件。
