# Attach 与 Agent 生命周期问题

| 字段 | 值 |
|------|-----|
| **话题** | 进程 attach 就绪探测、会话文件清理、accept 循环时序与 agent 线程生命周期问题 |
| **受影响组件** | core/attach, core/agent, tui process attach flow |
| **最高严重级别** | SEV-0 (Critical) |
| **事故次数** | 5 |
| **时间跨度** | 2026-02-26 至 2026-03-01 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#5](#事故-5首次-attach-间歇性超时) | 首次 attach 间歇性超时 | SEV-2 | 2026-03-01 |
| [#4](#事故-4快速-attachdetach-后-connection-refused) | 快速 attach/detach 后 Connection refused | SEV-1 | 2026-03-01 |
| [#3](#事故-3多次-attachdetach-线程泄漏导致资源耗尽) | 多次 attach/detach 线程泄漏导致资源耗尽 | SEV-0 | 2026-03-01 |
| [#2](#事故-2accept_ready-事件设置过早与线程不可观测) | accept_ready 事件设置过早与线程不可观测 | SEV-1 | 2026-02-27 |
| [#1](#事故-1ready-存在但-socket-尚不可连就绪误判) | `.ready` 存在但 socket 尚不可连(就绪误判) | SEV-2 | 2026-02-26 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题集中暴露 attach 与 agent 的“就绪判定—运行—清理”全链路时序问题：仅依赖 `.ready` 文件会误判就绪；accept 线程 event 设置过早导致连接窗口竞态；首次冷启动导入耗时与固定超时冲突；rapid attach 场景出现脚本清理时序与 stale 文件误判；最终在多次 attach/detach 循环中演化为线程泄漏（SEV-0）。

---

## 事故 #5：首次 attach 间歇性超时

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-2 | **日期**：2026-03-01

### 概要

首次向冷进程注入时偶发超时，用户需手动重试。核心原因是模块冷加载时间超过硬编码 5 秒。

### 根因分析

#### 类别
Configuration Error

#### 分析
首次注入需导入 13+ 命令模块，慢盘或高负载下超过 5 秒；且原流程无自动重试。

```python
max_attempts = 2
for attempt in range(max_attempts):
    try:
        if self._wait_for_agent_ready():
            return True
    except TimeoutError:
        if attempt < max_attempts - 1:
            # retry
```

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-03-01 前 | 初始 attach 使用固定 5 秒超时且无重试 |

### 复现

#### 前置条件
- 慢速机器或高负载环境

#### 步骤
1. 对从未注入过的进程执行首次 attach。

#### 预期行为
首次 attach 稳定成功。

#### 实际行为
约 30% 概率 5 秒超时失败。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `7d505e9` | 未记录 | 2026-03-01 | fix(attach): increase timeout and add retry for intermittent first-attach failure |

#### 变更内容
1. 超时 5s → 10s。
2. 新增一次自动重试（总 2 次）。

#### 验证
首次 attach 成功率显著提升，超时场景可自动恢复。

### 影响

- **受影响用户**：首次 attach 冷启动用户
- **持续时间**：初始实现至 `7d505e9`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-03-01 前 | 固定 5 秒超时且无重试 |
| 2026-03-01 | `7d505e9` 增加超时与重试 |

### 经验教训

#### 做得好的方面
- 通过“更长超时 + 重试”兼顾稳定性与用户体验。

#### 可以改进的方面
- 冷启动时延未纳入初始容量预算。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 记录首次注入耗时分布并动态调参 | P1 | 待处理 |

### 预防

- **立即执行**：冷启动路径使用宽松超时。
- **短期**：超时失败默认重试一次。
- **长期**：引入自适应超时机制。

### 参考

- 修复提交：`7d505e9`

---

## 事故 #4：快速 attach/detach 后 Connection refused

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-1 | **日期**：2026-03-01

### 概要

在 rapid attach 场景中第二次 attach 间歇失败。原因是注入脚本被过早删除与会话文件残留共同造成时序误判。

### 根因分析

#### 类别
Race Condition

#### 分析
1. `sys.remote_exec()` 为 fire-and-forget，`process_selector.py` 在 finally 调 `attacher.cleanup()` 可能提前删除目标尚未读取的脚本。
2. `agent.stop()` 未清理 `/tmp/peeka_{session_id}.{sock,ready,pid}`，`_check_existing_attachment()` 被 stale 文件误导为“已附加”。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-03-01 前 | 初始 TUI attach 流程含脚本清理时序与会话文件残留问题 |

### 复现

#### 前置条件
- 同一进程快速重复 attach/detach

#### 步骤
1. 在 TUI 执行 attach → detach → attach。

#### 预期行为
第二次 attach 正常。

#### 实际行为
第二次 attach 失败（Connection refused）。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `7a3066e` | 未记录 | 2026-03-01 | fix(tui): fix connection refused on rapid attach by cleaning up session files on detach |

#### 变更内容
1. `process_selector` finally 中不再立刻 `attacher.cleanup()`（避免脚本过早删除）。
2. `agent.stop()` 增加 `_cleanup_session_files()`，删除 `.sock/.ready/.pid`。

#### 验证
rapid attach/detach 可稳定成功，不再被 stale 文件误判。

### 影响

- **受影响用户**：频繁切换 attach 会话用户
- **持续时间**：初始流程至 `7a3066e`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-03-01 前 | 过早清理脚本 + 会话文件残留 |
| 2026-03-01 | `7a3066e` 修复 detach 清理策略 |

### 经验教训

#### 做得好的方面
- 同时修复注入前后两个时序窗口。

#### 可以改进的方面
- fire-and-forget 语义未在流程设计中显式体现。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 对 attach/detach 增加高频循环稳定性测试 | P0 | 待处理 |

### 预防

- **立即执行**：fire-and-forget 之后禁止立即清理依赖文件。
- **短期**：detach 统一清理会话副产物。
- **长期**：会话状态改为主动探测而非文件存在判断。

### 参考

- 修复提交：`7a3066e`

---

## 事故 #3：多次 attach/detach 线程泄漏导致资源耗尽

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-0 | **日期**：2026-03-01

### 概要

重复 attach/detach 后 accept 线程与客户端线程残留，线程数持续增长，最终资源耗尽并可能 OOM 崩溃。

### 根因分析

#### 类别
Resource Management

#### 分析
三项缺陷叠加：
1. `server.accept()` 无超时，无法周期检查 `self.running`。
2. 新注入前未清理旧 agent，旧实例留在 `sys._peeka_agents`。
3. `server.close()` 缺少错误处理。

关键修复代码：

```python
# Set timeout so accept() doesn't block forever
self.server.settimeout(1.0)

# In accept loop:
except socket.timeout:
    # Periodic wakeup to re-check self.running
    continue
except OSError:
    # Server socket closed (stop() called) — exit cleanly
    break

# On init: stop ALL existing agents from previous sessions
if hasattr(sys, "_peeka_agents"):
    old_agents = list(sys._peeka_agents.values())
    for old_agent in old_agents:
        old_agent.stop()
    sys._peeka_agents.clear()
```

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-03-01 前 | 初始 agent 生命周期管理未覆盖退出与重注入清理 |

### 复现

#### 前置条件
- 同一进程反复 attach/detach

#### 步骤
1. 循环 10 次 attach → detach。
2. 观察 `ps -T <pid> | wc -l`。

#### 预期行为
线程数稳定。

#### 实际行为
线程数持续增长。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `567d1c7` | 未记录 | 2026-03-01 | fix(agent): implement timeout for accept loop and cleanup of previous agents to prevent thread leaks |

#### 变更内容
1. `accept` 加 1s timeout。
2. 新会话初始化前停掉并清空全部旧 agent。
3. `stop` 时从注册表反注册。
4. `server.close()` 增加异常处理。

#### 验证
循环 attach/detach 后线程数不再增长。

### 影响

- **受影响用户**：长生命周期目标进程与高频 attach 用户
- **持续时间**：初始实现至 `567d1c7`
- **数据影响**：无直接数据损坏，但有进程稳定性风险

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-03-01 前 | accept 永久阻塞 + 旧 agent 未清理 |
| 2026-03-01 | `567d1c7` 修复超时与全局清理 |

### 经验教训

#### 做得好的方面
- 一次修复覆盖线程退出、实例回收、异常关闭三层。

#### 可以改进的方面
- 初始实现未将“重注入”作为一等场景设计。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 引入 attach/detach 长循环压力测试到 CI | P0 | 待处理 |

### 预防

- **立即执行**：阻塞 accept 必设 timeout。
- **短期**：每次注入前执行旧实例审计与清理。
- **长期**：统一 agent 进程内生命周期管理器。

### 参考

- 修复提交：`567d1c7`

---

## 事故 #2：accept_ready 事件设置过早与线程不可观测

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-1 | **日期**：2026-02-27

### 概要

attach 间歇失败，且线程默认命名导致调试困难。根因是 `accept_ready` 在 accept 线程真正进入循环前被设置。

### 根因分析

#### 类别
Race Condition

#### 分析
等待方看到 ready 后立即连接，但 accept 线程尚未开始 `accept()`；同时线程名均为 `Thread-*`，问题定位成本高。

```python
# In accept loop thread:
self.server.listen(5)
self.server.settimeout(1.0)
accept_ready.set()  # Set AFTER entering the loop context

while self.running:
    # accept ...
```

并新增线程命名：
- `peeka-agent-accept`
- `peeka-agent-client-{counter}`

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-02-27 前 | agent 初始 accept 时序与线程命名策略缺失 |

### 复现

#### 前置条件
- 反复 attach/detach

#### 步骤
1. 执行多轮 attach→detach。

#### 预期行为
稳定连接且线程易于识别。

#### 实际行为
约 20% 失败，线程难以定位。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `30fbb62` | 未记录 | 2026-02-27 | fix(agent): name threads and fix accept loop race condition |

#### 变更内容
1. `accept_ready` 改为在 accept 循环上下文中设置。
2. 全部 peeka 线程显式命名。

#### 验证
attach 稳定性提升，`ps/top` 可快速识别线程职责。

### 影响

- **受影响用户**：attach 高频用户与排障人员
- **持续时间**：初始实现至 `30fbb62`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-02-27 前 | ready 事件过早设置 |
| 2026-02-27 | `30fbb62` 修复时序并命名线程 |

### 经验教训

#### 做得好的方面
- 同时提升稳定性与可调试性。

#### 可以改进的方面
- 线程启动时序缺少设计约束文档。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 线程事件设置时机写入并发开发规范 | P1 | 待处理 |

### 预防

- **立即执行**：ready 事件必须在“可服务”后设置。
- **短期**：线程命名规则强制化。
- **长期**：并发初始化流程可视化与断言化。

### 参考

- 修复提交：`30fbb62`

---

## 事故 #1：`.ready` 存在但 socket 尚不可连（就绪误判）

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-2 | **日期**：2026-02-26

### 概要

attach 成功返回后立即连接 agent socket 间歇 `Connection refused`。原因是仅以 `.ready` 文件判定就绪。

### 根因分析

#### 类别
Race Condition

#### 分析
`.ready` 文件只证明流程走到 bind 后，不保证 accept 循环已可接收连接。

两阶段修复：
1. 等待 `.ready` 出现。
2. 主动探测 socket 可连接性。

```python
def _wait_for_agent_ready(self, timeout: int = 5) -> bool:
    # Phase 1: Wait for .ready file
    while time.time() - start_time < timeout:
        if ready_file.exists():
            break
    # Phase 2: Verify socket is actually connectable
    while time.time() - start_time < timeout:
        if self._is_socket_alive(socket_path):
            return True
        time.sleep(0.05)
```

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-02-26 前 | `_wait_for_agent_ready` 初始实现仅检测 ready 文件 |

### 复现

#### 前置条件
- 慢速机器或高抖动环境

#### 步骤
1. 多次执行 attach。

#### 预期行为
attach 后 socket 立即可连。

#### 实际行为
约 20% 概率连接拒绝。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `73d1fb5` | 未记录 | 2026-02-26 | fix(attach): verify socket connectivity in _wait_for_agent_ready |

#### 变更内容
在 ready 文件检测后增加 socket 主动连通性探测，双条件满足才返回成功。

#### 验证
连接失败概率显著下降，慢速机器稳定性提升。

### 影响

- **受影响用户**：attach 用户
- **持续时间**：初始实现至 `73d1fb5`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-02-26 前 | 仅以 ready 文件判定就绪 |
| 2026-02-26 | `73d1fb5` 增加 socket 连通性探测 |

### 经验教训

#### 做得好的方面
- 明确将“可连接性”定义为就绪标准。

#### 可以改进的方面
- 被动文件信号被过度信任。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 所有就绪检测统一采用“信号+主动探测”双阶段 | P1 | 待处理 |

### 预防

- **立即执行**：禁止单一文件信号作为最终就绪依据。
- **短期**：在 attach 日志输出两阶段耗时，便于诊断。
- **长期**：统一 readiness 协议与健康检查接口。

### 参考

- 修复提交：`73d1fb5`
