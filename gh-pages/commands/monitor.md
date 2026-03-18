---
layout: default
title: Peeka Monitor 命令详解
parent: 命令参考
nav_order: 5
---

# Peeka Monitor 命令详解
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 命令简介

`monitor` 命令用于定期收集和输出函数的性能统计数据，包括调用次数、成功/失败率、响应时间等关键指标。这是一个轻量级的性能监控工具，适合生产环境长期运行。

**核心功能**：
- 定期输出函数性能统计（默认每 60 秒）
- 统计调用次数、成功/失败率
- 统计响应时间（平均、最小、最大）
- 轻量级设计（不记录详细观测数据，仅统计）
- 支持多个函数同时监控
- 可配置监控周期和持续时间

**与 watch 命令的区别**：
- `watch`：记录**每次调用的详细信息**（参数、返回值、调用栈等）
- `monitor`：只记录**统计数据**（调用次数、响应时间等），输出周期性汇总

## TUI 使用

在 TUI 模式下，按 **`5`** 键切换到 **Monitor 视图**，提供以下交互式功能：

- **模式输入**：支持函数名自动补全（从目标进程实时获取）
- **参数配置**：可视化配置输出间隔、监控周期数
- **统计数据展示**：实时展示性能统计指标
  - 调用次数（total）、成功次数（success）、失败次数（fail）
  - 失败率（fail_rate）、响应时间（avg/min/max）
  - 周期计数器（cycle）和间隔时间（interval）
- **快捷操作**：
  - 输入模式后按 Enter 开始监控
  - 按 `s` 停止监控
  - 按 `c` 清空统计数据

**CLI 等效命令**：下文所有示例使用 CLI 命令演示，TUI 提供了相同功能的图形化界面。
---

## 使用场景

### 1. 生产环境性能监控

**场景**：长期监控关键函数的性能指标，及时发现性能劣化。

```bash
# 每 60 秒输出一次统计数据，持续运行
peeka-cli monitor "myapp.api.handle_request" --interval 60
```

**输出示例**：
```json
{
  "watch_id": "monitor_a1b2c3d4",
  "cycle": 1,
  "total": 1234,
  "success": 1200,
  "fail": 34,
  "fail_rate": 0.0275,
  "rt_avg": 45.678,
  "rt_min": 5.123,
  "rt_max": 234.567
}
```

**解读**：
- 1 分钟内共调用 1234 次
- 成功 1200 次，失败 34 次（失败率 2.75%）
- 平均响应时间 45.678 毫秒
- 最快 5.123 毫秒，最慢 234.567 毫秒

### 2. 服务健康检查

**场景**：监控服务核心函数的失败率，超过阈值时告警。

```bash
# 每 30 秒输出一次，持续 10 次（5 分钟）
peeka-cli monitor "myapp.payment.process" \
  --interval 30 -c 10 | \
  jq -r 'select(.fail_rate > 0.05) | "ALERT: Fail rate \(.fail_rate*100)%"'
```

**效果**：失败率超过 5% 时输出告警信息。

### 3. 性能基线建立

**场景**：在正常负载下建立性能基线，用于后续性能对比。

```bash
# 监控 1 小时（60 次，每分钟一次）
peeka-cli monitor "myapp.db.execute_query" \
  --interval 60 -c 60 > baseline.jsonl

# 分析数据
jq -s '{
  avg_rt: (map(.rt_avg) | add / length),
  avg_total: (map(.total) | add / length),
  max_fail_rate: (map(.fail_rate) | max)
}' baseline.jsonl
```

**输出**：
```json
{
  "avg_rt": 12.345,
  "avg_total": 567,
  "max_fail_rate": 0.0123
}
```

### 4. 多函数对比监控

**场景**：同时监控多个函数，对比性能差异。

```bash
# 终端 1：监控 API v1
peeka-cli monitor "myapp.api.v1.handler" --interval 30 > api_v1.jsonl

# 终端 2：监控 API v2
peeka-cli monitor "myapp.api.v2.handler" --interval 30 > api_v2.jsonl

# 终端 3：实时对比
while true; do
  v1=$(tail -1 api_v1.jsonl | jq -r '.rt_avg')
  v2=$(tail -1 api_v2.jsonl | jq -r '.rt_avg')
  echo "v1: ${v1}ms, v2: ${v2}ms"
  sleep 30
done
```

