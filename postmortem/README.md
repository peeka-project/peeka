# Postmortem 索引

生成日期：2026-07-05

## 话题列表

| 编号 | 话题 | 最高严重级别 | 组件 | 事故次数 | 最近事故 |
|------|------|-------------|------|----------|----------|
| [001](./001-docs-gh-pages.md) | 文档与 GitHub Pages 构建/链接/主题问题 | SEV-0 | docs, gh-pages | 6 | 2026-03-18 |
| [002](./002-tui-memory-view.md) | TUI Memory View 布局、GC 表格、刷新与交互 | SEV-1 | tui | 13 | 2026-03-10 |
| [003](./003-tui-autocomplete.md) | TUI 自动补全：缓存、触发、光标、`__main__` | SEV-2 | tui | 5 | 2026-03-05 |
| [004](./004-streaming-client-concurrency.md) | StreamingAgentClient 并发与 BrokenPipe | SEV-1 | core | 6 | 2026-03-10 |
| [005](./005-tui-threading-and-lifecycle.md) | TUI 线程模型、主线程阻塞与关机生命周期 | SEV-1 | tui | 9 | 2026-06-23 |
| [006](./006-attach-and-agent-lifecycle.md) | 进程 Attach 就绪探测与 Agent 生命周期 | SEV-0 | core | 10 | 2026-06-25 |
| [007](./007-gdb-injection-and-python38.md) | GDB 注入路径与 Python 3.8 兼容性 | SEV-1 | core | 4 | 2026-03-24 |
| [008](./008-injector-and-tracing.md) | DecoratorInjector 实例方法、`__main__` 解析与 trace 调用树 | SEV-1 | core, commands | 4 | 2026-07-04 |
| [009](./009-cli-commands-and-payloads.md) | CLI 命令分发、参数键与 JSONL payload 契约漂移 | SEV-1 | cli, core | 9 | 2026-06-25 |
| [010](./010-top-profiling.md) | Top 命令线程过滤、TopView 并发与 Agent 响应帧竞态 | SEV-1 | core, tui | 5 | 2026-04-26 |
| [011](./011-docker-build-and-images.md) | Docker 镜像构建、镜像源与容器进程模型 | SEV-2 | docker | 5 | 2026-03-01 |
| [012](./012-tui-ui-and-textual-api.md) | TUI 样式、DataTable API 与 Textual 兼容 | SEV-1 | tui | 7 | 2026-07-04 |
| [013](./013-tests-and-examples.md) | 测试期望、demo 日志与测试维护 | SEV-2 | tests | 4 | 2026-06-07 |
| [014](./014-security-safeeval.md) | simpleeval 异常处理与 fail-closed 安全机制 | SEV-0 | core | 1 | 2026-01-29 |
| [015](./015-basecommand-and-command-system.md) | BaseCommand 缺少 agent 参数 | SEV-1 | commands | 1 | 2026-02-05 |
| [016](./016-dependencies.md) | 依赖配置问题：版本约束不兼容与格式废弃 | SEV-3 | dependencies | 2 | 2026-04-12 |
| [017](./017-rpl-primitives-rollout.md) | Runtime Primitives Layer (RPL) 的引入与稳定化 | SEV-1 | core | 4 | 2026-05-26 |
| [018](./018-watch-stacking-and-orphans.md) | Watch 嵌套堆叠与孤立清理 | SEV-1 | core | 4 | 2026-06-15 |
| [019](./019-trace-sanitization-and-gevent.md) | Trace 数据清理与 Gevent 检测 | SEV-1 | core, commands | 2 | 2026-06-13 |
| [020](./020-agent-observation-queue.md) | Agent 观测队列与序列化性能 | SEV-1 | core | 2 | 2026-06-13 |
| [021](./021-process-discovery-and-runtime-environment.md) | 进程发现与运行时环境适应性 | SEV-2 | core, runtime | 1 | 2026-06-24 |

## 统计

- **话题总数**：21
- **事故总次数**：104
- **按最高严重级别**：SEV-0: 3, SEV-1: 13, SEV-2: 4, SEV-3: 1, SEV-4: 0
- **按组件**：
  - core: 9 个话题（004, 006, 007, 008, 014, 017, 018, 019, 020, 021）
  - tui: 7 个话题（002, 003, 005, 010, 012, 013, 018）
  - cli: 1 个话题（009）
  - docker: 1 个话题（011）
  - docs: 1 个话题（001）
  - commands: 2 个话题（015, 019）
  - dependencies: 1 个话题（016）
- **按根因类别**：
  - Race Condition: 话题 004, 006, 010, 020
  - Logic Error: 话题 008, 009, 010, 014, 018, 019, 020
  - Missing Validation: 话题 002, 005, 009, 018
  - Configuration Error: 话题 001, 002, 009, 011, 016
  - Type Error: 话题 007, 019
  - Regression: 话题 001, 003, 012, 013
  - Integration Error: 话题 004, 015
  - Resource Management: 话题 006
  - Environment Assumption / Missing Fallback: 话题 021
- **最近一次分析范围**：`v0.1.19..HEAD`
- **分析的 fix 提交总数**：18
- **入选事故组块数**：2
- **跳过/合并的 fix 提交数**：16

## 共性问题

- **线程安全与并发**（话题 004, 005, 006, 010, 020）— 5 个话题涉及线程模型、同步原语与分发竞态。v0.1.17 引入了原生锁（native lock）替代 Event 提升了稳定性，并实现了异步观测分发队列以降低生产者热路径延迟。
- **Agent/Probe 清理生命周期合同**（话题 005, 006, 009, 018）— v0.1.18 集中暴露 detach/reset/stop/cleanup_for_exit 的合同漂移：资源所有者返回式错误必须冒泡，CLI/TUI 必须展示 nested cleanup_summary，stop-by-id 与 pattern reset 必须分离。
- **探针堆叠与生命周期安全性**（话题 018）— 探针的卸载必须能够感知堆叠链的完整性。简单恢复原始函数会导致中间层丢失。建议所有对运行时的修改均采用基于“链”的恢复策略；monitor/trace/stack 与 watch 混合堆叠时同样适用。
- **数据序列化安全与边界清理**（话题 019）— 诊断数据在流向输出层前必须彻底清理内部字段（如 raw results/exceptions），否则不可序列化对象会破坏整个通信链路。
- **动态运行时环境适应性**（话题 019）— 诊断工具必须具备“热切换”策略的能力，以适应 gevent 补丁等延迟加载的环境变化。
- **TUI ↔ Agent 契约稳定性**（话题 009, 015）— 命令参数与输出契约漂移仍是回归主因。
- **Trace 输出模型迁移的跨层契约同步**（话题 008）— `children` → `direct_callees` 的 schema 变更需要同时收敛 backend、CLI、TUI drill-down 和文档示例，否则会出现公开字段漂移和深度栈不变量缺口。
- **流式 TUI 资源与选择状态一致性**（话题 012）— Clear、自动选择、参数解析等交互不能只操作 UI 层，必须和 Agent 端 active resource、后台 stream worker 作为同一状态机验证。

## 最近更新

| 日期 | 话题 | 事故 | 变更说明 |
|------|------|------|----------|
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
