# Peeka Demo 使用指南（BDD 验收测试文档）

本文档以 BDD（行为驱动开发）场景格式，介绍如何使用 Peeka 的每个诊断命令观测 `examples/demo.py` 演示应用。每个场景包含具体的 CLI 命令、预期输出和验证要点。

---

## 概述

Peeka 提供以下诊断命令：

| 分类 | 命令 | 功能 |
|------|------|------|
| 连接管理 | `attach` / `detach` | 附加/分离目标进程 |
| 函数观测 | `watch` | 观测函数调用的参数、返回值、异常、耗时 |
| 调用追踪 | `trace` | 追踪函数内部调用链和耗时分布 |
| 调用栈 | `stack` | 捕获函数被调用时的完整调用栈 |
| 性能统计 | `monitor` | 周期性统计函数调用次数、成功率、响应时间 |
| 采样分析 | `top` | CPU 采样分析，定位热点函数 |
| 代码搜索 | `sc` / `sm` | 搜索运行中进程的类和方法 |
| 对象检查 | `inspect` | 检查运行时对象的属性和状态 |
| 日志管理 | `logger` | 动态查看和修改日志级别 |
| 内存分析 | `memory` | 内存使用概览、分配追踪、GC 触发 |
| 线程诊断 | `thread` | 查看线程列表和状态 |
| 重置恢复 | `reset` | 移除所有观测，恢复原始函数 |

---

## 前提条件

### 启动演示应用

```bash
# 终端 1：启动 demo 应用（loop 模式）
python examples/demo.py --mode loop
```

输出示例：

```
╔════════════════════════════════════════════════════════════╗
║                  Peeka Demo Application                 ║
╚════════════════════════════════════════════════════════════╝

Process ID: examples/demo.py
Python Version: 3.14.3 (main, ...)

============================================================
Peeka Demo - Continuous Loop
============================================================

Running continuous loop. Press Ctrl+C to stop.
You can attach Peeka to this process while it runs.
当前进程 PID: 12345
```

记住输出中的 **PID**（如 `12345`），后续所有命令都需要用到。

### Demo 应用行为

demo 应用在 loop 模式下的行为规律：

| 迭代 | 操作 | 说明 |
|------|------|------|
| 每次 | `calc.add(counter, counter*2)` | 加法运算 |
| 每次 | `calc.multiply(counter, 3)` | 乘法运算 |
| 每 5 次 | `calc.power(2, counter%10)` | 幂运算 |
| 每 7 次 | `calc.divide(10, 2)` | 除法（正常） |
| 每 14 次 | `calc.divide(10, 0)` | 除法（**抛出 ValueError**） |
| 每 8 次 | `slow_operation(counter)` | 慢操作（约 20ms） |

### 函数匹配模式

因为 demo.py 作为脚本直接运行，模块名为 `__main__`。以下两种写法等价：

```
demo.Calculator.add      →  自动重定向为 __main__.Calculator.add
__main__.Calculator.add   →  直接匹配
```

---

## 1. 进程附加与分离（attach / detach）

### 场景 1.1：附加到目标进程

> **前提**：demo 应用正在运行，PID 为 12345
>
> **当**：执行附加命令
>
> ```bash
> # 终端 2：附加 peeka 到目标进程
> peeka-cli attach 12345
> ```
>
> **那么**：输出附加成功信息
>
> ```json
> {"type": "status", "level": "info", "message": "Attaching to process 12345"}
> {"type": "success", "command": "attach", "data": {"pid": 12345, "socket": "/tmp/peeka_12345.sock"}}
> ```

**验证要点**：
- `type` 为 `"success"` 表示附加成功
- `data.socket` 返回通信套接字路径
- 目标进程继续正常运行，不受影响

### 场景 1.2：分离目标进程

> **前提**：已附加到目标进程
>
> **当**：执行分离命令
>
> ```bash
> peeka-cli detach
> ```
>
> **那么**：输出分离成功信息
>
> ```json
> {"type": "success", "command": "detach", "data": {"status": "success"}}
> ```

**验证要点**：
- 分离后所有观测自动停止
- 目标进程恢复到附加前的状态

---

## 2. 函数观测（watch）

watch 是 Peeka 最核心的命令，支持在函数入口（AtEnter）、正常返回（AtExit）和异常退出（AtExceptionExit）三个位置进行观测。

### 场景 2.1：观测函数出入参（默认行为）

