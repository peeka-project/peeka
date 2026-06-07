# 测试期望与示例可测试性维护

| 字段 | 值 |
|------|-----|
| **话题** | 测试期望、demo 日志示例与测试维护 |
| **受影响组件** | tests, tui, examples/demo.py |
| **最高严重级别** | SEV-2 (Medium) |
| **事故次数** | 4 |
| **时间跨度** | 2026-02-07 至 2026-06-07 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#4](#事故-4probe-help-测试依赖本地-uv-导致-release-workflow-失败) | probe help 测试依赖本地 uv 导致 release workflow 失败 | SEV-2 | 2026-06-07 |
| [#3](#事故-3移除-agent-log-标签后测试仍期望-11-个标签) | 移除 Agent Log 标签后测试仍期望 11 个标签 | SEV-2 | 2026-03-23 |
| [#2](#事故-2demopy-缺失-logging-场景导致-logger-命令无法测试) | demo.py 缺失 logging 场景导致 logger 命令无法测试 | SEV-3 | 2026-03-02 |
| [#1](#事故-1mainscreen-构造函数签名变更后测试调用未更新) | MainScreen 构造函数签名变更后测试调用未更新 | SEV-3 | 2026-02-07 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题聚焦“实现变更后测试或示例未同步更新”的问题模式。具体表现为：TUI 结构/签名发生变化后，测试断言与构造调用仍停留在旧状态；示例程序未覆盖 logger 命令所需 logging 场景，导致命令可测试性缺失。影响主要集中在测试与验证链路，不直接影响核心运行时逻辑。

2026-06-07 的新增事故说明，测试代码也必须区分“本地开发约定”和“CI runner 可用工具”。项目开发规则要求开发者用 `uv run` 执行 Python 命令，但测试自身不能假设 GitHub Actions runner 已安装 uv；测试应使用当前解释器或直接调用被测函数。

---

## 事故 #4：probe help 测试依赖本地 uv 导致 release workflow 失败

> **Tag 范围**：`v0.1.15` → `v0.1.16` | **严重级别**：SEV-2 | **日期**：2026-06-07

### 概要

`v0.1.16` 第一次 tag push 后，`publish-pypi.yml` 的 Run Tests job 失败。失败用例是 `tests/test_probes_cli.py::TestProbeHelpOutput::test_probe_help_lists_5_subcommands`，它通过 `subprocess.run(["uv", "run", "peeka-cli", "probe", "--help"])` 启动 CLI。在本地开发机该命令可用，但 GitHub Actions 的 Python 3.12 runner 没有安装 uv，导致 `FileNotFoundError: [Errno 2] No such file or directory: 'uv'`，PyPI 发布和 GitHub Release 创建被阻断。

### 根因分析

#### 类别
Test Environment Assumption / Release Gate Failure

#### 分析

测试把项目开发指南中的“开发者运行 Python 命令必须加 `uv run`”误用到了测试内部。开发指南约束的是人和 agent 在仓库中执行命令的方式，不代表 CI runner 或最终用户环境一定存在 uv。

测试目标只是验证 `probe --help` 包含 5 个子命令，因此不需要经过 uv，也不需要依赖 entrypoint 是否安装到 PATH。更稳妥的方式是用当前测试解释器执行模块：

```python
[sys.executable, "-m", "peeka.cli.main", "probe", "--help"]
```

这保持了“使用同一个测试环境解释器”的合同，也避免引入额外工具依赖。

### 复现

#### 前置条件
- GitHub Actions runner 或任意没有安装 uv 的 Python 环境。

#### 步骤
1. 运行 `pytest tests/ -v --tb=short -m "not e2e and not container and not tui" --timeout=30 --ignore=tests/tui --ignore=tests/test_tui.py --ignore=tests/test_theme.py`。
2. 执行到 `TestProbeHelpOutput`。

#### 预期行为
测试使用当前解释器验证 probe help 输出并通过。

#### 实际行为
`subprocess.run()` 找不到 `uv`，测试失败，release workflow 中断。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`e0a8c14`](https://github.com/peeka-project/peeka/commit/e0a8c1410a41e04b7807e2a8d2a8fc66041fb4e3) | lufeihaidao | 2026-06-07 | test(cli): avoid uv dependency in probe help test |

#### 变更内容

- 引入 `sys.executable`。
- 将 subprocess 命令从 `uv run peeka-cli probe --help` 改为 `python -m peeka.cli.main probe --help`。
- 移动本地 `v0.1.16` tag 到修复后的 HEAD，强制更新远端 tag 后重新触发 release workflow。

#### 验证
- 本地复现 GitHub Actions 命令：834 passed。
- `uv run ruff check peeka/ tests/test_probes_cli.py tests/tui/test_dashboard_view.py`：通过。
- 第二次 `v0.1.16` `publish-pypi.yml` run 通过，PyPI 和 GitHub Release 成功发布。

### 影响

- **受影响用户**：无直接用户影响。
- **受影响流程**：`v0.1.16` 首次 release workflow 被阻断，PyPI 发布延后到第二次 tag 更新后完成。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-06-07 | 第一次推送 `v0.1.16` tag |
| 2026-06-07 | GitHub Actions Run Tests 因找不到 `uv` 失败 |
| 2026-06-07 | `e0a8c14` 修复测试命令 |
| 2026-06-07 | 强制更新 `v0.1.16` tag 并重新触发 workflow |
| 2026-06-07 | 第二次 workflow 通过并完成 PyPI/GitHub Release |

### 经验教训

#### 做得好的方面
- release workflow 在发布前阻断了 PyPI，避免了半成品发布。
- 失败日志定位明确，修复范围小。

#### 可以改进的方面
- 本地 release 前的全量 pytest 在有 uv 的环境中无法暴露“CI 无 uv”问题。
- 测试中出现外部工具命令时应优先使用 `sys.executable` 或 mock 入口，而不是依赖开发工具。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 测试内部不得调用 `uv run`，除非该测试明确验证 uv 集成 | P0 | 已完成 |
| 增加静态扫描或 review checklist：测试 subprocess 中禁止硬编码开发工具 | P1 | 待处理 |

### 预防

- **立即执行**：搜索测试目录中硬编码 `uv run` 的 subprocess 调用。
- **短期**：CLI help/entrypoint 测试统一使用 `sys.executable -m peeka.cli.main`。
- **长期**：release gate 加入“CI 命令与本地验证命令一致性”检查。

### 参考

- 修复提交：`e0a8c14`
- 失败 workflow：`27094576503`
- 成功 workflow：`27094670987`

---

## 事故 #3：移除 Agent Log 标签后测试仍期望 11 个标签

> **Tag 范围**：`未提供` → `未提供` | **严重级别**：SEV-2 | **日期**：2026-03-23

### 概要

`test_main_screen_has_correct_number_of_tabs` 失败。测试仍期望 11 个标签，但实际已变为 10 个；同时标签顺序断言也未同步更新。通过更新标签数量、标签列表与顺序断言完成修复。

### 根因分析

#### 类别
Regression

#### 分析
Agent Log 功能被合并到 Dashboard 后，独立标签被移除，但测试仍保留旧期望：
- 仍断言 `assert len(panes) == 11`
- 标签列表仍包含 `"agentlog"`
- 标签顺序仍按旧布局校验（Inspect 快捷键位置未更新）

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 重构移除 Agent Log 标签之后测试未更新 |

> 致因提交无法确定性定位；来源文件仅给出“重构移除 Agent Log 标签之后测试没更新”。

### 复现

#### 前置条件
- 使用已移除 Agent Log 标签的 TUI 代码
- 测试仍保留旧标签数量和顺序期望

#### 步骤
1. 运行 `uv run pytest tests/tui/test_tui.py::TestMainScreen`。
2. 查看 `test_main_screen_has_correct_number_of_tabs` 结果。

#### 预期行为
测试应与当前标签结构一致并通过。

#### 实际行为
测试失败：期望 11 个标签，实际 10 个；标签顺序断言不一致。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `d0a6f11` | 未提供 | 2026-03-23 | fix(tui): update expected tab count and order after removing agent log tab |

#### 变更内容
1. 修改测试期望：`assert len(panes) == 10`（从 11 改为 10）
2. 从标签列表移除 `"agentlog"`
3. 更新标签顺序：Inspect 快捷键改为 8（不再是 9）
4. 更新输入标签计数期望

#### 验证
测试通过，期望与当前实际标签结构一致。

### 影响

- **受影响用户**：运行该测试的开发与 CI 流程。
- **持续时间**：从移除 Agent Log 标签后到 `d0a6f11` 修复提交。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | Agent Log 标签移除，但测试未同步更新 |
| 2026-03-23 | 发现 `test_main_screen_has_correct_number_of_tabs` 失败 |
| 2026-03-23 | 修复提交：`d0a6f11` |
| 2026-03-23 | 测试验证通过 |

### 经验教训

#### 做得好的方面
- 失败由测试直接暴露，问题定位明确。
- 修复覆盖了数量、列表和顺序三个断言维度。

#### 可以改进的方面
- 功能删除后测试期望未同步。
- 标签顺序变更影响未一次性覆盖到相关测试。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 删除功能后同步更新测试期望（数量/列表/顺序） | P1 | 待处理 |
| 重构后执行相关测试套件全量回归 | P1 | 待处理 |

### 预防

- **立即执行**：删除/合并标签后立即更新对应测试断言。
- **短期**：检查所有相关测试，不只修复单个失败用例。
- **长期**：重构后固定执行完整测试套件，确保结构变更全部覆盖。

### 参考

- 修复 PR/提交：`d0a6f11 fix(tui): update expected tab count and order after removing agent log tab`
- 相关 issue：未提供

---

## 事故 #2：demo.py 缺失 logging 场景导致 logger 命令无法测试

> **Tag 范围**：`未提供` → `未提供` | **严重级别**：SEV-3 | **日期**：2026-03-02

### 概要

使用 peeka logger 命令测试时，demo 进程没有日志输出，`peeka logger list` 返回空列表，导致 logger 命令无法验证。修复通过在 `examples/demo.py` 增加完整 logging 使用示例完成。

### 根因分析

#### 类别
Missing Validation

#### 分析
`examples/demo.py` 未使用 Python `logging` 模块，因此没有日志可供 logger 命令捕获。该问题本质是示例程序未覆盖命令验证前置条件。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | demo 创建时未加入 logging |

> 致因提交无法确定性定位；来源文件仅说明“demo 创建时就没加 logging”。

### 复现

#### 前置条件
- 使用未集成 logging 的 `examples/demo.py`

#### 步骤
1. 运行示例程序。
2. 执行 `peeka logger list`。

#### 预期行为
应返回 logger 列表，并可通过 watch 观察日志。

#### 实际行为
`peeka logger list` 返回空列表，无法验证 logger 命令。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `ec16429` | 未提供 | 2026-03-02 | fix(demo): add logging usage so logger command can be tested |

#### 变更内容
在 `demo.py` 添加完整 logging 使用示例：
1. 使用 `logging.basicConfig()` 配置根日志
2. 创建多个 logger：`demo`、`demo.calculator`、`demo.performance`
3. 设置不同日志级别
4. 在各方法增加日志输出
5. 在主循环增加日志

#### 验证
- `peeka logger list` 能列出 logger
- `peeka logger watch` 能捕获日志输出

### 影响

- **受影响用户**：需要基于 demo 验证 logger 命令的开发和测试用户。
- **持续时间**：从 demo 创建到 `ec16429` 修复提交。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | demo 创建时未加入 logging |
| 2026-03-02 | 执行 `peeka logger list` 返回空列表 |
| 2026-03-02 | 修复提交：`ec16429` |
| 2026-03-02 | `logger list/watch` 验证通过 |

### 经验教训

#### 做得好的方面
- 问题定位到示例程序覆盖缺口，修复路径直接。
- 修复一次性补齐多个 logger 与日志输出场景。

#### 可以改进的方面
- 示例程序未覆盖每个命令的测试目标。
- 命令可测试性依赖未在示例中前置满足。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 示例程序覆盖 logger 命令完整使用场景 | P1 | 待处理 |
| 为每个命令补齐可在示例程序验证的测试目标 | P1 | 待处理 |

### 预防

- **立即执行**：示例程序补齐 logging 相关场景。
- **短期**：固定验证 `peeka logger list/watch` 在 demo 上可用。
- **长期**：示例程序持续覆盖所有命令的可测试路径。

### 参考

- 修复 PR/提交：`ec16429 fix(demo): add logging usage so logger command can be tested`
- 相关 issue：未提供

---

## 事故 #1：MainScreen 构造函数签名变更后测试调用未更新

> **Tag 范围**：`未提供` → `未提供` | **严重级别**：SEV-3 | **日期**：2026-02-07

### 概要

`MainScreen` 新增 `session_id` 和 `socket_path` 必需参数后，TUI 单元测试仍只传递 `pid`，导致构造失败。修复通过批量更新测试调用并补充哑值参数完成。

### 根因分析

#### 类别
Integration Error

#### 分析
`MainScreen` 构造函数签名发生变化，但测试调用点未同步更新，造成接口契约不一致。来源文件给出的修复调用如下：

```python
app.push_screen(
    MainScreen(
        pid=12345, session_id="test-session", socket_path="/tmp/fake.sock"
    )
)
```

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 重构 TUI 添加连接信息时变更构造函数签名 |

> 致因提交无法确定性定位；来源文件仅描述签名变更背景。

### 复现

#### 前置条件
- `MainScreen` 构造函数要求 `pid/session_id/socket_path`
- 测试仍按旧签名调用

#### 步骤
1. 运行 `uv run pytest tests/tui/ -v`。
2. 查看 `test_mainscreen` 相关测试结果。

#### 预期行为
测试应正常实例化 `MainScreen` 并通过。

#### 实际行为
测试失败，报错 `MainScreen()` 缺少参数。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `6b24b86` | 未提供 | 2026-02-07 | fix(test): Update TUI tests for MainScreen signature change |

#### 变更内容
更新所有 TUI 测试中的 `MainScreen` 构造调用，统一补充 `session_id` 与 `socket_path` 哑值。

#### 验证
所有 TUI 测试通过。

### 影响

- **受影响用户**：TUI 测试与 CI 使用者。
- **持续时间**：从签名变更到 `6b24b86` 修复提交。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | MainScreen 构造函数签名变更 |
| 2026-02-07 | 运行 `uv run pytest tests/tui/ -v` 发现测试失败 |
| 2026-02-07 | 修复提交：`6b24b86` |
| 2026-02-07 | 全部 TUI 测试验证通过 |

### 经验教训

#### 做得好的方面
- 自动化测试及时暴露接口契约漂移。
- 修复覆盖全部测试调用点。

#### 可以改进的方面
- 公共 API 签名变更后未同步更新测试。
- 测试代码更新覆盖检查不足。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 公共 API 签名变更后全量检查并更新测试调用点 | P1 | 待处理 |
| 使用覆盖率工具确认测试更新无遗漏 | P2 | 待处理 |

### 预防

- **立即执行**：签名变更后立即更新全部测试调用。
- **短期**：执行受影响测试套件全量回归。
- **长期**：持续使用覆盖率检查减少测试调用点遗漏。

### 参考

- 修复 PR/提交：`6b24b86 fix(test): Update TUI tests for MainScreen signature change`
- 相关 issue：未提供
