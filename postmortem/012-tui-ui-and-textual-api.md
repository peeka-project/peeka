# TUI 样式、Textual API 与交互行为问题复盘

| 字段 | 值 |
|------|-----|
| **话题** | TUI 样式可用性、Textual API 兼容、DataTable/TraceView 交互细节缺陷 |
| **受影响组件** | tui/views, tui/screens, tui/app CSS, tui/views/trace.py |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 7 |
| **时间跨度** | 2026-02-07 至 2026-07-04 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#7](#事故-7traceview-活动追踪状态选择与参数语义漂移) | TraceView 活动追踪状态、选择与参数语义漂移 | SEV-2 | 2026-07-04 |
| [#6](#事故-6自动滚动抢占光标用户无法稳定浏览历史) | 自动滚动抢占光标，用户无法稳定浏览历史 | SEV-2 | 2026-03-06 |
| [#5](#事故-5helpwatchtrace-残留-lsp-错误签名api-未同步) | help/watch/trace 残留 LSP 错误（签名/API 未同步） | SEV-3 | 2026-02-14 |
| [#4](#事故-4monitor-视图存在-7-处-update_cell_at-参数误用) | Monitor 视图存在 7 处 `update_cell_at` 参数误用 | SEV-3 | 2026-02-09 |
| [#3](#事故-3stack-视图-update_cell_at-误用导致计数更新异常) | Stack 视图 `update_cell_at` 误用导致计数更新异常 | SEV-3 | 2026-02-09 |
| [#2](#事故-2textual-api-破坏性变更导致多视图崩溃) | Textual API 破坏性变更导致多视图崩溃 | SEV-1 | 2026-02-07 |
| [#1](#事故-1tabs-与输入标签缺失样式导致可见性差) | Tabs 与输入标签缺失样式导致可见性差 | SEV-3 | 2026-02-07 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题涵盖 TUI 维度的四类问题：其一，Textual API 升级导致的兼容性断裂；其二，DataTable 更新 API 误用引发渲染异常；其三，UI/交互细节（样式、自动滚动）降低可用性；其四，TraceView 在活动追踪状态、表格选择、聚合节点数据和命令参数语义上的契约漂移。问题具有“跨视图复制扩散”和“UI 状态与 Agent 资源状态分离不足”的特征，说明组件级模式沉淀与回归测试覆盖仍需加强。

2026-07-04 的新增事故说明，流式 TUI 不仅要渲染 observation，还要把用户选择、后台 worker、Agent resource、表格行状态和快捷键行为作为同一个状态机验证。否则 Clear 看似只是清 UI，实际没有停止 trace；新 trace 启动后没有自动选中，用户看不到第一条 observation；`min_duration` 还会因 `int()` 解析而拒绝合法小数。

---

## 事故 #7：TraceView 活动追踪状态、选择与参数语义漂移

> **Tag 范围**：`v0.1.19` → `HEAD` | **严重级别**：SEV-2 | **日期**：2026-07-04

### 概要

TraceView 在 v0.1.20 开发周期内集中暴露多处交互状态漂移：Clear 按钮/快捷键只清空树和表格而不停止运行中的 trace；Active Traces 显示的计数与真实 stream 数不一致；新 trace 启动时如果没有选中 pattern，第一条 observation 不会自动渲染；`min_duration` 输入用 `int()` 解析，拒绝 `2.5ms` 这类合法阈值；聚合 callee 的 `min_ms=0.0` 还曾被当作“无数据”丢弃。

### 根因分析

#### 类别
Logic Error / Missing Validation

#### 分析

TraceView 的状态实际分为五层：Agent 端 trace resource、TUI `_active_traces`、observation 表、call tree 选中 pattern、后台 stream worker。修复前，Clear 只操作 UI 层：

```python
def action_clear_tree(self) -> None:
    tree.clear()
    obs_table.clear()
    self._observations_by_pattern.clear()
```

这会让用户误以为 trace 已停止，但 Agent 端仍继续采样。`9d5f27d` 将 `action_clear_tree()` 改为 async，并先停止 active traces，再清理 UI 状态。

另一个状态缺口是“启动后可见”：`_start_trace()` 已经向 agent 发送 start 并添加 obs table 行，但 `_selected_pattern` 为 `None` 时，后续 observation 不会进入当前 tree。`2ebdd04` 在 start 成功后自动设置 `_selected_pattern` 并移动表格光标。

参数语义方面，TraceView 输入标签写的是毫秒，backend 支持 float，但 UI 使用 `int(min_duration_input)`，导致 `2.5` 报 “Invalid min duration value”。`56f55f9` 改为 `float()` 并保留负数拒绝。

聚合展示方面，`80621e7` 修复了 `min_ms=0.0` 被 `mn > 0` 过滤掉的问题；`ab0f3cc` 修正 aggregated node 的 data type 和 `tree.cursor_node` 使用，避免 drill-down 依赖陈旧 `_last_highlighted_node`；`39a5fb2` 让 Active Traces 展示真实 `_active_traces` 数量。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 致因提交无法确定性定位 | - | 2026-06-30 前 | TraceView UI 状态、stream worker 和 Agent resource 生命周期分别演化，缺少端到端交互状态机测试 |

### 复现

#### 前置条件
- TUI 已连接 agent。
- TraceView 中至少启动一个 trace。

#### 步骤
1. 启动 `module.func` trace，然后按 `c` 或点击 Clear。
2. 检查 Agent 是否仍有 active trace resource。
3. 在没有选中任何 pattern 的状态下启动新 trace，并等待第一条 observation。
4. 在 Min Duration 输入 `2.5` 后启动 trace。
5. 构造 callee 聚合中 `min_ms=0.0` 的 observation。

#### 预期行为
Clear 同时停止 active trace 和清 UI；新 trace 自动选中并渲染 observation；小数 min duration 被透传；`0.0ms` 最小耗时被保留。

#### 实际行为
修复前 Clear 仅清 UI；未选中 pattern 时 tree 为空；`2.5` 被拒绝；`min_ms=0.0` 被丢弃；部分 drill-down 使用陈旧选中节点。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`ab0f3cc`](https://github.com/peeka-project/peeka/commit/ab0f3ccc6cb031faac8c5b7b0010a9bf8771f1c6) | lufeihaidao | 2026-06-30 | fix(tui): address F4 review feedback on exception styling, aggregate node data, and drill-down cursor |
| [`9d5f27d`](https://github.com/peeka-project/peeka/commit/9d5f27d336107e63f505c78b471c92cb8fe04f58) | lufeihaidao | 2026-07-03 | fix(tui): Clear stops running traces (button + key + test) |
| [`39a5fb2`](https://github.com/peeka-project/peeka/commit/39a5fb285c1825b9b1eb582c9e9c60a2a4866538) | lufeihaidao | 2026-07-03 | fix(tui): show real stream count in Active Traces |
| [`80621e7`](https://github.com/peeka-project/peeka/commit/80621e751611820a07f5bb3af0f7143d3ad96145) | lufeihaidao | 2026-07-03 | fix(tui): keep min_ms=0.0 in aggregated callee stats |
| [`56f55f9`](https://github.com/peeka-project/peeka/commit/56f55f919d2a780f45b951b011ef5838ab80c0dc) | lufeihaidao | 2026-07-04 | fix(tui): parse min_duration as float in trace view |
| [`2ebdd04`](https://github.com/peeka-project/peeka/commit/2ebdd0462b68211591edcdea17d2d80289098647) | lufeihaidao | 2026-07-04 | fix(tui): auto-select first trace pattern on start when none selected |

#### 变更内容
- `action_clear_tree()` 改为 async，并调用 `_stop_all_traces()` 后再清空 tree、obs table、`_observations_by_pattern` 和 `_selected_pattern`。
- Clear 按钮和 `c` key binding 都走同一 action，避免按钮/快捷键行为分叉。
- `_start_trace()` 成功后在无选中 pattern 时自动选中新 row 并移动 DataTable cursor。
- `min_duration` 改用 `float()`，默认值保持 `0.0`，负数继续拒绝。
- aggregated callee 节点写入可 drill-down 的 `aggregated_callee` data，统计中的 `min_ms=0.0` 被视为有效值。

#### 验证
`tests/tui/test_trace_view.py` 新增回归测试，覆盖 Clear 停止 active trace、`c` key binding、空 active trace 不发送 stop、真实 stream count、`min_ms=0.0`、float min duration、negative float rejection、start 后自动渲染第一条 observation。

### 影响

- **受影响用户**：使用 TUI TraceView 进行持续 trace、drill-down、聚合查看或小数阈值过滤的用户。
- **持续时间**：TraceView 聚合与交互重构后至 2026-07-04。
- **数据影响**：无持久数据损坏；风险是目标进程继续运行用户以为已停止的 trace，或 UI 展示缺失/误导。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-06-30 | `ab0f3cc` 修复 aggregated node data 和 drill-down cursor |
| 2026-07-03 | `9d5f27d`、`39a5fb2`、`80621e7` 修复 Clear、active count 和 `min_ms` |
| 2026-07-04 | `56f55f9`、`2ebdd04` 修复 float min duration 和启动后自动选择 |

### 经验教训

#### 做得好的方面
- 修复将按钮、快捷键和直接 action 调用统一到同一路径，降低交互分叉。
- 回归测试覆盖了用户可见行为，而不仅是内部字段存在。

#### 可以改进的方面
- 流式视图必须把“清 UI”和“停止远端资源”作为一个事务测试。
- TUI 输入类型应与 backend/CLI 契约共享，不应由 view 层自行假设 int/float。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为所有流式 TUI view 增加 Clear/Stop/退出时 resource cleanup 交互测试 | P0 | 待处理 |
| 将 trace 参数类型（如 `min_duration: float`）写入共享命令契约并由 TUI/CLI 共同引用 | P1 | 待处理 |
| 保留 TraceView 的 key binding 与按钮同路径测试 | P1 | 已完成 |

### 预防

- **立即执行**：流式 TUI 的 Clear 必须先停止远端 resource，再清本地 UI。
- **短期**：为 TraceView 建立状态机测试矩阵：start/observe/select/drill/clear/stop。
- **长期**：抽象 reusable streaming view controller，统一 active resource、selected row 和 cleanup 行为。

### 参考

- 修复提交：`ab0f3cc`, `9d5f27d`, `39a5fb2`, `80621e7`, `56f55f9`, `2ebdd04`

---

## 事故 #6：自动滚动抢占光标，用户无法稳定浏览历史

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-2 | **日期**：2026-03-06

### 概要

Watch/Trace 视图在流式新数据到达时始终滚到最后一行，用户选中历史行后立即被抢回，无法查看旧观测详情。

### 根因分析

#### 类别
Logic Error

#### 分析
自动滚动逻辑缺少“用户浏览历史态”状态机。每次新观测都触发滚动到底，忽略用户当前选择。

修复引入 `_auto_follow`：
- 选中最后一行：`_auto_follow = True`
- 选中非最后一行：`_auto_follow = False`

该模式已在 StackView 实践，迁移至 WatchView 与 TraceView。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 流式观测视图初版默认持续自动滚动 |

### 复现

#### 前置条件
- Watch/Trace 持续接收观测数据。

#### 步骤
1. 点击旧观测行（非最后一行）。
2. 等待下一条新观测。

#### 预期行为
光标保持在用户选择行，便于查看历史。

#### 实际行为
光标立刻跳回最后一行。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `08e237b` | 未提供 | 2026-03-06 | fix(tui): prevent auto-scroll from stealing cursor when browsing observation history |

#### 变更内容
- 在 WatchView/TraceView 引入 `_auto_follow` 跟随状态控制。
- 将“用户是否查看历史”显式纳入滚动决策。

#### 验证
- 选中旧行后新观测不再抢光标。
- 点击最后一行后恢复自动跟随。

### 影响

- **受影响用户**：使用 Watch/Trace 浏览历史观测的用户。
- **持续时间**：流式视图引入后至 2026-03-06。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | 自动滚动恒开逻辑引入 |
| 2026-03-06 | 光标抢占问题被确认 |
| 2026-03-06 | 修复提交：`08e237b` |
| 2026-03-06 | 历史浏览与自动跟随验证通过 |

### 经验教训

#### 做得好的方面
- 复用了已验证的 StackView 模式，降低设计风险。

#### 可以改进的方面
- 交互一致性模式未在初版统一。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为所有流式列表统一引入 auto-follow 交互规范 | P1 | 待处理 |

### 预防

- **立即执行**：流式 UI 默认遵循“浏览历史即暂停跟随”。
- **短期**：增加光标稳定性交互测试。
- **长期**：形成可复用流式交互组件基类。

### 参考

- 修复 PR/提交：`08e237b`
- 相关 issue：未提供

---

## 事故 #5：help/watch/trace 残留 LSP 错误（签名/API 未同步）

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-3 | **日期**：2026-02-14

### 概要

先前重构后，`help.py` 方法签名与 Textual 预期不符，`watch.py/trace.py` 仍调用过时 `update_cell_at`，导致 LSP 报错并存在潜在运行风险。

### 根因分析

#### 类别
Dependency Issue

#### 分析
批量 API 迁移遗漏边角文件：
1. `help.py` 的 `action_dismiss` 缺少 async 与关键字参数签名。
2. `watch.py/trace.py` 未从 `update_cell_at` 切换到 `update_cell`。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 之前 Textual API 批量重构未覆盖全部文件 |

### 复现

#### 前置条件
- 使用 LSP（如 VS Code Pylance）检查 TUI 文件。

#### 步骤
1. 打开 `help.py`, `watch.py`, `trace.py`。
2. 查看诊断输出。

#### 预期行为
无类型/签名错误。

#### 实际行为
出现方法签名与 API 类型不匹配错误。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `fd08105` | 未提供 | 2026-02-14 | fix(tui): fix LSP errors in help/watch/trace |

#### 变更内容
- `help.py`：改为 `async def action_dismiss(self, *, result: None = None) -> None:`，并使用 `self.dismiss()`。
- `watch.py/trace.py`：`update_cell_at` 改为 `update_cell`。

#### 验证
- LSP 诊断清零。
- 功能行为正常。

### 影响

- **受影响用户**：开发者（静态检查）及相关视图潜在运行稳定性。
- **持续时间**：批量重构后至 2026-02-14。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | 批量迁移遗漏引入 |
| 2026-02-14 | LSP 错误被记录 |
| 2026-02-14 | 修复提交：`fd08105` |
| 2026-02-14 | 诊断验证通过 |

### 经验教训

#### 做得好的方面
- 以 LSP 作为回归信号快速发现漏改文件。

#### 可以改进的方面
- 批量迁移缺少文件级覆盖清单。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 建立 Textual API 升级全仓迁移 checklist | P1 | 待处理 |

### 预防

- **立即执行**：提交前运行全量 LSP 诊断。
- **短期**：API 迁移后按视图清单逐一验证。
- **长期**：引入自动化 codemod 与迁移报告。

### 参考

- 修复 PR/提交：`fd08105`
- 相关 issue：未提供

---

## 事故 #4：Monitor 视图存在 7 处 `update_cell_at` 参数误用

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-3 | **日期**：2026-02-09

### 概要

Monitor 统计表格多处将字符串行键当作整数坐标传给 `update_cell_at`，导致数据不更新或 `IndexError`。

### 根因分析

#### 类别
Logic Error

#### 分析
复制粘贴扩散错误：同一 API 误用在 7 个调用点重复出现。

修复示例：

```python
# 修复前
table.update_cell_at((watch_id, 2), str(total))

# 修复后
table.update_cell(watch_id, "Calls", str(total))
```

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | Monitor 视图重构与面板添加时复制了错误 API 用法 |

### 复现

#### 前置条件
- Monitor 视图中存在监视项。

#### 步骤
1. 添加方法监视。
2. 触发调用。
3. 观察统计更新。

#### 预期行为
统计列实时更新。

#### 实际行为
不更新或抛 `IndexError`。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `f520a16` | 未提供 | 2026-02-09 | fix(tui): fix 7 update_cell_at bugs in monitor view, add panels |

#### 变更内容
- 将 7 处 `update_cell_at` 统一替换为 `update_cell`（行键 + 列键）。

#### 验证
- 统计单元格全部正常更新。
- 不再出现异常。

### 影响

- **受影响用户**：Monitor 视图用户。
- **持续时间**：重构引入后至 2026-02-09。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | Monitor 重构引入 API 误用 |
| 2026-02-09 | 7 处问题被识别 |
| 2026-02-09 | 修复提交：`f520a16` |
| 2026-02-09 | 表格更新验证通过 |

### 经验教训

#### 做得好的方面
- 一次性批量修复所有同类点位。

#### 可以改进的方面
- 复制代码后的 API 语义复核不足。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 对 DataTable 调用新增静态 lint 规则（键 vs 索引） | P1 | 待处理 |

### 预防

- **立即执行**：DataTable 更新 API 区分规则写入开发规范。
- **短期**：对批量替换执行全文 grep 回归检查。
- **长期**：抽象统一表格更新 helper，避免直接散落调用。

### 参考

- 修复 PR/提交：`f520a16`
- 相关 issue：未提供

---

## 事故 #3：Stack 视图 `update_cell_at` 误用导致计数更新异常

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-3 | **日期**：2026-02-09

### 概要

Stack 视图将 `(watch_id, 2)` 传入 `update_cell_at`，其中 `watch_id` 为字符串而非整数坐标，引发 `IndexError` 或更新失败。

### 根因分析

#### 类别
Logic Error

#### 分析
混淆了 DataTable 两套 API：
- `update_cell_at((row_index, col_index), value)`：坐标（整数）
- `update_cell(row_key, column_key, value)`：键（字符串）

修复示例：

```python
# 修复前
table.update_cell_at((watch_id, 2), str(count))

# 修复后
table.update_cell(watch_id, "Captures", str(count))
```

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | Stack 视图重构时 API 选型错误 |

### 复现

#### 前置条件
- Stack 视图中添加追踪项。

#### 步骤
1. 触发函数调用。
2. 观察捕获计数更新。

#### 预期行为
计数持续更新且无异常。

#### 实际行为
不更新或抛 `IndexError`。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `4e5689e` | 未提供 | 2026-02-09 | fix(tui): fix update_cell_at bug in stack view, add panels |

#### 变更内容
- 使用 `update_cell`（row_key + column_key）替代 `update_cell_at`。

#### 验证
- 计数更新正常。
- 异常消失。

### 影响

- **受影响用户**：Stack 视图用户。
- **持续时间**：Stack 重构后至 2026-02-09。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | Stack 重构引入 API 误用 |
| 2026-02-09 | 问题被确认 |
| 2026-02-09 | 修复提交：`4e5689e` |
| 2026-02-09 | 计数更新验证通过 |

### 经验教训

#### 做得好的方面
- 修复明确了 DataTable 双 API 适用场景。

#### 可以改进的方面
- API 文档理解与代码审查深度不足。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 在 TUI 开发指南新增 DataTable API 对照示例 | P2 | 待处理 |

### 预防

- **立即执行**：行键场景统一使用 `update_cell`。
- **短期**：为 Stack/Monitor 建立 UI 回归脚本。
- **长期**：封装 typed wrapper 限制错误 API 调用。

### 参考

- 修复 PR/提交：`4e5689e`
- 相关 issue：未提供

---

## 事故 #2：Textual API 破坏性变更导致多视图崩溃

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-1 | **日期**：2026-02-07

### 概要

升级至较新 Textual 版本后，Inspect/Logger/Monitor/Stack 多视图触发 `AttributeError`/`TypeError`，原因是代码仍使用旧 API。

### 根因分析

#### 类别
Dependency Issue

#### 分析
Textual API 变更点包括：
1. `Tree.root.set_label()` → `Tree.root.label = ...`
2. `Select.BLANK` 比较需使用 `is` 而非 `==`
3. `DataTable.update_cell(row_key, column_name)` → `DataTable.update_cell_at((row_key, column_index))`

代码未同步升级，导致运行时崩溃。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | TUI 重构迁移期间未跟进 Textual API 变化 |

### 复现

#### 前置条件
- 安装 `textual >= 0.40.0`。

#### 步骤
1. 启动 peeka TUI。
2. 点击 Inspect 等视图。

#### 预期行为
各视图正常渲染与交互。

#### 实际行为
视图崩溃并抛异常。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `13667b6` | 未提供 | 2026-02-07 | fix(tui): Fix Textual API compatibility issues in TUI views |

#### 变更内容
- 批量替换上述三类 API 调用至新语义。

#### 验证
- 相关视图恢复可用，无崩溃。

### 影响

- **受影响用户**：使用新版本 Textual 的 TUI 用户。
- **持续时间**：升级后未适配阶段至 2026-02-07。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | Textual API 变化与旧代码并存 |
| 2026-02-07 | 多视图崩溃问题确认 |
| 2026-02-07 | 修复提交：`13667b6` |
| 2026-02-07 | 视图回归验证通过 |

### 经验教训

#### 做得好的方面
- 一次修复覆盖多视图关键调用点。

#### 可以改进的方面
- 依赖升级前后缺少系统兼容性回归。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 依赖升级流程增加 CHANGELOG 审阅与 API 差异清单 | P0 | 待处理 |

### 预防

- **立即执行**：锁定兼容版本并记录 API 迁移注意事项。
- **短期**：升级后跑全视图冒烟测试。
- **长期**：建立 Textual 版本适配层，减少直接耦合。

### 参考

- 修复 PR/提交：`13667b6`
- 相关 issue：未提供

---

## 事故 #1：Tabs 与输入标签缺失样式导致可见性差

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-3 | **日期**：2026-02-07

### 概要

Tabs 激活态不明显，多个输入框缺少标签，用户难以判断输入含义与当前选中状态，影响可读性与可用性。

### 根因分析

#### 类别
Missing Validation

#### 分析
UI 重构时新增组件但未同步补全 CSS 与标签语义。

新增样式片段：

```css
Tab {
    color: $text;
}

Tab:hover {
    color: $text;
    text-style: bold;
}

Tab.-active {
    color: $text-primary;
    text-style: bold;
}
```

```css
.input-label {
    width: auto;
    padding: 0 1;
    content-align: center middle;
    height: 3;
}
```

输入标签示例：

```python
yield Container(
    Horizontal(
        Static("Object Path:", classes="input-label"),
        Input(placeholder="module.Class or module.Class", id="inspect-path"),
```

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 标签式布局重构时遗漏样式与标签 |

### 复现

#### 前置条件
- 启动 peeka TUI。

#### 步骤
1. 观察顶部 Tabs。
2. 观察 Inspect 等视图输入区。

#### 预期行为
激活状态清晰、输入项有明确标签。

#### 实际行为
激活态不明显、输入语义不足。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `b34ccb5` | 未提供 | 2026-02-07 | fix(tui): add tab CSS for visibility and input labels |

#### 变更内容
- 增加 `Tab` 激活/悬停样式。
- 增加 `.input-label` 样式类。
- 为各输入框补充显式标签。

#### 验证
- Tabs 激活与悬停反馈清晰。
- 输入区语义明确，体验改善。

### 影响

- **受影响用户**：所有 TUI 用户。
- **持续时间**：布局重构后至 2026-02-07。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | 标签布局重构引入样式遗漏 |
| 2026-02-07 | 可见性问题被确认 |
| 2026-02-07 | 修复提交：`b34ccb5` |
| 2026-02-07 | UI 可读性验证通过 |

### 经验教训

#### 做得好的方面
- 修复同时覆盖视觉反馈与表单语义。

#### 可以改进的方面
- 新 UI 组件上线前缺少主题可见性检查。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 增加 TUI 可用性检查清单（激活态/标签/主题对比） | P2 | 待处理 |

### 预防

- **立即执行**：表单输入必须配套显式标签。
- **短期**：在明暗主题下做可见性冒烟验证。
- **长期**：建设统一设计令牌与样式基线测试。

### 参考

- 修复 PR/提交：`b34ccb5`
- 相关 issue：未提供
