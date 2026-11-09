# ADR 0005: Profile Session 模型，Top 作为其实时视图

- 状态：Accepted
- 日期：2026-07-13（2026-11-08 按 profile review 修订）
- 决策者：peeka 维护者
- 实现：`peeka/core/profile/`、`peeka/commands/profile.py`、`peeka/commands/top.py`

## 上下文

peeka 原有 `top` 只保存聚合计数，结果无法保存、导出、复盘。设计前调研了两个项目：

- **pyinstrument**：sampling profiler、Session 数据模型、processor / renderer 分层、多种导出格式。
- **VizTracer**：exact trace、Chrome Trace / Perfetto 产物、bounded tracing 参数、remote attach 经验。

## 决策

**吸收架构，不依赖这两个包**（不把它们注入目标进程）：

```text
pyinstrument → session / frame records / processors / renderers
VizTracer    → bounded exact trace / timeline 产物 / Perfetto 导出
peeka        → 保留自己的 attach + agent runtime
```

1. **`profile` 是底层采集与产物模型**。一等对象 `ProfileSession`（`profile_id`、backend、config、raw samples / events、summary），由 agent 内的 `ProfileRegistry` 管理 start / stop / snapshot / list / export。
2. **`top` 保留，不改名、不删除**。`top` = 实时视图，`profile` = 可保存的采集 / 产物。`top` 内部创建 transient sampling profile，并返回 `profile_id`。
3. **采集与渲染分离**。采集层只保存原始 stack records / trace events；processor（top list、call tree、flamegraph、timeline、过滤）和 renderer（json、text、tui、speedscope、perfetto）负责展示。导出格式由 peeka 自己生成。
4. **默认低侵入，exact 显式开启**。生产默认 sampling；exact backend 必须短时、bounded（duration、max_events、overflow 标记）。

## 修订（2026-11-08，profile review）

review 发现 exact 路径有每事件 deepcopy、自死锁、内存无上限等问题。修复（已合入 master，`e047b9e`）后定下这些约束：

- `--backend exact` 必须同时加 `--experimental`（参数 `experimental=true`），否则拒绝。
- exact 与 sampling **互斥**，不能同时运行。
- 不加 `--keep-profile` 的 `top` 仍会创建 transient session、返回 `profile_id`，但**不保存原始栈**（samples 为空，聚合统计不受影响）。
- Registry 对已停止的 session 合计最多保留 500k samples（`DEFAULT_MAX_RETAINED_SAMPLES`），超出时淘汰最早的 session，但最近停止的一个总会保留。Registry 放在 `peeka/core/profile/registry.py`。

## 不做

- 不把 profile 告警打到目标进程的 stdout / stderr。
- 不长时间运行 `sys.setprofile` exact backend。
- diagnostic tree 只引用 `profile_id`，不内嵌完整的 profile 原始数据。
