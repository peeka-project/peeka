# Postmortem 索引

生成日期：2026-11-20

## 话题列表

| 编号 | 话题 | 最高严重级别 | 组件 | 事故次数 | 最近事故 |
|------|------|-------------|------|----------|----------|
| [001](./001-docs-gh-pages.md) | 文档与 GitHub Pages 构建/链接/主题问题 | SEV-0 | docs, gh-pages | 6 | 2026-03-18 |
| [002](./002-tui-memory-view.md) | TUI Memory View 布局、GC 表格、刷新与交互 | SEV-1 | tui | 13 | 2026-03-10 |
| [003](./003-tui-autocomplete.md) | TUI 自动补全：缓存、触发、光标、`__main__` | SEV-2 | tui | 5 | 2026-03-05 |
| [004](./004-streaming-client-concurrency.md) | StreamingAgentClient 并发与 BrokenPipe | SEV-1 | core | 10 | 2026-11-18 |
| [005](./005-tui-threading-and-lifecycle.md) | TUI 线程模型、主线程阻塞与关机生命周期 | SEV-1 | tui | 9 | 2026-06-23 |
| [006](./006-attach-and-agent-lifecycle.md) | 进程 Attach 就绪探测与 Agent 生命周期 | SEV-0 | core | 15 | 2026-11-20 |
| [007](./007-gdb-injection-and-python38.md) | GDB 注入路径与 Python 3.8 兼容性 | SEV-1 | core | 4 | 2026-03-24 |
| [008](./008-injector-and-tracing.md) | DecoratorInjector 实例方法、`__main__` 解析与 trace 调用树 | SEV-1 | core, commands | 8 | 2026-11-18 |
| [009](./009-cli-commands-and-payloads.md) | CLI 命令分发、参数键与 JSONL payload 契约漂移 | SEV-1 | cli, core | 10 | 2026-11-17 |
| [010](./010-top-profiling.md) | Top 命令线程过滤、TopView 并发与 Agent 响应帧竞态 | SEV-1 | core, tui | 6 | 2026-07-17 |
| [011](./011-docker-build-and-images.md) | Docker 镜像构建、镜像源与容器进程模型 | SEV-2 | docker | 5 | 2026-03-01 |
| [012](./012-tui-ui-and-textual-api.md) | TUI 样式、DataTable API 与 Textual 兼容 | SEV-1 | tui | 8 | 2026-11-07 |
| [013](./013-tests-and-examples.md) | 测试期望、demo 日志与测试维护 | SEV-2 | tests | 4 | 2026-06-07 |
| [014](./014-security-safeeval.md) | simpleeval 异常处理与 fail-closed 安全机制 | SEV-0 | core | 1 | 2026-01-29 |
| [015](./015-basecommand-and-command-system.md) | BaseCommand 缺少 agent 参数 | SEV-1 | commands | 1 | 2026-02-05 |
| [016](./016-dependencies.md) | 依赖配置问题：版本约束不兼容与格式废弃 | SEV-3 | dependencies | 2 | 2026-04-12 |
| [017](./017-rpl-primitives-rollout.md) | Runtime Primitives Layer (RPL) 的引入与稳定化 | SEV-1 | core | 5 | 2026-11-08 |
| [018](./018-watch-stacking-and-orphans.md) | Watch 嵌套堆叠与孤立清理 | SEV-1 | core | 5 | 2026-11-08 |
| [019](./019-trace-sanitization-and-gevent.md) | Trace 数据清理与 Gevent 检测 | SEV-1 | core, commands | 3 | 2026-11-07 |
| [020](./020-agent-observation-queue.md) | Agent 观测队列与序列化性能 | SEV-1 | core | 3 | 2026-11-20 |
| [021](./021-process-discovery-and-runtime-environment.md) | 进程发现与运行时环境适应性 | SEV-2 | core, runtime | 1 | 2026-06-24 |
| [022](./022-release-pipeline-and-wheels.md) | 发布流水线、wheel 构建矩阵与工具版本漂移 | SEV-1 | ci, packaging | 2 | 2026-11-09 |

