# Peeka 场景截图集

本文是 [场景案例教程](scenarios.md) 的配图版：7 个业务场景各自跑一遍真实的 `examples/scenario_*.py`，用当前版本的 `peeka-cli` 和 `peeka` TUI 截图。文字教程讲"为什么这么查"，这里展示"实际看到什么"。

## 截图说明

- **环境**：Linux，Python 3.14（PEP 768 原生 attach），本机进程。
- **CLI 截图**：命令就是图中 `$` 后的那一行，输出为真实 JSONL。为便于阅读，渲染时做了**仅显示层面**的整理：去掉值为 `null`/空的字段和 `event_id`/`probe_id`/`job_id`/`thread_id` 等簿记字段、去掉 `stack` 旁重复的 `data.stack_trace`、把绝对路径缩短为仓库相对路径或 `<stdlib>/`，超长行截断为 `…`；agent 的 `{"type": "log"}` 心跳日志行被过滤。`top` 截图把最后一个采样周期的 JSON 字段整理成表格。
- **TUI 截图**：真实的 `PeekaApp`（进程选择器 → attach → 各视图），在 160×44 的虚拟终端里运行。
- **重新生成**：

  ```bash
  .venv/bin/python scripts/scenario_demos/cli_scenarios.py      # 全部 CLI 截图，可传场景号如 1 3
  .venv/bin/python scripts/scenario_demos/tui_scenarios.py      # 全部 TUI 截图
  ```

  工具链全程无头：CLI 输出用 Rich 导出 SVG，TUI 用 Textual `run_test()` + `save_screenshot()`，再由 headless Chromium 转成 PNG，不会在桌面上弹出窗口。目标进程通过 `scripts/scenario_demos/launch_target.py` 启动（先 `prctl(PR_SET_PTRACER_ANY)` 再 `exec`），因此在 `kernel.yama.ptrace_scope = 1` 下无需 sudo 也能 attach。

---

## 场景 1：电商订单金额计算错误

**业务问题**：部分打折订单的应付金额远高于商品小计。

### CLI

1. 启动订单服务，记下 PID。

   ![场景 1 启动](assets/scenarios/s1-cli-1-start.png)

2. attach 到进程。

   ![场景 1 attach](assets/scenarios/s1-cli-2-attach.png)

3. `watch` 订单计算函数：无折扣订单返回 79.97，而 `discount: "20"` 的订单返回 1599.4——折扣被当成了倍数。

   ![场景 1 watch](assets/scenarios/s1-cli-3-watch.png)

4. `stack` 确认调用路径：`main → process_order → calculate_total`。

   ![场景 1 stack](assets/scenarios/s1-cli-4-stack.png)

5. 收尾：`reset` 还原注入的探针，`detach` 断开。

   ![场景 1 cleanup](assets/scenarios/s1-cli-5-cleanup.png)

### TUI

| 步骤 | 截图 |
|------|------|
| 进程选择器中按 PID 过滤并 attach | ![](assets/scenarios/s1-tui-1-attach.png) |
| Dashboard 总览 | ![](assets/scenarios/s1-tui-2-dashboard.png) |
| Watch 视图：结果列里 1599.4 一眼可见 | ![](assets/scenarios/s1-tui-3-watch.png) |
| Stack 视图：调用路径 | ![](assets/scenarios/s1-tui-4-stack.png) |

---

## 场景 2：API 偶发慢请求

**业务问题**：商品搜索接口偶尔极慢，其余请求都正常。

> 本节截图拍摄时，示例的慢路径还是约 100 秒（已在 `fix/scenario-demo-bugs` 分支修正为约 1 秒），所以目标以 `--interval 3` 启动，以便先采到正常请求。

### CLI

1. 启动 API 服务。

   ![场景 2 启动](assets/scenarios/s2-cli-1-start.png)

2. attach。

   ![场景 2 attach](assets/scenarios/s2-cli-2-attach.png)

3. `monitor` 搜索接口：正常请求的耗时都很低。

   ![场景 2 monitor](assets/scenarios/s2-cli-3-monitor.png)

4. 慢请求可能根本不返回，所以用 `watch -b` 在**入口**按条件 `len(params[0]) > 10` 抓：长查询 `"high performance laptop computer"` 进入了 `search_products`。

   ![场景 2 watch](assets/scenarios/s2-cli-4-watch.png)

5. `thread` 看当下卡在哪：主线程停在 `search_products` 的慢循环里。

   ![场景 2 thread](assets/scenarios/s2-cli-5-thread.png)

6. 收尾。

   ![场景 2 cleanup](assets/scenarios/s2-cli-6-cleanup.png)