### 5. 负载测试期间监控

**场景**：负载测试时实时监控函数性能，观察系统表现。

```bash
# 监控核心函数，每 10 秒输出一次
peeka-cli monitor "myapp.process" --interval 10 | \
  jq -r '"\(.cycle): \(.total) calls, \(.rt_avg)ms avg, \(.fail_rate*100)% fail"'
```

**输出**：
```
1: 123 calls, 45.67ms avg, 1.2% fail
2: 234 calls, 67.89ms avg, 2.3% fail
3: 345 calls, 89.01ms avg, 3.4% fail
...
```

---

## 命令格式

```bash
# 必须先附加到目标进程
peeka-cli attach <pid>

# 然后执行 monitor 命令
peeka-cli monitor <pattern> [options]
```

**必需参数**：
- `pattern`：目标函数的模式（如 `module.Class.method`）

**可选参数**：
- `--interval`：输出间隔（秒，默认 60）
- `-c, --cycles`：监控周期数（-1 表示无限，默认 -1）

---

## 参数说明

### pattern - 函数模式

指定要监控的目标函数，格式与 `watch` 命令相同。

| 格式 | 说明 | 示例 |
|------|------|------|
| `module.function` | 模块级函数 | `myapp.utils.calculate` |
| `module.Class.method` | 类方法 | `myapp.models.User.save` |
| `module.Class.static_method` | 静态方法 | `myapp.utils.Helper.validate` |

**注意事项**：
- 必须使用完整限定名（从模块根开始）
- 不支持通配符
- 目标函数必须已被加载到内存中

### --interval - 输出间隔

控制统计数据的输出频率（单位：秒）。

| 值 | 说明 | 适用场景 |
|----|------|----------|
| `10` | 每 10 秒输出一次 | 负载测试、实时监控 |
| `30` | 每 30 秒输出一次 | 高频监控 |
| `60`（默认）| 每 60 秒输出一次 | 生产环境常规监控 |
| `300` | 每 5 分钟输出一次 | 长期趋势分析 |

**示例**：
```bash
# 高频监控（每 10 秒）
peeka-cli monitor "myapp.api.handler" --interval 10

# 长期监控（每 5 分钟）
peeka-cli monitor "myapp.batch.process" --interval 300
```

**注意**：
- 间隔越短，输出数据越频繁（建议根据函数调用频率设置）
- 间隔太短可能导致单个周期内调用次数过少，统计意义不大
- 间隔太长可能错过重要的性能变化

### -c, --cycles - 监控周期数

控制监控持续的周期数。

| 值 | 说明 | 适用场景 |
|----|------|----------|
| `-1`（默认）| 无限监控 | 生产环境持续监控 |
| `1` | 监控 1 个周期后停止 | 快速查看当前状态 |
| `10` | 监控 10 个周期后停止 | 固定时长监控 |
| `60` | 监控 60 个周期后停止 | 1 小时监控（interval=60） |

**示例**：
```bash
# 监控 1 次后停止（查看当前 1 分钟的统计）
peeka-cli monitor "myapp.func" --interval 60 -c 1

# 监控 10 分钟（10 次，每次 1 分钟）
peeka-cli monitor "myapp.func" --interval 60 -c 10

# 持续监控（直到手动停止）
peeka-cli monitor "myapp.func" --interval 60
```

**计算总时长**：
- 总时长 = `interval` × `cycles`
- 例如：`--interval 60 -c 10` = 10 分钟
- 例如：`--interval 30 -c 120` = 1 小时

---

## 统计指标说明

### 基础指标

| 指标 | 类型 | 说明 |
|------|------|------|
| `total` | int | 当前周期内的总调用次数 |
| `success` | int | 成功调用次数（未抛出异常） |
| `fail` | int | 失败调用次数（抛出异常） |

### 派生指标

| 指标 | 类型 | 计算公式 | 说明 |
|------|------|----------|------|
| `fail_rate` | float | `fail / total` | 失败率（0-1 之间，保留 4 位小数） |
| `rt_avg` | float | `sum(duration) / total` | 平均响应时间（毫秒，保留 3 位小数） |
| `rt_min` | float | `min(duration)` | 最小响应时间（毫秒，保留 3 位小数） |
| `rt_max` | float | `max(duration)` | 最大响应时间（毫秒，保留 3 位小数） |