## 统计

- **话题总数**：22
- **事故总次数**：122
- **按最高严重级别**：SEV-0: 3, SEV-1: 14, SEV-2: 4, SEV-3: 1, SEV-4: 0
- **按组件**：
  - core: 9 个话题（004, 006, 007, 008, 014, 017, 018, 019, 020, 021）
  - tui: 7 个话题（002, 003, 005, 010, 012, 013, 018）
  - ci/packaging: 1 个话题（022）
  - cli: 1 个话题（009）
  - docker: 1 个话题（011）
  - docs: 1 个话题（001）
  - commands: 2 个话题（015, 019）
  - dependencies: 1 个话题（016）
- **按根因类别**：
  - Race Condition: 话题 004, 006, 010, 020
  - Logic Error: 话题 008, 009, 010, 014, 018, 019, 020
  - Missing Validation: 话题 002, 005, 009, 018
  - Configuration Error: 话题 001, 002, 009, 011, 016, 022
  - Type Error: 话题 007, 019
  - Regression: 话题 001, 003, 012, 013
  - Integration Error: 话题 004, 015
  - Resource Management: 话题 006
  - Environment Assumption / Missing Fallback: 话题 021
  - Dependency Issue: 话题 017, 022
- **最近一次分析范围**：`v0.1.22..v0.1.23`
- **分析的 fix 提交总数**：20
- **本次新增事故组块数**：3

## v0.1.23 候选筛选说明

| 修复提交 | 归属与筛选依据 |
|---|---|
| 82629c0、7605b84 | 006 #14、#15 分别记录退出信号重入和跨代投递。 |
| 3e435b6、63eefd5 | 合并为 020 #3，记录短脚本从 Agent 到 CLI 的尾帧交付。 |
| 9c60625、b27968b、235ec6a、654f3b4、440d424 | 008 #7、#8 已记录调用树归属、异步调用协议和格式化隔离。 |
| 490fb8e、2bbee72 | 004 #9、#10 覆盖单 reader 和失步连接；TUI 另有视图隔离回归。 |
| 0f75d99、e2a6589、3cc7c04 | 006 #13 记录启动和清理门控；并发 stop 可见性属于同一生命周期。 |
| 083263d、3b24740 | ADR 0005 和 exact 所有权回归已记录采样器互斥、安装撤销和安全拒绝。 |
| 58b8d7b、ab8f2b0 | 018 和控制面回归覆盖按所有者撤销及终态事件提交。 |
| ca954aa | 009 的路由契约新增多目标歧义回归。 |
| d2f48fd | 测试夹具重复启动容器，未涉及发布包的运行行为。 |

## v0.1.22 候选筛选说明

已逐项阅读本轮 9 个 fix 的实际 diff，并对照已有话题全文：

| 提交 | 决策 | 归属与理由 |
|------|------|------------|
| 9b6f65e | include | 008 #5：描述符绑定与每次调用上下文隔离 |
| 19c4a9d、8873544 | include / merge | 008 #6：协程执行期追踪及旧解释器 follow-up |
| f8cb264 | include | 009 #10：双执行与发布前重排回归 |
| 4fccc7f、cd3ba40 | include / merge | 004 #9：单 reader 分发及信号重入 follow-up |
| efae7b3 | include | 006 #11：规范模块 registry 身份；有界写和连接关闭同时延续 004 #8、006 #3/#9 的既有预防原则 |
| dee1fbe | include | 006 #12：PID 作用域与 PermissionError 语义 |
| 14a0e3c | reference-only | monitor 锁外 join、共享状态锁顺序、RPL 原语迁移，延续 018 #5、017 #5 与 006 #10，避免重复事故块；停止顺序矩阵和 Python 3.12 runtime 专项通过 |

