---
layout: default
title: trace 命令
parent: 命令参考
nav_order: 3
---

# trace 命令
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}


## 简介

`trace` 命令用于追踪 Python 函数的完整调用链和执行耗时，以树形结构展示方法调用的层次关系。这是一个强大的性能分析和问题诊断工具，可以帮助开发者快速定位性能瓶颈和理解代码执行路径。


## TUI 使用

在 TUI 模式下，按 **`3`** 键切换到 **Trace 视图**，提供以下交互式功能：

- **模式输入**：支持函数名自动补全（从目标进程实时获取）
- **参数配置**：可视化配置深度、次数、条件表达式、skip-builtin
- **调用树可视化**：以交互式树形结构展示调用链，可展开/折叠
- **色彩编码耗时**：
  - 🟢 绿色：< 10ms（快速）
  - 🟡 黄色：10-100ms（中速）
  - 🔴 红色：>= 100ms（慢速）
- **快捷操作**：
  - 输入模式后按 Enter 开始追踪
  - 按 Enter 展开/折叠节点
  - 按 `c` 清空追踪记录
  - 按 Delete 删除选中记录

**CLI 等效命令**：下文所有示例使用 CLI 命令演示，TUI 提供了相同功能的图形化界面。

## 使用场景

- **性能瓶颈定位**：通过耗时数据快速找出慢调用
- **调用链路分析**：理解函数内部的调用关系和执行流程
- **代码执行路径追踪**：观察不同条件下的代码执行路径
- **子函数耗时分析**：分析各个子函数的耗时占比
- **递归调用诊断**：追踪递归调用的深度和耗时分布

## 命令格式

```bash
peeka-cli attach <pid>    # 首先附加到目标进程
peeka-cli trace <pattern> [options]
```

### 参数说明

| 参数                    | 说明                    | 默认值     | 示例                                      |
|-----------------------|-----------------------|---------|-----------------------------------------|
| `pattern`             | 函数匹配模式                | -       | `module.Class.method`                   |
| `-d, --depth`         | 追踪深度（最大调用层数）          | `3`     | `-d 5`                                  |
| `-n, --times`         | 观测次数（-1 表示无限）         | `-1`    | `-n 10`                                 |
| `--condition` | 条件表达式（支持 `cost` 变量）   | 无       | `--condition "cost > 50"`       |
| `--skip-builtin`      | 跳过内置函数和标准库函数          | `true`  | `--skip-builtin=false`                  |
| `--min-duration`      | 最小耗时过滤（毫秒）            | `0`     | `--min-duration 10`                     |

**注意**：
- 追踪深度建议不超过 5 层，深度过大会显著增加性能开销
- `--skip-builtin` 默认启用，以减少输出噪音
- 条件表达式中的 `cost` 变量表示整个调用的总耗时（毫秒）

### 函数匹配模式 (pattern)

支持以下格式：

```python
# 1. 模块级函数
"mymodule.my_function"

# 2. 类方法
"mymodule.MyClass.my_method"

# 3. 嵌套类方法
"mypackage.mymodule.OuterClass.InnerClass.method"

# 4. 模块路径
"package.subpackage.module.function"
```

**注意**：必须使用完整的模块路径（从导入根开始），当前版本不支持通配符匹配。

## 基本用法

### 1. 追踪函数调用链

```bash
# 首先附加到目标进程
peeka-cli attach 12345

# 追踪 5 次调用
peeka-cli trace "calculator.Calculator.calculate" -n 5
```

**输出示例**：

```json
{
  "type": "observation",
  "watch_id": "trace_abc123",
  "timestamp": 1705586200.123,
  "func_name": "calculator.Calculator.calculate",
  "location": "AtExit",
  "call_tree": [
    {
      "depth": 0,
      "function": "calculator.Calculator.calculate",
      "filename": "/app/calculator.py",
      "lineno": 42,
      "duration_ms": 125.3,
      "children": [
        {
          "depth": 1,
          "function": "calculator.Calculator._validate",
          "filename": "/app/calculator.py",
          "lineno": 18,
          "duration_ms": 2.1
        },
        {
          "depth": 1,
          "function": "calculator.Calculator._compute",
          "filename": "/app/calculator.py",
          "lineno": 25,
          "duration_ms": 98.2,
          "children": [
            {
              "depth": 2,
              "function": "math.sqrt",
              "duration_ms": 95.1
            }
          ]
        },
        {
          "depth": 1,
          "function": "calculator.Logger.info",
          "filename": "/app/logger.py",
          "lineno": 10,
          "duration_ms": 15.7
        }
      ]
    }
  ],
  "total_duration_ms": 125.3,
  "node_count": 5
}
```