### 元数据

| 字段 | 类型 | 说明 |
|------|------|------|
| `watch_id` | string | 监控任务的唯一标识符 |
| `cycle` | int | 当前周期编号（从 1 开始） |

---

## 输出格式

`monitor` 命令输出 JSON Lines 格式（每个周期一行），便于流式处理。

### 完整输出示例

```json
{
  "watch_id": "monitor_a1b2c3d4",
  "cycle": 1,
  "total": 1234,
  "success": 1200,
  "fail": 34,
  "fail_rate": 0.0275,
  "rt_avg": 45.678,
  "rt_min": 5.123,
  "rt_max": 234.567
}
```

### 字段说明

| 字段 | 类型 | 说明 | 示例 |
|------|------|------|------|
| `watch_id` | string | 监控任务的唯一标识符 | `"monitor_a1b2c3d4"` |
| `cycle` | int | 周期编号（从 1 开始） | `1`, `2`, `3`... |
| `total` | int | 当前周期总调用次数 | `1234` |
| `success` | int | 成功调用次数 | `1200` |
| `fail` | int | 失败调用次数 | `34` |
| `fail_rate` | float | 失败率（0-1） | `0.0275`（2.75%） |
| `rt_avg` | float | 平均响应时间（毫秒） | `45.678` |
| `rt_min` | float | 最小响应时间（毫秒） | `5.123` |
| `rt_max` | float | 最大响应时间（毫秒） | `234.567` |

### 统计周期说明

**重要**：每个周期的统计数据是**累积的**（从监控开始到当前时刻）。

```json
// 周期 1（0-60 秒）
{"cycle": 1, "total": 100, "rt_avg": 50}

// 周期 2（0-120 秒，累积）
{"cycle": 2, "total": 250, "rt_avg": 55}

// 周期 3（0-180 秒，累积）
{"cycle": 3, "total": 400, "rt_avg": 53}
```

**如需计算单个周期的数据**：
```bash
# 计算周期 2 的新增调用次数
total_cycle2 - total_cycle1 = 250 - 100 = 150
```

---

## 使用示例

### 示例 1：基本监控

**场景**：监控 API 入口函数，每分钟输出一次统计。

```bash
peeka-cli monitor "myapp.api.handle_request" --interval 60
```

**输出**：
```json
{"watch_id":"monitor_a1b2c3d4","cycle":1,"total":1234,"success":1200,"fail":34,"fail_rate":0.0275,"rt_avg":45.678,"rt_min":5.123,"rt_max":234.567}
{"watch_id":"monitor_a1b2c3d4","cycle":2,"total":2456,"success":2400,"fail":56,"fail_rate":0.0228,"rt_avg":48.123,"rt_min":5.123,"rt_max":345.678}
{"watch_id":"monitor_a1b2c3d4","cycle":3,"total":3678,"success":3600,"fail":78,"fail_rate":0.0212,"rt_avg":46.890,"rt_min":5.123,"rt_max":345.678}
...
```

### 示例 2：固定时长监控

**场景**：监控 5 分钟（5 次，每次 1 分钟）。

```bash
peeka-cli monitor "myapp.payment.charge" --interval 60 -c 5
```

**行为**：
- 输出 5 次统计数据
- 第 5 次输出后自动停止
- 总监控时长：5 分钟

### 示例 3：实时监控（高频）

**场景**：负载测试期间实时监控，每 10 秒输出一次。

```bash
peeka-cli monitor "myapp.process" --interval 10 | \
  jq -r '"\(.cycle): \(.total) calls, \(.rt_avg)ms avg, \(.fail) fails"'
```

**输出**：
```
1: 123 calls, 45.67ms avg, 2 fails
2: 278 calls, 52.34ms avg, 5 fails
3: 456 calls, 58.90ms avg, 8 fails
...
```

### 示例 4：失败率告警

**场景**：监控失败率，超过 5% 时发出告警。

```bash
peeka-cli monitor "myapp.critical_func" --interval 30 | \
  jq -r 'if .fail_rate > 0.05 then
           "⚠️  ALERT: Fail rate \(.fail_rate * 100)% at cycle \(.cycle)"
         else
           "✅  Healthy: \(.fail_rate * 100)% fail rate"
         end'
```

**输出**：
```
✅  Healthy: 1.2% fail rate
✅  Healthy: 2.3% fail rate
⚠️  ALERT: Fail rate 6.7% at cycle 3
```