> **前提**：已附加到 demo 进程
>
> **当**：观测 Calculator.add 方法，限定 3 次
>
> ```bash
> peeka-cli watch 'demo.Calculator.add' -n 3
> ```
>
> **那么**：输出 3 次 AtExit 观测数据
>
> ```json
> {"type": "event", "event": "watch_started", "data": {"watch_id": "watch_001", "pattern": "demo.Calculator.add"}}
> {"watch_id": "watch_001", "timestamp": 1705586200.123, "location": "AtExit", "func_name": "__main__.Calculator.add", "params": "(1, 2)", "kwargs": "{}", "target": {"__class__": "__main__.Calculator", "__attrs__": {"name": "loop-calc", "history": [["add", 1, 2, 3]]}}, "returnObj": "3", "success": true, "throwExp": null, "cost": 0.052, "thread_id": 140234567890, "thread_name": "MainThread"}
> {"watch_id": "watch_001", "timestamp": 1705586200.623, "location": "AtExit", "func_name": "__main__.Calculator.add", "params": "(2, 4)", "kwargs": "{}", "target": {"__class__": "__main__.Calculator", "__attrs__": {"name": "loop-calc", "history": [["add", 1, 2, 3], ["multiply", 1, 3, 3], ["add", 2, 4, 6]]}}, "returnObj": "6", "success": true, "throwExp": null, "cost": 0.048, "thread_id": 140234567890, "thread_name": "MainThread"}
> {"watch_id": "watch_001", "timestamp": 1705586201.123, "location": "AtExit", "func_name": "__main__.Calculator.add", "params": "(3, 6)", "kwargs": "{}", "target": {"__class__": "__main__.Calculator", "__attrs__": {"name": "loop-calc", "history": [["add", 1, 2, 3], ["multiply", 1, 3, 3], ["add", 2, 4, 6], ["multiply", 2, 3, 6], ["add", 3, 6, 9]]}}, "returnObj": "9", "success": true, "throwExp": null, "cost": 0.045, "thread_id": 140234567890, "thread_name": "MainThread"}
> ```

**验证要点**：

| 字段 | 说明 | 期望值 |
|------|------|--------|
| `location` | 观测位置 | `"AtExit"`（默认只在返回时观测） |
| `func_name` | 完整函数名 | `"__main__.Calculator.add"` |
| `params` | 位置参数（字符串格式） | `"(counter, counter*2)"` 如 `"(1, 2)"` |
| `kwargs` | 关键字参数 | `"{}"` |
| `target` | self 对象 | 包含 `name` 和 `history` 属性 |
| `returnObj` | 返回值（字符串格式） | `"3"`, `"6"`, `"9"` 等（a+b 的结果） |
| `success` | 是否成功 | `true` |
| `throwExp` | 异常信息 | `null`（无异常） |
| `cost` | 执行耗时（毫秒） | 通常 < 1ms |

### 场景 2.2：仅观测函数入口（-b 标志）

> **前提**：已附加到 demo 进程
>
> **当**：使用 `-b` 标志观测 multiply 方法入口
>
> ```bash
> peeka-cli watch 'demo.Calculator.multiply' -b -n 2
> ```
>
> **那么**：输出 AtEnter 观测数据（无返回值）
>
> ```json
> {"watch_id": "watch_002", "timestamp": 1705586200.234, "location": "AtEnter", "func_name": "__main__.Calculator.multiply", "params": "(1, 3)", "kwargs": "{}", "target": {"__class__": "__main__.Calculator", "__attrs__": {"name": "loop-calc", "history": [["add", 1, 2, 3]]}}, "returnObj": null, "success": true, "throwExp": null, "cost": 0.0, "thread_id": 140234567890, "thread_name": "MainThread"}
> ```

**验证要点**：
- `location` 为 `"AtEnter"`
- `returnObj` 为 `null`（入口处函数尚未执行，无返回值）
- `cost` 为 `0.0`（入口处无耗时统计）
- `target` 中可以看到调用前的 `history` 状态

### 场景 2.3：仅观测异常调用（-e 标志）

> **前提**：已附加到 demo 进程
>
> **当**：使用 `-e` 标志观测 divide 方法的异常调用
>
> ```bash
> peeka-cli watch 'demo.Calculator.divide' -e -n 1
> ```
>
> **那么**：等待约 7 秒（第 14 次迭代），输出异常观测数据
>
> ```json
> {"watch_id": "watch_003", "timestamp": 1705586210.456, "location": "AtExceptionExit", "func_name": "__main__.Calculator.divide", "params": "(10, 0)", "kwargs": "{}", "target": {"__class__": "__main__.Calculator", "__attrs__": {"name": "loop-calc", "history": [...]}}, "returnObj": null, "success": false, "throwExp": "ValueError: Division by zero", "cost": 0.031, "thread_id": 140234567890, "thread_name": "MainThread"}
> ```

**验证要点**：

| 字段 | 期望值 |
|------|--------|
| `location` | `"AtExceptionExit"` |
| `success` | `false` |
| `throwExp` | `"ValueError: Division by zero"` |
| `returnObj` | `null`（异常退出无返回值） |
| `params` | `"(10, 0)"`（第二个参数为 0 触发异常） |

> **注意**：正常的 `divide(10, 2)` 调用（每 7 次）不会被 `-e` 捕获，只有每 14 次的 `divide(10, 0)` 才会触发。

### 场景 2.4：同时观测入口和出口（-b -s 标志）

