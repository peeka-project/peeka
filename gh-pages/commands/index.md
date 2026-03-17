---
layout: default
title: 命令参考
nav_order: 4
has_children: true
permalink: /commands
---

# 命令参考
{: .no_toc }

Peeka 提供了一系列强大的诊断命令，每个命令都专注于特定的诊断场景。本文档涵盖了 13 个核心命令。
{: .fs-6 .fw-300 }
## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}


---

## 命令概览

| 命令 | 功能 | 适用场景 |
|------|------|---------|
| [attach]({% link commands/attach.md %}) | 附加到目标进程 | 所有场景的第一步 |
| [watch]({% link commands/watch.md %}) | 观测函数调用 | 查看参数、返回值、执行时间 |
| [trace]({% link commands/trace.md %}) | 追踪调用链 | 分析函数调用关系和耗时分布 |
| [stack]({% link commands/stack.md %}) | 追踪调用栈 | 追踪函数被谁调用 |
| [monitor]({% link commands/monitor.md %}) | 性能统计 | 实时监控函数性能指标 |
| [logger]({% link commands/logger.md %}) | 日志管理 | 动态调整日志级别 |
| [memory]({% link commands/memory.md %}) | 内存分析 | 分析内存使用和泄漏 |
| [inspect]({% link commands/inspect.md %}) | 对象检查 | 运行时检查对象属性 |
| [search]({% link commands/search.md %}) | 搜索类和方法 (sc/sm) | 代码探索和发现 |
| [thread]({% link commands/thread.md %}) | 线程分析 | 枚举线程和查看线程栈 |
| [top]({% link commands/top.md %}) | 函数性能采样 | 函数级性能热点分析 |
| [detach]({% link commands/detach.md %}) | 断开连接 | 安全退出诊断会话 |
| [reset]({% link commands/reset.md %}) | 重置增强 | 恢复被观测的函数 |

---

## 通用参数

所有命令共享以下参数格式：

### Pattern 格式

用于指定目标函数的模式：

```bash
# 类方法
module.ClassName.method_name

# 模块函数
module.function_name

# 支持通配符
module.ClassName.*
module.*
*.method_name
```

### 输出格式

所有命令输出 JSONL（JSON Lines）格式，每行一个 JSON 对象：

```json
{"type":"status","level":"info","message":"..."}
{"type":"success","command":"attach","data":{...}}
{"type":"observation","watch_id":"...","data":{...}}
```

### 消息类型

| 类型 | 说明 |
|------|------|
| `status` | 状态信息（非关键） |
| `success` | 命令成功 |
| `error` | 命令失败 |
| `event` | 控制事件（started, stopped） |
| `observation` | 观测数据 |
| `result` | 查询结果 |

---

## 命令使用流程

### 标准诊断流程

```bash
# 1. 附加到进程
peeka-cli attach <pid>

# 2. 使用具体诊断命令
peeka-cli watch "module.func"

# 3. 分析结果
peeka-cli watch "module.func" | jq 'select(.type == "observation")'

# 4. （可选）重置增强
peeka-cli reset "module.func"
```

### TUI 交互式流程

```bash
# 启动 TUI
peeka

# 使用数字键切换视图
# 1 - Dashboard 仪表盘
# 2 - Watch 观测视图
# 3 - Trace 追踪视图
# 4 - Stack 调用栈视图
# 5 - Monitor 性能监控视图
# 6 - Memory 内存分析视图
# 7 - Logger 日志管理视图
# 8 - Inspect 对象检查视图
# 9 - Threads 线程分析视图
# 0 - Top 函数热点视图
```

详见 [TUI 使用指南]({% link tui.md %})。

---

## 条件表达式

许多命令支持 `--condition` 参数，用于过滤观测结果。

### 可用变量

| 变量 | 说明 | 类型 |
|------|------|------|
| `params` | 函数参数列表 | list |
| `kwargs` | 关键字参数字典 | dict |
| `returnObj` | 返回值 | any |
| `throwExp` | 异常对象 | Exception or None |
| `cost` | 执行时间（毫秒） | float |
| `target` | 目标对象（实例方法） | object |

### 条件示例

```bash
# 参数过滤
--condition "params[0] > 100"
--condition "len(params) > 2"
--condition "kwargs.get('debug') == True"

# 返回值过滤
--condition "returnObj is not None"
--condition "len(returnObj) > 10"

# 执行时间过滤
--condition "cost > 100"  # 超过 100ms
--condition "cost > 10 and cost < 100"  # 10-100ms

# 异常过滤
--condition "throwExp is not None"
--condition "type(throwExp).__name__ == 'ValueError'"

# 组合条件
--condition "params[0] > 100 and cost > 50"
--condition "len(params) > 2 or returnObj is None"
```

### 安全限制

条件表达式使用 `simpleeval` 库进行安全评估，不支持：

- ❌ `__import__`, `eval`, `exec` 等危险函数
- ❌ 文件操作（`open`, `read`, `write`）
- ❌ 反射操作（`__class__`, `__subclasses__`）
- ✅ 算术运算、比较、逻辑运算
- ✅ 字符串操作、列表索引
- ✅ 安全的内置函数（`len`, `str`, `int` 等）

---

## 性能影响

| 命令 | 性能开销 | 说明 |
|------|---------|------|
| `watch` | < 1% | 装饰器注入，开销极小 |
| `trace` | < 5% (3.12+) | 使用 sys.monitoring API |
| `trace` | < 20% (3.9-3.11) | 使用 sys.settrace |
| `stack` | < 1% | 仅捕获调用栈 |
| `monitor` | < 1% | 定期统计 |
| `logger` | 0% | 不影响性能 |
| `memory` | 可配置 | 取决于采样频率 |

---

## 下一步

选择您需要的命令查看详细文档：

- [attach - 附加到进程]({% link commands/attach.md %}) 
- [watch - 观测函数调用]({% link commands/watch.md %})
- [trace - 追踪调用链]({% link commands/trace.md %})
- [stack - 追踪调用栈]({% link commands/stack.md %})
- [monitor - 性能监控]({% link commands/monitor.md %})
- [logger - 日志管理]({% link commands/logger.md %})
- [memory - 内存分析]({% link commands/memory.md %})
- [inspect - 对象检查]({% link commands/inspect.md %})
- [search - 搜索类和方法]({% link commands/search.md %})
- [reset - 重置增强]({% link commands/reset.md %})
- [thread - 线程分析]({% link commands/thread.md %})
- [top - 函数性能采样]({% link commands/top.md %})
- [detach - 断开连接]({% link commands/detach.md %})

或查看 [快速开始]({% link quickstart.md %}) 了解基本使用方法。