### 示例 5：响应时间趋势

**场景**：监控响应时间变化，绘制趋势图。

```bash
# 监控 30 分钟（30 次，每次 1 分钟）
peeka-cli monitor "myapp.db.query" --interval 60 -c 30 | \
  jq -r '"\(.cycle) \(.rt_avg)"' > rt_trend.dat

# 使用 gnuplot 绘制趋势图（需要安装 gnuplot）
gnuplot <<EOF
set terminal png size 800,600
set output 'rt_trend.png'
set xlabel 'Cycle'
set ylabel 'Response Time (ms)'
set title 'Response Time Trend'
plot 'rt_trend.dat' with lines
EOF
```

### 示例 6：与 watch 命令结合

**场景**：先用 `monitor` 发现性能问题，再用 `watch` 深入排查。

```bash
# 步骤 1：启动监控，发现响应时间异常
peeka-cli monitor "myapp.process" --interval 60 | \
  jq -r 'select(.rt_avg > 100)'
# 输出：{"cycle": 5, "rt_avg": 234.567, ...}

# 步骤 2：使用 watch 查看详细调用信息
peeka-cli watch "myapp.process" -n 10
# 分析参数、返回值、执行时间

# 步骤 3：定位问题后停止监控
# （Ctrl+C 或使用 cycles 参数）
```

---

## 完整监控流程

### 流程 1：生产环境性能基线建立

**目标**：建立正常负载下的性能基线，用于后续性能对比。

```bash
# 步骤 1：监控核心函数 1 小时
peeka-cli monitor "myapp.api.handle_request" \
  --interval 60 -c 60 > baseline_$(date +%Y%m%d).jsonl

# 步骤 2：计算基线统计
jq -s '{
  avg_total: (map(.total) | add / length),
  avg_rt: (map(.rt_avg) | add / length),
  p50_rt: (map(.rt_avg) | sort)[30],
  p95_rt: (map(.rt_avg) | sort)[57],
  max_fail_rate: (map(.fail_rate) | max)
}' baseline_$(date +%Y%m%d).jsonl > baseline_summary.json

# 步骤 3：查看基线
cat baseline_summary.json
```

**输出**：
```json
{
  "avg_total": 567.8,
  "avg_rt": 45.678,
  "p50_rt": 44.123,
  "p95_rt": 67.890,
  "max_fail_rate": 0.0123
}
```

### 流程 2：性能劣化检测

**目标**：对比当前性能与基线，检测性能劣化。

```bash
# 步骤 1：加载基线数据
baseline_rt=$(jq -r '.avg_rt' baseline_summary.json)
echo "Baseline avg RT: ${baseline_rt}ms"

# 步骤 2：实时监控并对比
peeka-cli monitor "myapp.api.handle_request" --interval 60 | \
  jq -r --arg baseline "$baseline_rt" '
    if .rt_avg > ($baseline | tonumber * 1.5) then
      "⚠️  DEGRADATION: \(.rt_avg)ms (baseline: \($baseline)ms)"
    else
      "✅  Normal: \(.rt_avg)ms"
    end
  '
```

**输出**：
```
✅  Normal: 47.123ms
✅  Normal: 48.567ms
⚠️  DEGRADATION: 89.012ms (baseline: 45.678ms)
```

### 流程 3：多函数性能对比

**目标**：对比不同实现的性能差异（如 API v1 vs v2）。

```bash
# 步骤 1：同时监控两个函数
peeka-cli monitor "myapp.api.v1.handler" --interval 30 > v1.jsonl &
peeka-cli monitor "myapp.api.v2.handler" --interval 30 > v2.jsonl &

# 步骤 2：等待收集数据（10 分钟）
sleep 600

# 步骤 3：停止监控
kill %1 %2

# 步骤 4：对比分析
echo "API v1:"
jq -s 'map(.rt_avg) | add / length' v1.jsonl
echo "API v2:"
jq -s 'map(.rt_avg) | add / length' v2.jsonl
```

**输出**：
```
API v1:
67.890
API v2:
45.123
```

**结论**：v2 性能优于 v1（平均快 33%）。

### 流程 4：负载测试监控

**目标**：负载测试期间监控系统性能，观察性能曲线。