> **前提**：已附加到 demo 进程
>
> **当**：使用 `-b -s` 标志同时观测入口和成功返回
>
> ```bash
> peeka-cli watch 'demo.Calculator.multiply' -b -s -n 2
> ```
>
> **那么**：每次调用输出两条数据（AtEnter + AtExit）
>
> ```json
> {"watch_id": "watch_004", "timestamp": 1705586200.234, "location": "AtEnter", "func_name": "__main__.Calculator.multiply", "params": "(1, 3)", "kwargs": "{}", "target": {"__class__": "__main__.Calculator", "__attrs__": {"name": "loop-calc", "history": [...]}}, "returnObj": null, "success": true, "throwExp": null, "cost": 0.0, "thread_id": 140234567890, "thread_name": "MainThread"}
> {"watch_id": "watch_004", "timestamp": 1705586200.234, "location": "AtExit", "func_name": "__main__.Calculator.multiply", "params": "(1, 3)", "kwargs": "{}", "target": {"__class__": "__main__.Calculator", "__attrs__": {"name": "loop-calc", "history": [..., ["multiply", 1, 3, 3]]}}, "returnObj": "3", "success": true, "throwExp": null, "cost": 0.048, "thread_id": 140234567890, "thread_name": "MainThread"}
> ```

**验证要点**：
- 同一次调用产生两条数据：先 `AtEnter`，再 `AtExit`
- `AtEnter` 的 `target.history` 不含本次操作；`AtExit` 的 `target.history` 包含本次操作
- 可以对比入口和出口的 `target` 变化，观察方法对对象状态的修改

### 场景 2.5：条件过滤 — 按执行耗时过滤（cost 变量）

> **前提**：已附加到 demo 进程
>
> **当**：使用条件表达式过滤耗时 > 15ms 的 slow_operation 调用
>
> ```bash
> peeka-cli watch 'demo.slow_operation' --condition 'cost > 15' -n 2
> ```
>
> **那么**：只输出 cost > 15ms 的调用（slow_operation 内部 sleep 20ms，应全部命中）
>
> ```json
> {"watch_id": "watch_005", "timestamp": 1705586204.123, "location": "AtExit", "func_name": "__main__.slow_operation", "params": "(8,)", "kwargs": "{}", "target": null, "returnObj": "16", "success": true, "throwExp": null, "cost": 21.345, "thread_id": 140234567890, "thread_name": "MainThread"}
> ```

**验证要点**：
- `cost` 值约 20ms（因 `time.sleep(0.02)`）
- `target` 为 `null`（`slow_operation` 是模块级函数，没有 self）
- `params` 格式为 `"(8,)"` — 单参数的元组表示
- `returnObj` 为 `"16"`（`value * 2`，即 `8 * 2`）
- 条件表达式中的 `cost` 变量单位为毫秒

### 场景 2.6：条件过滤 — 按参数值过滤

> **前提**：已附加到 demo 进程
>
> **当**：使用条件表达式过滤第一个参数 > 50 的 add 调用
>
> ```bash
> peeka-cli watch 'demo.Calculator.add' --condition 'params[0] > 50' -n 1
> ```
>
> **那么**：等待约 25 秒（counter 达到 51），输出匹配的调用
>
> ```json
> {"watch_id": "watch_006", "timestamp": 1705586225.123, "location": "AtExit", "func_name": "__main__.Calculator.add", "params": "(51, 102)", "kwargs": "{}", "target": {"__class__": "__main__.Calculator", "__attrs__": {"name": "loop-calc", "history": [...]}}, "returnObj": "153", "success": true, "throwExp": null, "cost": 0.045, "thread_id": 140234567890, "thread_name": "MainThread"}
> ```

**验证要点**：
- 条件表达式中 `params` 是参数元组，`params[0]` 为第一个位置参数
- 只有满足条件的调用才会输出

### 场景 2.7：观测 self 对象的详细信息

> **前提**：已附加到 demo 进程
>
> **当**：观测 Calculator.add 并关注 target 字段
>
> ```bash
> peeka-cli watch 'demo.Calculator.add' -n 1
> ```
>
> **那么**：`target` 字段展示 Calculator 实例的完整状态
>
> ```json
> {
>     "target": {
>         "__class__": "__main__.Calculator",
>         "__attrs__": {
>             "name": "loop-calc",
>             "history": [
>                 ["add", 1, 2, 3],
>                 ["multiply", 1, 3, 3],
>                 ["add", 2, 4, 6],
>                 ["multiply", 2, 3, 6]
>             ]
>         }
>     }
> }
> ```

**验证要点**：
- `target.__class__` 显示类的完整路径
- `target.__attrs__` 包含所有**公开属性**（以 `_` 开头的私有属性被跳过）
- `name` 为 `"loop-calc"`（构造时传入）
- `history` 记录了所有已执行的运算，格式为 `[操作名, 参数1, 参数2, 结果]`
- history 列表最多显示 20 项（超出部分被截断）

---

## 3. 调用链追踪（trace）

trace 命令追踪目标函数内部的完整调用链，展示各子调用的执行耗时。

### 场景 3.1：追踪函数调用链

