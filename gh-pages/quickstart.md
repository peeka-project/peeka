---
layout: default
title: 快速开始
nav_order: 3
---

# 快速开始
{: .no_toc }

通过简单的几步，快速上手 Peeka 的基本功能。
{: .fs-6 .fw-300 }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 第一个示例

### 1. 准备目标程序

创建一个简单的 Python 程序 `demo.py`：

```python
# demo.py
import time

class Calculator:
    def add(self, a, b):
        time.sleep(0.1)  # 模拟计算耗时
        return a + b

    def multiply(self, a, b):
        time.sleep(0.05)
        return a * b

def main():
    calc = Calculator()
    while True:
        result1 = calc.add(1, 2)
        print(f"add(1, 2) = {result1}")

        result2 = calc.multiply(3, 4)
        print(f"multiply(3, 4) = {result2}")

        time.sleep(1)

if __name__ == "__main__":
    print(f"进程 PID: {os.getpid()}")
    main()
```

### 2. 运行目标程序

```bash
python demo.py
# 输出: 进程 PID: 12345
```

### 3. 附加到进程

在另一个终端窗口：

```bash
peeka-cli attach 12345
```

输出：
```json
{"type":"status","level":"info","message":"Attaching to process 12345"}
{"type":"success","command":"attach","data":{"pid":12345,"socket":"/tmp/peeka_xxx.sock"}}
```

### 4. 观测函数调用

观测 `add` 方法的调用：

```bash
peeka-cli watch "demo.Calculator.add" --times 3
```

输出：
```json
{"type":"event","event":"watch_started","data":{"watch_id":"watch_001","pattern":"demo.Calculator.add"}}
{"type":"observation","watch_id":"watch_001","timestamp":1705586200.123,"func_name":"demo.Calculator.add","args":[1,2],"result":3,"success":true,"duration_ms":100.123,"count":1}
{"type":"observation","watch_id":"watch_001","timestamp":1705586201.123,"func_name":"demo.Calculator.add","args":[1,2],"result":3,"success":true,"duration_ms":100.087,"count":2}
{"type":"observation","watch_id":"watch_001","timestamp":1705586202.123,"func_name":"demo.Calculator.add","args":[1,2],"result":3,"success":true,"duration_ms":100.091,"count":3}
{"type":"event","event":"watch_stopped","data":{"watch_id":"watch_001","reason":"max_count_reached"}}
```

---

## 核心功能演示

### 观测函数调用（watch）

#### 基本观测

```bash
# 观测 5 次调用
peeka-cli watch "demo.Calculator.add" --times 5

# 无限观测（按 Ctrl+C 停止）
peeka-cli watch "demo.Calculator.add"
```

#### 条件过滤

只观测满足特定条件的调用：

```bash
# 只观测第一个参数大于 100 的调用
peeka-cli watch "demo.Calculator.multiply" --condition "params[0] > 100"

# 只观测执行时间超过 10ms 的调用
peeka-cli watch "demo.Calculator.add" --condition "cost > 10"

# 组合条件
peeka-cli watch "demo.func" --condition "len(params) > 2 and cost > 5"
```

#### 观测点控制

```bash
# 函数入口观测（查看输入参数）
peeka-cli watch "demo.Calculator.add" --before

# 仅成功时观测
peeka-cli watch "demo.Calculator.add" --success

# 仅异常时观测
peeka-cli watch "demo.Calculator.add" --exception
```

### 追踪调用链（trace）

查看函数的完整调用链和每个调用的耗时：

```bash
peeka-cli trace "demo.Calculator.add" --depth 3 --times 1
```

输出（树形结构）：
```
`---[125.3ms] demo.Calculator.add()
    +---[2.1ms] time.sleep()
    `---[1.2ms] builtins.print()
```

### 追踪调用栈（stack）

查看函数被谁调用：

```bash
peeka-cli stack "demo.Calculator.add" --times 1
```

输出：
```
Thread: MainThread
  File "demo.py", line 15, in main
    result1 = calc.add(1, 2)
  File "demo.py", line 6, in add
    return a + b
```

### 性能监控（monitor）

实时统计函数性能指标：

```bash
peeka-cli monitor "demo.Calculator.add" --interval 5 -c 3
```

输出：
```json
{"type":"observation","timestamp":1705586200.123,"func_name":"demo.Calculator.add","total":10,"success":10,"fail":0,"avg_rt":100.5,"min_rt":98.2,"max_rt":105.3}
```

---

## 数据处理

### 使用 jq 处理输出

Peeka 输出标准 JSONL 格式，可以方便地与 jq 等工具集成。

#### 提取观测数据

```bash
# 只显示观测数据（过滤其他消息）
peeka-cli watch "demo.func" | jq 'select(.type == "observation")'

# 只显示函数返回值
peeka-cli watch "demo.func" | jq 'select(.type == "observation") | .result'

# 显示参数和返回值
peeka-cli watch "demo.func" | jq 'select(.type == "observation") | {args, result}'
```

#### 过滤和统计