```bash
# 步骤 1：启动监控（高频，每 10 秒）
peeka-cli monitor "myapp.process" --interval 10 > load_test.jsonl &

# 步骤 2：启动负载测试（另一个终端）
# ab -n 10000 -c 100 http://localhost:8000/api/endpoint

# 步骤 3：实时观察性能指标
tail -f load_test.jsonl | \
  jq -r '"\(.cycle): \(.total) calls, \(.rt_avg)ms avg, \(.fail_rate*100)% fail"'

# 步骤 4：测试结束后停止监控
kill %1

# 步骤 5：分析性能曲线
jq -r '"\(.cycle) \(.total) \(.rt_avg) \(.fail_rate)"' load_test.jsonl > metrics.dat
```

---

## 注意事项

### 1. 性能影响

**影响程度**：
- **统计记录**：每次调用约 0.1-0.2ms 额外开销
- **统计计算**：每个周期约 0.01ms（可忽略）
- **JSON 输出**：每个周期约 0.1ms（可忽略）

**总体开销**：约 0.1-0.2ms/次（比 `watch` 命令轻量 10 倍）

**优势**：
- 不记录详细数据，内存占用极小
- 适合长期运行，性能影响可忽略
- 适合高频函数监控

### 2. 统计数据是累积的

**重要**：`monitor` 的统计数据是**累积的**，不是单周期的。

```json
// 周期 1：累积 0-60 秒
{"cycle": 1, "total": 100}

// 周期 2：累积 0-120 秒（不是第 2 个 60 秒）
{"cycle": 2, "total": 250}
```

**计算单周期数据**：
```bash
# 提取单周期调用次数
jq -s '[.[0].total] + [range(1; length) | 
  {cycle: .[.].cycle, calls: .[.].total - .[-1].total}]' monitor.jsonl
```

### 3. 响应时间统计

**rt_avg 的计算方式**：
- 累积平均：`sum(所有调用的duration) / total`
- 不是加权移动平均
- 不是单周期平均

**示例**：
```json
// 周期 1：100 次调用，平均 50ms
{"cycle": 1, "total": 100, "rt_avg": 50}

// 周期 2：新增 100 次调用，平均 60ms
// 累积平均 = (100*50 + 100*60) / 200 = 55ms
{"cycle": 2, "total": 200, "rt_avg": 55}
```

### 4. 失败的定义

**fail 计数规则**：
- 函数抛出异常 → `fail` +1
- 函数正常返回 → `success` +1
- 即使返回 `None` 或错误码，只要不抛异常，就算 `success`

**注意**：
- 如果应用使用错误码而非异常，`fail` 计数可能为 0
- 建议结合业务逻辑分析 `success` 的真实性

### 5. 停止监控

**方法 1**：使用 `-c` 参数限制周期数（自动停止）
```bash
peeka-cli monitor "myapp.func" --interval 60 -c 10
```

**方法 2**：手动 Ctrl+C（不影响目标进程）
```bash
peeka-cli monitor "myapp.func" --interval 60
# 按 Ctrl+C 停止
```

**重要**：
- 停止监控后，目标函数恢复原样（无性能影响）
- 统计数据不会持久化（需要手动保存输出）
- 多个监控任务相互独立

### 6. 多个监控任务

**支持**：可以同时启动多个 `monitor` 任务监控不同函数。

```bash
# 终端 1：监控 API
peeka-cli monitor "myapp.api.handler" --interval 60

# 终端 2：监控数据库
peeka-cli monitor "myapp.db.query" --interval 60

# 终端 3：监控缓存
peeka-cli monitor "myapp.cache.get" --interval 60
```

**注意**：
- 每个任务独立统计，不会互相影响
- 监控函数越多，性能开销累加
- 建议监控不超过 10 个函数

---

## 常见问题

### Q1: 如何查看当前有哪些监控任务？

**方法 1**：使用 `status` 动作（如果 CLI 支持）
```bash
peeka-cli reset -l
```

**方法 2**：检查进程是否有对应的客户端连接
```bash
ps aux | grep "peeka-cli monitor" | grep 12345
```

**方法 3**：查看目标进程的套接字连接
```bash
lsof -p 12345 | grep peeka
```

### Q2: 如何计算单个周期的调用次数？

**方法**：使用 `jq` 计算相邻周期的差值。