> **前提**：已附加到 demo 进程
>
> **当**：追踪 Calculator.add 方法的调用链
>
> ```bash
> peeka-cli trace 'demo.Calculator.add' -n 1
> ```
>
> **那么**：输出调用树结构
>
> ```json
> {"watch_id": "trace_001", "timestamp": 1705586200.123, "location": "AtExit", "func_name": "__main__.Calculator.add", "call_tree": [{"depth": 0, "function": "__main__.Calculator.add", "filename": "demo.py", "lineno": 18, "duration_ms": 0.052, "children": [{"depth": 1, "function": "list.append", "filename": "<built-in>", "lineno": 0, "duration_ms": 0.005, "children": []}]}], "total_duration_ms": 0.052, "node_count": 2, "thread_id": 140234567890, "thread_name": "MainThread"}
> ```

**验证要点**：

| 字段 | 说明 |
|------|------|
| `call_tree` | 调用树的嵌套结构，每个节点包含 `function`、`duration_ms`、`children` |
| `total_duration_ms` | 整个调用链的总耗时 |
| `node_count` | 调用树中的节点数 |
| `depth` | 调用深度（0 为根节点） |

### 场景 3.2：追踪递归函数

> **前提**：已附加到 demo 进程，且 demo 应用调用了 `factorial` 或 `fibonacci`
>
> **当**：追踪 factorial 函数，设置追踪深度为 5
>
> ```bash
> peeka-cli trace 'demo.factorial' -d 5 -n 1
> ```
>
> **那么**：输出递归调用树，展示每层调用的耗时
>
> ```json
> {"watch_id": "trace_002", "timestamp": 1705586200.456, "location": "AtExit", "func_name": "__main__.factorial", "call_tree": [{"depth": 0, "function": "__main__.factorial", "filename": "demo.py", "lineno": 49, "duration_ms": 0.15, "children": [{"depth": 1, "function": "__main__.factorial", "filename": "demo.py", "lineno": 49, "duration_ms": 0.12, "children": [{"depth": 2, "function": "__main__.factorial", "filename": "demo.py", "lineno": 49, "duration_ms": 0.08, "children": []}]}]}], "total_duration_ms": 0.15, "node_count": 3, "thread_id": 140234567890, "thread_name": "MainThread"}
> ```

**验证要点**：
- 递归调用以嵌套 `children` 形式展示
- `-d` 参数控制最大追踪深度，超出部分不展开
- 可以直观看到递归调用的层数和各层耗时

### 场景 3.3：过滤慢调用

> **前提**：已附加到 demo 进程
>
> **当**：追踪 slow_operation 并过滤最小耗时
>
> ```bash
> peeka-cli trace 'demo.slow_operation' --min-duration 10 -n 1
> ```
>
> **那么**：调用树中只保留耗时 >= 10ms 的节点

**验证要点**：
- `--min-duration` 单位为毫秒
- 耗时低于阈值的子调用节点被过滤掉
- `--skip-builtin` 默认开启，内置函数（如 `time.sleep`）会被跳过

---

## 4. 调用栈捕获（stack）

stack 命令捕获函数被调用时的完整调用栈，用于回答"这个函数是从哪里被调用的"。

### 场景 4.1：捕获函数调用栈

> **前提**：已附加到 demo 进程
>
> **当**：捕获 Calculator.add 的调用栈
>
> ```bash
> peeka-cli stack 'demo.Calculator.add' -n 1 --depth 5
> ```
>
> **那么**：输出带有 `stack` 字段的 AtEnter 观测数据
>
> ```json
> {"watch_id": "stack_001", "timestamp": 1705586200.123, "location": "AtEnter", "func_name": "__main__.Calculator.add", "params": "(1, 2)", "kwargs": "{}", "target": {"__class__": "__main__.Calculator", "__attrs__": {"name": "loop-calc", "history": []}}, "returnObj": null, "success": true, "throwExp": null, "cost": 0.0, "stack": [{"filename": "/opt/demo.py", "lineno": 129, "name": "demo_loop", "line": "result1 = calc.add(counter, counter * 2)"}, {"filename": "/opt/demo.py", "lineno": 126, "name": "demo_loop", "line": "while True:"}, {"filename": "/opt/demo.py", "lineno": 181, "name": "main", "line": "demo_loop()"}, {"filename": "/opt/demo.py", "lineno": 206, "name": "<module>", "line": "main()"}], "thread_id": 140234567890, "thread_name": "MainThread"}
> ```

**验证要点**：

| 字段 | 说明 |
|------|------|
| `stack` | 调用栈帧数组（从调用点往上回溯） |
| `stack[].filename` | 源文件路径 |
| `stack[].lineno` | 行号 |
| `stack[].name` | 函数名 |
| `stack[].line` | 对应的源代码行 |

- `--depth` 控制回溯的栈帧数量
- 栈的第一项是**直接调用位置**（`demo_loop` 中的 `calc.add(...)` 行）
- 可以追踪完整的调用路径：`<module>` → `main()` → `demo_loop()` → `calc.add()`

### 场景 4.2：条件过滤调用栈

