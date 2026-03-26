# GDB 注入路径与 Python 3.8 兼容性问题复盘

| 字段 | 值 |
|------|-----|
| **话题** | GDB 注入路径中的初始化、类型转换与 Python 3.8 兼容性故障 |
| **受影响组件** | core/attach, core/agent, GDB fallback 注入链路 |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 4 |
| **时间跨度** | 2026-02-05 至 2026-03-24 |

## 话题概述

该话题集中于 Python 3.8–3.13 的 GDB fallback 注入路径。故障模式反复出现在三个层面：注入上下文假设错误（`__name__` 判断）、GDB C API 类型转换不严谨（`Invalid cast`）、以及 Python 3.8 特有的调度行为差异（注入期间创建线程后不被调度）。多次修复显示该链路对执行上下文、超时预算与错误检查高度敏感；可用性优化需优先保证“注入代码必定执行并可观测失败原因”。

---

## 事故 #4：Python 3.8 中 GDB 注入创建线程后永不调度

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-未标注（原文未提供） | **日期**：2026-03-24

### 概要

在 Python 3.8 Docker 环境中，attach 稳定超时，`.ready` 文件长期不出现。问题被定位为“注入阶段创建的新线程在线程对象存在的情况下仍不被 OS 调度执行”，最终通过改为当前上下文同步 `exec` 完整 agent 初始化修复。

### 根因分析

#### 类别
Integration Error

#### 分析
原实现在 GDB 注入 bootstrap 中通过新线程执行 agent 脚本，bootstrap 立即返回。流程为：GDB 停进程 → `PyRun_SimpleString` 创建 daemon 线程并返回 → GDB detach。该流程在 Python 3.8 上稳定出现“线程已创建但代码不执行”。

原始注入片段：

```python
bootstrap = (
    "import threading as _t; "
    f"_c = open(\\\"{escaped_script}\\\").read(); "
    "_t.Thread("
    "target=exec, args=(_c,), "
    "name='peeka-bootstrap', daemon=True"
    ").start()"
);
```

修复后改为同一上下文直接执行：

```python
# For Python <= 3.8, there's a bug where threads created during
# injection don't get scheduled after GDB detaches.
# So instead we just execute directly here while we still hold the GIL.
# This takes a bit longer but is guaranteed to work.
bootstrap = (
    f"_c = open(\\\"{escaped_script}\\\").read(); "
    "exec(_c);"
);
```

源文件记录的三次排障尝试（调试符号、daemon 开关、创建后 sleep）均被证伪，说明问题不在符号匹配或简单线程属性，而在该版本/场景下的注入执行模型与调度交互。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | GDB 注入 bootstrap 采用“创建线程后返回”的原始实现 |

> 原文未给出确定性 hash；候选范围为 `peeka/core/attach.py` 中 `_inject_via_gdb` 早期线程化 bootstrap 变更。

### 复现

#### 前置条件
- Python 3.8 目标进程（Docker 场景可稳定复现）
- 使用 GDB fallback attach 路径

#### 步骤
1. 对 Python 3.8 进程执行 `peeka attach`。
2. 进入 `_wait_for_agent_ready` 等待 `.ready` 文件。
3. 持续等待至超时（30 秒）。

#### 预期行为
注入后 agent 初始化完成，`.ready` 与 socket 在超时前创建。