```bash
jq -s '
  [range(0; length)] | map({
    cycle: .[.].cycle,
    calls: (if . == 0 then .[0].total else .[.].total - .[.-1].total end),
    rt_avg: .[.].rt_avg
  })
' monitor.jsonl
```

**输出**：
```json
[
  {"cycle": 1, "calls": 100, "rt_avg": 50},
  {"cycle": 2, "calls": 150, "rt_avg": 55},
  {"cycle": 3, "calls": 200, "rt_avg": 53}
]
```

### Q3: rt_avg 突然下降是什么原因？

**可能原因**：
1. **新调用的响应时间更快**：累积平均被拉低
2. **缓存生效**：后续调用命中缓存
3. **负载降低**：系统资源充足，响应更快

**排查方法**：
```bash
# 查看 rt_min 和 rt_max 的变化
jq -r '"\(.cycle) \(.rt_min) \(.rt_avg) \(.rt_max)"' monitor.jsonl
```

**示例**：
```
1  5.123  50.000  234.567
2  5.123  48.000  234.567  ← rt_avg 下降，但 rt_min/max 不变
3  2.456  35.000  234.567  ← rt_min 下降，说明新调用更快
```

### Q4: 如何监控异步函数？

**答案**：`monitor` 命令支持异步函数（async def）。

```bash
peeka-cli monitor "myapp.async_handler" --interval 60
```

**注意**：
- 统计的是异步函数的**实际执行时间**（不包括等待时间）
- 如果函数内部有 `await`，等待时间不计入 `rt_avg`

### Q5: 为什么 total 数字很大但输出很少？

**原因**：`monitor` 只输出**周期性统计**，不输出每次调用。

- `total` 是累积调用次数
- 每个 `interval` 只输出 1 次统计
- 如果需要每次调用的详细信息，使用 `watch` 命令

### Q6: 可以监控标准库函数吗？

**答案**：可以，但需要注意性能影响。

```bash
# 监控 json.dumps（可能调用频率极高）
peeka-cli monitor "json.dumps" --interval 10 -c 6
```

**警告**：
- 标准库函数通常调用频率极高
- 即使轻量级的 `monitor`，累积开销也可能明显
- 建议先用 `--interval 10 -c 1` 测试，观察 `total` 数量

---

## 高级技巧

### 1. 实时性能仪表盘

**场景**：使用 `watch` 命令（shell 工具）创建实时仪表盘。

```bash
#!/bin/bash
# dashboard.sh

PID=12345
PATTERN="myapp.api.handler"
LOG="monitor.jsonl"

# 启动监控（后台）
peeka-cli monitor "$PATTERN" --interval 10 > $LOG &
MONITOR_PID=$!

# 实时显示仪表盘
while kill -0 $MONITOR_PID 2>/dev/null; do
  clear
  echo "=== Performance Dashboard ==="
  echo ""
  tail -1 $LOG | jq -r '
    "Cycle: \(.cycle)",
    "Total Calls: \(.total)",
    "Success Rate: \((1 - .fail_rate) * 100)%",
    "Fail Rate: \(.fail_rate * 100)%",
    "Avg RT: \(.rt_avg)ms",
    "Min RT: \(.rt_min)ms",
    "Max RT: \(.rt_max)ms"
  '
  sleep 10
done
```

### 2. 与 Prometheus 集成

**场景**：将监控数据导出到 Prometheus。

```bash
#!/bin/bash
# export_to_prometheus.sh

PID=12345
PATTERN="myapp.api.handler"
METRICS_FILE="/var/lib/node_exporter/textfile_collector/peeka.prom"

peeka-cli monitor "$PATTERN" --interval 60 | \
  jq -r '
    "peeka_calls_total{\(pattern=\"\($PATTERN)\"} \(.total)",
    "peeka_success_total{\(pattern=\"\($PATTERN)\"} \(.success)",
    "peeka_fail_total{\(pattern=\"\($PATTERN)\"} \(.fail)",
    "peeka_fail_rate{pattern=\"\($PATTERN)\"} \(.fail_rate)",
    "peeka_rt_avg_ms{pattern=\"\($PATTERN)\"} \(.rt_avg)",
    "peeka_rt_min_ms{pattern=\"\($PATTERN)\"} \(.rt_min)",
    "peeka_rt_max_ms{pattern=\"\($PATTERN)\"} \(.rt_max)"
  ' > $METRICS_FILE
```