```bash
# 过滤慢调用（执行时间 > 10ms）
peeka-cli watch "demo.func" | jq 'select(.type == "observation" and .duration_ms > 10)'

# 统计成功率
peeka-cli watch "demo.func" | \
  jq -r 'select(.type == "observation") | if .success then "OK" else "ERROR" end' | \
  uniq -c

# 计算平均执行时间
peeka-cli watch "demo.func" --times 100 | \
  jq 'select(.type == "observation") | .duration_ms' | \
  awk '{sum+=$1; count++} END {print "avg:", sum/count, "ms"}'
```

#### 保存到文件

```bash
# 保存观测数据
peeka-cli watch "demo.func" --times 1000 > observations.jsonl

# 后续分析
cat observations.jsonl | jq 'select(.type == "observation" and .success == false)'
```

---

## 使用 TUI 界面

Peeka 提供了一个基于 Textual 的交互式 TUI 界面。

### 启动 TUI

```bash
peeka
```

### TUI 功能

1. **进程选择** - 自动发现并选择目标进程
2. **Dashboard 仪表盘** (`1`) - 实时显示进程信息
3. **Watch 观测视图** (`2`) - 交互式观测函数
4. **Trace 追踪视图** (`3`) - 可视化调用树
5. **Stack 调用栈视图** (`4`) - 调用栈追踪
6. **Monitor 监控视图** (`5`) - 性能监控
7. **Memory 内存视图** (`6`) - 内存分析
8. **Logger 日志视图** (`7`) - 日志管理
9. **Inspect 检查视图** (`8`) - 对象检查
10. **Threads 线程视图** (`9`) - 线程分析
11. **Top 热点视图** (`0`) - 函数性能采样

### TUI 快捷键

| 快捷键 | 功能 |
|-------|------|
| `1` | 切换到 Dashboard 仪表盘 |
| `2` | 切换到 Watch 观测视图 |
| `3` | 切换到 Trace 追踪视图 |
| `4` | 切换到 Stack 调用栈视图 |
| `5` | 切换到 Monitor 监控视图 |
| `6` | 切换到 Memory 内存视图 |
| `7` | 切换到 Logger 日志视图 |
| `8` | 切换到 Inspect 检查视图 |
| `9` | 切换到 Threads 线程视图 |
| `0` | 切换到 Top 热点视图 |
| `?` | 显示帮助 |
| `q` | 退出 |

更多 TUI 使用详情请参阅 [TUI 使用指南]({% link tui.md %})。

---

## 实际应用场景

### 场景 1：诊断慢接口

```bash
# 观测 API 处理函数，找出慢调用
peeka-cli watch "app.api.handle_request" --condition "cost > 1000"

# 追踪慢调用的完整调用链
peeka-cli trace "app.api.handle_request" --condition "cost > 1000" --depth 5
```

### 场景 2：定位异常原因

```bash
# 只观测异常情况
peeka-cli watch "app.service.process" --exception

# 查看异常时的调用栈
peeka-cli stack "app.service.process" --condition "throwExp != None"
```

### 场景 3：监控函数性能

```bash
# 每 10 秒统计一次性能指标
peeka-cli monitor "app.service.critical_func" --interval 10

# 结合 jq 实时告警
peeka-cli monitor "app.service.critical_func" --interval 5 | \
  jq 'select(.type == "observation" and .avg_rt > 100) | "Alert: avg RT = \(.avg_rt)ms"'
```

### 场景 4：验证参数

```bash
# 检查特定参数值的调用
peeka-cli watch "app.service.process" --condition "params[0] == 'debug_value'"

# 查看参数分布
peeka-cli watch "app.service.process" --times 100 | \
  jq 'select(.type == "observation") | .args[0]' | \
  sort | uniq -c
```

---

## 最佳实践

### 1. 使用条件过滤减少噪音

生产环境函数调用频繁，使用条件过滤只观测关键调用：

```bash
# ✅ 推荐：只观测慢调用
peeka-cli watch "func" --condition "cost > 100"

# ❌ 不推荐：观测所有调用（数据量大）
peeka-cli watch "func"
```

### 2. 限制观测次数

避免长时间观测产生过多数据：

```bash
# ✅ 推荐：观测固定次数
peeka-cli watch "func" --times 10

# ❌ 不推荐：无限观测
peeka-cli watch "func"  # 可能产生大量数据
```

### 3. 使用 JSONL 格式便于分析

将观测数据保存为 JSONL，便于后续分析：

```bash
# 收集数据
peeka-cli watch "func" --times 1000 > data.jsonl

# 离线分析
cat data.jsonl | jq 'select(.type == "observation") | {duration_ms, success}' | \
  jq -s 'group_by(.success) | map({success: .[0].success, count: length})'
```

### 4. 分层诊断

从粗到细，逐步定位问题：

```bash
# 1. 先用 monitor 了解整体性能
peeka-cli monitor "app.api.*" --interval 10

# 2. 发现异常后用 watch 观测细节
peeka-cli watch "app.api.slow_func" --condition "cost > 100"

# 3. 用 trace 追踪完整调用链
peeka-cli trace "app.api.slow_func" --depth 5
```

---

## 下一步

- [命令参考]({% link commands/index.md %}) - 了解所有命令的详细用法
- [示例教程]({% link examples.md %}) - 更多实际应用场景
- [架构设计]({% link architecture.md %}) - 了解 Peeka 的设计原理
- [故障排除]({% link troubleshooting.md %}) - 遇到问题时的解决方案