> **前提**：已附加到 demo 进程
>
> **当**：只捕获参数满足条件的调用栈
>
> ```bash
> peeka-cli stack 'demo.Calculator.divide' --condition 'params[1] == 0' -n 1 --depth 10
> ```
>
> **那么**：只捕获除数为 0 的调用栈，帮助定位异常调用来源

**验证要点**：
- 条件表达式在 stack 命令中同样可用
- 结合条件过滤可以精准定位特定场景的调用路径

---

## 5. 性能统计（monitor）

monitor 命令周期性统计函数的调用次数、成功率和响应时间。

### 场景 5.1：监控函数性能

> **前提**：已附加到 demo 进程
>
> **当**：监控 Calculator.add 的性能，每 5 秒输出一次统计，共 3 个周期
>
> ```bash
> peeka-cli monitor 'demo.Calculator.add' --cycle 5 -c 3
> ```
>
> **那么**：每 5 秒输出一次统计数据
>
> ```json
> {"type": "event", "event": "monitor_started", "data": {"watch_id": "monitor_001", "pattern": "demo.Calculator.add"}}
> {"type": "observation", "watch_id": "monitor_001", "data": {"total": 10, "success": 10, "fail": 0, "fail_rate": 0.0, "rt_avg": 0.048, "rt_min": 0.032, "rt_max": 0.078, "cycle": 1, "watch_id": "monitor_001"}}
> {"type": "observation", "watch_id": "monitor_001", "data": {"total": 10, "success": 10, "fail": 0, "fail_rate": 0.0, "rt_avg": 0.051, "rt_min": 0.035, "rt_max": 0.082, "cycle": 2, "watch_id": "monitor_001"}}
> {"type": "observation", "watch_id": "monitor_001", "data": {"total": 10, "success": 10, "fail": 0, "fail_rate": 0.0, "rt_avg": 0.046, "rt_min": 0.031, "rt_max": 0.075, "cycle": 3, "watch_id": "monitor_001"}}
> ```

**验证要点**：

| 字段 | 说明 |
|------|------|
| `total` | 该周期内的总调用次数 |
| `success` | 成功次数 |
| `fail` | 失败次数 |
| `fail_rate` | 失败率（0.0 ~ 1.0） |
| `rt_avg` | 平均响应时间（毫秒） |
| `rt_min` | 最小响应时间（毫秒） |
| `rt_max` | 最大响应时间（毫秒） |
| `cycle` | 当前周期编号 |

- add 方法不会抛出异常，因此 `fail` 始终为 0
- 每 0.5 秒调用一次，5 秒周期内约有 10 次调用

### 场景 5.2：监控有异常的函数

> **前提**：已附加到 demo 进程
>
> **当**：监控 Calculator.divide 的性能
>
> ```bash
> peeka-cli monitor 'demo.Calculator.divide' --cycle 10 -c 2
> ```
>
> **那么**：可以观测到 fail_rate > 0 的周期
>
> ```json
> {"type": "observation", "watch_id": "monitor_002", "data": {"total": 2, "success": 1, "fail": 1, "fail_rate": 0.5, "rt_avg": 0.035, "rt_min": 0.028, "rt_max": 0.042, "cycle": 1, "watch_id": "monitor_002"}}
> ```

**验证要点**：
- divide 方法每 7 次迭代调用一次，其中每 14 次触发异常
- 约 50% 的 divide 调用会失败，因此 `fail_rate` 预期在 0.5 左右
- 可以用来快速发现函数的稳定性问题

---

## 6. 采样分析（top）

top 命令通过 CPU 采样分析定位热点函数，类似 Linux 的 `top` 命令。

### 场景 6.1：启动采样分析

> **前提**：已附加到 demo 进程
>
> **当**：启动采样分析，采样间隔 10ms
>
> ```bash
> peeka-cli top --interval 0.01 --stream
> ```
>
> **那么**：定期输出采样快照
>
> ```json
> {"type": "top_snapshot", "top_id": "top_001", "total_samples": 100, "sample_interval": 0.01, "functions": [{"name": "slow_operation", "filename": "demo.py", "line": 63, "own_pct": 35.2, "total_pct": 35.2, "own_time": 0.352, "total_time": 0.352, "own_count": 35, "total_count": 35}, {"name": "demo_loop", "filename": "demo.py", "line": 94, "own_pct": 28.5, "total_pct": 95.0, "own_time": 0.285, "total_time": 0.950, "own_count": 28, "total_count": 95}, {"name": "add", "filename": "demo.py", "line": 18, "own_pct": 12.0, "total_pct": 12.0, "own_time": 0.120, "total_time": 0.120, "own_count": 12, "total_count": 12}]}
> ```

**验证要点**：

| 字段 | 说明 |
|------|------|
| `total_samples` | 总采样次数 |
| `functions` | 按 `own_pct` 降序排列的函数列表 |
| `own_pct` | 函数自身 CPU 占比（%） |
| `total_pct` | 函数及其子调用的总 CPU 占比（%） |
| `own_time` | 函数自身占用时间（秒） |
| `own_count` | 函数自身采样命中次数 |