**Prometheus 查询示例**：
```promql
# 失败率告警
rate(peeka_fail_total[5m]) / rate(peeka_calls_total[5m]) > 0.05

# 响应时间趋势
peeka_rt_avg_ms{pattern="myapp.api.handler"}
```

### 3. 性能回归检测

**场景**：每次部署后自动检测性能是否劣化。

```bash
#!/bin/bash
# regression_test.sh

PID=12345
PATTERN="myapp.api.handler"
BASELINE="baseline_rt.txt"

# 读取基线
baseline_rt=$(cat $BASELINE)

# 监控 5 分钟
current_rt=$(peeka-cli monitor "$PATTERN" --interval 60 -c 5 | \
  jq -s 'map(.rt_avg) | add / length')

# 对比
if (( $(echo "$current_rt > $baseline_rt * 1.2" | bc -l) )); then
  echo "❌ REGRESSION: $current_rt ms (baseline: $baseline_rt ms)"
  exit 1
else
  echo "✅ PASS: $current_rt ms (baseline: $baseline_rt ms)"
  exit 0
fi
```

### 4. 多函数聚合统计

**场景**：监控多个函数，汇总统计数据。

```bash
# 监控 3 个函数（并行）
peeka-cli monitor "myapp.api.v1" --interval 60 -c 10 > v1.jsonl &
peeka-cli monitor "myapp.api.v2" --interval 60 -c 10 > v2.jsonl &
peeka-cli monitor "myapp.api.v3" --interval 60 -c 10 > v3.jsonl &

# 等待完成
wait

# 汇总统计
jq -s '
  reduce .[] as $item ({}; 
    .total += $item.total |
    .success += $item.success |
    .fail += $item.fail
  ) | 
  .fail_rate = .fail / .total
' v1.jsonl v2.jsonl v3.jsonl
```

### 5. 自动告警脚本

**场景**：检测到异常时自动发送告警（Slack、邮件等）。

```bash
#!/bin/bash
# alert_on_degradation.sh

PID=12345
PATTERN="myapp.critical"
THRESHOLD_RT=100      # 响应时间阈值（毫秒）
THRESHOLD_FAIL=0.05   # 失败率阈值（5%）

peeka-cli monitor "$PATTERN" --interval 60 | \
  jq -r --arg rt "$THRESHOLD_RT" --arg fail "$THRESHOLD_FAIL" '
    if .rt_avg > ($rt | tonumber) or .fail_rate > ($fail | tonumber) then
      "ALERT: cycle=\(.cycle), rt=\(.rt_avg)ms, fail=\(.fail_rate*100)%"
    else
      empty
    end
  ' | \
  while read line; do
    # 发送告警（示例：Slack）
    curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
      -H 'Content-Type: application/json' \
      -d "{\"text\": \"$line\"}"
  done
```

### 6. 历史数据分析

**场景**：分析历史监控数据，找出性能规律。

```bash
# 收集 1 周的监控数据
for day in {1..7}; do
  peeka-cli monitor "myapp.func" --interval 3600 -c 24 > \
    monitor_day${day}.jsonl
  sleep 86400  # 1 天
done

# 分析每天同一时刻的性能
for hour in {0..23}; do
  echo -n "Hour $hour: "
  jq -s --arg h "$hour" 'map(select(.cycle == ($h | tonumber + 1))) | 
    map(.rt_avg) | add / length' monitor_day*.jsonl
done
```

---


## 总结

`monitor` 命令是生产环境性能监控的强大工具，特别适合：
- 长期性能监控
- 建立性能基线
- 性能劣化检测
- 负载测试期间实时监控
- 与 Prometheus 等监控系统集成

**最佳实践**：
- 根据函数调用频率选择合适的 `--interval`（建议 30-60 秒）
- 使用 `-c` 限制周期数（避免忘记停止）
- 输出到文件（`> monitor.jsonl`）便于后续分析
- 结合 `jq` 进行强大的数据分析
- 与 `watch` 命令配合使用（先 `monitor` 发现问题，再 `watch` 深入排查）

**下一步**：
- 了解 [`watch`](watch.md) 命令（观测函数详细信息）
- 了解 [`stack`](stack.md) 命令（追踪调用栈）
- 了解 [`memory`](memory.md) 命令（内存分析）
- 参考 [AGENTS.md](../AGENTS.md)（开发者指南）