**字段说明**：

| 字段                 | 说明           | 示例值                       |
|--------------------|--------------|---------------------------|
| `watch_id`         | 观测 ID        | `"trace_abc123"`          |
| `timestamp`        | 时间戳          | `1705586200.123`          |
| `func_name`        | 目标函数名        | `"calculator.calculate"`  |
| `location`         | 观测位置         | `"AtExit"`                |
| `call_tree`        | 调用树（嵌套结构）    | `[...]`                   |
| `total_duration_ms`| 总执行耗时（毫秒）    | `125.3`                   |
| `node_count`       | 调用节点总数       | `5`                       |

**调用树节点字段**：

| 字段            | 说明         | 示例值                    |
|---------------|------------|------------------------|
| `depth`       | 调用深度（从 0 开始）| `0`, `1`, `2`          |
| `function`    | 函数完整名称     | `"module.Class.method"`|
| `filename`    | 文件路径       | `"/app/module.py"`     |
| `lineno`      | 行号         | `42`                   |
| `duration_ms` | 执行耗时（毫秒）   | `10.5`                 |
| `children`    | 子调用列表      | `[...]`                |

### 2. 树形文本输出（TUI）

在 TUI 模式下，调用树以可视化的树形结构展示：

```
`---[125.3ms] calculator.Calculator.calculate()
    +---[2.1ms] calculator.Calculator._validate()
    +---[98.2ms] calculator.Calculator._compute()
    |   `---[95.1ms] math.sqrt()
    `---[15.7ms] calculator.Logger.info()
```

**说明**：
- `---` 表示最后一个子节点
- `+---` 表示中间子节点
- `|` 表示父节点有后续兄弟节点的连接线
- `[Xms]` 显示函数执行耗时

### 3. 调整追踪深度

```bash
# 深度为 1：只追踪直接调用
peeka-cli trace "service.process" -d 1

# 深度为 5：追踪 5 层调用
peeka-cli trace "service.process" -d 5
```

**深度对比示例**：

```python
# 原始调用链
process() → validate() → check_type() → isinstance()
  ├── query_db() → execute() → connect()
  └── format_result() → json.dumps()

# depth=1
process() → validate()
          → query_db()
          → format_result()

# depth=2
process() → validate() → check_type()
          → query_db() → execute()
          → format_result() → json.dumps()

# depth=3（默认）
process() → validate() → check_type() → isinstance()
          → query_db() → execute() → connect()
          → format_result() → json.dumps()
```

### 4. 条件过滤

```bash
# 只追踪耗时超过 50ms 的调用
peeka-cli trace "api.handler" --condition "cost > 50"

# 组合参数和耗时条件
peeka-cli trace "service.query" --condition "cost > 100 and params[0] > 1000"
```

### 5. 跳过内置函数

```bash
# 默认行为：跳过内置函数（减少输出噪音）
peeka-cli trace "mymodule.func"

