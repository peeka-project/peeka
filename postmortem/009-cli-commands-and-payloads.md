# CLI 命令分发与 Payload 参数契约问题复盘

| 字段 | 值 |
|------|-----|
| **话题** | CLI 到 Agent 的命令分发与参数键契约不一致问题，以及 CLI run 命令实现缺陷 |
| **受影响组件** | cli/main.py, core/output.py, core/bootstrap.py |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 5 |
| **时间跨度** | 2026-01-29 至 2026-04-03 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#5](#事故-5peeka-cli-run-命令-outputformatter-stdout-捕获缺陷及多处实现问题) | peeka-cli run 命令 OutputFormatter stdout 捕获缺陷及多处实现问题 | SEV-2 | 2026-04-03 |
| [#4](#事故-4cli-与-agent-payload-键名重构后失配) | CLI 与 Agent payload 键名重构后失配 | SEV-2 | 2026-03-18 |
| [#3](#事故-3sm-命令参数键与结构错误导致完全失败) | `sm` 命令参数键与结构错误导致完全失败 | SEV-1 | 2026-03-01 |
| [#2](#事故-2top-命令已实现但未接入主分发) | `top` 命令已实现但未接入主分发 | SEV-3 | 2026-02-26 |
| [#1](#事故-1clipy-与-cli-冲突及-arthas-参数不完整) | `cli.py` 与 `cli/` 冲突及 Arthas 参数不完整 | SEV-2 | 2026-01-29 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题聚焦 CLI 入口与 Agent 命令契约的演化失步：包括命令未接入主分发、字段命名不一致、参数结构不匹配及历史模块结构冲突。共同模式是"接口定义变更后未端到端同步验证"，导致命令可见但不可用，或直接返回缺参错误。

2026-04-03 新增第五类问题：`peeka-cli run` 命令初始实现中存在多处缺陷，包括 `OutputFormatter` 的 `file=` 参数默认值在 pytest 环境下捕获了 monkeypatch 前的 stdout 对象，导致测试输出路由错误；bootstrap 模板内联维护困难；run 命令缺少 `--output-file` 等实用参数；临时文件未在异常路径下清理。

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