- `slow_operation` 因包含 `time.sleep(0.02)` 应排名靠前
- `demo_loop` 的 `total_pct` 应接近 100%（几乎所有调用都在它内部）
- Ctrl+C 停止采样

---

## 7. 类与方法搜索（sc / sm）

### 场景 7.1：搜索类

> **前提**：已附加到 demo 进程
>
> **当**：搜索包含 "Calc" 的类
>
> ```bash
> peeka-cli sc '*Calc*'
> ```
>
> **那么**：返回匹配的类列表
>
> ```json
> {"type": "result", "command": "sc", "data": {"status": "success", "classes": [{"name": "Calculator", "module": "__main__", "full_name": "__main__.Calculator"}]}}
> ```

**验证要点**：
- 支持通配符匹配（`*` 匹配任意字符）
- 返回类的模块和完整限定名

### 场景 7.2：搜索类的详细信息

> **前提**：已附加到 demo 进程
>
> **当**：使用 `-d` 查看类的详细信息
>
> ```bash
> peeka-cli sc '__main__.Calculator' -d
> ```
>
> **那么**：返回类的方法列表、基类等详细信息
>
> ```json
> {"type": "result", "command": "sc", "data": {"status": "success", "classes": [{"name": "Calculator", "module": "__main__", "full_name": "__main__.Calculator", "bases": ["object"], "methods": ["__init__", "add", "multiply", "power", "divide", "get_history"]}]}}
> ```

### 场景 7.3：搜索方法

> **前提**：已附加到 demo 进程
>
> **当**：搜索所有 "add" 方法
>
> ```bash
> peeka-cli sm '*add*'
> ```
>
> **那么**：返回匹配的方法列表
>
> ```json
> {"type": "result", "command": "sm", "data": {"status": "success", "methods": [{"name": "add", "class": "Calculator", "module": "__main__", "full_name": "__main__.Calculator.add"}]}}
> ```

### 场景 7.4：搜索方法的详细信息

> **前提**：已附加到 demo 进程
>
> **当**：使用 `-d` 查看方法的详细信息（参数签名等）
>
> ```bash
> peeka-cli sm '__main__.Calculator.add' -d
> ```
>
> **那么**：返回方法签名、源文件位置等
>
> ```json
> {"type": "result", "command": "sm", "data": {"status": "success", "methods": [{"name": "add", "class": "Calculator", "module": "__main__", "full_name": "__main__.Calculator.add", "signature": "(self, a: int, b: int) -> int", "doc": "Add two numbers", "filename": "/opt/demo.py", "lineno": 18}]}}
> ```

**验证要点**：
- `signature` 显示完整的参数签名和类型注解
- `doc` 显示方法的文档字符串
- `filename` 和 `lineno` 定位源文件位置

---

## 8. 对象检查（inspect / vmtool）

inspect 命令在运行时检查对象实例的属性和状态。

### 场景 8.1：查看类的实例数量

> **前提**：已附加到 demo 进程
>
> **当**：统计 Calculator 类的实例数量
>
> ```bash
> peeka-cli inspect --action count --class-name '__main__.Calculator'
> ```
>
> **那么**：返回实例数量
>
> ```json
> {"type": "result", "command": "inspect", "data": {"status": "success", "class_name": "__main__.Calculator", "count": 1}}
> ```

**验证要点**：
- demo loop 模式只创建了一个 `Calculator("loop-calc")` 实例

### 场景 8.2：获取类的所有实例

> **前提**：已附加到 demo 进程
>
> **当**：获取所有 Calculator 实例
>
> ```bash
> peeka-cli inspect --action instances --class-name '__main__.Calculator'
> ```
>
> **那么**：返回实例列表及其属性
>
> ```json
> {"type": "result", "command": "inspect", "data": {"status": "success", "class_name": "__main__.Calculator", "instances": [{"__class__": "__main__.Calculator", "__attrs__": {"name": "loop-calc", "history": [["add", 1, 2, 3], ["multiply", 1, 3, 3], ["add", 2, 4, 6]]}}]}}
> ```

**验证要点**：
- 返回的实例数据格式与 watch 命令中的 `target` 字段一致
- 可以看到 Calculator 的当前状态：`name` 和完整 `history`

### 场景 8.3：检查特定对象的属性

> **前提**：已附加到 demo 进程
>
> **当**：获取指定表达式的对象详情
>
> ```bash
> peeka-cli inspect --action get --target 'Calculator.name'
> ```
>
> **那么**：返回对象的值

**验证要点**：
- `--target` 使用安全表达式求值（基于 simpleeval，不会执行任意代码）
- 可以访问对象的公开属性

---

## 9. 日志管理（logger）

logger 命令可以在不重启进程的情况下查看和修改 Python 日志级别。

### 场景 9.1：列出所有日志记录器

