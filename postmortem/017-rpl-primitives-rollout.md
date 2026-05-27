# RPL Primitives 层迁移与稳定化

| 字段 | 值 |
|------|-----|
| **话题** | Runtime Primitives Layer (RPL) 的引入与稳定化 — 在 agent/attach 路径中替换裸 stdlib 调用，以抵御 gevent/eventlet monkey-patching |
| **受影响组件** | `peeka/core/runtime/primitives.py`、`peeka/core/attach.py`、`peeka/core/agent.py`、`tests/runtime/` |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 4 |
| **时间跨度** | 2026-05-17 至 2026-05-26 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#4](#事故-4gevent-data-plane-兼容矩阵契约漂移) | gevent data-plane 兼容矩阵契约漂移 | SEV-2 | 2026-05-26 |
| [#3](#事故-3rpl-混沌测试与-rlock-版本检查与设计语义脱节) | RPL 混沌测试与 RLock 版本检查与设计语义脱节 | SEV-3 | 2026-05-24 |
| [#2](#事故-2attach-notify-server-在-pep-768-路径上调用了被遮蔽的-acceptaccept-在被-monkey-patch-时不安全) | attach notify server 在 PEP 768 路径上调用了被遮蔽的 `accept()`（accept 在被 monkey-patch 时不安全） | SEV-1 | 2026-05-24 |
| [#1](#事故-1integrity_check-自创身份判断错误判定-rpl-为-degraded) | `integrity_check` 自创身份判断错误判定 RPL 为 degraded | SEV-2 | 2026-05-17 |

> 索引按时间倒序排列，点击编号跳转到对应事故。

## 话题概述

为支持在被 `gevent.monkey.patch_all()` 或 `eventlet.monkey_patch()` 的目标进程中安全运行，peeka 在 v0.1.14 引入 `peeka.core.runtime.primitives`（简称 RPL）。该模块在 import 时通过 `gevent.monkey.get_original`（若可用）或直接从 `_socket` / `_thread` / `time` 抓取**原始**实现并缓存为 `_NATIVE_*` 引用，供 agent/attach 内部代码使用，避免运行时再次解析已被替换的模块属性。

迁移过程中暴露了三类典型问题：

1. **遗漏迁移点**：仍有热路径直接调用 stdlib 高层 API（如 `server.accept()`），在协程化目标进程中会触发协程切换甚至抛 `RuntimeError`。
2. **完整性自检的语义混淆**：`integrity_check` 早期版本对每个 native 引用做"是否与当前模块属性同一对象"的硬身份比对，导致正常 gevent 环境下被判为 degraded。
3. **测试假设与设计语义脱节**：随 RPL 一起加入的混沌测试沿用了"运行期检测 monkey-patching"的心智模型，与 RPL "import 期抓取即固化"的真实合同冲突；同时 RLock 测试基于错误的 Python 版本前提（`_thread.RLock` 实为自 Python 3.2 起存在）。
4. **公开兼容矩阵合同漂移**：gevent data-plane 策略在首次实现时合并了 trace backend 字符串、把 stack 标为 degraded，并让 top 继续报告 frame-walk backend。这些值会进入 JSONL `meta`，属于外部可观察契约，必须用冻结矩阵测试守住。

RPL 是 peeka 在异步/协程框架下生存的基础设施。其设计合同必须在源代码和测试中同时清晰表达，任何"现态检测"的语义都属于反模式，应交由真正的端到端 chaos 用例覆盖。

---

## 事故 #4：gevent data-plane 兼容矩阵契约漂移

> **Tag 范围**：`v0.1.14` → `v0.1.15` | **严重级别**：SEV-2 | **日期**：2026-05-26

### 概要

gevent data-plane 策略首次落地后，与计划中的公开 JSONL 元数据合同存在偏差：trace 的 safe backend 被合并为 `settrace_or_monitoring`，top 在 gevent patched/active hub 状态下仍报告 `frame_walk`，stack 被标记为 degraded。由于这些字段会透传到 `meta.backend`、`meta.greenlet_blind` 和 `meta.degraded_reason`，偏差会让用户和自动化工具误读命令行为。

### 根因分析

#### 类别
Integration Error / Regression

#### 分析

`peeka/core/runtime/compat.py` 最初将 trace 的安全路径抽象为单一 backend：

```python
BACKEND_SETTRACE_OR_MONITORING = "settrace_or_monitoring"
_SAFE_TRACE = Policy(DECISION_SAFE, BACKEND_SETTRACE_OR_MONITORING, None, False)
```

这降低了实现复杂度，但破坏了“backend 字符串是精确公开契约”的要求。top 的 gevent 降级策略仍复用 `frame_walk`：

```python
_DEGRADED_TOP = Policy(DECISION_DEGRADED, BACKEND_FRAME_WALK, ..., True)
```

而计划要求使用后续实现的 `greenlet_aware_sampling`，并明确标注 suspended greenlet 盲区。stack 则被过度保守地标为 degraded，和矩阵规格的“全四态 safe + inspect_stack”不一致。

问题本质不是功能崩溃，而是策略层、命令实现层和测试合同之间没有一次性冻结同一张矩阵。对 peeka 这类 JSONL 诊断工具，`meta` 字段属于机器可读 API，不能只按内部实现便利命名。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `9cdd618` | lufeihaidao | 2026-05-26 | feat(runtime): add gevent-aware data plane policy |

### 复现

#### 前置条件
- 目标进程已导入或 monkey-patch gevent。
- 使用 `trace`、`top` 或 `stack` 命令并读取 JSONL `meta`。

#### 步骤
1. 在 clean runtime 下启动 `trace`，观察 `meta.backend`。
2. 在 gevent patched/active hub 下启动 `top`，观察 `meta.backend`。
3. 在 gevent patched/active hub 下启动 `stack`，观察 `meta.decision`/`meta.greenlet_blind`。

#### 预期行为
- trace safe backend 精确为 `sys_monitoring` 或 `settrace`。
- top gevent backend 为 `greenlet_aware_sampling`，`greenlet_blind` 为 `true`。
- stack 四态均为 safe，backend 为 `inspect_stack`。

#### 实际行为
- trace safe backend 被合并为 `settrace_or_monitoring`。
- top gevent backend 仍为 `frame_walk`。
- stack gevent 状态被标为 degraded。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`a0c5075`](https://github.com/peeka-project/peeka/commit/a0c5075ce100754e1834641ed3f3bbf98e1c4d0a) | lufeihaidao | 2026-05-26 | fix(runtime): align gevent compatibility matrix contract |

#### 变更内容

- 新增 `BACKEND_SETTRACE`、`BACKEND_SYS_MONITORING`、`BACKEND_GREENLET_AWARE_SAMPLING` 三个稳定 backend 字符串。
- 通过 `_select_safe_trace_backend()` 按解释器能力选择精确 trace backend。
- 将 top 的 gevent 降级 backend 改为 `greenlet_aware_sampling`。
- 将 stack 的 patched/active hub 单元恢复为 safe + `inspect_stack`。
- 将测试文件移到计划要求的根层路径：`tests/test_compat_matrix.py`、`tests/test_gevent_probe.py`。
- 增加 `test_public_string_sets_are_frozen()`，显式冻结 decision/backend 字符串集合。

#### 验证
- `tests/test_compat_matrix.py` 覆盖 5 个命令 x 4 个 gevent 状态。
- `tests/test_trace_command_policy.py` 根据矩阵期望断言 `force_backend` 和 JSONL meta。
- `v0.1.15` 发布流水线 `publish-pypi.yml` 的测试 job 通过。

### 影响

- **受影响用户**：读取 JSONL `meta` 判断运行时兼容性的 CLI、TUI 或外部自动化工具用户。
- **持续时间**：从 `9cdd618` 到 `a0c5075`，约 1 小时内在同一开发周期内修复，未进入正式 PyPI 版本。
- **数据影响**：无。影响为诊断元数据合同不准确。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-05-26 | `9cdd618` 引入 gevent-aware data-plane policy |
| 2026-05-26 | review 发现矩阵与计划契约偏差 |
| 2026-05-26 | `a0c5075` 修复矩阵、backend 字符串和测试路径 |
| 2026-05-27 | `v0.1.15` 发布流水线验证通过 |

### 经验教训

#### 做得好的方面
- 偏差在发布前通过计划对照 review 发现，未进入 PyPI。
- 修复后用矩阵测试冻结公开字符串，避免后续“内部重命名”破坏外部合同。

#### 可以改进的方面
- 任何会进入 JSONL 的新增 `meta` 字段，都应在实现前定义字段值表和兼容性矩阵。
- top、trace、stack 的命令实现和 compat 矩阵需要在同一个测试维度里被审计，而不是分散验证。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 保留 `test_public_string_sets_are_frozen()`，新增 backend 时必须显式更新测试 | P0 | 已完成 |
| 对输出到 JSONL `meta` 的枚举字符串建立文档化 registry | P1 | 待处理 |

### 预防

- **立即执行**：所有 data-plane 策略改动必须同时更新矩阵测试和 command policy 测试。
- **短期**：为 `meta.backend`、`meta.gevent_state` 等字段补充公开契约文档。
- **长期**：考虑将 compat 矩阵导出为单一数据源，用它生成测试参数和用户文档，减少手写漂移。

### 参考

- 修复提交：`a0c5075`
- 致因提交：`9cdd618`

---

## 事故 #3：RPL 混沌测试与 RLock 版本检查与设计语义脱节

> **Tag 范围**：`v0.1.13` → `v0.1.14` | **严重级别**：SEV-3 | **日期**：2026-05-24

### 概要

随 RPL 引入的两项 pytest 单元用例在 GitHub Actions Python 3.12 矩阵上失败，导致 `v0.1.14` 标签首次推送时 `publish-pypi.yml` 工作流的 test 任务中断、PyPI 发布被阻塞。失败的两条断言均与代码运行行为无关，而是测试侧对设计合同与 Python 版本特性的错误假设。

### 根因分析

#### 类别
Logic Error（测试断言）+ Missing Validation（测试前提未与运行时环境对齐）

#### 分析

`tests/runtime/test_rpl_chaos.py::test_rpl_integrity_under_chaos`：

```python
result = primitives.integrity_check()
assert result["socket_native"] is True
assert result["lock_native"] is False        # 错误假设
assert result["thread_native"] is False      # 错误假设
```

该断言隐含的心智模型是"`integrity_check` 检测当前 monkey-patching 状态"。但 RPL 的设计合同恰恰相反：原始引用在 import 期抓取并固化，`*_native` 标志只表达"我们捕获到了原始可调用对象"，与 monkey-patch fixture 在运行期对 `_thread.allocate_lock` 做的属性替换无关。fixture 替换仅影响 `_thread` 模块属性，而 RPL 已经保存了被替换前的原始函数引用。

`tests/runtime/test_rpl_primitives.py::test_rlock_uses_threading_not_thread`：

```python
if sys.version_info < (3, 13):
    assert not hasattr(_thread, "RLock")
```

该断言的注释声称 "In Python < 3.13, `_thread.RLock` doesn't exist"。这是事实错误：`_thread.RLock` 作为内部类自 Python 3.2 起即存在，仅 `threading.RLock` 在不同 CPython 版本中的实现路径不同。CI 上 Python 3.12.13 拥有 `_thread.RLock`，断言 `not hasattr(...)` 恒为 False。

两条用例本地恰好通过（开发机为 Python 3.14，且 chaos 用例在某些条件下 fixture 行为巧合），但都没有按 CI 真实矩阵（Python 3.12）跑过。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `b5a600f` | lufeihaidao | 2026-05-16 | test(runtime): add reverse chaos fixture for gevent/eventlet patching |
| `f7d5d31` | lufeihaidao | 2026-05-16 | test(runtime): add RPL primitives unit tests for identity and integrity |

### 复现

#### 前置条件
- Python 3.12 解释器
- 工作区位于 v0.1.13..HEAD 之间任意提交（v0.1.14 标签之前）

#### 步骤
1. `python3.12 -m pytest tests/runtime/test_rpl_chaos.py::test_rpl_integrity_under_chaos`
2. `python3.12 -m pytest tests/runtime/test_rpl_primitives.py::test_rlock_uses_threading_not_thread`

#### 预期行为
两条用例通过，发布流水线放行。

#### 实际行为
```
tests/runtime/test_rpl_chaos.py:125: AssertionError: assert True is False
tests/runtime/test_rpl_primitives.py:199: AssertionError: assert not True
```

`publish-pypi.yml` 的 test 任务以 exit code 1 终止，publish 阶段被跳过，PyPI 上不会出现 0.1.14。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `c2ba335` | lufeihaidao | 2026-05-24 | fix(test): align RPL chaos and RLock tests with actual design semantics |

#### 变更内容

- `test_rpl_integrity_under_chaos`：将 `lock_native`/`thread_native` 的期望从 `False` 改为 `True`，并补充 `ok is True` 断言。新增 docstring 明确"eager-capture 合同"，将端到端的混沌韧性指派给同文件的 `test_rpl_*_survives_*` 用例。
- `test_rlock_uses_threading_not_thread`：删除 `sys.version_info < (3, 13)` 分支与对应的 `not hasattr(_thread, "RLock")` 断言，保留唯一有意义的检查 `primitives._NATIVE_RLOCK is threading.RLock`，并在 docstring 中说明为何刻意不绑定 `_thread`。

#### 验证

- `uv run pytest tests/runtime/ -m "not e2e and not container and not tui"`：20/20 通过。
- `uv run pytest tests/ -m "not e2e and not container and not tui" --ignore=tests/tui --ignore=tests/test_tui.py --ignore=tests/test_theme.py`：473 通过、1 跳过。
- 重新推送 `v0.1.14` 后 GitHub Actions 全绿，PyPI 0.1.14 发布成功。

### 影响

- **受影响用户**：v0.1.14 候选发布期间，PyPI 上短时间内无 0.1.14；GitHub Release 同步缺失。无对已发布版本用户的影响。
- **持续时间**：约 8 分钟（从首次推送 tag 到 force-push 撤销并重新推送）。
- **数据影响**：无。tag `v0.1.14` 经 `git push origin --delete` + `git tag -d` 并 force-push 主分支撤销，无悬挂引用。

### 时间线

| 时间（UTC） | 事件 |
|------|------|
| 2026-05-16 | 提交 `b5a600f` 与 `f7d5d31` 引入有问题的测试断言 |
| 2026-05-24 15:20 | 首次推送 `v0.1.14` 触发流水线 |
| 2026-05-24 15:21 | test 任务在 Python 3.12 上以 2 failed 退出 |
| 2026-05-24 15:24 | 撤销远端 tag、本地 tag、release commit |
| 2026-05-24 15:27 | 修复测试断言并提交 `c2ba335` |
| 2026-05-24 15:28 | 重新推送 `v0.1.14`，流水线全部 job 成功 |
| 2026-05-24 15:30 | PyPI 出现 0.1.14，GitHub Release 创建完成 |

### 经验教训

#### 做得好的方面
- 发布流水线在 publish 阶段之前强制运行 test job，避免了缺陷直接污染 PyPI。
- 回滚流程（删 tag、reset、force-push）按 release skill 的预案顺利执行。

#### 可以改进的方面
- 新引入的测试模块没有在本地多 Python 版本矩阵上验证。
- 设计合同（eager capture）只存在于源代码 docstring，未在测试侧以"反例不应该出现"的形式固化。
- 错误的 Python 版本断言（`_thread.RLock` 缺失声明）暴露了对底层 stdlib 模块的认知缺口。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 在新增 RPL 相关测试时，配套 docstring 写明"测试反映哪条设计合同条款" | P1 | 已落实于 `c2ba335` |
| 评估为发布流水线增加 Python 3.12 + 3.14 双矩阵测试 job（当前只跑 3.12） | P2 | 待处理 |
| 对 stdlib 私有模块（`_thread`、`_socket`）的版本特性假设需用 `python -c "import _thread; print(hasattr(_thread, X))"` 现网验证后再写入断言 | P2 | 待处理 |

### 预防

- **立即执行**：在 `tests/runtime/` 下新增测试时，必须先用 CI 同版本（`uv run --python 3.12 pytest …`）跑通后再提交。
- **短期**：在 `AGENTS.md` 的 "Python 版本支持" 章节追加一条注释："不要在测试中用 `hasattr(_thread, ...)` 作为版本判别条件，使用 `sys.version_info`"。
- **长期**：将 publish 工作流的 test job 扩展为矩阵（3.12 + 3.14），并将设计合同测试与混沌端到端测试分到不同标记下，便于按层定位。

### 参考

- 修复提交：`c2ba335`
- 致因提交：`b5a600f`、`f7d5d31`
- 失败工作流 run：`26365071311`
- 成功工作流 run：`26365245624`

---

## 事故 #2：attach notify server 在 PEP 768 路径上调用了被遮蔽的 `accept()`（accept 在被 monkey-patch 时不安全）

> **Tag 范围**：`v0.1.13` → `v0.1.14` | **严重级别**：SEV-1 | **日期**：2026-05-24

### 概要

`peeka/core/attach.py` 的 PEP 768 路径在等待目标进程 agent 回连时，对 notify server socket 直接调用了 `server.accept()`。当目标进程已被 `gevent.monkey.patch_all()` 处理后，socket 模块被替换，`accept()` 可能切换到 greenlet 调度甚至抛 `RuntimeError`，导致 attach 阶段长时间挂起，最终落到 GDB 回退路径。

### 根因分析

#### 类别
Integration Error（RPL 迁移遗漏点）

#### 分析

RPL 模块在 v0.1.14 周期引入，目标是为 attach/agent 链路上的所有 socket/lock/thread 调用提供"被 monkey-patch 之前抓取"的原始实现。迁移分批进行（`ce8b5a9` 系列），但 PEP 768 分支中第 988 行附近的 `accept()` 调用被遗漏。该处 socket 由 `_rpl.create_socket()` 创建（因此是裸 `_socket.socket`），但在其上调用的 `.accept()` 仍走 `socket.socket.__bases__` 中的高层 wrapper，被 gevent 替换后语义不再纯阻塞。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `b0bd99b` | lufeihaidao | 2026-05-16 | refactor(core): migrate agent.py socket call sites to runtime primitives |
| `ce8b5a9` | lufeihaidao | 2026-05-16 | refactor(core): migrate attach.py server primitives to runtime layer |

迁移批次未覆盖 PEP 768 子路径的 `accept` 调用点。

### 复现

#### 前置条件
- 目标进程为 Python 3.14+ 且启动前执行 `gevent.monkey.patch_all()`
- peeka v0.1.14 之前的 attach 路径

#### 步骤
1. `python -c "import gevent.monkey; gevent.monkey.patch_all(); import time; time.sleep(3600)"` 启动目标进程
2. `peeka-cli attach <pid>`

#### 预期行为
PEP 768 路径在数秒内完成 attach，agent 回连成功。

#### 实际行为
PEP 768 等待 agent 回连阶段挂起；TUI 用户看到 attach 长时间无进度，最终通用错误模板。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `14b45d9` | lufeihaidao | 2026-05-17 | fix(core): fix socket accept bug, bare except blocks, and ruff errors |
| `5617058` | lufeihaidao | 2026-05-24 | fix(core): use native_accept on raw _socket.socket at notify server |

#### 变更内容

- 将 `server.accept()` 替换为 `_rpl.native_accept(server)`，由 RPL 提供绑定到 `_socket.socket.accept`（原始 C 级实现）的可调用对象。
- `tests/test_attach_socket.py` 新增 90 行单元用例，断言 `accept` 路径不会进入被替换的 socket 模块。

#### 验证

- `uv run pytest tests/test_attach_socket.py -v`：全部通过。
- 在 `peeka-test:3.14` 容器中以 gevent 目标手动验证：PEP 768 attach 在 <2 秒内完成。

### 影响

- **受影响用户**：使用 gevent 的 Python 3.14+ 应用 attach 时降级为 GDB 路径或超时失败的用户。
- **持续时间**：从 RPL 引入（2026-05-16）到 `5617058` 合入（2026-05-24），约 8 天。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-05-16 | RPL 迁移批次未覆盖 `accept()` 调用点（`b0bd99b`、`ce8b5a9`） |
| 2026-05-17 | 第一次部分修复 `14b45d9`（attach.py:583） |
| 2026-05-24 | 完整修复 `5617058`，含 notify server 路径 + 回归用例 |

### 经验教训

#### 做得好的方面
- RPL 模块设计将 `native_accept` 作为显式 API 暴露，使修复变得机械。
- 通过 `tests/test_attach_socket.py` 固化了"不应该走高层 socket"的契约。

#### 可以改进的方面
- 迁移批次缺少全量调用点清单。`grep` 应在迁移完成后对 `\.accept\(`、`\.bind\(`、`\.listen\(` 跑一遍，确认所有点位都已切换到 RPL。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 编写迁移 checker 脚本：`ast-grep` 扫描 `peeka/core/` 下任何非 RPL 来源的 socket 高层调用 | P1 | 待处理 |
| 在 CI 中加入 lint：发现 `peeka/core/{attach,agent}.py` 出现直接 `socket.socket(...)` 即失败 | P2 | 待处理 |

### 预防

- **立即执行**：对未来任何对运行时基础设施的"广覆盖迁移"，必须先编排"待迁移点位清单"，迁移完成后逐行勾销。
- **长期**：考虑用 mypy / pyright 自定义插件，对 `peeka/core/` 内 socket / threading 高层 API 引用进行禁用提示。

### 参考

- 修复提交：`14b45d9`、`5617058`
- 测试：`tests/test_attach_socket.py`

---

## 事故 #1：`integrity_check` 自创身份判断错误判定 RPL 为 degraded

> **Tag 范围**：`v0.1.13` → `v0.1.14` | **严重级别**：SEV-2 | **日期**：2026-05-17

### 概要

RPL 模块首版 `integrity_check()` 对每个 `_NATIVE_*` 引用执行严格的"与当前模块属性同一对象"身份比对。在 gevent 已对 `_thread` 做属性替换的环境下，`_NATIVE_ALLOCATE_LOCK is _thread.allocate_lock` 自然为 False，导致返回 `status="degraded"`、`ok=False`，TUI dashboard agent log 误报 "RPL degraded"。但实际上 RPL 已经在 import 期通过 `gevent.monkey.get_original` 抓到了真正的原始函数，运行完全正常。

### 根因分析

#### 类别
Logic Error（自检语义与设计语义不一致）

#### 分析

设计合同：`_NATIVE_*` 是 import-time eager capture，与当前模块属性是否一致**无关**；合法路径是"通过 patcher 提供的 get_original 拿到原始可调用对象"。早期 `integrity_check` 自行做 `obj is current_module_attr` 比较，违反了合同。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `0c32165` | lufeihaidao | 2026-05-13 | feat(runtime): add RPL primitives module with eager capture |

### 复现

#### 前置条件
- 目标进程已执行 `gevent.monkey.patch_all()`

#### 步骤
1. attach 到目标进程
2. 在 TUI dashboard 查看 agent log 中的 RPL 完整性输出

#### 预期行为
`status: ok`，所有 `*_native` 字段为 True。

#### 实际行为
`status: degraded`，`lock_native: false`、`thread_native: false`、`event_native: false`。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `294e577` | lufeihaidao | 2026-05-17 | fix(core): trust patcher's get_original in RPL integrity_check |

#### 变更内容

- 引入辅助 `_was_captured_via_get_original(captured)`：仅判断 `captured is not None and callable(captured)`。
- 将 `lock_ok`、`thread_ok`、`event_ok`、`time_ok`、`get_ident_ok`、`rlock_ok` 全部改为使用该辅助函数。
- 仅 `socket_ok` 和 `perf_counter_ok` 保留严格身份比对，因为它们绑定到的 `_socket.socket` 与 `time.perf_counter` 是 monkey-patch 通常不替换的低层符号。
- 在 docstring 中明确写出"\*_native 表示我们捕获到了原始可调用对象，而非当前属性仍为原始"。
- `tests/test_runtime_primitives.py` 新增 133 行覆盖：clean env 全 True、gevent env 仍为 True、非可调用对象返回 False。

#### 验证

- `uv run pytest tests/test_runtime_primitives.py`：全部通过。
- 容器 gevent 目标进程实测：RPL 状态报告恢复 `ok`。

### 影响

- **受影响用户**：使用 gevent 的目标用户在 v0.1.13 短期开发版上看到误报；正式 release 前已修复。
- **持续时间**：约 4 天（`0c32165` → `294e577`）。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-05-13 | RPL 首版引入，integrity_check 使用严格身份比对 |
| 2026-05-14 ~ 16 | 内部 gevent 测试发现 degraded 误报 |
| 2026-05-17 | `294e577` 合入，自检语义对齐设计合同 |

### 经验教训

#### 做得好的方面
- 自检模块在发布前的 gevent 场景测试中暴露了语义偏差，避免了用户侧误报。

#### 可以改进的方面
- 设计合同最初只存在于实现者头脑中，未在源代码 docstring 中固化。
- 自检函数的单元测试在引入时只覆盖了 clean env，没有覆盖 monkey-patched env。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 任何新增的"完整性/健康检查"类函数必须同时提供 clean 与 patched 两种环境的测试 | P1 | 已落实于 `294e577` |
| 在 `peeka/core/runtime/primitives.py` 顶部 docstring 中明确列出 RPL 设计合同条款 | P2 | 部分落实 |

### 预防

- **立即执行**：自检/健康检查函数的语义应在源码 docstring 中以"WHAT 与 WHAT NOT"两栏说明。
- **短期**：在 `tests/runtime/` 下补充"语义合同测试"目录，专门固化 RPL 的设计契约。

### 参考

- 修复提交：`294e577`
- 测试：`tests/test_runtime_primitives.py`