#### 实际行为
`.ready` 文件始终未创建，attach 超时失败。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未在源文件中给出` | 未提供 | 2026-03-24 | Python 3.8 GDB injection 线程不调度问题修复（改为直接 exec） |

#### 变更内容
- 将 `_inject_via_gdb` bootstrap 从“新线程执行”改为“当前上下文同步执行”。
- 保证在 GDB detach 前完成 socket 创建、ready 文件落盘、accept 线程启动。
- 补充注释说明 Python 版本相关行为差异。

#### 验证
- Python 3.8 attach 稳定在 5 秒内成功。
- ready 文件和 socket 正确创建。
- Python 3.12/3.14 路径不受影响。

### 影响

- **受影响用户**：Python 3.8 且走 GDB fallback 的用户。
- **持续时间**：自线程化 bootstrap 引入后持续至 2026-03-24 修复。
- **数据影响**：无数据损坏；表现为 attach 失败与诊断能力不可用。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | 线程化 bootstrap 被引入至 GDB 注入路径 |
| 2026-03-24 | Python 3.8 环境中稳定复现“ready 超时” |
| 2026-03-24 | 修复提交（hash 未在源文件记录）：改为直接 `exec(_c)` |
| 2026-03-24 | 验证通过：5 秒内稳定 attach |

### 经验教训

#### 做得好的方面
- 记录并保留了多个错误假设的证伪过程，避免重复排障。
- 借鉴成熟工具 pyrasite 的注入策略，缩短修复路径。

#### 可以改进的方面
- 对 Python 3.8 专项兼容测试前置不足。
- GDB 注入失败时缺少更细粒度阶段日志。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为 Python 3.8 GDB 注入增加端到端回归测试（ready/socket） | P0 | 待处理 |
| 在 `_inject_via_gdb` 增加阶段性可观测日志 | P1 | 待处理 |

### 预防

- **立即执行**：GDB 路径统一采用同步直接执行，避免注入期新线程依赖。
- **短期**：在 CI/container 测试增加 Python 3.8 注入稳定性基线。
- **长期**：将 GDB fallback 分阶段（加载脚本、执行、ready）建立独立健康检查。

### 参考

- 修复 PR/提交：源文件未提供 hash（文件：`2026-03-24-python38-gdb-inject-thread-never-scheduled.md`）
- 相关 issue：未提供

---

## 事故 #3：Python 3.8 GDB attach 频繁超时（超时预算不足）

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-1 | **日期**：2026-03-20

### 概要

在修复线程调度问题后，初始化被改为在 GDB 当前上下文同步完成，导致执行时长上升。原 5 秒等待预算不足，attach 出现约 50% 超时。

### 根因分析

#### 类别
Configuration Error

#### 分析
`_wait_for_agent_ready` 的默认超时值与 GDB 路径真实耗时不匹配。GDB 上下文中需要完成脚本读取、十多个模块导入、Unix socket 绑定，5 秒窗口过窄。

修复前后关键差异：

```python
def _wait_for_agent_ready(self, timeout: int = 15) -> bool:
```

即将超时从 5 秒提升至 15 秒。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 线程问题修复后，GDB 路径改为同步初始化，未同步调整等待预算 |

> 原文指向“修复线程调度问题后修改注入路径”，未给出确定性 hash。

### 复现

#### 前置条件
- Python 3.8 进程
- GDB fallback 注入

#### 步骤
1. 连续多次 attach 同一类型目标进程。
2. 观察 `_wait_for_agent_ready` 结果。

#### 预期行为
attach 稳定成功。

#### 实际行为
约 50% 概率在 5 秒窗口内超时失败。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `1a74096` | 未提供 | 2026-03-20 | fix(core): resolve frequent GDB attach timeout on Python 3.8 |

#### 变更内容
- 调整 `_wait_for_agent_ready` 默认超时至 15 秒。
- 策略上将 GDB fallback 可用性置于低延迟之上。

#### 验证
- 成功率提升到 95%+，超时显著下降。

### 影响

- **受影响用户**：Python 3.8 GDB fallback 用户。
- **持续时间**：自同步初始化变更引入后至 2026-03-20。
- **数据影响**：无；为 attach 可用性问题。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | 同步初始化路径被引入 |
| 2026-03-20 | 频繁超时问题被记录 |
| 2026-03-20 | 修复提交：`1a74096` |
| 2026-03-20 | 成功率验证 95%+ |

### 经验教训

#### 做得好的方面
- 通过实测成功率量化了修复效果。

#### 可以改进的方面
- 注入路径变更缺少性能预算回归检查。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为不同注入路径维护独立超时基线 | P1 | 待处理 |

### 预防

- **立即执行**：GDB 路径使用更宽松默认超时。
- **短期**：将 attach 成功率/时延纳入回归测试。
- **长期**：分离“初始化完成”与“连接可用”两个等待阶段。

### 参考

- 修复 PR/提交：`1a74096`
- 相关 issue：未提供

---

## 事故 #2：GDB 注入类型转换错误触发 Invalid cast

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-1 | **日期**：2026-03-20

### 概要

GDB 注入在部分 Python 版本出现 `Invalid cast`，后续表现为注入超时。根因是 `PyLong_FromVoidPtr`、`PySys_GetObject` 等 API 的 `gdb.Value` 类型转换不正确且缺少逐步校验。

### 根因分析

#### 类别
Type Error

#### 分析
GDB Python API 对类型严格，不同 Python 版本签名差异放大了转换错误。原实现在 C API 查找/转换失败后未及时中止，导致错误被延迟成“ready 超时”。同时存在函数名拼写问题：`PyState_Get()` 应为 `PyThreadState_Get()`。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | GDB 注入初始实现中类型转换与校验不足 |

> 源文未提供确定性致因 hash。

### 复现

#### 前置条件
- 使用 GDB 注入路径

#### 步骤
1. 对目标 Python 进程执行注入。
2. 观察 GDB 输出与 attach 结果。

#### 预期行为
注入链路完成且 agent 就绪。

#### 实际行为
GDB 报 `Invalid cast` 类错误，最终注入超时。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `074e9d1` | 未提供 | 2026-03-20 | Fix GDB injection type casts and add comprehensive validation tests (#10) |

#### 变更内容
- 修正 `gdb.Value` 类型转换路径。
- 每个 C API 查找后增加非空校验，失败即提前报错。
- 修正 `PyState_Get()` 拼写为 `PyThreadState_Get()`。
- 增加覆盖全部转换路径的验证测试，防止回归。

#### 验证
- 注入成功，无类型转换错误。
- C API 查找与转换均通过测试覆盖。

### 影响

- **受影响用户**：多 Python 版本上的 GDB fallback 用户。
- **持续时间**：自 GDB 注入初始实现起至 2026-03-20。
- **数据影响**：无；导致注入失败。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | GDB 注入初始实现引入类型转换风险 |
| 2026-03-20 | `Invalid cast` 问题被记录 |
| 2026-03-20 | 修复提交：`074e9d1` |
| 2026-03-20 | 验证测试覆盖并通过 |

### 经验教训

#### 做得好的方面
- 修复同时补齐了系统性校验与测试，而非仅修单点。

#### 可以改进的方面
- 早期实现缺乏“每一步失败即中止”的防御式编程。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为 GDB C API 绑定增加静态检查清单 | P1 | 待处理 |

### 预防

- **立即执行**：所有 C API 查找/转换加断言与错误返回。
- **短期**：补齐跨 Python 小版本的注入兼容测试矩阵。
- **长期**：抽象统一的 GDB API 适配层，隔离版本差异。

### 参考

- 修复 PR/提交：`074e9d1`
- 相关 issue：`#10`

