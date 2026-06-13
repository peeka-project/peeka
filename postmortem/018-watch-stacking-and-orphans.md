# Watch 嵌套堆叠与孤立清理问题复盘

| 字段 | 值 |
|------|-----|
| **话题** | Watch 探针在重叠 pattern 下的堆叠顺序、归属权管理与孤立清理安全性 |
| **受影响组件** | core/injector, core/instrumentation/registry |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 3 |
| **时间跨度** | 2026-06-13 至 2026-06-13 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#3](#事故-3watch-探针恢复逻辑在非线性卸载下破坏堆叠) | Watch 探针恢复逻辑在非线性卸载下破坏堆叠 | SEV-1 | 2026-06-13 |
| [#2](#事故-2liveness-检查异常导致孤立探针被误清理) | Liveness 检查异常导致孤立探针被误清理 | SEV-2 | 2026-06-13 |
| [#1](#事故-1多个会话重叠-watch-导致归属权与卸载混乱) | 多个会话重叠 Watch 导致归属权与卸载混乱 | SEV-1 | 2026-06-13 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题聚焦于 Peeka 的“探针堆叠”设计。当多个用户或会话同时 `watch` 同一个函数时，Peeka 采用类似于 Python 装饰器的堆叠机制。事故暴露了该机制在三个方面的脆弱性：卸载时的原始函数恢复逻辑（简单恢复导致中间层丢失）、孤立探针清理的安全性（异常路径误杀）、以及缺乏显式的堆叠组（group）管理导致的归属权漂移。

---

## 事故 #3：Watch 探针恢复逻辑在非线性卸载下破坏堆叠

> **Tag 范围**：`v0.1.16` → `v0.1.17` | **严重级别**：SEV-1 | **日期**：2026-06-13

### 概要

当多个 watch 探针堆叠在同一函数上时，如果先卸载“中间”的一个探针，会导致整个堆叠链断裂，甚至将函数恢复为原始状态，从而意外移除其他仍然活跃的探针。

### 根因分析

#### 类别
Logic Error

#### 分析
原卸载逻辑简单地将属性替换回该 watch ID 记录的 `original`（即注入时看到的函数）。在堆叠场景下，`original` 可能是上一个探针的 wrapper。如果卸载顺序与注入顺序不一致（非 LIFO），简单替换会导致当前堆叠顶部的函数直接跳过中间活跃层。

修复方案引入了 `_live_previous_watch_wrapper` 逻辑，通过检查 `__wrapped__` 链并比对当前依然注册的活跃探针，找到最近的一个合法 wrapper 进行恢复，确保了非线性卸载的安全性。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `c9c6634` | lufeihaidao | 2026-06-13 | fix(watch): make watch ownership and stacking safe |

> 注：虽然 c9c6634 引入了初步的 group 管理，但其卸载逻辑在 c18bcf8 中才最终修补完整。

### 复现

#### 前置条件
- 对同一函数执行两次 watch（会话 A 和会话 B）。

#### 步骤
1. 会话 A: `watch module.func`
2. 会话 B: `watch module.func`
3. 会话 A: `stop w1` (卸载第一个探针)

#### 预期行为
函数仍然保留会话 B 的探针。

#### 实际行为
函数被恢复为原始状态，会话 B 的探针虽然在注册表中，但实际上已从运行时移除（不再触发观测）。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`c18bcf8`](https://github.com/peeka-project/peeka/commit/c18bcf8) | lufeihaidao | 2026-06-13 | fix(watch): restore live wrapper stack safely |

#### 变更内容
- 实现了 `_live_previous_watch_wrapper`，递归扫描 `__wrapped__` 链以定位最近的活跃探针。
- 增强了 `uninject` 逻辑，使其在卸载中间层时能正确“缝合”剩余的堆叠链。

#### 验证
- 新增 `tests/test_watch_owner_cleanup.py` 覆盖 LIFO 和非 LIFO 卸载场景。

### 经验教训

#### 做得好的方面
- 采用了基于 `__wrapped__` 链的动态发现，而不是静态记录，增强了对外部装饰器的兼容性。

#### 可以改进的方面
- 堆叠机制的设计初衷是支持多用户，但在单用户场景下测试不足。

---

## 事故 #2：Liveness 检查异常导致孤立探针被误清理

> **Tag 范围**：`v0.1.16` → `v0.1.17` | **严重级别**：SEV-2 | **日期**：2026-06-13

### 概要

`cleanup_orphan_watches` 在调用 agent 的 liveness 检查钩子时，如果钩子抛出异常（如会话状态瞬时不可用），会默认将该会话判定为已死亡，导致正常的探针被作为“孤立探针”强制清理。

### 根因分析

#### 类别
Logic Error / Missing Validation

#### 分析
`cleanup_orphan_watches` 采用 fail-closed 逻辑：如果无法确认会话存活（包括检查过程出错），则认为它已死亡。在分布式或高负载环境下，这类瞬时错误会导致正常的诊断任务被中断。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `47171f8` | lufeihaidao | 2026-06-13 | fix(watch): cleanup abandoned orphan watches |

### 复现

#### 前置条件
- 存在活跃的 watch 探针。
- `agent.is_client_session_live` 钩子由于某种原因抛出异常。

#### 步骤
1. 启动 watch。
2. 触发孤立清理任务（通常是定时或手动触发）。
3. 钩子报错。

#### 预期行为
清理任务跳过该探针，或保持现状。

#### 实际行为
探针被立即卸载。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`2595be6`](https://github.com/peeka-project/peeka/commit/2595be6) | lufeihaidao | 2026-06-13 | fix(watch): fail-open on liveness errors, clean unused param |

#### 变更内容
- 将 liveness 检查的异常捕获修改为 `is_live = True`（fail-open）。即无法确认死亡时，默认认为其存活。

#### 验证
- 模拟钩子异常，验证探针不再被清理。

---

## 事故 #1：多个会话重叠 Watch 导致归属权与卸载混乱

> **Tag 范围**：`v0.1.16` → `v0.1.17` | **严重级别**：SEV-1 | **日期**：2026-06-13

### 概要

在引入 `client_session_id` 之前，注入器无法区分不同客户端对同一 pattern 的多次注入。当一个客户端重置或停止所有 watch 时，会意外清理掉属于其他客户端的探针。

### 根因分析

#### 类别
Logic Error / Architectural Gap

#### 分析
原始注入器注册表 `instrumented` 是平铺的，键通常是 pattern 或简单 UUID。它缺乏“堆叠组”的概念，没有记录每个 wrapper 实际上是由哪个客户端、在哪一层注入的。这导致卸载操作（特别是 `uninject_all`）缺乏细粒度的控制。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`c9c6634`](https://github.com/peeka-project/peeka/commit/c9c6634) | lufeihaidao | 2026-06-13 | fix(watch): make watch ownership and stacking safe |

#### 变更内容
- 引入 `watch_group_key` 和 `client_session_id` 元数据。
- 重构了 `uninject_all`，使其在处理共享同一个函数槽位的探针组时，能够识别并保护其他活跃会话的探针。
- 引入了 `_get_watch_wrapper_group` 来检测函数是否已被 peeka 注入。

### 经验教训

#### 可以改进的方面
- 核心资源的共享（如函数入口点）必须有明确的引用计数或组管理机制，不能简单依赖 ID 映射。