# 显示所有调用（包括内置函数）
peeka-cli trace "mymodule.func" --skip-builtin=false
```

**内置函数示例**：
- Python 内置函数：`len()`, `str()`, `isinstance()`, `print()`
- 标准库函数：`json.dumps()`, `os.path.join()`, `datetime.now()`

## 实现技术

### 实现原理

Peeka 的 `trace` 命令根据 Python 版本自动选择最优实现方案：

| Python 版本 | 实现方案            | 性能开销  | 说明                |
|-----------|-----------------|-------|-------------------|
| 3.12+     | sys.monitoring  | < 5%  | 官方 PEP 669 API，最优性能         |
| 3.9-3.11  | sys.settrace | < 20% | 兼容性好，自动启用         |

**sys.monitoring 实现 (Python 3.12+)**:

- 基于 [PEP 669](https://peps.python.org/pep-0669/) 的官方监控 API
- 使用 `PY_START` 和 `PY_RETURN` 事件捕获调用
- 性能开销 < 5%，推荐生产环境使用
- 自动分配 tool_id，多个观测不冲突

**sys.settrace 实现 (Python 3.9-3.11)**:

- 使用 Python 内置的 `sys.settrace()` 机制
- 仅在目标函数执行期间启用（局部 trace）
- 性能开销 < 20%，完全可用于大多数场景

**skip-builtin 过滤机制**:

- 检查 `code.co_filename.startswith('<')` 过滤内置函数（如 `<built-in>`）
- 检查 Python 标准库路径，过滤标准库函数
- 默认启用，可减少 50% 以上的输出节点

## 性能影响

### 性能开销

| 场景                  | 开销    | 说明            |
|---------------------|-------|---------------|
| **简单函数**            | < 5%  | Python 3.12+  |
| **简单函数**            | < 20% | Python 3.9-3.11 |
| **复杂调用树（深度 5）**    | 10-30%| 根据 Python 版本  |
| **高频调用（>1000 QPS）** | 20-50%| 建议限制观测次数      |

**说明**：
- Python 3.12+ 使用 `sys.monitoring`，性能开销显著降低
- 深度越深，性能开销越大
- 建议生产环境使用条件过滤和次数限制

### 性能优化建议

1. **限制追踪深度**
   ```bash
   # 只追踪 3 层调用
   peeka-cli trace "func" -d 3
   ```

2. **跳过内置函数**
   ```bash
   # 默认启用，减少 50% 以上的节点
   peeka-cli trace "func" --skip-builtin
   ```

3. **使用条件过滤**
   ```bash
   # 只追踪慢调用
   peeka-cli trace "func" --condition "cost > 100"
   ```

4. **限制观测次数**
   ```bash
   # 只观测 10 次
   peeka-cli trace "func" -n 10
   ```

5. **最小耗时过滤**
   ```bash
   # 只记录耗时 > 10ms 的子调用
   peeka-cli trace "func" --min-duration 10
   ```

## 使用示例

### 1. 定位性能瓶颈

```bash
# 追踪慢接口，找出耗时最长的子调用
peeka-cli trace "api.handler.process_request" --condition "cost > 100"
```

**输出**：
```
`---[1250ms] api.handler.process_request()
    +---[10ms] api.validator.check_params()
    +---[1200ms] database.query.execute()  ← 瓶颈在这里！
    |   +---[50ms] database.connection.connect()
    |   `---[1150ms] database.cursor.fetch_all()
    `---[20ms] api.formatter.to_json()
```

**结论**：数据库查询占用了 96% 的时间，需要优化 SQL 或添加索引。

### 2. 分析递归调用

```bash
# 追踪递归函数的执行深度和耗时
peeka-cli trace "algorithm.factorial" -d 10
```

**输出**：
```
`---[5.2ms] algorithm.factorial(n=5)
    `---[4.1ms] algorithm.factorial(n=4)
        `---[3.0ms] algorithm.factorial(n=3)
            `---[2.0ms] algorithm.factorial(n=2)
                `---[1.0ms] algorithm.factorial(n=1)
                    `---[0.1ms] algorithm.factorial(n=0)
```

### 3. 理解代码执行路径

```bash
# 追踪条件分支的执行路径
peeka-cli trace "service.business_logic" -n 1
```

**场景 A（正常流程）**：
```
`---[50ms] service.business_logic()
    +---[5ms] service.validate_input()
    +---[30ms] service.process_data()
    `---[10ms] service.save_result()
```

**场景 B（异常流程）**：
```
`---[20ms] service.business_logic()
    +---[5ms] service.validate_input()
    +---[10ms] service.handle_invalid_input()
    `---[3ms] service.log_error()
```

### 4. 对比优化前后性能

```bash
# 优化前
peeka-cli trace "converter.parse_json" -n 10 > before.jsonl

# 优化后
peeka-cli trace "converter.parse_json" -n 10 > after.jsonl

# 分析耗时变化
jq '.total_duration_ms' before.jsonl | awk '{sum+=$1; count++} END {print "Before:", sum/count, "ms"}'
jq '.total_duration_ms' after.jsonl | awk '{sum+=$1; count++} END {print "After:", sum/count, "ms"}'
```

