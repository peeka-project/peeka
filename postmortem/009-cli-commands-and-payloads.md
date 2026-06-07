# CLI 命令分发与 Payload 参数契约问题复盘

| 字段 | 值 |
|------|-----|
| **话题** | CLI 到 Agent 的命令分发、参数键和 JSONL payload 契约不一致问题，以及 CLI run 命令实现缺陷 |
| **受影响组件** | cli/main.py, core/output.py, core/bootstrap.py, core/injector.py, commands/monitor.py, tests/container/ |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 7 |
| **时间跨度** | 2026-01-29 至 2026-06-07 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#7](#事故-7session-control-plane-多目标路由与-probe-契约缺口) | session control-plane 多目标路由与 probe 契约缺口 | SEV-2 | 2026-06-07 |
| [#6](#事故-6容器诊断-cli-兼容性回归) | 容器诊断 CLI 兼容性回归 | SEV-2 | 2026-05-27 |
| [#5](#事故-5peeka-cli-run-命令-outputformatter-stdout-捕获缺陷及多处实现问题) | peeka-cli run 命令 OutputFormatter stdout 捕获缺陷及多处实现问题 | SEV-2 | 2026-04-03 |
| [#4](#事故-4cli-与-agent-payload-键名重构后失配) | CLI 与 Agent payload 键名重构后失配 | SEV-2 | 2026-03-18 |
| [#3](#事故-3sm-命令参数键与结构错误导致完全失败) | `sm` 命令参数键与结构错误导致完全失败 | SEV-1 | 2026-03-01 |
| [#2](#事故-2top-命令已实现但未接入主分发) | `top` 命令已实现但未接入主分发 | SEV-3 | 2026-02-26 |
| [#1](#事故-1clipy-与-cli-冲突及-arthas-参数不完整) | `cli.py` 与 `cli/` 冲突及 Arthas 参数不完整 | SEV-2 | 2026-01-29 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题聚焦 CLI 入口与 Agent 命令契约的演化失步：包括命令未接入主分发、字段命名不一致、参数结构不匹配及历史模块结构冲突。共同模式是"接口定义变更后未端到端同步验证"，导致命令可见但不可用，或直接返回缺参错误。

2026-04-03 新增第五类问题：`peeka-cli run` 命令初始实现中存在多处缺陷，包括 `OutputFormatter` 的 `file=` 参数默认值在 pytest 环境下捕获了 monkeypatch 前的 stdout 对象，导致测试输出路由错误；bootstrap 模板内联维护困难；run 命令缺少 `--output-file` 等实用参数；临时文件未在异常路径下清理。

2026-05-27 新增第六类问题：容器级诊断测试暴露了 CLI shell 参数拼接、logger 参数别名、monitor 统计字段、instance method 参数语义、stack observation 兼容字段和 TUI smoke 覆盖之间的多点契约漂移。这类问题不一定表现为单个命令完全不可用，但会让真实容器中的 CLI/TUI 工作流出现断言失败、条件表达式误判或输出字段缺失。

2026-06-07 新增第七类问题：session/control-plane 重构引入了 target、client、job、probe、consumer 和 dx 等新命名空间，但 CLI 侧 target 解析、agent 侧响应 envelope、probe/job 生命周期和 streaming observation 路由没有一次性用跨命名空间契约测试冻结。问题不是某个单点命令拼错，而是“对象模型扩展后，入口、路由、生命周期和输出 schema 同步不足”。

---

## 事故 #7：session control-plane 多目标路由与 probe 契约缺口

> **Tag 范围**：`v0.1.15` → `v0.1.16` | **严重级别**：SEV-2 | **日期**：2026-06-07

### 概要

`v0.1.16` 引入 target/client/job/probe/consumer/dx 控制面后，review 发现几类契约缺口：带 `--target` 的 CLI 命令仍可能连接 `_check_agent_attached()` 找到的第一个 agent；target detach 使用了 agent 不支持的 RPC 形状；`probe.stop` 只更新 registry 状态而没有传播到实际 instrumentation；probe 非 start 动作被错误标记为 streaming job；TUI stream client 在 hello 身份建立后收不到 observation。

这些问题会在多目标或长生命周期 probe 场景下表现为“命令打到错误进程”“agent 被从文件系统隐藏但仍留在目标进程中”“用户看到 probe stopped 但 wrapper/top/monitor 还在运行”或“Dashboard/TUI 连接存在但没有实时数据”。

### 根因分析

#### 类别
Contract Drift / Lifecycle State Mismatch

#### 分析

这次缺口来自同一个系统性根因：新的 session/control-plane 对象模型被分层实现，但跨层合同没有一开始就冻结为测试矩阵。

1. CLI handler 已支持 `--target`，但部分路径仍先调用通用 `_check_agent_attached()`，导致 socket 选择早于 target 解析。
2. target detach 清理文件前没有确认 agent 实际执行了支持的 `{"type": "detach"}` 命令，形成“本地已解绑、目标仍注入”的不可发现状态。
3. probe registry 的状态更新与 DecoratorInjector/monitor/top 运行资源之间缺少双向绑定，`probe.stop` 只改账本，不停实际资源。
4. job lifecycle 将 probe namespace 的成功动作泛化为 streaming，导致 stop/status/inspect 这类终止型 RPC 也可能占住 foreground job。
5. agent transport 的 observation 广播没有把 hello 后的 stream-only client 身份作为稳定路由条件，TUI stream client 能连接但收不到数据。

### 复现

#### 前置条件
- 至少两个 alive target。
- 一个通过 watch/trace/monitor/top 启动的 probe。
- 一个 TUI 或 StreamingAgentClient stream 连接。

#### 步骤
1. 对 target A 和 target B 分别 attach。
2. 执行 `peeka-cli client create --target <target_B>` 或 target-filtered `job/probe/consumer/dx` 命令。
3. 启动 watch/trace probe 后执行 `peeka-cli probe stop --probe <id>`。
4. 在 TUI Dashboard/stream view 中观察是否收到实时 observation。

#### 预期行为
- 所有 target-scoped CLI 命令先解析 target，再连接对应 socket。
- detach 只在 agent 确认成功后清理 target 文件。
- probe stop 终止实际 instrumentation 并清理 foreground job。
- 只有 probe start 类动作保持 streaming；status/inspect/stop/cleanup 应进入终态。
- stream client 通过 hello 建立身份后可收到匹配 observation。

#### 实际行为
review 时发现上述路径存在偏差，可能导致错误路由、孤儿 agent、非终态 job 或 TUI 无实时数据。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`4f5797f`](https://github.com/peeka-project/peeka/commit/4f5797f9f262eba588d3a24154781c014f585639) | lufeihaidao | 2026-06-07 | fix(client-session): remediate F1 oracle architectural defects |
| [`3c91a1d`](https://github.com/peeka-project/peeka/commit/3c91a1de2f5f41f3f236f30f9bc75bc8bbb86aff) | lufeihaidao | 2026-06-07 | fix(command-job): F-wave remediation (D1-D7) — lifecycle, envelope, scope |
| [`8376876`](https://github.com/peeka-project/peeka/commit/8376876a1d18073854b4d6f7c5a514ba14bf0e71) | lufeihaidao | 2026-06-07 | fix(agent): wrap probe.* responses in data envelope to match job.* convention |
| [`ff6b1d1`](https://github.com/peeka-project/peeka/commit/ff6b1d16928c4df96ac6cb0725904c391e032598) | lufeihaidao | 2026-06-07 | fix(probe): probe.cleanup returns list of removed ids matching job.cleanup pattern |
| [`b8a68a1`](https://github.com/peeka-project/peeka/commit/b8a68a142077011981410a472c4c767dab7e16f8) | lufeihaidao | 2026-06-07 | fix(probe): rename inspect response key recent_events -> events to match CLI contract |
| [`ef8be8c`](https://github.com/peeka-project/peeka/commit/ef8be8cebdb9c2dab813379c9bc3dffc6d91f212) | lufeihaidao | 2026-06-07 | fix(probe): align cleanup/inspect/status with plan spec |
| [`6d7e6d4`](https://github.com/peeka-project/peeka/commit/6d7e6d49e8fc3882459ff3ee48a990b0d34d09c2) | lufeihaidao | 2026-06-07 | fix(probe): isolate control-plane RPC from OBS broadcast latency |
| [`b34160f`](https://github.com/peeka-project/peeka/commit/b34160f224635e864624e93de108fc8b5a8f5c01) | lufeihaidao | 2026-06-07 | fix(agent): serialize control-plane responses to prevent transport error under streaming load |
| [`a1c5df2`](https://github.com/peeka-project/peeka/commit/a1c5df24521027c03062cfac80cea7523a7b1677) | lufeihaidao | 2026-06-07 | fix(agent): stream observations to TUI stream clients |
| [`169b57d`](https://github.com/peeka-project/peeka/commit/169b57d372632da25c4a71f4ca5ab9a548103da5) | lufeihaidao | 2026-06-07 | fix(cli): require target-aware resource routing |
| [`9fd579e`](https://github.com/peeka-project/peeka/commit/9fd579eb14b6858a1af727ed4afeb0ee49af55fb) | lufeihaidao | 2026-06-07 | fix(monitor): reuse injector target resolution |

#### 变更内容

- CLI target-scoped handlers 在创建 client/session 前解析 target，并把 socket、target_id 和 client_session_id 显式传入后续命令。
- `target detach --force` 改为使用 agent 支持的 detach RPC，并在 RPC 失败时保留 socket/pid 文件。
- probe stop 传播到 watch/trace/monitor/top 的实际资源，start job 也进入终态。
- probe inspect/cleanup/status 的响应 envelope、字段名和 cleanup 返回结构向 job namespace 对齐。
- agent transport 将 control-plane 响应和 observation 广播隔离，避免 stream 背压影响 RPC。
- TUI stream client 通过 hello 身份后可收到 observation。

#### 验证
- `uv run pytest tests/ -v --tb=short -m "not e2e and not container and not tui" --timeout=30 --ignore=tests/tui --ignore=tests/test_tui.py --ignore=tests/test_theme.py`：834 passed。
- `uv run pytest tests/tui/test_dashboard_view.py -q`：15 passed。
- `v0.1.16` 发布流水线 `publish-pypi.yml` 第二次运行通过。

### 影响

- **受影响用户**：多目标 attach 用户、通过 CLI 管理 client/job/probe/consumer/dx 的用户、TUI 实时流用户。
- **持续时间**：同一 release 开发周期内被 review 和测试发现，未进入成功发布的 PyPI 版本。
- **数据影响**：无持久数据损坏。风险是命令作用于错误进程、agent 孤儿化、probe 账本与实际 instrumentation 不一致。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-06-07 | session/control-plane 功能实现后进入 review |
| 2026-06-07 | review 发现 target detach、multi-target routing、probe lifecycle 和 stream routing 缺口 |
| 2026-06-07 | 多个 fix 提交修复 control-plane 契约和生命周期 |
| 2026-06-07 | `v0.1.16` 发布流水线验证通过 |

### 经验教训

#### 做得好的方面
- review 明确指出了跨命名空间的系统性缺口，而不是只修单个命令。
- 后续补充了 agent/client/job/probe/target/consumer/dx 的单元和容器契约覆盖。

#### 可以改进的方面
- 新增 control-plane namespace 时，应先定义 target/client/job/probe 的对象图和路由矩阵。
- “registry 状态”和“实际运行资源”必须有同一套 lifecycle 不变量，不能只测账本。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为所有 target-scoped CLI handler 保留“先解析 target 再连接 socket”的测试 | P0 | 已完成 |
| 为 probe stop 增加实际 instrumentation/resource cleanup 断言 | P0 | 已完成 |
| 为新增 control-plane namespace 维护共享 envelope/schema contract 表 | P1 | 待处理 |

### 预防

- **立即执行**：所有新增 namespace 必须有 handler-level envelope 测试和 CLI target routing 测试。
- **短期**：把 target/client/job/probe/consumer/dx 的状态迁移和 cross-reference 写入 schema 文档。
- **长期**：考虑从同一份 schema 生成 CLI parser 参数、agent handler envelope 和 JSONL contract tests。

### 参考

- 修复提交：`4f5797f`, `3c91a1d`, `8376876`, `ff6b1d1`, `b8a68a1`, `ef8be8c`, `6d7e6d4`, `b34160f`, `a1c5df2`, `169b57d`, `9fd579e`

---

## 事故 #6：容器诊断 CLI 兼容性回归

> **Tag 范围**：`v0.1.14` → `v0.1.15` | **严重级别**：SEV-2 | **日期**：2026-05-27

### 概要

`v0.1.15` 发布前的容器测试发现多个诊断命令在真实 CLI/TUI 工作流中存在兼容性问题：测试 helper 用裸字符串拼接命令导致带空格/特殊字符的参数被 shell 重新解释；logger 只接受 `--logger`，缺少历史 `--name` 别名；monitor observation 缺少 `count`/`call_count` 兼容字段；watch/trace 条件表达式在实例方法上把 `self` 暴露进 `params`；stack observation 没有同时提供 `data.stack_trace`。

### 根因分析

#### 类别
Integration Error / Contract Drift

#### 分析

该事故由多个小契约漂移叠加而成，根因是单元测试覆盖了各模块局部行为，但缺少足够的真实容器 CLI 工作流约束。

1. 容器测试 helper 直接拼接 shell 命令：

```python
cli_cmd = f"python -m peeka.cli.main {' '.join(cmd_parts)}"
```

当参数中包含 `params[0] > 5`、函数 pattern 或其他 shell 敏感字符时，命令行语义可能被 shell 改写。修复改为逐参数 `shlex.quote()`。

2. logger CLI 参数在文档/旧测试中仍使用 `--name`，但 parser 只保留了 `--logger`。这属于历史别名兼容性缺失。

3. monitor 输出只包含 manager 内部字段，未提供下游测试和用户常用的 `count`/`call_count` 兼容键。

4. `DecoratorInjector` 在实例方法上把 `self` 放进 `params`，导致 Arthas 风格条件 `params[0] > 5` 实际取到目标对象而非第一个用户参数。相同问题也影响 trace 条件过滤。

5. stack observation 顶层有 `stack`，但容器 E2E 期望 `data.stack_trace`。字段命名没有做到 additive 兼容。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | - | 2026-05-27 前 | 多个历史 CLI/Agent/测试契约分别演化，缺少统一 schema 或容器级契约测试 |

### 复现

#### 前置条件
- 使用 `peeka-test:3.12` 或 `peeka-test:3.14` 容器镜像。
- 目标进程已启动，CLI 通过 attach 连接到目标。

#### 步骤
1. 运行 watch 条件过滤：`peeka-cli watch "__main__.Calculator.add" --condition "params[0] > 5" -n 2`。
2. 运行 logger list/get/set，尤其使用 `--name` 历史参数。
3. 运行 monitor 并检查 observation 中是否有 `count`/`call_count`。
4. 运行 stack 并检查 observation 中是否有 `data.stack_trace`。
5. 在容器中运行 TUI smoke，切换主要 tab。

#### 预期行为
真实容器中的 CLI/TUI 诊断工作流可以稳定解析参数、执行命令，并输出兼容 JSONL 字段。

#### 实际行为
部分命令因参数解析或字段缺失失败；部分测试只能通过放宽断言而不能证明诊断输出完整。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`75b09c4`](https://github.com/peeka-project/peeka/commit/75b09c45bdc66ad8717b7a32ff2f71887e15ae8c) | lufeihaidao | 2026-05-27 | fix(container): restore diagnostic CLI compatibility |

#### 变更内容

- `tests/container/test_cli_e2e.py` 的 `run_cli_command()` 改为 `shlex.quote()` 逐参数构造命令。
- `peeka/cli/main.py` 为 logger 参数恢复 `--name` 兼容别名，并统一写入 `dest="logger"`。
- `peeka/commands/monitor.py` 在周期输出中补充 `count` 和 `call_count`。
- `peeka/core/injector.py` 对实例方法引入 `user_args`，条件表达式和 observation `params` 都排除 `self`；stack observation additive 增加 `data.stack_trace`。
- 新增 `tests/container/tui_smoke_inner.py`，在容器内用 Textual headless mode 验证 TUI 启动、help 快捷键和主 tab 切换。
- 调整容器测试对长时间观察命令的退出码期望，允许在已产生有效输出后由外层 timeout 结束。

#### 验证
- `uv run pytest tests/container/ -v -m container --timeout=180`：176 passed。
- `v0.1.15` 发布流水线 `publish-pypi.yml` 的测试 job 通过。

### 影响

- **受影响用户**：通过 CLI 使用 watch/trace/stack/monitor/logger 的用户，以及依赖容器 E2E 验证真实诊断工作流的开发者。
- **持续时间**：无法精确定位；多个契约漂移来自不同历史提交，在 `v0.1.15` 发布前集中修复。
- **数据影响**：无。影响为命令可用性、条件过滤语义和 JSONL 字段兼容性。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-05-27 前 | CLI、Agent 输出和容器测试契约分别演化 |
| 2026-05-27 | 容器测试暴露多点兼容性问题 |
| 2026-05-27 | `75b09c4` 修复 CLI 参数、输出字段和 TUI smoke 覆盖 |
| 2026-05-27 | `v0.1.15` 发布流水线验证通过 |

### 经验教训

#### 做得好的方面
- 容器测试覆盖了真实 shell、真实 CLI 入口、agent socket 和 TUI headless 生命周期，发现了单元测试难以暴露的问题。
- 修复采用 additive 字段策略，没有删除现有输出字段。

#### 可以改进的方面
- CLI 参数别名和 JSONL observation 字段需要集中声明，避免通过测试期望隐式维护。
- 诊断命令的“实例方法 params 不含 self”语义应写入命令契约，而不是只靠 Arthas 习惯推断。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为 watch/trace/stack/monitor/logger 建立最小 CLI contract 表，覆盖参数别名和 JSONL 字段 | P1 | 待处理 |
| 容器测试 helper 必须使用 argv quoting，禁止裸 `' '.join(args)` | P0 | 已完成 |
| 对 instance method 条件表达式增加非容器单元回归测试 | P1 | 待处理 |

### 预防

- **立即执行**：保留容器 E2E 中的条件表达式、stack payload 和 TUI smoke 覆盖。
- **短期**：将常用 JSONL observation 字段加入 schema/contract 测试。
- **长期**：为 CLI parser 和 Agent command 参数生成共享契约，减少双端手写漂移。

### 参考

- 修复提交：`75b09c4`

---

## 事故 #5：peeka-cli run 命令 OutputFormatter stdout 捕获缺陷及多处实现问题

> **Tag 范围**：`v0.1.7` → `v0.1.8` | **严重级别**：SEV-2 | **日期**：2026-04-03

### 概要

`peeka-cli run` 命令在初始实现（v0.1.7）中存在多个缺陷：`OutputFormatter` 各方法的 `file=` 参数默认值在模块加载时绑定为 `sys.stdout`，在 pytest 中 monkeypatch stdout 后实际输出不走 monkeypatch 的目标，导致测试断言失败；bootstrap 注入代码以内联 f-string 维护，难以阅读和修改；`run` 命令缺少 `--output-file` 参数；临时文件在异常路径下未清理。以上问题在运行测试和实际使用中均可观察到。

### 根因分析

#### 类别
Logic Error / Configuration Error

#### 分析

1. **OutputFormatter stdout 捕获问题**：`file=sys.stdout` 作为默认参数在函数定义时求值，绑定了定义时的 `sys.stdout` 对象。pytest 的 `capsys`/monkeypatch 替换的是 `sys.stdout` 引用，而非已绑定的对象，导致输出绕过捕获。修复将默认值改为 `None`，方法内部使用 `file or sys.stdout`，每次调用时动态解析：

```python
# 修复前（定义时绑定）
def status(message: str, file=sys.stdout, **kwargs) -> None:
    print(json.dumps(output), flush=True, file=file)

# 修复后（调用时解析）
def status(message: str, file=None, **kwargs) -> None:
    print(json.dumps(output), flush=True, file=file or sys.stdout)
```

2. **bootstrap 模板内联**：注入代码以 f-string 内联在 `cli/main.py` 中，提取到独立的 `peeka/core/bootstrap.py` 模板文件后可读性和可维护性大幅改善。

3. **临时文件清理**：`cmd_run` 未使用 `try/finally` 包裹，异常退出时临时文件不会被清理。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 致因提交为 `run` 命令初始实现提交（4d459d1） | lufeihaidao | 2026-04-03 前 | feat(cli): add peeka-cli run command for short-lived scripts |

### 复现

#### 前置条件
- 使用 pytest + capsys 测试 `OutputFormatter` 输出
- 或运行 `peeka-cli run` 脚本遇到异常

#### 步骤
1. 编写 pytest 测试，monkeypatch `sys.stdout`，调用 `OutputFormatter.status(...)`
2. 断言捕获到的输出

#### 预期行为
输出被 capsys/monkeypatch 捕获

#### 实际行为
输出写入定义时绑定的原始 sys.stdout，测试断言失败

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`d7ad207`](https://github.com/peeka-project/peeka/commit/d7ad2075353a48c3d4f8bb0d38e3d7f62d304c71) | lufeihaidao | 2026-04-03 | fix(cli): polish peeka-cli run command and add bootstrap template |

#### 变更内容
- `OutputFormatter` 所有方法 `file=` 默认值改为 `None`，方法内 `file or sys.stdout` 动态解析
- bootstrap 注入代码提取到 `peeka/core/bootstrap.py`
- `cmd_run` 用 `try/finally` 确保临时文件清理
- 添加 `--output-file` 参数支持将观测输出写入文件
- 观测数据路由到 stdout，控制消息路由到 stderr
- `ProcessAttacher` 增加 `session_id` 参数，使用 uuid4 替代 `pid=0`

#### 验证
`peeka-cli run` 相关测试通过；临时文件清理行为验证通过。

### 影响

- **受影响用户**：使用 `peeka-cli run` 命令的用户；编写 OutputFormatter 相关测试的开发者
- **持续时间**：从 `run` 命令初始实现（4d459d1）到 v0.1.8 修复
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 初始实现（4d459d1） | `run` 命令及 OutputFormatter 缺陷引入 |
| 2026-04-03 | 缺陷被识别 |
| 2026-04-03 | 修复提交：`d7ad207` |

### 经验教训

#### 做得好的方面
- 集中修复了多个相关缺陷，避免后续积累。

#### 可以改进的方面
- Python 函数默认参数"定义时求值"是经典陷阱，应在代码评审中主动检查涉及全局对象（stdout/stderr/None）的默认参数。
- 新命令实现应包含基本的 happy path + 异常 path 测试。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 新增函数默认参数评审检查项：禁止使用可变对象或全局流对象作为默认值 | P1 | 待处理 |
| 所有新 CLI 命令实现须包含 try/finally 清理逻辑 | P1 | 已完成（d7ad207） |

### 预防

- **立即执行**：OutputFormatter 所有输出方法 `file=` 默认值统一为 `None`，方法内动态解析。
- **短期**：添加 CLI run 命令的端到端测试，覆盖正常路径和异常退出路径。
- **长期**：建立"Python 常见陷阱"检查清单（默认参数、mutable default、stdout 绑定等），纳入代码评审流程。

### 参考

- 修复 PR/提交：`d7ad207 fix(cli): polish peeka-cli run command and add bootstrap template`
- 相关 issue：未提供

---



## 事故 #4：CLI 与 Agent payload 键名重构后失配

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-2 | **日期**：2026-03-18

### 概要

重构后若干命令字段改名未同步到 CLI 侧，`logger` 与 `vmtool` 命令因缺失/错误键名失败。

### 根因分析

#### 类别
Integration Error

#### 分析
命令契约在 Agent 侧演进后，CLI payload 仍使用旧键：
- `logger`：CLI 发送 `name`，Agent 期望 `logger_name`
- `vmtool`：CLI 未发送必须字段 `action`

属于典型双端协议漂移。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 命令参数命名重构后 CLI 未同步更新 |

### 复现

#### 前置条件
- 使用受影响 CLI 命令。

#### 步骤
1. 运行 `peeka-cli logger list`。
2. 运行 `peeka-cli vmtool`。

#### 预期行为
命令成功执行并返回结果。

#### 实际行为
报缺少参数（`logger_name` 或 `action`）。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `454a70d` | 未提供 | 2026-03-18 | fix(cli): correct payload key mismatches between CLI and agent commands |

#### 变更内容
- `logger` payload：`"name": args.name` → `"logger_name": args.name`
- `vmtool` payload：补充 `"action": args.action`

#### 验证
- 受影响 CLI 命令恢复执行。
- 参数成功传递至 Agent。

### 影响

- **受影响用户**：使用 logger/vmtool 的 CLI 用户。
- **持续时间**：自参数重构未同步起至 2026-03-18。
- **数据影响**：无；命令失败。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | 参数命名重构引入契约漂移 |
| 2026-03-18 | 失配问题确认 |
| 2026-03-18 | 修复提交：`454a70d` |
| 2026-03-18 | CLI 命令验证通过 |

### 经验教训

#### 做得好的方面
- 问题定位直接指向字段级契约，修复成本低。

#### 可以改进的方面
- 缺少 CLI↔Agent 契约测试与变更清单。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为所有 CLI 命令增加 payload schema 回归测试 | P0 | 待处理 |

### 预防

- **立即执行**：命令字段改名必须双端同改并评审。
- **短期**：建立命令契约表并在 CI 中比对。
- **长期**：引入共享 schema 生成 CLI/Agent 参数层。

### 参考

- 修复 PR/提交：`454a70d`
- 相关 issue：未提供

---

## 事故 #3：`sm` 命令参数键与结构错误导致完全失败

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-1 | **日期**：2026-03-01

### 概要

`sm` CLI 将 `class_pattern` 与 `method_pattern` 分开发送，且使用 `detail` 错拼；Agent 期望 `pattern` 与 `details`，命令完全不可用。

### 根因分析

#### 类别
Integration Error

#### 分析
协议结构和键名双重不匹配：
- 结构：Agent 要求 `pattern="class.method"`
- 键名：`details` 被写成 `detail`

修复前后：

```python
# 修改前
command = {
    "type": "sm",
    "class_pattern": args.class_pattern,
    "method_pattern": args.method_pattern,
    "detail": args.detail,
}

# 修改后
command = {
    "type": "sm",
    "pattern": f"{args.class_pattern}.{args.method_pattern}",
    "details": args.detail,
}
```

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | `sm` CLI 实现时未按 Agent 契约组装参数 |

### 复现

#### 前置条件
- 存在可匹配类与方法。

#### 步骤
1. 执行 `peeka-cli sm Calculator add`。

#### 预期行为
返回匹配方法结果。

#### 实际行为
Agent 返回缺少 `pattern`。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `b00b0f4` | 未提供 | 2026-03-01 | fix(cli): fix sm command sending wrong parameter keys to agent |

#### 变更内容
- 合并类/方法参数为单字段 `pattern`。
- 修正 `detail` → `details`。

#### 验证
- `sm` 命令可正确执行并返回搜索结果。

### 影响

- **受影响用户**：使用 `sm` 的用户。
- **持续时间**：自 `sm` 引入至 2026-03-01。
- **数据影响**：无；功能不可用。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | `sm` CLI 初版引入参数错配 |
| 2026-03-01 | 缺参故障确认 |
| 2026-03-01 | 修复提交：`b00b0f4` |
| 2026-03-01 | 命令验证通过 |

### 经验教训

#### 做得好的方面
- 用最小改动恢复协议一致性。

#### 可以改进的方面
- 拼写与结构错误应由自动化测试提前拦截。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为 `sm` 增加 CLI->Agent 契约单测（含键名和格式） | P0 | 待处理 |

### 预防

- **立即执行**：新增命令后做端到端 smoke 测试。
- **短期**：实现 payload 字段白名单检查。
- **长期**：通过共享数据模型消除手写字典。

### 参考

- 修复 PR/提交：`b00b0f4`
- 相关 issue：未提供

---

## 事故 #2：`top` 命令已实现但未接入主分发

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-3 | **日期**：2026-02-26

### 概要

`top` 模块与测试已存在，但 `peeka/cli/main.py` 分发遗漏 `top` 分支，用户执行时报 `Unknown command: top`。

### 根因分析

#### 类别
Missing Validation

#### 分析
新增命令后缺少“入口分发完整性”检查。属于注册流程漏步骤问题，而非命令实现问题。

修复片段：

```python
elif args.command == "top":
    return cmd_top(args)
```

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 添加 top 命令时遗漏 main 分发分支 |

### 复现

#### 前置条件
- 安装包含 top 命令实现的版本。

#### 步骤
1. 执行：
   ```bash
   peeka-cli top <pid>
   ```

#### 预期行为
进入 top 命令执行流程。

#### 实际行为
输出 `Unknown command: top`。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `28330f8` | 未提供 | 2026-02-26 | fix(cli): add missing top command dispatch in main() |

#### 变更内容
- 在主命令分发中添加 `top` case。

#### 验证
- `peeka-cli top` 可正常解析并执行。

### 影响

- **受影响用户**：CLI `top` 命令用户。
- **持续时间**：命令实现发布后至 2026-02-26。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | top 命令实现上线但未接入分发 |
| 2026-02-26 | Unknown command 故障报告 |
| 2026-02-26 | 修复提交：`28330f8` |
| 2026-02-26 | CLI 验证通过 |

### 经验教训

#### 做得好的方面
- 修复直接、低风险。

#### 可以改进的方面
- 缺少“命令枚举与分发一致性”自动检查。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 增加命令注册完整性测试（help 列表与分发分支对齐） | P1 | 待处理 |

### 预防

- **立即执行**：新增命令 checklist 必含“main 分发更新”。
- **短期**：自动比较 argparse 子命令与处理函数覆盖。
- **长期**：改为声明式命令注册机制。

### 参考

- 修复 PR/提交：`28330f8`
- 相关 issue：未提供

---

## 事故 #1：`cli.py` 与 `cli/` 冲突及 Arthas 参数不完整

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-2 | **日期**：2026-01-29

### 概要

项目同时存在 `peeka/cli.py` 与 `peeka/cli/`，造成导入歧义；同时 CLI 对 Arthas 兼容参数实现不完整，功能体验与预期不一致。

### 根因分析

#### 类别
Configuration Error

#### 分析
重构后遗留同名文件与包目录，触发 Python 导入路径歧义。另有参数体系半迁移：缺失 `-b/-e/-s/-f` 等标志，并将条件参数命名与目标兼容接口不一致。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | CLI 重构后未移除旧 `cli.py`，且参数兼容迁移不完整 |

### 复现

#### 前置条件
- 含冲突结构与旧参数定义的版本。

#### 步骤
1. 执行 `import peeka.cli`。
2. 执行 `peeka-cli -h` 查看参数。

#### 预期行为
导入唯一且参数集完整。

#### 实际行为
可能导入错误模块；帮助中缺少关键兼容参数。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `7dc6294` | 未提供 | 2026-01-29 | fix(cli): add full Arthas flag support and resolve file/directory conflict |

#### 变更内容
- 删除冲突文件 `peeka/cli.py`，保留包目录结构。
- 补齐 Arthas 兼容参数：`-b/--before`、`-e/--exception`、`-s/--success`、`-f/--finish`。
- 参数重命名：`-c/--condition` → `--condition-express`。

#### 验证
- 导入歧义消除。
- 参数可完整解析并保持兼容性。

### 影响

- **受影响用户**：CLI 使用者与二次开发导入场景。
- **持续时间**：自 CLI 重构后至 2026-01-29。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | CLI 重构引入文件/目录冲突与参数缺失 |
| 2026-01-29 | 问题确认 |
| 2026-01-29 | 修复提交：`7dc6294` |
| 2026-01-29 | 导入与参数验证通过 |

### 经验教训

#### 做得好的方面
- 一次修复同时清理结构冲突与参数兼容缺口。

#### 可以改进的方面
- 重构清理流程缺少“同名模块冲突”检查。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 在 CI 增加模块导入冲突扫描 | P1 | 待处理 |

### 预防

- **立即执行**：重构后执行同名文件/目录冲突审计。
- **短期**：为 Arthas 兼容参数建立对照测试表。
- **长期**：维护 CLI 契约版本化文档。

### 参考

- 修复 PR/提交：`7dc6294`
- 相关 issue：未提供
