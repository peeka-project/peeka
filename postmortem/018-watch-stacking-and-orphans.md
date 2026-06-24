# Watch 嵌套堆叠与孤立清理问题复盘

| 字段 | 值 |
|------|-----|
| **话题** | Watch/Trace/Stack/Monitor 探针在重叠 pattern 下的堆叠顺序、归属权管理与孤立清理安全性 |
| **受影响组件** | core/injector, core/instrumentation/registry, commands/monitor, commands/reset, cli/streaming |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 4 |
| **时间跨度** | 2026-06-13 至 2026-06-15 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#4](#事故-4混合探针与-monitor-卸载破坏-wrapper-链和别名恢复) | 混合探针与 Monitor 卸载破坏 wrapper 链和别名恢复 | SEV-1 | 2026-06-15 |
| [#3](#事故-3watch-探针恢复逻辑在非线性卸载下破坏堆叠) | Watch 探针恢复逻辑在非线性卸载下破坏堆叠 | SEV-1 | 2026-06-13 |
| [#2](#事故-2liveness-检查异常导致孤立探针被误清理) | Liveness 检查异常导致孤立探针被误清理 | SEV-2 | 2026-06-13 |
| [#1](#事故-1多个会话重叠-watch-导致归属权与卸载混乱) | 多个会话重叠 Watch 导致归属权与卸载混乱 | SEV-1 | 2026-06-13 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题聚焦于 Peeka 的“探针堆叠”设计。当多个用户或会话同时 `watch` 同一个函数时，Peeka 采用类似于 Python 装饰器的堆叠机制。事故暴露了该机制在三个方面的脆弱性：卸载时的原始函数恢复逻辑（简单恢复导致中间层丢失）、孤立探针清理的安全性（异常路径误杀）、以及缺乏显式的堆叠组（group）管理导致的归属权漂移。

v0.1.18 进一步证明该问题不局限于 watch：monitor、trace、stack 与 watch 可以共同包裹同一个函数槽位。若 monitor stop 只恢复自己记录的 `original`，或者 CLI 清理仍按 pattern 执行 broad reset，就会误杀其他活跃探针、留下 stale `__wrapped__` 链，或让模块别名指向与 canonical slot 不一致的 callable。探针生命周期必须以“共享 wrapper 链 + 资源所有者边界”为基本模型。

---

## 事故 #4：混合探针与 Monitor 卸载破坏 wrapper 链和别名恢复

> **Tag 范围**：`v0.1.17` → `v0.1.18` | **严重级别**：SEV-1 | **日期**：2026-06-15

### 概要

在 v0.1.18 生命周期加固中，watch、trace、stack 与 monitor 混合堆叠暴露出多组不变量违背：monitor stop 可能恢复到错误的下层 wrapper 或 root original；stack 起初未参与共享 wrapper group 生命周期；trace 别名未随 canonical slot 一起替换/恢复；CLI streaming cleanup 使用 pattern reset 时会停止无关 live probe。用户可见症状是某个探针停止后，其他仍显示 active 的探针不再触发观测，或别名入口与原始入口行为不一致。

### 根因分析

#### 类别
Logic Error / Resource Management

#### 分析

根因是 Peeka 的运行时 instrumentation 已经从“单探针包裹单函数”演化为“多个探针共享一个 wrapper 链”，但 monitor、stack、trace 和 CLI cleanup 各自仍保留局部假设：

1. `DecoratorInjector.inject_function()` 曾对带 `stack_depth` 的 stack probe 跳过 `wrapper_group_key` 维护，导致 stack 不参与统一 stop-order 规则。
2. `MonitorCommand._stop_monitor()` 早期以 `monitor_info["original"]` 或 `owned_root_original` 为恢复目标，不能可靠区分“仍然活跃的下层 Peeka wrapper”和“真正的 root original”。
3. trace 注入未完整复用 alias discovery/restore，模块别名在 stop/reset 后可能仍指向旧 wrapper。
4. CLI streaming cleanup 在 stop-by-id 后还执行 pattern reset，pattern 与多个探针重叠时会清理不属于本次命令的 live probe。
5. 中间 wrapper 被移除后，剩余 live wrapper 的 `__wrapped__` 链和闭包中的 `func` 仍可能指向已移除 wrapper，形成 stale chain。

关键修复包括：所有 injector-managed probe 都写入 `wrapper_group_key`；monitor stop 先找最近的 lower live wrapper；`_relink_wrapped_chain()` 切断 stale `__wrapped__`；`_retarget_wrapper_func()` 同步更新 wrapper 闭包；CLI cleanup 改为仅 stop-by-id。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 致因提交无法确定性定位 | - | 2026-06-13 至 2026-06-15 | watch 堆叠、monitor wrapper 和 trace alias 各自演化，缺少跨探针 stop-order invariant |

### 复现

#### 前置条件
- 同一目标函数可通过 canonical module path 和 alias path 调用。
- 对同一函数依次启动 watch/trace/stack/monitor 中的多个探针。

#### 步骤
1. 启动 watch `module.func`。
2. 启动 monitor `module.func`，再启动 stack 或 trace。
3. 非 LIFO 地停止 monitor 或 CLI `-n` 到达本地限制触发 cleanup。
4. 再次调用 `module.func` 与其 alias，观察剩余探针是否继续产出观测。

#### 预期行为
停止某个探针只移除该探针的 wrapper；其他 live wrapper 的调用链、别名绑定和 ProbeContext 状态保持一致。

#### 实际行为
某些路径恢复到 root original 或 stale wrapper，导致其他探针被静默绕过；pattern reset 还可能停止同 pattern 下无关 live probe。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`60c9a4c`](https://github.com/peeka-project/peeka/commit/60c9a4c845e3c309b058324d949041e8af60a546) | lufeihaidao | 2026-06-13 | fix(probes): monitor_id compat, stack wrapper lifecycle, reset monitor cleanup, alias restore |
| [`c27bea1`](https://github.com/peeka-project/peeka/commit/c27bea133eaa09144a82e571ed6e7156741d966a) | lufeihaidao | 2026-06-14 | fix(monitor): restore aliases to computed replacement |
| [`8c08a52`](https://github.com/peeka-project/peeka/commit/8c08a52406e63a3b25da71d3afd74ca1aace606c) | lufeihaidao | 2026-06-14 | fix(monitor): preserve lower live probes on stop |
| [`3775b03`](https://github.com/peeka-project/peeka/commit/3775b0333603666a4fbc9db9da2453087157ea0b) | lufeihaidao | 2026-06-15 | fix(monitor): preserve root_original and owned_root_original on stacked probe stop |
| [`79ad2d8`](https://github.com/peeka-project/peeka/commit/79ad2d84848d7bf13cb325719fe6e12efc7251a8) | lufeihaidao | 2026-06-15 | fix(lifecycle): fix all probe lifecycle invariant violations |

#### 变更内容
- Stack 不再因 `stack_depth` 跳过共享 wrapper group 元数据。
- Monitor 输出和 stop/status 同时暴露 `monitor_id` 与 legacy `watch_id`，避免 CLI/agent ID 契约漂移。
- Monitor stop 使用 `_nearest_lower_live_wrapper()` 选择 live replacement，并对 alias 使用同一个 computed replacement。
- Registry 在移除中间 wrapper 后调用 `_relink_wrapped_chain()`，避免 live wrapper 的 `__wrapped__` 指向已移除 wrapper。
- CLI streaming cleanup 移除 broad pattern reset，只发送对应 ID 的 stop command。

#### 验证
修复提交新增/调整 `tests/test_monitor.py`、`tests/test_reset.py`、`tests/test_stack.py`、`tests/test_watch_owner_cleanup.py`、`tests/test_trace.py` 等回归测试。`79ad2d8` 提交说明中记录“16 regression tests now pass. 177/177 total. Ruff clean.”

### 影响

- **受影响用户**：在同一函数上混合使用 watch/trace/stack/monitor 的用户，以及依赖 `peeka-cli ... -n` 自动停止的用户。
- **持续时间**：从共享 wrapper lifecycle 引入到 v0.1.18 修复完成；同一 release 开发周期内被回归测试发现。
- **数据影响**：无持久数据损坏；诊断观测可能静默缺失或错误停止其他会话探针。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-06-13 | `60c9a4c` 暴露 monitor/reset/stack/alias lifecycle 缺口并添加第一批回归测试 |
| 2026-06-14 | 多个 monitor stop-order 与 alias 修复陆续合入 |
| 2026-06-15 | `79ad2d8` 统一修复 probe lifecycle invariant violations |

### 经验教训

#### 做得好的方面
- 修复最终收敛到跨 probe 类型的不变量，而不是只补某个命令分支。
- 测试覆盖了 mixed probe、layered monitor、alias restore 和 CLI cleanup 等真实组合场景。

#### 可以改进的方面
- 新 probe 类型接入时没有强制通过“共享 wrapper 链”测试矩阵。
- CLI 本地限制 cleanup 把 stop-by-id 与 pattern reset 混在一起，说明“停止资源”和“重置 pattern”边界不清。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为每个 injector-managed probe 类型保留 LIFO 与非 LIFO 混合卸载测试 | P0 | 已完成 |
| CLI streaming cleanup 禁止执行 pattern reset，只允许 stop-by-id | P0 | 已完成 |
| 在设计文档中定义 wrapper group、root original、owned root original 和 alias replacement 的不变量 | P1 | 待处理 |

### 预防

- **立即执行**：新增 probe 类型必须声明是否 injector-managed，并进入 mixed stacking test matrix。
- **短期**：把 alias binding restore 纳入所有 wrapper 替换/恢复测试。
- **长期**：将 wrapper 链管理集中到单一 registry API，禁止命令各自手写恢复逻辑。

### 参考

- 修复提交：`60c9a4c`, `c27bea1`, `8c08a52`, `3775b03`, `79ad2d8`

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
