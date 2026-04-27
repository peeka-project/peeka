# Postmortem 索引

生成日期：2026-04-27

## 话题列表

| 编号 | 话题 | 最高严重级别 | 组件 | 事故次数 | 时间跨度 |
|------|------|-------------|------|----------|----------|
| [001](./001-docs-gh-pages.md) | 文档与 GitHub Pages 构建/链接/主题问题 | SEV-0 | docs, gh-pages | 6 | 2026-03-13 ~ 2026-03-18 |
| [002](./002-tui-memory-view.md) | TUI Memory View 布局、GC 表格、刷新与交互 | SEV-1 | tui (memory, logger, css) | 13 | 2026-02-26 ~ 2026-03-10 |
| [003](./003-tui-autocomplete.md) | TUI 自动补全：缓存、触发、光标、`__main__` | SEV-2 | tui, commands (complete) | 5 | 2026-02-07 ~ 2026-03-05 |
| [004](./004-streaming-client-concurrency.md) | StreamingAgentClient 并发与 BrokenPipe | SEV-1 | core/client, tui views | 6 | 2026-02-28 ~ 2026-03-10 |
| [005](./005-tui-threading-and-lifecycle.md) | TUI 线程模型、主线程阻塞与关机生命周期 | SEV-1 | tui (app, screens, views) | 6 | 2026-02-07 ~ 2026-03-05 |
| [006](./006-attach-and-agent-lifecycle.md) | 进程 Attach 就绪探测与 Agent 生命周期 | SEV-0 | core/attach, core/agent | 5 | 2026-02-26 ~ 2026-03-01 |
| [007](./007-gdb-injection-and-python38.md) | GDB 注入路径与 Python 3.8 兼容性 | SEV-1 | core/attach, core/agent | 4 | 2026-02-05 ~ 2026-03-24 |
| [008](./008-injector-and-tracing.md) | DecoratorInjector 实例方法、`__main__` 解析与 trace 调用树 | SEV-1 | core/injector, commands/trace | 3 | 2026-01-29 ~ 2026-02-28 |
| [009](./009-cli-commands-and-payloads.md) | CLI 命令分发、参数键契约不一致与 run 命令实现缺陷 | SEV-1 | cli/main.py, core/output.py | 5 | 2026-01-29 ~ 2026-04-03 |
| [010](./010-top-profiling.md) | Top 命令线程过滤、TopView 并发与 Agent 响应帧竞态 | SEV-1 | commands/top, tui/views/top, core/agent | 5 | 2026-02-26 ~ 2026-04-26 |
| [011](./011-docker-build-and-images.md) | Docker 镜像构建、镜像源与容器进程模型 | SEV-2 | docker, 容器测试 | 5 | 2026-02-07 ~ 2026-03-01 |
| [012](./012-tui-ui-and-textual-api.md) | TUI 样式、DataTable API 与 Textual 兼容 | SEV-1 | tui/views, tui/screens | 6 | 2026-02-07 ~ 2026-03-06 |
| [013](./013-tests-and-examples.md) | 测试期望、demo 日志与测试维护 | SEV-2 | tests, examples/demo.py | 3 | 2026-02-07 ~ 2026-03-23 |
| [014](./014-security-safeeval.md) | simpleeval 异常处理与 fail-closed 安全机制 | SEV-0 | security, injector | 1 | 2026-01-29 |
| [015](./015-basecommand-and-command-system.md) | BaseCommand 缺少 agent 参数 | SEV-1 | commands/base.py | 1 | 2026-02-05 |
| [016](./016-dependencies.md) | 依赖配置问题：版本约束不兼容与格式废弃 | SEV-3 | dependencies, pyproject.toml | 2 | 2026-03-20 ~ 2026-04-12 |

## 统计

- **话题总数**：16
- **事故总次数**：76
- **按严重级别**：SEV-0: 3, SEV-1: 9, SEV-2: 3, SEV-3: 1, SEV-4: 1
- **按组件**：
  - tui: 7 个话题（002, 003, 004, 005, 010, 012, 013）
  - core: 4 个话题（006, 007, 008, 014）
  - cli: 1 个话题（009）
  - docker: 1 个话题（011）
  - docs: 1 个话题（001）
  - commands: 1 个话题（015）
  - dependencies: 1 个话题（016）
- **按根因类别**（主要）：
  - Race Condition: 话题 004, 006, 010
  - Logic Error: 话题 008, 009, 010, 014
  - Missing Validation: 话题 002, 005, 009
  - Configuration Error: 话题 001, 002, 009, 011, 016
  - Type Error: 话题 007
  - Regression: 话题 001, 003, 012, 013
  - Integration Error: 话题 004, 015
  - Resource Management: 话题 006

## 共性问题

- **线程安全与并发**（话题 004, 005, 006, 010）— 4 个话题涉及线程模型误用、套接字竞争或并发状态管理不当。建议进行全面并发审计，统一流式连接与共享客户端的使用策略。
- **TUI 生命周期与初始化顺序**（话题 002, 005, 012）— 3 个话题暴露 mount/client 注入时序、worker 生命周期与视图初始化顺序问题。建议构建统一 ViewBase 生命周期框架。
- **CLI ↔ Agent 契约不一致**（话题 009, 015）— 参数键命名与分发逻辑多次出错。建议建立 schema 验证或契约测试。
- **CSS 特异性与布局**（话题 002, 003, 012）— 多处 CSS 规则优先级冲突导致视觉缺陷。建议统一 CSS 命名空间与特异性策略。
- **GDB/Python 3.8 兼容**（话题 007, 016）— 低版本 Python 持续出现类型转换和依赖约束问题。建议强化 Python 3.8 CI 覆盖。
- **安全 fail-closed**（话题 014）— 安全控制异常路径默认放行是高危模式。建议对所有安全路径添加 fail-closed 断言测试。
- **Python 函数默认参数陷阱**（话题 009 #5）— `file=sys.stdout` 定义时绑定导致 pytest 捕获失败。建议对全局流对象默认参数统一使用 `None` + 运行时解析。

## 最近更新

| 日期 | 话题 | 事故 | 变更说明 |
|------|------|------|----------|
| 2026-04-27 | [010](./010-top-profiling.md) | #5 | 新增事故：Agent 并发响应帧写入导致 top 命令 JSON 损坏（v0.1.8） |
| 2026-04-27 | [009](./009-cli-commands-and-payloads.md) | #5 | 新增事故：peeka-cli run OutputFormatter stdout 捕获缺陷（v0.1.8） |
| 2026-04-27 | [016](./016-dependencies.md) | #2 | 新增事故：dev-dependencies 使用已废弃 [tool.uv] 字段（v0.1.8） |