### TUI

| 步骤 | 截图 |
|------|------|
| attach | ![](assets/scenarios/s2-tui-1-attach.png) |
| Monitor 视图：这个统计窗口里完成数为 0——窗口内进来的唯一一个请求就是慢请求，还没返回 | ![](assets/scenarios/s2-tui-2-monitor.png) |
| Threads 视图：主线程卡在 `search_products:80`，栈上还能看到 monitor 的 `wrapper` | ![](assets/scenarios/s2-tui-3-threads.png) |

---

## 场景 3：CPU 占用过高

**业务问题**：数据处理服务 CPU 长期偏高，需要找出热点函数。

> 截图时目标以 `--batch-size 20000 --interval 0.01` 启动，让排序热点足够明显（默认参数下进程大部分时间在 sleep）。

### CLI

1. 启动数据处理服务。

   ![场景 3 启动](assets/scenarios/s3-cli-1-start.png)

2. attach。

   ![场景 3 attach](assets/scenarios/s3-cli-2-attach.png)

3. `top` 采样：除主循环外，业务代码里 `transform_data` 及其排序用的 `<lambda>` 占比最高。

   ![场景 3 top](assets/scenarios/s3-cli-3-top.png)

4. `watch transform_data`：每批都对数据做重复排序。

   ![场景 3 watch](assets/scenarios/s3-cli-4-watch.png)

5. 收尾。

   ![场景 3 cleanup](assets/scenarios/s3-cli-5-cleanup.png)

### TUI

| 步骤 | 截图 |
|------|------|
| attach | ![](assets/scenarios/s3-tui-1-attach.png) |
| Top 视图 | ![](assets/scenarios/s3-tui-2-top.png) |
| Trace 视图：`process_batch` 调用树 | ![](assets/scenarios/s3-tui-3-trace.png) |
| Watch 视图：`transform_data` | ![](assets/scenarios/s3-tui-4-watch.png) |

---

## 场景 4：内存持续增长

**业务问题**：服务内存随运行时间持续上涨，怀疑缓存泄漏。

### CLI

1. 启动服务。

   ![场景 4 启动](assets/scenarios/s4-cli-1-start.png)

2. attach 后立即 `memory --action start` 开启 tracemalloc。

   ![场景 4 attach + memory start](assets/scenarios/s4-cli-2-attach.png)

3. `memory --action top`：分配最多的是 `scenario_4_memory_leak.py` 第 133、137 行。

   ![场景 4 memory top](assets/scenarios/s4-cli-3-top.png)

4. 间隔 10 秒打两次快照再 `diff`：同样两行在 10 秒内各增长约 1.8 MB，且只增不减。

   ![场景 4 memory diff](assets/scenarios/s4-cli-4-diff.png)

5. 收尾：`memory --action stop` 停止 tracemalloc，再 `reset` / `detach`。

   ![场景 4 cleanup](assets/scenarios/s4-cli-5-cleanup.png)

### TUI

| 步骤 | 截图 |
|------|------|
| attach | ![](assets/scenarios/s4-tui-1-attach.png) |
| Memory 视图 · Allocations | ![](assets/scenarios/s4-tui-2-allocations.png) |
| Memory 视图 · 快照 Diff | ![](assets/scenarios/s4-tui-3-diff.png) |
| Memory 视图 · GC Objects | ![](assets/scenarios/s4-tui-4-gc-objects.png) |

---

## 场景 5：多线程死锁

**业务问题**：转账服务运行一段时间后完全停止处理，进程仍在。

### CLI

1. 启动转账服务（等几秒让两个 worker 互相卡住）。

   ![场景 5 启动](assets/scenarios/s5-cli-1-start.png)

2. attach。

   ![场景 5 attach](assets/scenarios/s5-cli-2-attach.png)

3. `thread`：`Worker-A→B` 和 `Worker-B→A` 的栈顶都停在 `transfer` 第 103 行（`with to_account.lock`）。

   ![场景 5 thread](assets/scenarios/s5-cli-3-thread.png)

4. `thread --tid` 看其中一个 worker 的完整栈：`worker_b_to_a → transfer:103`，停在内层的 `with to_account.lock`。两个 worker 转账方向相反、都卡在第二把锁上——典型的加锁顺序不一致导致的死锁。

   ![场景 5 thread stack](assets/scenarios/s5-cli-4-stack.png)

5. 收尾。

   ![场景 5 cleanup](assets/scenarios/s5-cli-5-cleanup.png)

### TUI

