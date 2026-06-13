# Agent 观测队列与序列化性能问题复盘

| 字段 | 值 |
|------|-----|
| **话题** | Agent 观测分发队列的稳定性、内存隔离与热路径序列化优化 |
| **受影响组件** | core/agent, core/runtime |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 2 |
| **时间跨度** | 2026-06-09 至 2026-06-13 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#2](#事故-2观测分发在多连接场景下存在内存/性能热点) | 观测分发在多连接场景下存在内存/性能热点 | SEV-1 | 2026-06-13 |
| [#1](#事故-1观测生产者热路径包含重型-json-序列化) | 观测生产者热路径包含重型 JSON 序列化 | SEV-1 | 2026-06-09 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

Peeka Agent 负责将注入器产生的数据分发给多个客户端。该话题涉及分发系统的两个核心改进：一是将序列化开销从生产者（目标函数 wrapper）转移到消费者（异步 flush 线程），降低对业务代码的侵入；二是改进分发同步原语，从 Event 切换到 Lock 以提高在高频观测下的可靠性。

---

## 事故 #2：观测分发在多连接场景下存在内存/性能热点

> **Tag 范围**：`v0.1.16` → `v0.1.17` | **严重级别**：SEV-1 | **日期**：2026-06-13

### 概要

Agent 在向 stream 连接同步发送观测数据时，如果使用了 `_rpl.create_event()` 作为等待原语，在高频场景下可能出现信号丢失或等待超时，导致观测丢包。

### 根因分析

#### 类别
Logic Error / Race Condition

#### 分析
原实现在 `_send_frame_to_connection` 中使用 `_rpl.create_event()` 来等待后台线程发送完成。在多线程高度竞争环境下，Event 的语义在某些 Python runtime（特别是 gevent 注入后）可能不如 Lock 稳定。

修复方案切换到了“原生锁（allocate_lock）”作为同步原语，利用锁的阻塞获取（acquire with timeout）来精确控制分发超时，避免了 Event 信号被覆盖的风险。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `9bccbdb` | lufeihaidao | 2026-06-13 | fix(agent): use native lock for observation send-frame sync |

### 复现

#### 前置条件
- 高频 watch 观测。
- 多个并发 client 连接。

#### 预期行为
所有观测均应稳健分发，或明确记录丢包。

#### 实际行为
在高负载下出现同步等待超时，即使后台线程其实已经完成任务。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`9bccbdb`](https://github.com/peeka-project/peeka/commit/9bccbdb) | lufeihaidao | 2026-06-13 | fix(agent): use native lock for observation send-frame sync |

#### 变更内容
- 将同步原语从 `_rpl.create_event()` 切换为 `_rpl.allocate_lock()`。
- 使用锁的 acquire/release 机制替代 event 的 set/wait。

---

## 事故 #1：观测生产者热路径包含重型 JSON 序列化

> **Tag 范围**：`v0.1.16` → `v0.1.17` | **严重级别** | SEV-1 | **日期**：2026-06-09

### 概要

在 `v0.1.16` 之前，每次函数被调用时，wrapper 都会在生产者线程（业务线程）中直接进行 JSON 序列化。如果观测数据巨大或调用频率极高，这会显著拖慢业务代码的执行。

### 根因分析

#### 类别
Logic Error / Performance Regression

#### 分析
`_send_observation` 函数在生产者路径（hot path）执行了 `json.dumps()` 和 `socket.sendall()`。这意味着诊断工具的开销直接与数据大小成正比，违背了“最小侵入性”原则。

修复方案引入了异步刷新机制：生产者仅将原始 dict 放入 per-connection 的 `_ObservationQueue`，具体的序列化、字节编码（OBS 帧构建）和网络发送由专用的 `peeka-observation-flusher` 线程负责。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `118208e` | lufeihaidao | 2026-06-09 | fix(agent): close observation queue lifecycle holes |

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`ed57833`](https://github.com/peeka-project/peeka/commit/ed57833) | lufeihaidao | 2026-06-09 | fix(agent): remove JSON encoding from _send_observation producer path |

#### 变更内容
- 实现了 `_ObservationQueue`（基于 `collections.deque` 的有界 FIFO）。
- 将 JSON 编码逻辑下沉到 `_flush_connection` 和 `_encode_observation_frame`。
- 引入了 `_ObservationQueueStats` 记录分发、丢包和编码错误指标。
- 增加了 `_flush_loop` 异步处理分发任务。

### 经验教训

#### 做得好的方面
- 将序列化开销从业务线程剥离，使得观测海量数据时的业务抖动显著降低。
- 引入了详细的丢包统计（dropped_count, encode_dropped_count），增强了可观测性。

#### 可以改进的方面
- 异步队列虽然降低了延迟，但也引入了内存增长风险，需要严格的有界策略（maxlen=1024）。