---

## 事故 #1：`__name__` 检查导致 GDB exec 注入后 Agent 未初始化

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-1 | **日期**：2026-02-05

### 概要

GDB 注入通过 `exec()` 在 `__main__` 上下文执行，旧逻辑使用 `if __name__ != "__main__":` 保护初始化，导致 GDB 路径被整体跳过。

### 根因分析

#### 类别
Logic Error

#### 分析
同一段自动初始化逻辑面向两种路径（PEP 768 模块导入与 GDB exec）时，错误地将“非 `__main__`”作为必要条件。对于 GDB 路径该条件恒为假，`_init_agent` 不执行，socket 不创建。

修复前：

```python
# Auto-initialize when injected via sys.remote_exec()
if __name__ != "__main__":
    _session_id = "{{SESSION_ID}}"
    ...
    if not _session_id.startswith("{{"):
        _init_agent(_session_id, _attached_pid)
```

修复后：

```python
# Auto-initialize when injected via sys.remote_exec() or GDB
# {{SESSION_ID}} and {{ATTACHED_PID}} are replaced by ProcessAttacher before injection
_session_id = "{{SESSION_ID}}"
_attached_pid_str = "{{ATTACHED_PID}}"
_attached_pid = int(_attached_pid_str) if _attached_pid_str.isdigit() else None
if not _session_id.startswith("{{"):
    _init_agent(_session_id, _attached_pid)
```

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 初始 Agent 自动初始化实现加入 `__name__ != "__main__"` 检查 |

> 源文未给出具体 hash。

### 复现

#### 前置条件
- Python < 3.14，使用 GDB fallback

#### 步骤
1. 对目标进程执行 attach。
2. 等待 agent ready。
3. 30 秒后超时。

#### 预期行为
两种注入路径均应触发 `_init_agent`。

#### 实际行为
GDB 路径初始化被跳过，socket 永不创建。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `caf8343` | 未提供 | 2026-02-05 | fix: remove __name__ check to support GDB exec() injection |

#### 变更内容
- 删除 `__name__` 判断。
- 以模板变量替换状态（`{{SESSION_ID}}`）作为是否执行初始化的唯一条件。

#### 验证
- GDB 注入后 Agent 可正确初始化。
- PEP 768 路径行为保持正常。

### 影响

- **受影响用户**：所有依赖 GDB fallback 的用户。
- **持续时间**：自初始实现起至 2026-02-05。
- **数据影响**：无；attach 不可用。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | `__name__` 检查被引入 |
| 2026-02-05 | GDB attach 超时问题确认 |
| 2026-02-05 | 修复提交：`caf8343` |
| 2026-02-05 | 验证 GDB/PEP768 双路径正常 |

### 经验教训

#### 做得好的方面
- 采用模板变量检查替代环境假设，条件更稳健。

#### 可以改进的方面
- 注入路径差异缺乏早期设计文档和测试。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为 GDB 与 PEP 768 维护对照测试用例 | P0 | 待处理 |

### 预防

- **立即执行**：去除对 `__name__` 的路径耦合判断。
- **短期**：新增注入上下文差异测试（`__main__` vs module）。
- **长期**：建立注入路径一致性契约与兼容矩阵。

### 参考

- 修复 PR/提交：`caf8343`
- 相关 issue：未提供
