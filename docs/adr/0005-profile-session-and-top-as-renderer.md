# ADR 0005: Profile Session 模型，Top 作为其实时视图

- 状态：Accepted
- 日期：2026-07-13（2026-11-08 按 profile review 修订；2026-11-18 按 `3b24740` 纠正 exact 后端适用条件及安全拒绝）
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

## 修订（2026-11-18，exact 后端适用条件与安全拒绝，master 未发布 `083263d` / `3b24740`）

> 状态说明：本节对应 `v0.1.22` 之后合入 `master` 的已提交修复（`083263d`、`3b24740`），尚未随新版本发布；已发布的 `v0.1.22` 仍包含旧的 `setprofile` 回退判断。

后续对 `ExactProfileSampler`（[exact.py](../../peeka/core/profile/exact.py)）与 `ProfileCommand`（[profile.py](../../peeka/commands/profile.py)）的生命周期审计确认，此前在无 `sys.monitoring` 或 tool ID 不可用时回退到 `sys.setprofile` / `threading.setprofile_all_threads` 的做法存在两类不可接受的破坏：

- 线程局部 `sys.setprofile` 无法由 duration timer 或 RPC `stop` 等其他线程安全清除；
- `threading.setprofile_all_threads` 会静默覆盖其他线程上既有的第三方 profiler（如 coverage、业务自带 profiler）。

因此收紧 exact 后端适用条件并强制 fail-closed 安全拒绝：

- **唯一允许的 exact 后端**：仅支持 Python 3.12+ 且提供 `sys.monitoring` 的运行时（`backend_name="sys_monitoring"`），并按 `PROFILER_ID(2), 4, 3, 5, 1, 0` 顺序探测认领空闲 tool ID。
- **拒绝一切 `setprofile` 回退**：无论单线程还是多线程环境，只要不具备 `sys.monitoring`（Python < 3.12 或缺少 `sys.monitoring`）或 6 个 `sys.monitoring` tool ID 均已被占用，`check_capability()` 即返回 `available=False, backend_name=None`，`start()` 直接抛出 `RuntimeError` 且不安装任何 hook（同时 `ProfileCommand` 不留下活跃会话或 owner）。
- **既有的前置安全拒绝继续强制生效**：检测到 gevent monkey-patch 运行时（`gevent incompatibility`），或检测到 `sys.getprofile()` / `threading` profile hook 已安装（`another profiler is already installed`），或未传 `--experimental`（`experimental=true`），均直接拒绝。
- **所有权与安装/释放序列化**：`ExactProfileSampler` 序列化 tool ID 认领、回调注册、`set_events`、中段并发 `stop()` 回滚与跨线程释放；`_is_peeka_frame()` 跳过调用栈中含 `peeka` / `peeka.*` 帧的回调以防自死锁；`ProfileCommand` 通过 `_exact_starting_token` 与 `_exact_inflight_*` 保障 exact 与 sampling 在启动窗口内的原子互斥。

## 不做

- 不把 profile 告警打到目标进程的 stdout / stderr。
- 不启用或回退到 `sys.setprofile` / `threading.setprofile_all_threads` 作为 exact backend（无可用 `sys.monitoring` tool ID 时直接安全拒绝）。
- diagnostic tree 只引用 `profile_id`，不内嵌完整的 profile 原始数据。

## 参考

- 实现：[exact.py](../../peeka/core/profile/exact.py)、[profile.py](../../peeka/commands/profile.py)
- 防复发测试：[test_profile_exact.py](../../tests/commands/test_profile_exact.py)、[test_sampler_ownership_regressions.py](../../tests/test_sampler_ownership_regressions.py)
- 事故复盘：[010-top-profiling.md](../../postmortem/010-top-profiling.md)