| 步骤 | 截图 |
|------|------|
| attach | ![](assets/scenarios/s5-tui-1-attach.png) |
| Threads 视图 | ![](assets/scenarios/s5-tui-2-threads.png) |
| 选中 worker 查看栈 | ![](assets/scenarios/s5-tui-3-thread-stack.png) |

---

## 场景 6：线上紧急诊断

**业务问题**：生产服务行为异常，但 DEBUG 日志是关的，又不能重启。

> 目标以 `--mode loop` 启动（持续处理请求）。

### CLI

1. 启动服务。

   ![场景 6 启动](assets/scenarios/s6-cli-1-start.png)

2. attach。

   ![场景 6 attach](assets/scenarios/s6-cli-2-attach.png)

3. `watch get_user`：参数、返回值，以及 `self` 上的配置和 logger 级别（30 = WARNING）一并可见。

   ![场景 6 watch](assets/scenarios/s6-cli-3-watch.png)

4. `logger`：查看 `__main__` 当前级别为 WARNING，运行时直接调到 DEBUG，无需重启。

   ![场景 6 logger](assets/scenarios/s6-cli-4-logger.png)

5. 收尾：把级别调回去，再 `reset` / `detach`。

   ![场景 6 cleanup](assets/scenarios/s6-cli-5-cleanup.png)

### TUI

| 步骤 | 截图 |
|------|------|
| attach | ![](assets/scenarios/s6-tui-1-attach.png) |
| Watch 视图 | ![](assets/scenarios/s6-tui-2-watch.png) |
| Logger 视图：把 `__main__` 调到 DEBUG | ![](assets/scenarios/s6-tui-3-logger.png) |
| Inspect 视图：`UserService` | ![](assets/scenarios/s6-tui-4-inspect.png) |

---

## 场景 7："谁在调用我"

**业务问题**：数据库查询量比预期高很多，不知道是哪个服务在打。

### CLI

1. 启动服务。

   ![场景 7 启动](assets/scenarios/s7-cli-1-start.png)

2. attach。

   ![场景 7 attach](assets/scenarios/s7-cli-2-attach.png)

3. 不熟悉代码时先用 `sc` / `sm` 找类和方法：`Database.execute_query(self, sql)` 是入口。

   ![场景 7 sc + sm](assets/scenarios/s7-cli-3-sc-sm.png)

4. `stack execute_query`：连续多次调用都来自 `Worker-Reports` 线程的 `generate_daily_report`。

   ![场景 7 stack](assets/scenarios/s7-cli-4-stack.png)

5. 收尾。

   ![场景 7 cleanup](assets/scenarios/s7-cli-5-cleanup.png)

### TUI

| 步骤 | 截图 |
|------|------|
| attach | ![](assets/scenarios/s7-tui-1-attach.png) |
| Monitor 视图：`execute_query` 调用频率 | ![](assets/scenarios/s7-tui-2-monitor.png) |
| Trace 视图：`generate_daily_report` | ![](assets/scenarios/s7-tui-3-trace.png) |
| Stack 视图：调用方几乎都是 `generate_daily_report` | ![](assets/scenarios/s7-tui-4-stack.png) |

---

## 截图过程中发现的问题

以下问题均已在 `fix/scenario-demo-bugs` 分支修复，场景 3 和场景 6 的相关截图已用修复后的代码重拍：

- `examples/scenario_2_slow_api.py` 的慢路径实际要跑约 100 秒（内层循环从不 `break`），文档写的是约 1 秒。现已改为每个商品一次 10ms 的模拟 I/O，约 1 秒。
- `peeka-cli top` 开着 `filter_peeka`，结果里仍有 agent 自身的 `<string>` 帧（`_handle_client` 等），own% 超过 100%。原因是 agent 代码在目标进程里以源码方式执行，文件名不在 peeka 包目录下；现在按线程入口帧识别 agent 线程。
- TUI Logger 视图 "Set Level" 发出的字段是 `logger`，agent 要求 `name`，报 `Missing required parameters: name`。已改为 `name`。
- TUI 中开 Stack/Watch/Trace/Monitor 流后，共享命令连接失去响应（`no response received`、`Broken pipe`）。原因是 TUI 在主连接上发 `start`，agent 把主连接也升级为观察流连接并向它推送数据，没人读取导致缓冲区写满、连接被当作慢客户端踢掉。现在 TUI 的非流连接会声明不接收观察数据。截图脚本仍为每个视图开独立 TUI 会话，但这已不是必需的。
- `scenarios.md` 中过时的命令写法（`monitor -i/-n`、`reset --all`、`detach <PID>`、`top <pattern>`、`inspect --attr` 等）和重复的场景 1-5 章节已清理。
