# TUI 线程模型与生命周期问题

| 字段 | 值 |
|------|-----|
| **话题** | TUI 的 run_worker 使用、主线程阻塞、错误反馈与关机生命周期问题 |
| **受影响组件** | tui (app, screens, views) |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 8 |
| **时间跨度** | 2026-02-07 至 2026-05-07 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#8](#事故-8dashboard-未挂载时访问-app-导致-lifecycle-测试崩溃) | Dashboard 未挂载时访问 app 导致 lifecycle 测试崩溃 | SEV-3 | 2026-05-07 |
| [#7](#事故-7logging-配置向-stderr-输出破坏-tui-活动日志集成) | logging 配置向 stderr 输出破坏 TUI 活动日志集成 | SEV-2 | 2026-05-06 |
| [#6](#事故-6tui-缺少优雅关机信号处理) | TUI 缺少优雅关机信号处理 | SEV-2 | 2026-03-05 |
| [#5](#事故-5所有视图缺少-workerresult-错误处理) | 所有视图缺少 worker.result 错误处理 | SEV-2 | 2026-02-26 |
| [#4](#事故-4attach-在进程选择界面阻塞主线程) | attach 在进程选择界面阻塞主线程 | SEV-1 | 2026-02-26 |
| [#3](#事故-3dockerssh-终端环境变量缺失导致渲染异常) | Docker/SSH 终端环境变量缺失导致渲染异常 | SEV-2 | 2026-02-25 |
| [#2](#事故-2send_command-在主线程执行导致-ui-卡死) | send_command 在主线程执行导致 UI 卡死 | SEV-1 | 2026-02-14 |
| [#1](#事故-1run_worker-参数传递错误触发-noactiveworker-崩溃) | run_worker 参数传递错误触发 NoActiveWorker 崩溃 | SEV-1 | 2026-02-07 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题聚焦 Textual 应用的基本运行约束：阻塞 IO 不可在主线程执行、worker 必须在正确上下文启动、后台线程结果必须安全回到 UI 线程、以及进程终止时需执行清理。事故跨越启动、运行、退出全生命周期，反复指向同一系统性原因——线程边界与生命周期边界未在架构层被统一约束。

---

## 事故 #8：Dashboard 未挂载时访问 app 导致 lifecycle 测试崩溃

> **Tag 范围**：`v0.1.10` → `v0.1.11` | **严重级别**：SEV-3 | **日期**：2026-05-07

### 概要

发布前回归测试中，`DashboardView.set_active(True)` 在未挂载到 Textual App 的单元测试上下文中调用 `_load_client_activity_history()`，该方法直接访问 `self.app`，触发 `NoActiveAppError`。

### 根因分析

#### 类别
Missing Validation

#### 分析
Dashboard 新增 app 级 activity replay/listener 机制后，辅助方法默认 `self.app` 一定存在。但 lifecycle 单元测试会直接构造 `DashboardView` 并调用 `set_active(True)`，此时 Textual 的 active app 上下文不存在。activity replay/listener 本身是可选增强能力，未挂载时应 no-op，而不应阻断 view 生命周期测试或激活流程。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 候选范围 | lufeihaidao | 2026-05-06 前 | Dashboard activity log 集成引入对 `self.app` 的直接依赖 |

> 致因提交无法确定性定位；从修复 diff 可确定问题来自 Dashboard activity hook 对挂载状态的隐式假设。

### 复现

#### 前置条件
- 直接构造 `DashboardView(pid=12345)`，不通过 Textual app mount。
- 设置 `_active = False` 且注入 fake client。

#### 步骤
1. 运行 `uv run pytest tests/tui/test_view_lifecycle.py::TestDashboardLifecycle::test_set_active_restarts_dashboard_work -v`。
2. 调用 `view.set_active(True)`。

#### 预期行为
未挂载上下文中跳过可选 app-level activity replay/listener，继续重启 dashboard worker。

#### 实际行为
访问 `self.app` 抛出 `textual._context.NoActiveAppError`。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `15463f9` | lufeihaidao | 2026-05-07 | fix(tui): guard dashboard activity hooks before mount |

#### 变更内容
1. 新增 `_get_optional_app()`，捕获未挂载时的 app 访问异常。
2. `_register_client_activity_listener()`、`_unregister_client_activity_listener()`、`_load_client_activity_history()`、`_record_client_activity()` 在无 app 时 no-op。
3. 本地 extension build 会生成 `.so`，同步把 `*.so` 加入 `.gitignore`，避免 release 前工作区被构建产物污染。

#### 验证
- `uv run pytest tests/tui/test_view_lifecycle.py::TestDashboardLifecycle::test_set_active_restarts_dashboard_work -v`
- `uv run pytest tests/tui/test_view_lifecycle.py tests/test_attach_refactor.py -v`
- `uv run pytest tests/ -v -m "not e2e and not container"` 中该 lifecycle 失败被修复；剩余 native extension import 失败通过 `uv pip install -e .` 构建扩展后验证通过。

### 影响

- **受影响用户**：主要影响测试和未挂载上下文下的 view 生命周期调用；真实已挂载 TUI 行为保持不变。
- **持续时间**：Dashboard activity hook 引入后至 `15463f9`。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-05-07 | 发布前 CI-safe 本地测试发现 `NoActiveAppError` |
| 2026-05-07 | `15463f9` 增加 optional app guard |
| 2026-05-07 | lifecycle 与 attach focused tests 通过 |

### 经验教训

#### 做得好的方面
- 发布前完整测试矩阵暴露了隐藏 lifecycle 边界。
- 修复范围保持在可选 app activity hooks，没有改变 mounted TUI 的主路径。

#### 可以改进的方面
- 新增 app 级集成点时未同步考虑 direct view unit test 场景。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为所有可选 app-level view hook 统一使用 optional app 获取模式 | P1 | 待处理 |
| TUI view lifecycle 测试覆盖 mounted 与 unmounted 两类上下文 | P1 | 待处理 |

### 预防

- **立即执行**：可选 app 能力在未挂载时必须 no-op。
- **短期**：对 direct view unit tests 中的 `self.app` 访问做审计。
- **长期**：抽取 ViewBase 生命周期/应用上下文辅助方法，减少每个 view 自行处理。

### 参考

- 修复提交：`15463f9 fix(tui): guard dashboard activity hooks before mount`

---

## 事故 #7：logging 配置向 stderr 输出破坏 TUI 活动日志集成

> **Tag 范围**：`v0.1.10` → `v0.1.11` | **严重级别**：SEV-2 | **日期**：2026-05-06

### 概要

TUI 运行时复用 core 的 `configure_logging()`，该函数默认通过 `logging.basicConfig()` 给 root logger 添加 stderr stream handler。TUI 希望将客户端/内部日志呈现在 Dashboard activity log 中，但默认 stderr handler 会把日志写到终端输出通道，干扰 Textual 渲染与活动日志体验。

### 根因分析

#### 类别
Integration Error

#### 分析
`configure_logging()` 最初服务 CLI/JSONL 输出场景，默认向 stderr 写日志是合理的；TUI 场景需要不同输出目标，却只能调用同一个全局配置函数。缺少可注入 handler 和禁用 stream handler 的参数，导致 CLI 与 TUI 对日志目的地的要求耦合在一起。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | lufeihaidao | 2026-05-06 前 | core logging 配置初始实现默认绑定 stderr stream handler |

### 复现

#### 前置条件
- 启动 peeka TUI。
- 触发会写 Python logging 的客户端或 TUI 内部路径。

#### 步骤
1. TUI `on_mount()` 调用 logging 配置。
2. 触发日志输出。

#### 预期行为
日志进入 Dashboard activity log，不污染 TUI 终端渲染。

#### 实际行为
日志经 root stream handler 写到 stderr，可能破坏 TUI 显示，并且无法统一进入 activity log。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `0d19c22` | lufeihaidao | 2026-05-06 | fix: prevent logging from breaking TUI |

#### 变更内容
1. `configure_logging()` 增加 `add_stream_handler` 与 `custom_handler` 参数。
2. TUI 新增 `TUILogHandler`，将 logging record 转为 `record_client_activity(..., source="log")`。
3. `PeekaApp.on_mount()` 移除 root 上已有的 `StreamHandler`，再用 `configure_logging(add_stream_handler=False, custom_handler=...)` 绑定 TUI activity log handler。

#### 验证
- 发布前本地测试：`uv run pytest tests/ -v -m "not e2e and not container"`。
- GitHub Actions release tests：`v0.1.11` 发布 workflow 的 `Run Tests` job 通过。

### 影响

- **受影响用户**：使用 TUI 且启用/触发 logging 输出的用户。
- **持续时间**：TUI 使用通用 logging 配置后至 `0d19c22`。
- **数据影响**：无。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-05-06 | 发现 logging 输出破坏 TUI 显示/活动日志路径 |
| 2026-05-06 | `0d19c22` 支持自定义 logging handler 并接入 TUI activity log |
| 2026-05-07 | `v0.1.11` release workflow 验证通过 |

### 经验教训

#### 做得好的方面
- 保留 CLI 默认 stderr 行为，同时给 TUI 提供显式定制入口。
- 将日志统一进入 existing activity log，而不是新增第二套显示通道。

#### 可以改进的方面
- core helper 的默认输出副作用在跨入口复用前缺少场景审计。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为 `configure_logging(add_stream_handler=False, custom_handler=...)` 增加单元测试 | P1 | 待处理 |
| TUI smoke 测试覆盖 logging 输出不会写入 stderr/破坏渲染 | P1 | 待处理 |

### 预防

- **立即执行**：跨 CLI/TUI 复用的全局配置函数必须支持注入目标和禁用默认副作用。
- **短期**：对 TUI `on_mount()` 的全局状态变更做测试覆盖。
- **长期**：将 CLI logging 与 TUI logging 配置入口拆分为明确场景 API。

### 参考

- 修复提交：`0d19c22 fix: prevent logging from breaking TUI`

---

## 事故 #6：TUI 缺少优雅关机信号处理

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-2 | **日期**：2026-03-05

### 概要

`SIGTERM/SIGHUP` 终止 TUI 时未触发连接清理，可能遗留专用客户端 socket 与僵尸连接。

### 根因分析

#### 类别
Resource Management

#### 分析
未注册信号处理器，也无 `atexit` 兜底回调，退出路径仅覆盖正常交互退出场景。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-03-05 前 | TUI 初始实现未覆盖信号退出路径 |

### 复现

#### 前置条件
- 运行中的 peeka TUI

#### 步骤
1. 执行 `kill -TERM <peeka-pid>`。

#### 预期行为
触发优雅退出并清理视图连接。

#### 实际行为
进程退出但清理不完整。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `929c3f9` | 未记录 | 2026-03-05 | fix(tui): add graceful shutdown via signal handlers and atexit fallback |

#### 变更内容

```python
# Register signal handlers
loop = asyncio.get_event_loop()
for sig in (signal.SIGHUP, signal.SIGTERM):
    loop.add_signal_handler(sig, lambda: asyncio.ensure_future(self.action_quit()))

# atexit fallback
atexit.register(_atexit_cleanup)
```

#### 验证
信号可触发 `action_quit()`，连接被正确关闭，`atexit` 覆盖兜底路径。

### 影响

- **受影响用户**：被外部信号终止会话的用户
- **持续时间**：初始实现至 `929c3f9`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-03-05 前 | 信号退出无清理机制 |
| 2026-03-05 | `929c3f9` 增加 signal + atexit |

### 经验教训

#### 做得好的方面
- 同时覆盖正常与异常退出路径。

#### 可以改进的方面
- 生命周期测试未覆盖信号场景。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 增加 SIGTERM/SIGHUP 退出回归测试 | P1 | 待处理 |

### 预防

- **立即执行**：应用入口统一注册退出清理。
- **短期**：清理代码要求幂等且吞异常。
- **长期**：建立生命周期状态机并可观测化。

### 参考

- 修复提交：`929c3f9`

---

## 事故 #5：所有视图缺少 worker.result 错误处理

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-2 | **日期**：2026-02-26

### 概要

inspect/logger/monitor/stack/watch 等视图在连接异常后静默失败，用户无反馈。

### 根因分析

#### 类别
Missing Validation

#### 分析
memory 先修复后，其余视图未同步；`worker.result` 访问未统一包裹异常处理。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-02-26 前 | 各视图初始实现缺少统一错误反馈模式 |

### 复现

#### 前置条件
- 连接已断开

#### 步骤
1. 点击 inspect/logger/monitor/stack/watch 任一按钮。

#### 预期行为
弹出错误通知。

#### 实际行为
无反应、无提示。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `b7e9033` | 未记录 | 2026-02-26 | fix(tui): add worker error handling to remaining view buttons |

#### 变更内容
覆盖文件：`inspect.py`(1)、`logger.py`(2)、`monitor.py`(1)、`stack.py`(1)、`watch.py`(1)。

统一模式：

```python
await worker.wait()
try:
    response = worker.result
except Exception as e:
    self.app.notify(f"Connection error: {e}", severity="error")
    return
```

#### 验证
所有按钮在错误路径均可见提示。

### 影响

- **受影响用户**：全部相关视图用户
- **持续时间**：初始实现至 `b7e9033`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-02-26 前 | 多视图静默失败 |
| 2026-02-26 | `b7e9033` 批量补齐错误处理 |

### 经验教训

#### 做得好的方面
- 系统性覆盖剩余视图，减少局部修补。

#### 可以改进的方面
- 缺少可复用的统一错误封装。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 提供统一 `await_worker_result_or_notify()` 辅助函数 | P1 | 待处理 |

### 预防

- **立即执行**：所有 `worker.result` 读取必须 try/except。
- **短期**：代码审查清单加入“用户操作必须有失败反馈”。
- **长期**：构建通用 worker 结果处理框架。

### 参考

- 修复提交：`b7e9033`

---

## 事故 #4：attach 在进程选择界面阻塞主线程

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-1 | **日期**：2026-02-26

### 概要

点击 attach 时 `attacher.attach()` 在 UI 主线程执行，界面冻结数秒；重复点击会触发多次 attach。

### 根因分析

#### 类别
Race Condition

#### 分析
阻塞调用占用事件循环；缺少 `_attaching` 防重入；连接瞬态失败无重试。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-02-26 前 | 进程选择界面初始 attach 流程 |

### 复现

#### 前置条件
- 打开 peeka 进程选择界面

#### 步骤
1. 选择进程并点击 attach。
2. 快速重复点击。

#### 预期行为
UI 保持响应，attach 仅触发一次。

#### 实际行为
界面冻结并可能发起多次 attach。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `595e4a8` | 未记录 | 2026-02-26 | fix(tui): run process attach in worker thread and add connection retry |

#### 变更内容
1. `attach()` 移入 worker 线程。
2. `_attaching` 防重复点击。
3. attach 中禁用 UI，完成后恢复。
4. `call_from_thread()` 回主线程推进界面。
5. MainScreen 连接增加指数退避重试（0.2s→0.4s→0.8s，3 次）。

#### 验证
attach 期间 UI 仍响应，重复点击无效，瞬态连接失败可自动恢复。

### 影响

- **受影响用户**：所有 TUI attach 用户
- **持续时间**：初始实现至 `595e4a8`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-02-26 前 | attach 在主线程阻塞 |
| 2026-02-26 | `595e4a8` 迁移 worker + 加重试 |

### 经验教训

#### 做得好的方面
- 同时处理阻塞、重入、瞬态失败三类问题。

#### 可以改进的方面
- 初始流程未设“主线程阻塞预算”约束。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 建立 UI 主线程操作耗时门限（>100ms 禁止） | P0 | 待处理 |

### 预防

- **立即执行**：阻塞操作全部下沉 worker。
- **短期**：用户触发动作默认防重入。
- **长期**：attach 流程状态机化与可观测化。

### 参考

- 修复提交：`595e4a8`

---

## 事故 #3：Docker/SSH 终端环境变量缺失导致渲染异常

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-2 | **日期**：2026-02-25

### 概要

在 Docker/SSH 环境中 `TERM`/`COLORTERM` 未设置，Textual 无法正确识别终端能力，导致渲染乱码或启动失败。

### 根因分析

#### 类别
Configuration Error

#### 分析
入口层未提供环境兜底，依赖调用环境完整传递终端变量。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-02-25 前 | TUI 入口未处理容器/远程终端缺省变量 |

### 复现

#### 前置条件
- Docker/SSH 会话无 `TERM`

#### 步骤
1. 在该环境执行 `peeka`。

#### 预期行为
TUI 正常渲染。

#### 实际行为
渲染异常或启动失败。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `c83774e` | 未记录 | 2026-02-25 | fix(tui): set terminal env defaults for Docker/SSH TUI sessions |

#### 变更内容

```python
if "TERM" not in os.environ:
    os.environ["TERM"] = "xterm-256color"
if "COLORTERM" not in os.environ:
    os.environ["COLORTERM"] = "truecolor"
```

并在 Dockerfile 中同步设定。

#### 验证
Docker/SSH 场景可正确渲染，本地已有变量不被覆盖。

### 影响

- **受影响用户**：容器与远程会话用户
- **持续时间**：初始实现至 `c83774e`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-02-25 前 | 入口缺少终端变量默认值 |
| 2026-02-25 | `c83774e` 增加 TERM/COLORTERM 兜底 |

### 经验教训

#### 做得好的方面
- 在入口集中修复，避免分散补丁。

#### 可以改进的方面
- 缺少容器/SSH 启动场景测试。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 增加 Docker/SSH TUI 启动回归 | P1 | 待处理 |

### 预防

- **立即执行**：入口统一处理关键环境变量。
- **短期**：将终端能力检测结果打印到诊断日志。
- **长期**：建立运行环境兼容矩阵测试。

### 参考

- 修复提交：`c83774e`

---

## 事故 #2：send_command 在主线程执行导致 UI 卡死

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-1 | **日期**：2026-02-14

### 概要

各视图按钮直接在主线程执行阻塞网络 IO，导致 TUI 在命令返回前完全无响应。

### 根因分析

#### 类别
Integration Error

#### 分析
违反 GUI 主线程原则。Textual 事件循环被阻塞，输入和重绘均暂停。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-02-14 前 | 原始 TUI 视图统一在主线程调用 send_command |

### 复现

#### 前置条件
- 打开 memory 或其他视图

#### 步骤
1. 点击 `Refresh GC` 等按钮。

#### 预期行为
UI 可持续交互。

#### 实际行为
UI 冻结直至请求完成。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `1ab4f83` | 未记录 | 2026-02-14 | fix(tui): move all send_command calls to worker threads in all views |

#### 变更内容
1. 所有阻塞调用通过 `run_worker()` 后台执行。
2. 结果经 `app.call_from_thread()` 回主线程更新。
3. 覆盖 dashboard/watch/trace/stack/monitor/memory/logger/inspect。

#### 验证
按钮触发后 UI 即时响应，命令完成后异步更新。

### 影响

- **受影响用户**：全量 TUI 用户
- **持续时间**：初始实现至 `1ab4f83`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-02-14 前 | 主线程阻塞 IO 普遍存在 |
| 2026-02-14 | `1ab4f83` 全视图迁移到 worker |

### 经验教训

#### 做得好的方面
- 批量改造覆盖全面。

#### 可以改进的方面
- 初始架构未定义线程边界。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 增加主线程阻塞检测（lint/运行时告警） | P0 | 待处理 |

### 预防

- **立即执行**：禁止主线程执行阻塞 IO。
- **短期**：新增视图必须复用 worker 模板。
- **长期**：构建统一异步任务调度层。

### 参考

- 修复提交：`1ab4f83`

---

## 事故 #1：run_worker 参数传递错误触发 NoActiveWorker 崩溃

> **Tag 范围**：`N/A（来源为日期归档文件）` | **严重级别**：SEV-1 | **日期**：2026-02-07

### 概要

流式视图启动时将方法调用结果直接传给 `run_worker()`，导致方法在主线程即时执行，访问 worker 上下文时报 `NoActiveWorker` 并崩溃。

### 根因分析

#### 类别
Logic Error

#### 分析
`run_worker()` 需要可调用对象而非调用结果。错误写法导致执行时机和线程上下文都错误。

**修改前：**
```python
worker = self.run_worker(
    self._stream_observations(watch_id, pattern),
    thread=True,
    exclusive=False,
)
```

**修改后：**
```python
worker = self.run_worker(
    lambda: self._stream_observations(watch_id, pattern),
    thread=True,
    exclusive=False,
)
```

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 无法确定性定位 | 未记录 | 2026-02-07 前 | 流式视图初始 run_worker 用法错误 |

### 复现

#### 前置条件
- 打开 Watch/Monitor/Stack/Trace 任一流式视图

#### 步骤
1. 输入表达式并点击 Start。

#### 预期行为
流式 worker 正常启动。

#### 实际行为
抛 `NoActiveWorker`，TUI 崩溃。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `49aab9b` | 未记录 | 2026-02-07 | fix(tui): wrap run_worker calls in lambda to fix NoActiveWorker crash |

#### 变更内容
将所有直接方法调用改为 lambda 延迟执行，确保在 worker 线程上下文运行。

#### 验证
流式视图可正常启动，不再触发 NoActiveWorker。

### 影响

- **受影响用户**：流式视图用户
- **持续时间**：初始流式实现至 `49aab9b`
- **数据影响**：无

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-02-07 前 | run_worker 参数传递错误 |
| 2026-02-07 | `49aab9b` 统一改为 lambda |

### 经验教训

#### 做得好的方面
- 修复后适用于所有流式视图调用点。

#### 可以改进的方面
- 框架 API 使用缺少示例对齐审查。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 将 run_worker 正确用法写入开发模板 | P1 | 待处理 |

### 预防

- **立即执行**：`run_worker` 参数必须是 callable。
- **短期**：静态扫描 `run_worker(` 调用是否传入可调用对象。
- **长期**：封装安全 worker 启动助手函数。

### 参考

- 修复提交：`49aab9b`
