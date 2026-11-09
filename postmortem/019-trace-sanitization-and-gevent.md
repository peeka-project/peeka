# Trace 数据清理与 Gevent 运行时检测问题复盘

| 字段 | 值 |
|------|-----|
| **话题** | Trace 命令在复杂运行环境下的数据安全性与运行时策略降级 |
| **受影响组件** | commands/trace, core/instrumentation/trace |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 3 |
| **时间跨度** | 2026-06-08 至 2026-11-07 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#3](#事故-3gevent-下-trace-后端策略收窄后丢失-runtime_meta) | gevent 下 trace 后端策略收窄后丢失 runtime_meta | SEV-2 | 2026-11-07 |
| [#2](#事故-2trace-运行时无法感知延迟加载的-gevent) | Trace 运行时无法感知延迟加载的 Gevent | SEV-1 | 2026-06-13 |
| [#1](#事故-1trace-调用树包含不可序列化对象导致-json-损坏) | Trace 调用树包含不可序列化对象导致 JSON 损坏 | SEV-1 | 2026-06-08 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

`trace` 命令作为 Peeka 最复杂的诊断工具，直接操作 Python 的 `sys.settrace` 或 `sys.monitoring`。该话题涉及 trace 在两个维度上的鲁棒性：数据序列化安全（防止不可序列化对象破坏通信）和环境适应性（在 gevent 被延迟加载/打补丁后的动态策略调整）。


v0.1.21 允许 Python 3.12+ 的 gevent 应用使用 `sys.monitoring` 精确 trace（事故 #3）；版本相关的降级与元数据上报应以“是否使用 monitoring”这一能力为条件。

---

## 事故 #3：gevent 下 trace 后端策略收窄后丢失 runtime_meta

> **Tag 范围**：`v0.1.20` → `v0.1.21` | **严重级别**：SEV-2 | **日期**：2026-11-07

### 概要

为让 Python 3.12+ 的 gevent 应用使用 `sys.monitoring` 精确 trace，兼容矩阵与运行时降级条件被调整。降级条件被收窄为 `force_backend == settrace` 后，Python < 3.12 上的 auto 后端（`None`）和启动前已 patch 的 `wrapper_only` 路径同样不使用 `sys.monitoring`，它们的观测因此丢失了 `runtime_meta`，导致 E2E Tests 工作流中 Python 3.9 单元测试失败。

### 根因分析

#### 类别
Logic Error

#### 分析
- `28c1ca0` 在 `peeka/core/runtime/compat.py` 中为 gevent `PATCHED` / `ACTIVE_HUB` 状态改用 `_SAFE_MONITORING_ONLY`：3.12+ 选择 `sys.monitoring`，否则保持降级策略。理由是 `sys.monitoring` 按 tool 注册，不安装全局 tracer。
- `dd93aeb` 让 wrapper 内的运行时降级只作用于非 monitoring 路径，但 `runtime_meta` 的上报条件被写成了与具体 `force_backend` 值比较，而"是否使用 monitoring"才是真正的判定维度。
- 本地开发环境为 3.12+，该分支在本地不会执行，回归只在 CI 的 3.9 矩阵中暴露。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `dd93aeb` | lufeihaidao | 2026-07-06 | fix(core): only downgrade settrace backend at runtime under gevent |

### 复现

#### 前置条件
- Python 3.9，目标进程已 gevent patch。

#### 步骤
1. 对目标函数执行 `trace`（auto 后端）。
2. 检查观测中的 `runtime_meta`。

#### 预期行为
观测带有 gevent 降级 `runtime_meta`。

#### 实际行为
`runtime_meta` 缺失，相关单元测试失败（run 29217656195）。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`28c1ca0`](https://github.com/peeka-project/peeka/commit/28c1ca0) | lufeihaidao | 2026-07-06 | fix(core): allow sys.monitoring trace backend under gevent on 3.12+ |
| [`dd93aeb`](https://github.com/peeka-project/peeka/commit/dd93aeb) | lufeihaidao | 2026-07-06 | fix(core): only downgrade settrace backend at runtime under gevent |
| [`804aa34`](https://github.com/peeka-project/peeka/commit/804aa34) | lufeihaidao | 2026-11-07 | fix(trace): report gevent downgrade runtime_meta on non-monitoring path |

#### 变更内容
`runtime_meta` 的上报条件改为 `not use_monitoring`，并新增与解释器版本无关的回归测试，使 3.12+ 的本地运行也能覆盖该分支。

#### 验证
CI 3.9 / 3.12 / 3.14 矩阵通过；新增版本无关回归测试。

### 影响

- **受影响用户**：未发布，仅影响 CI；如未修复，3.12 以下的 gevent 用户会看不到降级说明。
- **数据影响**：无。

### 经验教训

#### 可以改进的方面
- 版本分支逻辑应以"能力"（是否使用 monitoring）为条件，而不是以某个具体后端取值为条件。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 版本相关分支补充可在任意解释器上运行的模拟测试 | P2 | 已完成（本次修复） |

### 预防

- **立即执行**：改动兼容矩阵时同时检查 `runtime_meta` 上报条件。
- **短期**：推送前在本地至少用 3.9 跑一次 trace / gevent 相关单元测试。

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