`90554d6` 为测试基线修正，不计入 fix 事故；预热后仍严格检查五轮启停的线程恢复。发布前门禁为 1570 passed、2 skipped，Ruff 通过；容器首轮 98 passed，发现的 6 个生命周期失败修复后全数通过。TUI/run 专项 45 passed，真实 run 冒烟测试通过。

## 共性问题

- **线程安全与并发**（话题 004, 005, 006, 010, 020）— 5 个话题涉及线程模型、同步原语与分发竞态。v0.1.17 引入了原生锁（native lock）替代 Event 提升了稳定性，并实现了异步观测分发队列以降低生产者热路径延迟。
- **Agent/Probe 清理生命周期合同**（话题 005, 006, 009, 018）— v0.1.18 集中暴露 detach/reset/stop/cleanup_for_exit 的合同漂移：资源所有者返回式错误必须冒泡，CLI/TUI 必须展示 nested cleanup_summary，stop-by-id 与 pattern reset 必须分离。
- **探针堆叠与生命周期安全性**（话题 018）— 探针的卸载必须能够感知堆叠链的完整性。简单恢复原始函数会导致中间层丢失。建议所有对运行时的修改均采用基于“链”的恢复策略；monitor/trace/stack 与 watch 混合堆叠时同样适用。
- **数据序列化安全与边界清理**（话题 019）— 诊断数据在流向输出层前必须彻底清理内部字段（如 raw results/exceptions），否则不可序列化对象会破坏整个通信链路。
- **动态运行时环境适应性**（话题 019）— 诊断工具必须具备“热切换”策略的能力，以适应 gevent 补丁等延迟加载的环境变化。
- **TUI ↔ Agent 契约稳定性**（话题 009, 015）— 命令参数与输出契约漂移仍是回归主因。
- **Trace 输出模型迁移的跨层契约同步**（话题 008）— `children` → `direct_callees` 的 schema 变更需要同时收敛 backend、CLI、TUI drill-down 和文档示例，否则会出现公开字段漂移和深度栈不变量缺口。
- **流式 TUI 资源与选择状态一致性**（话题 012）— Clear、自动选择、参数解析等交互不能只操作 UI 层，必须和 Agent 端 active resource、后台 stream worker 作为同一状态机验证。
- **慢消费者与锁内调用**（话题 004, 018）— v0.1.21 暴露两类“一个组件卡住拖垮全局”的模式：agent 对不读取的连接做无界阻塞写，以及 wrapper 在持有不可重入锁时调用下一层 wrapper。写出必须有界，锁内只做决策、锁外调用。
- **发布流水线的隐式外部假设**（话题 022）— runner 标签下线、wheel 与发布工作流互不依赖、CI 工具不锁版本，都只在 tag 推送时暴露。

## 最近更新