> **前提**：已附加到 demo 进程
>
> **当**：列出所有 logger
>
> ```bash
> peeka-cli logger --action list
> ```
>
> **那么**：返回日志记录器列表
>
> ```json
> {"type": "result", "command": "logger", "data": {"status": "success", "loggers": [{"name": "root", "level": "WARNING", "effective_level": "WARNING", "handlers": []}]}}
> ```

**验证要点**：
- 列出进程中所有已注册的 logger
- `level` 为显式设置的级别，`effective_level` 为生效级别（考虑继承）

### 场景 9.2：获取特定 logger 信息

> **前提**：已附加到 demo 进程
>
> **当**：获取 root logger 的详细信息
>
> ```bash
> peeka-cli logger --action get -n root
> ```
>
> **那么**：返回该 logger 的配置信息

### 场景 9.3：动态修改日志级别

> **前提**：已附加到 demo 进程
>
> **当**：将 root logger 的级别修改为 DEBUG
>
> ```bash
> peeka-cli logger --action set -n root -l DEBUG
> ```
>
> **那么**：返回修改成功信息
>
> ```json
> {"type": "result", "command": "logger", "data": {"status": "success", "name": "root", "old_level": "WARNING", "new_level": "DEBUG"}}
> ```

**验证要点**：
- 日志级别立即生效，无需重启进程
- 返回修改前后的级别对比
- 支持的级别：DEBUG, INFO, WARNING, ERROR, CRITICAL

---

## 10. 内存分析（memory）

### 场景 10.1：查看内存概览

> **前提**：已附加到 demo 进程
>
> **当**：查看内存使用概览
>
> ```bash
> peeka-cli memory --action overview
> ```
>
> **那么**：返回内存使用统计
>
> ```json
> {"type": "result", "command": "memory", "data": {"status": "success", "overview": {"rss_mb": 25.6, "vms_mb": 128.4, "gc_enabled": true, "gc_counts": [85, 5, 1], "gc_thresholds": [700, 10, 10], "object_count": 45678}}}
> ```

**验证要点**：

| 字段 | 说明 |
|------|------|
| `rss_mb` | 驻留内存（实际物理内存使用） |
| `vms_mb` | 虚拟内存大小 |
| `gc_enabled` | 垃圾回收是否启用 |
| `gc_counts` | 三代 GC 计数 |
| `gc_thresholds` | 三代 GC 阈值 |
| `object_count` | 跟踪的对象总数 |

### 场景 10.2：触发垃圾回收

> **前提**：已附加到 demo 进程
>
> **当**：手动触发 GC
>
> ```bash
> peeka-cli memory --action gc
> ```
>
> **那么**：返回 GC 结果
>
> ```json
> {"type": "result", "command": "memory", "data": {"status": "success", "collected": 0, "uncollectable": 0}}
> ```

**验证要点**：
- `collected` 为本次 GC 回收的对象数量
- `uncollectable` 为无法回收的对象数量（通常为 0）
- 可以用于排查内存泄漏问题

### 场景 10.3：查看内存分配 Top N

> **前提**：已附加到 demo 进程
>
> **当**：查看内存分配最多的类型
>
> ```bash
> peeka-cli memory --action top
> ```
>
> **那么**：返回按对象数量排序的类型统计

**验证要点**：
- 可以发现哪些类型的对象占用了最多内存
- 结合 `start` / `stop` 动作可以追踪内存增长

---

## 11. 线程诊断（thread）

### 场景 11.1：列出所有线程

> **前提**：已附加到 demo 进程
>
> **当**：列出所有线程
>
> ```bash
> peeka-cli thread
> ```
>
> **那么**：返回线程列表
>
> ```json
> {"type": "result", "command": "thread", "data": {"status": "success", "threads": [{"tid": 140234567890, "name": "MainThread", "daemon": false, "state": "TIMED_WAITING", "stack": ["time.sleep(0.5)", "demo_loop()", "main()", "<module>"]}, {"tid": 140234567891, "name": "peeka-agent", "daemon": true, "state": "WAITING", "stack": ["socket.accept()", "..."]}]}}
> ```

**验证要点**：

| 字段 | 说明 |
|------|------|
| `tid` | 线程 ID |
| `name` | 线程名称 |
| `daemon` | 是否为守护线程 |
| `state` | 线程状态（RUNNABLE, WAITING, TIMED_WAITING 等） |
| `stack` | 线程当前调用栈 |

- MainThread 大部分时间在 `time.sleep(0.5)`，状态为 `TIMED_WAITING`
- peeka-agent 线程是 Peeka 注入的 Agent 线程，状态为 `WAITING`

### 场景 11.2：按状态过滤线程

> **前提**：已附加到 demo 进程
>
> **当**：只查看运行中的线程
>
> ```bash
> peeka-cli thread --state RUNNABLE
> ```
>
> **那么**：返回状态为 RUNNABLE 的线程

---

## 12. 重置与清理（reset）

### 场景 12.1：重置所有观测

