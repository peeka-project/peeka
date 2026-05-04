# Streaming Client 并发与协议漂移问题

| 字段 | 值 |
|------|-----|
| **话题** | StreamingAgentClient 并发访问、专用连接策略与协议同步问题（含 BrokenPipe） |
| **受影响组件** | core/client, tui views |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 7 |
| **时间跨度** | 2026-02-28 至 2026-05-04 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#7](#事故-7streaming-client-连接标识缺失导致活动日志源歧义) | Streaming Client 连接标识缺失导致活动日志源歧义 | SEV-3 | 2026-05-04 |
| [#6](#事故-6nframetrackstop-右对齐失败css-特异性) | nframe/Track/Stop 右对齐失败(CSS 特异性) | SEV-3 | 2026-03-10 |
| [#5](#事故-5请求-响应视图重新引入专用客户端以抑制竞态) | 请求-响应视图重新引入专用客户端以抑制竞态 | SEV-1 | 2026-03-03 |
| [#4](#事故-4请求-响应视图误用专用客户端造成资源浪费) | 请求-响应视图误用专用客户端造成资源浪费 | SEV-3 | 2026-03-03 |
| [#3](#事故-3streamingagentclient-并发-send_command-破坏协议) | StreamingAgentClient 并发 send_command 破坏协议 | SEV-1 | 2026-03-01 |
| [#2](#事故-2多流式视图共享连接导致读取竞争与-brokenpipe) | 多流式视图共享连接导致读取竞争与 BrokenPipe | SEV-1 | 2026-02-28 |
| [#1](#事故-1异常路径未排空-obs-帧导致协议漂移) | 异常路径未排空 OBS 帧导致协议漂移 | SEV-1 | 2026-02-28 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题体现了“共享连接 + 多线程 + 流式帧”组合下的系统性复杂度：读取竞争会破坏帧边界，发送并发会破坏长度前缀协议，异常后未排空 OBS 帧会导致后续请求响应错位；同时“专用客户端是否必要”在不同视图类型间被反复修正，反映连接模型边界在实践中逐步澄清。

---

## 事故 #7：Streaming Client 连接标识缺失导致活动日志源歧义

> **Tag 范围**：`v0.1.8..v0.1.9` | **严重级别**：SEV-3 | **日期**：2026-05-04
> **相关提交**：`a90d080 fix(core): identify streaming clients on connect`, `965ff22 feat(core): label clients with stable sources`, `b1b0412 feat(tui): enrich activity diagnostics`

### 概要

活动日志（activity log）中无法区分多个 streaming client 的来源，不同视图的连接事件显示为相同标识。

### 根因分析

#### 类别
Observability Gap

#### 分析
所有 `StreamingAgentClient` 实例在连接时记录的活动事件使用相同的 source 标识，用户无法分辨：
1. `watch` 视图的连接 vs `trace` 视图的连接
2. 同一视图的多次重连
3. 不同 tab 中相同视图的独立连接

### 复现步骤
1. 打开 `watch` 视图和 `trace` 视图
2. 两者都建立 streaming 连接
3. 在 activity log 中查看 — 两个连接事件无区别

### 修复详情

```python
# TUI 创建客户端时携带稳定的 client_info
self._stream_client = StreamingAgentClient(
    self._socket_path,
    activity_reporter=make_activity_reporter(self.app, "watch-stream"),
    client_info=make_client_info(self.app, "watch-stream"),
)

# StreamingAgentClient 在 connect() 时发送内部 hello 帧
def _identify_connection(self) -> Dict[str, Any]:
    return self.send_command({"type": "client", "action": "hello"})

# Agent 端提取 _client 元数据，并在 activity log 中使用稳定 label
raw_command = json.loads(data.decode("utf-8"))
client_info = self._extract_client_info(raw_command)
client_label = self._format_client_label(client_id, client_info)
```

### 经验教训

1. **诊断系统需要可观测性而非可调试性** — 用户需要在运行时就知道"是谁在做什么"，而不是事后 debug
2. **多实例场景必须有标识** — 只要一个类可能被实例化多次，就需要实例标识
3. **source 应该在创建点设置** — 下游不应该猜测自己属于哪个业务场景

### 预防措施

- [x] 为 `StreamingAgentClient` 增加可选 `client_info`
- [x] TUI 流式视图在创建客户端时传递 `make_client_info(...)`
- [x] Agent 端提取 `_client` 元数据并在 activity log 中显示 source
- [x] 增加 client identity 与 hello 帧的单元测试

---

## 事故 #6：nframe/Track/Stop 右对齐失败（CSS 特异性）

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-3 | **日期**：2026-03-10

### 概要

Memory 状态栏中 nframe 与 Track/Stop 未能右对齐。该事故属于同一并发治理周期内的 UI 回归项。

### 根因分析

#### 类别
Configuration Error

#### 分析
`.spacer { width: 1fr }` 被通用 `#memory-status-bar Static` 覆盖，spacer 未取得占位宽度。

```css
#memory-status-bar .spacer {
    width: 1fr;
    padding: 0;
}
```

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-03-10 前 | spacer 引入后特异性不足 |

### 复现

#### 前置条件
- Memory 状态栏启用 spacer

#### 步骤
1. 观察 nframe 与 Track/Stop 排布。

#### 预期行为
控件靠右浮动。

#### 实际行为
控件仍靠左。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `05c34e1` | 未记录 | 2026-03-10 | fix(tui): float nframe+Track/Stop to right via spacer specificity fix |

#### 变更内容
提高选择器特异性覆盖通用规则。

#### 验证
spacer 正常占位，控件右对齐。

### 影响

- **受影响用户**：Memory 视图用户
- **持续时间**：引入后至 `05c34e1`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-03-10 前 | spacer 特异性不足 |
| 2026-03-10 | `05c34e1` 修复 |

### 经验教训

#### 做得好的方面
- 使用最小 CSS 修复恢复布局。

#### 可以改进的方面
- 状态栏样式缺少集中规则。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 统一状态栏选择器命名与特异性策略 | P2 | 待处理 |

### 预防

- **立即执行**：关键占位元素使用上下文限定选择器。
- **短期**：布局变更进行多规则冲突检查。
- **长期**：组件化状态栏样式。

### 参考

- 修复提交：`05c34e1`

---

## 事故 #5：请求-响应视图重新引入专用客户端以抑制竞态

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-1 | **日期**：2026-03-03

### 概要

删除专用客户端后，在后台自动刷新与用户点击并发场景中再次出现 BrokenPipe/Connection refused，需回滚并为 Logger/Memory/Inspect 重新配置专用连接。

### 根因分析

#### 类别
Race Condition

#### 分析
虽然属于请求-响应视图，但存在后台 worker 周期刷新，与交互请求并发。共享连接下连接生命周期竞争仍会发生。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `2dcb265` | 未记录 | 2026-03-03 | fix(tui): remove unnecessary dedicated clients from request-response views |

### 复现

#### 前置条件
- Memory 开启自动 GC 刷新

#### 步骤
1. 高频点击操作按钮并保持后台刷新。

#### 预期行为
连接稳定，无异常。

#### 实际行为
出现 BrokenPipeError/Connection refused。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `7e73f1f` | 未记录 | 2026-03-03 | fix(tui): add dedicated client connections and handlers field for LoggerView, MemoryView, InspectView |

#### 变更内容
1. LoggerView 恢复 `_own_client` + `_handlers`。
2. MemoryView 恢复 `_own_client`。
3. InspectView 恢复 `_own_client` + `_handlers`。

#### 验证
长时间运行无 BrokenPipe，刷新与点击互不干扰。

### 影响

- **受影响用户**：并发操作 TUI 用户
- **持续时间**：`2dcb265` 至 `7e73f1f`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-03-03 | `2dcb265` 删除专用连接 |
| 2026-03-03 | 并发场景暴露竞态 |
| 2026-03-03 | `7e73f1f` 恢复专用连接 |

### 经验教训

#### 做得好的方面
- 快速承认并修复架构假设偏差。

#### 可以改进的方面
- 删除资源前未充分压测并发生命周期。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 建立“是否需要专用连接”的判定准则 | P0 | 待处理 |

### 预防

- **立即执行**：存在后台并发请求的视图优先专用连接。
- **短期**：连接模型变更必须经过并发压测。
- **长期**：统一连接池与生命周期管理器。

### 参考

- 修复提交：`7e73f1f`
- 相关引入提交：`2dcb265`

---

## 事故 #4：请求-响应视图误用专用客户端造成资源浪费

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-3 | **日期**：2026-03-03

### 概要

Inspect/Logger/Memory 视图为请求-响应模式却各自持有专用 socket，额外占用文件描述符与线程。

### 根因分析

#### 类别
Resource Management

#### 分析
从 TopView（流式场景）复制架构到所有视图，未区分持续流式与偶发请求场景。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-03-03 前 | 专用客户端策略被过度推广 |

### 复现

#### 前置条件
- 运行 TUI 并打开相关视图

#### 步骤
1. 执行 `lsof -p <target-pid> | grep peeka`。

#### 预期行为
仅保留必要连接。

#### 实际行为
出现主客户端 + 3 个附加 socket。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `2dcb265` | 未记录 | 2026-03-03 | fix(tui): remove unnecessary dedicated clients from request-response views |

#### 变更内容
移除 Inspect/Logger/Memory 的 `_own_client`，改用共享 `self._client`。

#### 验证
功能可用且减少额外连接 3 个。

### 影响

- **受影响用户**：长会话用户（资源占用增加）
- **持续时间**：专用客户端过度推广后至 `2dcb265`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-03-03 前 | 请求-响应视图持有多余专用连接 |
| 2026-03-03 | `2dcb265` 移除专用连接 |

### 经验教训

#### 做得好的方面
- 识别并清理资源冗余。

#### 可以改进的方面
- 后续证明该结论在并发刷新场景不稳定，判定边界需更精细。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 增加“资源最小化 vs 并发稳定性”对比基准 | P1 | 待处理 |

### 预防

- **立即执行**：架构决策同时评估资源与并发两维。
- **短期**：按视图行为（是否后台刷新）分类连接策略。
- **长期**：连接策略自动化配置与运行时观测。

### 参考

- 修复提交：`2dcb265`

---

## 事故 #3：StreamingAgentClient 并发 send_command 破坏协议

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-1 | **日期**：2026-03-01

### 概要

多线程同时在同一 `StreamingAgentClient` 调用 `send_command`，长度前缀与 payload 交错，触发 JSON 解析错误、响应错配与 BrokenPipe。

### 根因分析

#### 类别
Race Condition

#### 分析
`send_command` 无同步保护，线程交错写入：长度前缀被破坏后接收端读取错位，协议整体损坏。

```python
class StreamingAgentClient:
    def __init__(...):
        self._send_lock = threading.Lock()

    def send_command(...):
        with self._send_lock:
            payload = json.dumps(...).encode(...)
            self._sock.sendall(...)
            # ... read response ...
```

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-03-01 前 | StreamingAgentClient 初始实现缺少线程安全 |

### 复现

#### 前置条件
- 多 worker 并发（autocomplete + 多视图按钮）

#### 步骤
1. 高频连续触发命令。

#### 预期行为
请求响应有序匹配。

#### 实际行为
约 10% 概率协议错误。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `b4f4c4e` | 未记录 | 2026-03-01 | fix(client): add threading lock to StreamingAgentClient.send_command |

#### 变更内容
添加 `threading.Lock`，将完整 send/receive 周期串行化。

#### 验证
高并发下不再出现协议损坏。

### 影响

- **受影响用户**：并发操作用户
- **持续时间**：初始实现至 `b4f4c4e`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-03-01 前 | send_command 线程不安全 |
| 2026-03-01 | `b4f4c4e` 增加锁保护 |

### 经验教训

#### 做得好的方面
- 保护范围覆盖完整请求-响应，不仅是发送。

#### 可以改进的方面
- 协议并发模型未在设计期明确定义。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为长度前缀协议添加并发压力测试 | P0 | 待处理 |

### 预防

- **立即执行**：共享客户端默认串行化命令。
- **短期**：记录并发调用来源并审计。
- **长期**：演进为多路复用或每消费者独立连接。

### 参考

- 修复提交：`b4f4c4e`

---

## 事故 #2：多流式视图共享连接导致读取竞争与 BrokenPipe

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-1 | **日期**：2026-02-28

### 概要

Watch/Stack/Trace/Monitor 多流式视图共享一个客户端连接，多线程并发读取同一 socket 造成帧分裂与协议破坏。

### 根因分析

#### 类别
Integration Error

#### 分析
`_send_lock` 仅序列化发送，无法阻止多线程并发读取。读取竞争会把同一帧分给不同线程。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-02-28 前 | 多流式视图初始实现共享客户端 |

### 复现

#### 前置条件
- 同时开启 Watch + Stack + Monitor 等流式视图

#### 步骤
1. 持续运行数分钟。

#### 预期行为
各视图稳定接收各自数据。

#### 实际行为
BrokenPipeError，连接断开。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `067a2a0` | 未记录 | 2026-02-28 | fix(tui): use dedicated stream clients per view to prevent BrokenPipeError |

#### 变更内容
为 Watch/Stack/Trace/Monitor 分配各自 `StreamingAgentClient` 与独立 socket。

#### 验证
多流式视图长时间并行运行稳定。

### 影响

- **受影响用户**：多视图并发用户
- **持续时间**：初始实现至 `067a2a0`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-02-28 前 | 流式视图共享连接 |
| 2026-02-28 | `067a2a0` 切分专用连接 |

### 经验教训

#### 做得好的方面
- 架构层面一次性消除读取竞争源。

#### 可以改进的方面
- 早期未区分“发送同步”与“读取隔离”。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 设计文档明确“每流式消费者独立连接”原则 | P0 | 待处理 |

### 预防

- **立即执行**：禁止多线程读取同一 socket。
- **短期**：流式视图连接策略加静态检查。
- **长期**：统一流式传输抽象层。

### 参考

- 修复提交：`067a2a0`

---

## 事故 #1：异常路径未排空 OBS 帧导致协议漂移

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-1 | **日期**：2026-02-28

### 概要

命令异常后仅关闭 socket，不清理缓冲区中已在途 OBS 帧，导致下一次请求把旧帧当响应解析，最终 BrokenPipe。

### 根因分析

#### 类别
Integration Error

#### 分析
流式观察（OBS）与请求-响应复用同一连接时，异常恢复必须重同步协议状态。缺失 drain 逻辑导致帧边界持续错位。

```python
except Exception:
    # Drain any pending observation frames that are already in-flight
    # to clear the socket before we recover or close
    self._drain_observation_frames()
```

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-02-28 前 | 引入流式观察后异常恢复路径缺少 drain |

### 复现

#### 前置条件
- 启停 watch/stack/monitor 多次

#### 步骤
1. 反复启动/停止流式观察。

#### 预期行为
异常后可继续稳定复用连接。

#### 实际行为
协议错乱并最终 BrokenPipe。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `f22383e` | 未记录 | 2026-02-28 | fix(client): drain OBS frames in StreamingAgentClient to prevent BrokenPipeError |

#### 变更内容
在 `send_command` 异常路径调用 `_drain_observation_frames()`，读取并分发/丢弃在途 OBS 帧，恢复协议同步。

#### 验证
多次启停后连接稳定，不再因旧帧污染响应。

### 影响

- **受影响用户**：长时间使用流式命令用户
- **持续时间**：流式功能引入后至 `f22383e`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-02-28 前 | 异常恢复路径未 drain OBS 帧 |
| 2026-02-28 | `f22383e` 增加 drain 机制 |

### 经验教训

#### 做得好的方面
- 明确了“异常恢复=协议重同步”原则。

#### 可以改进的方面
- 协议边界条件测试不足。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 新增异常恢复与帧漂移回归测试套件 | P0 | 待处理 |

### 预防

- **立即执行**：异常后必须清理在途帧并重同步。
- **短期**：为 OBS/request 复用链路增加一致性检测。
- **长期**：考虑分离流式通道与命令通道。

### 参考

- 修复提交：`f22383e`