| 日期 | 话题 | 事故 | 变更说明 |
|------|------|------|----------|
| 2026-11-20 | [006](./006-attach-and-agent-lifecycle.md) | #14 | 退出信号打断持锁线程时清理自锁（v0.1.23） |
| 2026-11-20 | [006](./006-attach-and-agent-lifecycle.md) | #15 | 重新附加后旧事件进入新消费者（v0.1.23） |
| 2026-11-20 | [020](./020-agent-observation-queue.md) | #3 | 短脚本关闭流连接时丢失尾帧（v0.1.23） |
| 2026-11-17 | [004](./004-streaming-client-concurrency.md) | #9 | v0.1.22：多 watch 分发和信号重入 |
| 2026-11-17 | [006](./006-attach-and-agent-lifecycle.md) | #11-12 | v0.1.22：registry 身份、连接关闭和 PID 隔离 |
| 2026-11-17 | [008](./008-injector-and-tracing.md) | #5-6 | v0.1.22：描述符和异步追踪语义 |
| 2026-11-17 | [009](./009-cli-commands-and-payloads.md) | #10 | v0.1.22：run 单次执行与顺序保持 |
| 2026-11-09 | [022](./022-release-pipeline-and-wheels.md) | #1-2 | 新增话题：PyPI 只发布单一 glibc 2.34 wheel、CI 未锁定 ruff 导致 release gate 失败（v0.1.21） |
| 2026-11-09 | [004](./004-streaming-client-concurrency.md) | #8 | 新增事故：不读取的连接阻塞 agent 日志广播（v0.1.21） |
| 2026-11-09 | [018](./018-watch-stacking-and-orphans.md) | #5 | 新增事故：已停止 trace wrapper 持锁调用导致死锁（v0.1.21） |
| 2026-11-09 | [017](./017-rpl-primitives-rollout.md) | #5 | 新增事故：RPL 在 gevent 下发放绿色锁、integrity_check 恒为 ok（v0.1.21） |
| 2026-11-09 | [012](./012-tui-ui-and-textual-api.md) | #8 | 新增事故：TUI 焦点链断裂导致快捷键失效（v0.1.21） |
| 2026-11-09 | [019](./019-trace-sanitization-and-gevent.md) | #3 | 新增事故：gevent trace 策略收窄后丢失 runtime_meta（v0.1.21） |
| 2026-11-09 | [010](./010-top-profiling.md) | #6 | 新增事故：Profile 子系统开发期生命周期与并发缺陷（v0.1.21） |
| 2026-07-04 | [012](./012-tui-ui-and-textual-api.md) | #7 | 新增事故：TraceView 活动追踪状态、选择与参数语义漂移（v0.1.20） |
| 2026-07-04 | [008](./008-injector-and-tracing.md) | #4 | 新增事故：Trace 直接被调函数聚合与 stdlib 跳过栈不变量漂移（v0.1.20） |
| 2026-06-25 | [021](./021-process-discovery-and-runtime-environment.md) | #1 | 新增话题：sudo 环境下 pycache 写入失败与 /proc 不可用时进程发现中断（v0.1.19） |
| 2026-06-25 | [009](./009-cli-commands-and-payloads.md) | #9 | 新增事故：detach 清理摘要警告与本地 marker 回退契约（v0.1.19） |
| 2026-06-25 | [006](./006-attach-and-agent-lifecycle.md) | #10 | 新增事故：ProbeContext 退出失败与 monitor/top 停止超时未暴露（v0.1.19） |
| 2026-06-23 | [006](./006-attach-and-agent-lifecycle.md) | #9 | 新增事故：Agent stop 清理合同与信号钩子恢复漂移（v0.1.18） |
| 2026-06-23 | [009](./009-cli-commands-and-payloads.md) | #8 | 新增事故：Streaming 本地限制、stop cleanup 与 reset 退出码契约漂移（v0.1.18） |
| 2026-06-23 | [005](./005-tui-threading-and-lifecycle.md) | #9 | 新增事故：TUI 流式视图退出清理未暴露 nested cleanup_summary 错误（v0.1.18） |
| 2026-06-15 | [018](./018-watch-stacking-and-orphans.md) | #4 | 新增事故：混合探针与 Monitor 卸载破坏 wrapper 链和别名恢复（v0.1.18） |
| 2026-06-13 | [018](./018-watch-stacking-and-orphans.md) | #1-3 | 新增话题：Watch 堆叠恢复与孤立清理安全性（v0.1.17） |
| 2026-06-13 | [019](./019-trace-sanitization-and-gevent.md) | #1-2 | 新增话题：Trace 数据清理与 Gevent 检测（v0.1.17） |
| 2026-06-13 | [020](./020-agent-observation-queue.md) | #1-2 | 新增话题：Agent 异步观测队列与锁同步（v0.1.17） |
| 2026-06-07 | [013](./013-tests-and-examples.md) | #4 | 新增事故：probe help 测试依赖本地 uv（v0.1.16） |
| 2026-06-07 | [009](./009-cli-commands-and-payloads.md) | #7 | 新增事故：session control-plane 路由契约缺口（v0.1.16） |
| 2026-06-07 | [006](./006-attach-and-agent-lifecycle.md) | #8 | 新增事故：GDB fallback injector 路径 uv 假设（v0.1.16） |