### 5. 集成到 CI/CD

```bash
# 性能回归测试
#!/bin/bash
THRESHOLD=100  # 最大允许耗时 100ms

peeka-cli attach $PID
RESULT=$(peeka-cli trace "critical.function" -n 50 | \
  jq -s 'map(select(.type == "observation")) | map(.total_duration_ms) | add / length')

if (( $(echo "$RESULT > $THRESHOLD" | bc -l) )); then
  echo "Performance regression detected: ${RESULT}ms > ${THRESHOLD}ms"
  exit 1
fi
```

## 数据处理与分析

### 使用 jq 处理 JSON

```bash
# 1. 提取调用树
peeka-cli trace "func" | jq '.call_tree'

# 2. 计算平均耗时
peeka-cli trace "func" -n 100 | jq '.total_duration_ms' | \
  awk '{sum+=$1; count++} END {print "avg:", sum/count, "ms"}'

# 3. 找出最慢的子调用
peeka-cli trace "func" | jq '.call_tree | .. | objects | select(.duration_ms != null) | {function, duration_ms}' | \
  jq -s 'sort_by(.duration_ms) | reverse | .[0]'

# 4. 统计调用频次
peeka-cli trace "func" -n 100 | jq '.call_tree | .. | objects | select(.function != null) | .function' | \
  sort | uniq -c | sort -rn

# 5. 生成火焰图数据
peeka-cli trace "func" -n 1000 | jq -r '.call_tree | .. | objects | select(.function != null) | "\(.function) \(.duration_ms)"' > flamegraph.txt
```

### Python 数据分析

```python
import json
import sys
from collections import defaultdict

# 统计子调用的总耗时和次数
stats = defaultdict(lambda: {"count": 0, "total_ms": 0})

for line in sys.stdin:
    data = json.loads(line)
    if data["type"] == "observation":
        def traverse(node):
            if "function" in node:
                stats[node["function"]]["count"] += 1
                stats[node["function"]]["total_ms"] += node.get("duration_ms", 0)

            for child in node.get("children", []):
                traverse(child)

        for root in data["call_tree"]:
            traverse(root)

# 按总耗时排序
sorted_stats = sorted(stats.items(), key=lambda x: x[1]["total_ms"], reverse=True)

print("Top 10 Time-Consuming Functions:")
print(f"{'Function':<60} {'Count':>10} {'Total (ms)':>15} {'Avg (ms)':>12}")
print("-" * 100)

for func, stat in sorted_stats[:10]:
    avg_ms = stat["total_ms"] / stat["count"]
    print(f"{func:<60} {stat['count']:>10} {stat['total_ms']:>15.2f} {avg_ms:>12.2f}")
```

**运行**：
```bash
peeka-cli trace "module.func" -n 100 | python analyze_trace.py
```

**输出**：
```
Top 10 Time-Consuming Functions:
Function                                                      Count     Total (ms)      Avg (ms)
----------------------------------------------------------------------------------------------------
database.query.execute                                          100       12500.00       125.00
api.handler.process_request                                     100       15000.00       150.00
json.dumps                                                      500        1000.00         2.00
...
```

## 常见问题

### 1. 追踪深度不够

**问题**：调用树只显示 3 层，但实际有更多层级

**解决方案**：

```bash
# 增加深度限制
peeka-cli trace "module.func" -d 10

# 注意：深度过大会增加性能开销
```

### 2. 输出数据过多

**问题**：包含大量内置函数调用，输出难以阅读

**解决方案**：

```bash
# 跳过内置函数（默认启用）
peeka-cli trace "module.func" --skip-builtin

# 只记录耗时 > 10ms 的调用
peeka-cli trace "module.func" --min-duration 10

# 使用条件过滤
peeka-cli trace "module.func" --condition "cost > 50"
```

### 3. 性能开销过大

**问题**：启用 trace 后应用响应变慢

**解决方案**：

