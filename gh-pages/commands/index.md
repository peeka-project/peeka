---
layout: default
title: 命令参考
nav_order: 4
has_children: true
permalink: /commands
---

# 命令参考
{: .no_toc }

Peeka 提供了一系列强大的诊断命令，每个命令都专注于特定的诊断场景。
{: .fs-6 .fw-300 }

---

## 命令概览

| 命令 | 功能 | 适用场景 |
|------|------|---------|
| [attach]({{ site.baseurl }}{% link commands/attach.md %}) | 附加到目标进程 | 所有场景的第一步 |
| [watch]({{ site.baseurl }}{% link commands/watch.md %}) | 观测函数调用 | 查看参数、返回值、执行时间 |
| [trace]({{ site.baseurl }}{% link commands/trace.md %}) | 追踪调用链 | 分析函数调用关系和耗时分布 |
| [stack]({{ site.baseurl }}{% link commands/stack.md %}) | 追踪调用栈 | 追踪函数被谁调用 |
| [monitor]({{ site.baseurl }}{% link commands/monitor.md %}) | 性能统计 | 实时监控函数性能指标 |
| [logger]({{ site.baseurl }}{% link commands/logger.md %}) | 日志管理 | 动态调整日志级别 |
| [memory]({{ site.baseurl }}{% link commands/memory.md %}) | 内存分析 | 分析内存使用和泄漏 |
| [inspect]({{ site.baseurl }}{% link commands/inspect.md %}) | 对象检查 | 运行时检查对象属性 |
| [sc/sm]({{ site.baseurl }}{% link commands/search.md %}) | 搜索类和方法 | 代码探索和发现 |
| [reset]({{ site.baseurl }}{% link commands/reset.md %}) | 重置增强 | 恢复被观测的函数 |

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

# 支持通配符（计划中）
module.ClassName.*
module.*
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

# 使用快捷键切换视图
# W - Watch 视图
# T - Trace 视图
# S - Stack 视图
# M - Monitor 视图
# L - Logger 视图
# Y - Memory 视图
```

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

- [attach - 附加到进程]({{ site.baseurl }}{% link commands/attach.md %})
- [watch - 观测函数调用]({{ site.baseurl }}{% link commands/watch.md %})
- [trace - 追踪调用链]({{ site.baseurl }}{% link commands/trace.md %})
- [stack - 追踪调用栈]({{ site.baseurl }}{% link commands/stack.md %})
- [monitor - 性能监控]({{ site.baseurl }}{% link commands/monitor.md %})

或查看 [快速开始]({{ site.baseurl }}{% link quickstart.md %}) 了解基本使用方法。