> **前提**：已附加到 demo 进程，且有多个 watch/trace 正在运行
>
> **当**：重置所有增强
>
> ```bash
> peeka-cli reset
> ```
>
> **那么**：所有函数恢复原始状态
>
> ```json
> {"type": "result", "command": "reset", "data": {"status": "success", "reset_count": 3, "details": ["__main__.Calculator.add", "__main__.Calculator.multiply", "__main__.Calculator.divide"]}}
> ```

**验证要点**：
- `reset_count` 显示重置了多少个函数
- `details` 列出被重置的所有函数
- 重置后目标函数恢复到注入前的原始状态，无性能开销

### 场景 12.2：按模式重置

> **前提**：已附加到 demo 进程，有多个 watch 正在运行
>
> **当**：只重置 Calculator.add 的观测
>
> ```bash
> peeka-cli reset --pattern 'demo.Calculator.add'
> ```
>
> **那么**：仅重置指定函数，其他观测不受影响

---

## 验收检查清单

使用以下清单验证 Peeka 的各项功能是否正常工作：

### 连接管理

- [ ] `attach`：成功附加到 demo 进程，输出 socket 路径
- [ ] `detach`：成功分离，目标进程继续正常运行

### 函数观测（watch）

- [ ] 默认模式：观测到 AtExit 数据，包含 `params`、`returnObj`、`cost`
- [ ] `-b` 模式：观测到 AtEnter 数据，`returnObj` 为 null
- [ ] `-e` 模式：只捕获异常调用，`throwExp` 包含异常信息
- [ ] `-b -s` 模式：同一调用产生 AtEnter + AtExit 两条数据
- [ ] `--condition 'cost > 15'`：只输出慢调用
- [ ] `--condition 'params[0] > 50'`：只输出参数满足条件的调用
- [ ] `-n` 限制：达到指定次数后自动停止
- [ ] `target` 字段：实例方法显示 self 对象（含 `__class__` 和 `__attrs__`）
- [ ] `target` 字段：模块级函数为 null

### 调用追踪（trace）

- [ ] 调用树结构正确，包含 `function`、`duration_ms`、`children`
- [ ] `-d` 控制追踪深度
- [ ] `--min-duration` 过滤慢调用

### 调用栈（stack）

- [ ] `stack` 字段包含调用栈帧，每帧有 `filename`、`lineno`、`name`、`line`
- [ ] `--depth` 控制栈帧数量

### 性能统计（monitor）

- [ ] 周期性输出 `total`、`success`、`fail`、`fail_rate`、`rt_avg`
- [ ] 监控 divide 方法时 `fail_rate` > 0

### 采样分析（top）

- [ ] 输出函数列表，包含 `own_pct`、`total_pct`
- [ ] `slow_operation` 排名靠前

### 搜索（sc / sm）

- [ ] `sc '*Calc*'`：找到 Calculator 类
- [ ] `sm '*add*'`：找到 add 方法
- [ ] `-d` 标志：返回详细信息（签名、文档、源文件位置）

### 对象检查（inspect）

- [ ] `--action count`：返回实例数量
- [ ] `--action instances`：返回实例列表及属性

### 日志管理（logger）

- [ ] `--action list`：列出所有 logger
- [ ] `--action set`：动态修改日志级别

### 内存分析（memory）

- [ ] `--action overview`：返回 RSS、VMS、GC 统计
- [ ] `--action gc`：触发垃圾回收

### 线程诊断（thread）

- [ ] 列出所有线程，包含名称、状态、调用栈
- [ ] MainThread 状态为 TIMED_WAITING（在 sleep 中）

### 重置（reset）

- [ ] 重置所有观测后，函数恢复原始状态
- [ ] `--pattern` 选择性重置

---

## 常见问题

### Q: watch 观测不到数据？

1. 确认函数名格式正确：`demo.Calculator.add` 或 `__main__.Calculator.add`
2. 确认函数确实被调用（loop 模式下大部分函数每 0.5 秒调用一次）
3. 检查 `--condition` 是否过于严格
4. 使用 `sm '*add*'` 搜索确认函数存在

### Q: 条件表达式中可以使用哪些变量？

| 变量 | 说明 | 示例 |
|------|------|------|
| `params` | 位置参数元组 | `params[0] > 10` |
| `kwargs` | 关键字参数字典 | `kwargs.get('debug')` |
| `returnObj` | 返回值 | `returnObj > 100` |
| `throwExp` | 异常信息 | `throwExp is not None` |
| `target` | self 对象 | `target.name == 'loop-calc'` |
| `cost` | 执行耗时（毫秒） | `cost > 15` |

### Q: 如何配合 jq 使用？

```bash
# 只看观测数据
peeka-cli watch 'demo.Calculator.add' | jq 'select(.location == "AtExit")'

# 提取返回值
peeka-cli watch 'demo.Calculator.add' | jq '.returnObj'

# 过滤慢调用
peeka-cli watch 'demo.slow_operation' | jq 'select(.cost > 15)'

# 统计成功率
peeka-cli monitor 'demo.Calculator.divide' --cycle 10 | jq 'select(.type == "observation") | .data.fail_rate'
```