```bash
# 1. 减少追踪深度
peeka-cli trace "module.func" -d 2

# 2. 限制观测次数
peeka-cli trace "module.func" -n 10

# 3. 使用条件过滤，只追踪慢调用
peeka-cli trace "module.func" --condition "cost > 100"

# 4. 考虑升级到 Python 3.12+ 获得更好性能
```

### 4. 无法观测到数据

**可能原因**：
- 函数没有被调用
- 函数名拼写错误
- 条件表达式过于严格
- 已达到观测次数限制（-n 参数）

**排查步骤**：

```bash
# 1. 确认函数名是否正确
python3 -c "import mymodule; print(mymodule.MyClass.my_method)"

# 2. 去掉条件表达式，先观测一次
peeka-cli trace "mymodule.func" -n 1

# 3. 检查进程是否存在
ps aux | grep <pid>
```

## 高级技巧

### 1. 生成火焰图

```bash
# 收集追踪数据
peeka-cli trace "module.func" -n 1000 > trace.jsonl

# 转换为火焰图格式
jq -r '.call_tree | .. | objects | select(.function != null) | "\(.function);\(.duration_ms)"' trace.jsonl \
  > folded.txt

# 生成火焰图（需要安装 flamegraph.pl）
flamegraph.pl folded.txt > flamegraph.svg
```

### 2. 对比多个版本的性能

```bash
# 版本 A
git checkout v1.0
peeka-cli trace "module.func" -n 100 > trace_v1.jsonl

# 版本 B
git checkout v2.0
peeka-cli trace "module.func" -n 100 > trace_v2.jsonl

# 对比平均耗时
echo "v1.0: $(jq -s 'map(.total_duration_ms) | add / length' trace_v1.jsonl) ms"
echo "v2.0: $(jq -s 'map(.total_duration_ms) | add / length' trace_v2.jsonl) ms"
```

### 3. 自动化性能监控

```python
#!/usr/bin/env python3
"""性能回归监控脚本"""
import json
import subprocess
import time

THRESHOLD = 100  # 最大允许耗时 (ms)
CHECK_INTERVAL = 3600  # 检查间隔 (秒)

def check_performance(pid, pattern):
    cmd = ["peeka-cli", "trace", pattern, "-n", "50"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)

    durations = []
    for line in proc.stdout:
        data = json.loads(line)
        if data["type"] == "observation":
            durations.append(data["total_duration_ms"])

    avg_duration = sum(durations) / len(durations) if durations else 0

    if avg_duration > THRESHOLD:
        send_alert(f"Performance regression: {avg_duration:.2f}ms > {THRESHOLD}ms")

    return avg_duration

def send_alert(message):
    # 发送告警（邮件、Slack、钉钉等）
    print(f"ALERT: {message}")

if __name__ == "__main__":
    pid = int(sys.argv[1])
    pattern = sys.argv[2]

    while True:
        duration = check_performance(pid, pattern)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Avg duration: {duration:.2f}ms")
        time.sleep(CHECK_INTERVAL)
```

### 4. 集成到 Prometheus

```python
from prometheus_client import Histogram, start_http_server
import json
import subprocess

# 定义指标
trace_duration = Histogram('trace_duration_ms', 'Function trace duration', ['function'])

# 启动 Prometheus 服务器
start_http_server(8000)

# 收集追踪数据
proc = subprocess.Popen(
    ["peeka-cli", "trace", "module.func"],
    stdout=subprocess.PIPE,
    text=True
)

for line in proc.stdout:
    data = json.loads(line)
    if data["type"] == "observation":
        # 递归处理调用树
        def record_metrics(node):
            if "function" in node and "duration_ms" in node:
                trace_duration.labels(function=node["function"]).observe(node["duration_ms"])
            for child in node.get("children", []):
                record_metrics(child)

        for root in data["call_tree"]:
            record_metrics(root)
```

## 参考资料

- [PEP 669: Low Impact Monitoring for CPython](https://peps.python.org/pep-0669/)
- [Peeka 架构设计](../ARCHITECTURE.md)

## 更新日志

| 版本    | 日期      | 更新内容          |
|-------|---------|---------------|
| 0.2.0 | 2026-02 | 添加 trace 命令文档 |
| 0.1.0 | 2025-01 | 初始版本          |


