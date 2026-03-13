---
layout: default
title: 示例教程
nav_order: 5
---

# 示例教程
{: .no_toc }

通过实际场景学习如何使用 Peeka 诊断和解决问题。
{: .fs-6 .fw-300 }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 场景 1：诊断慢接口

### 问题描述

API 接口偶尔响应很慢（> 1 秒），需要找出慢调用的原因。

### 解决步骤

#### 1. 附加到进程

```bash
# 找到 API 服务进程
ps aux | grep "api_server.py"
# 输出: user 12345 ...

# 附加
peeka-cli attach 12345
```

#### 2. 监控整体性能

```bash
# 每 10 秒统计一次
peeka-cli monitor "app.api.handle_request" --interval 10
```

输出：
```json
{"type":"observation","func_name":"app.api.handle_request","total":150,"success":148,"fail":2,"avg_rt":250.5,"min_rt":50.2,"max_rt":1850.3}
```

发现 `max_rt` 高达 1850ms，存在慢调用。

#### 3. 观测慢调用

```bash
# 只观测执行时间 > 1000ms 的调用
peeka-cli watch "app.api.handle_request" \
  --condition "cost > 1000" \
  --times 10
```

输出：
```json
{"type":"observation","watch_id":"watch_001","func_name":"app.api.handle_request","args":[{"user_id": 12345}],"result":{"status": "ok"},"duration_ms":1850.3,"count":1}
```

发现慢调用参数为 `user_id=12345`。

#### 4. 追踪调用链

```bash
# 追踪完整调用链，找出耗时环节
peeka-cli trace "app.api.handle_request" \
  --condition "cost > 1000" \
  --depth 5 \
  --times 1
```

输出：
```
`---[1850.3ms] app.api.handle_request()
    +---[5.2ms] app.auth.validate_token()
    +---[1800.1ms] app.db.query_user_data()  ← 慢
    |   +---[1795.5ms] sqlalchemy.query.all()
    |   `---[2.1ms] app.db._parse_results()
    `---[15.7ms] app.response.build()
```

**结论**: 慢调用是由 `app.db.query_user_data()` 引起，SQL 查询耗时过长。

#### 5. 修复验证

优化 SQL 查询后，再次监控：

```bash
peeka-cli monitor "app.api.handle_request" --interval 10
```

输出：
```json
{"type":"observation","total":150,"avg_rt":120.5,"max_rt":450.3}
```

性能显著提升！

---

## 场景 2：定位异常原因

### 问题描述

后台任务偶尔抛出 `ValueError`，但日志不完整，无法定位原因。

### 解决步骤

#### 1. 观测异常

```bash
# 只观测抛出异常的调用
peeka-cli watch "app.tasks.process_data" \
  --exception
```

输出：
```json
{
  "type":"observation",
  "func_name":"app.tasks.process_data",
  "args":[{"data": [1, 2, null]}],
  "success":false,
  "exception":"ValueError: invalid value",
  "duration_ms":5.2
}
```

发现异常参数包含 `null`。

#### 2. 查看调用栈

```bash
# 捕获异常时的调用栈
peeka-cli stack "app.tasks.process_data" \
  --condition "throwExp is not None" \
  --times 1
```

输出：
```
Thread: WorkerThread-1
  File "scheduler.py", line 45, in run
    self.execute_task(task)
  File "scheduler.py", line 78, in execute_task
    result = task.process_data(data)
  File "tasks.py", line 120, in process_data
    validated = self._validate(data)  ← 这里抛出异常
```

**结论**: 异常由 `scheduler.py` 传入的 `null` 数据引起。

#### 3. 修复验证

添加输入验证后，再次测试：

```bash
peeka-cli watch "app.tasks.process_data" --times 100
```

观测 100 次调用，无异常。

---

## 场景 3：验证代码修改

### 问题描述

修改了缓存逻辑，需要验证缓存是否真的生效。

### 解决步骤

#### 1. 观测缓存函数

```bash
# 观测缓存命中情况
peeka-cli watch "app.cache.get" --times 20
```

输出：
```json
{"type":"observation","func_name":"app.cache.get","args":["user_123"],"result":{"name":"Alice"},"from_cache":true}
{"type":"observation","func_name":"app.cache.get","args":["user_456"],"result":null,"from_cache":false}
{"type":"observation","func_name":"app.cache.get","args":["user_123"],"result":{"name":"Alice"},"from_cache":true}
```

#### 2. 统计命中率

```bash
peeka-cli watch "app.cache.get" --times 1000 | \
  jq 'select(.type == "observation") | .from_cache' | \
  awk '{if($1=="true") hit++; total++} END {print "Hit Rate:", (hit/total)*100, "%"}'
```

输出：
```
Hit Rate: 85.3 %
```

**结论**: 缓存命中率 85%，符合预期。

---

## 场景 4：监控函数性能回归

### 问题描述

部署新版本后，担心性能回归，需要实时监控。

### 解决步骤

#### 1. 建立性能基线

部署前：
```bash
peeka-cli monitor "app.service.critical_func" --interval 5 -c 12 > baseline.jsonl
```

#### 2. 部署后监控

```bash
peeka-cli monitor "app.service.critical_func" --interval 5 -c 12 > after_deploy.jsonl
```

#### 3. 对比分析

```python
# compare.py
import json

def load_stats(file):
    stats = []
    with open(file) as f:
        for line in f:
            msg = json.loads(line)
            if msg.get("type") == "observation":
                stats.append(msg["avg_rt"])
    return sum(stats) / len(stats) if stats else 0

baseline = load_stats("baseline.jsonl")
after = load_stats("after_deploy.jsonl")

print(f"Baseline: {baseline:.2f}ms")
print(f"After Deploy: {after:.2f}ms")
print(f"Change: {((after - baseline) / baseline) * 100:.1f}%")
```

输出：
```
Baseline: 125.50ms
After Deploy: 130.20ms
Change: +3.7%
```

**结论**: 性能轻微下降 3.7%，在可接受范围内。

---

## 场景 5：调试条件竞争

### 问题描述

多线程程序偶尔出现数据不一致，怀疑是条件竞争。

### 解决步骤

#### 1. 观测关键函数调用顺序

```bash
# 观测两个关键函数
peeka-cli watch "app.data.read" --times 100 > read.jsonl &
peeka-cli watch "app.data.write" --times 100 > write.jsonl &
```

#### 2. 分析时间戳

```python
# analyze_race.py
import json
from collections import defaultdict

def load_calls(file):
    calls = []
    with open(file) as f:
        for line in f:
            msg = json.loads(line)
            if msg.get("type") == "observation":
                calls.append((msg["timestamp"], msg["func_name"]))
    return calls

reads = load_calls("read.jsonl")
writes = load_calls("write.jsonl")

# 合并并排序
all_calls = sorted(reads + writes, key=lambda x: x[0])

# 查找可疑模式：read -> read（中间无 write）
for i in range(len(all_calls) - 1):
    curr_func = all_calls[i][1]
    next_func = all_calls[i+1][1]
    if "read" in curr_func and "read" in next_func:
        print(f"Suspicious pattern at {all_calls[i][0]}")
```

#### 3. 验证修复

添加锁保护后，再次测试：

```bash
peeka-cli watch "app.data.read" --times 100 | \
  jq 'select(.type == "observation") | .data_version' | \
  uniq -c
```

输出显示数据版本一致，无竞争。

---

## 场景 6：分析参数分布

### 问题描述

需要了解函数参数的分布情况，优化缓存策略。

### 解决步骤

#### 1. 收集参数数据

```bash
peeka-cli watch "app.service.query" --times 1000 > params.jsonl
```

#### 2. 分析分布

```bash
# 提取第一个参数
cat params.jsonl | \
  jq 'select(.type == "observation") | .args[0]' | \
  sort | uniq -c | sort -rn | head -10
```

输出：
```
    245 "user_type_A"
    198 "user_type_B"
     87 "user_type_C"
     45 "user_type_D"
     ...
```

#### 3. 可视化

```python
# visualize.py
import json
from collections import Counter
import matplotlib.pyplot as plt

params = []
with open("params.jsonl") as f:
    for line in f:
        msg = json.loads(line)
        if msg.get("type") == "observation":
            params.append(msg["args"][0])

counter = Counter(params)
labels, values = zip(*counter.most_common(10))

plt.bar(labels, values)
plt.xlabel("Parameter Value")
plt.ylabel("Frequency")
plt.title("Parameter Distribution")
plt.xticks(rotation=45)
plt.tight_layout()
plt.savefig("param_dist.png")
```

**结论**: `user_type_A` 和 `user_type_B` 占比最高，应优先缓存。

---

## 场景 7：生产环境实时告警

### 问题描述

需要在生产环境实时监控关键函数，异常时自动告警。

### 解决步骤

#### 1. 编写监控脚本

```bash
#!/bin/bash
# monitor_and_alert.sh

peeka-cli monitor "app.api.critical" --interval 10 | \
while read -r line; do
    # 解析 JSON
    avg_rt=$(echo "$line" | jq -r '.avg_rt // 0')
    fail=$(echo "$line" | jq -r '.fail // 0')

    # 告警条件
    if (( $(echo "$avg_rt > 500" | bc -l) )); then
        echo "ALERT: High latency detected: ${avg_rt}ms" | \
          mail -s "Peeka Alert" ops@example.com
    fi

    if (( fail > 0 )); then
        echo "ALERT: ${fail} failures detected" | \
          mail -s "Peeka Alert" ops@example.com
    fi
done
```

#### 2. 后台运行

```bash
nohup ./monitor_and_alert.sh > alert.log 2>&1 &
```

#### 3. 集成到监控系统

```python
# prometheus_exporter.py
from prometheus_client import Gauge, start_http_server
import json
import subprocess

# 定义指标
api_latency = Gauge('api_critical_latency_ms', 'API critical latency')
api_failures = Gauge('api_critical_failures', 'API critical failures')

# 启动 HTTP 服务器
start_http_server(8000)

# 读取 Peeka 输出
proc = subprocess.Popen(
    ['peeka-cli', 'monitor', 'app.api.critical', '--interval', '10'],
    stdout=subprocess.PIPE,
    text=True
)

for line in proc.stdout:
    msg = json.loads(line)
    if msg.get("type") == "observation":
        api_latency.set(msg.get("avg_rt", 0))
        api_failures.set(msg.get("fail", 0))
```

---

## 最佳实践总结

### 1. 逐步缩小范围

```bash
# 从粗到细
monitor → watch → trace → stack
```

### 2. 使用条件过滤

```bash
# 避免数据过多
--condition "cost > 100"
--times 10
```

### 3. 保存观测数据

```bash
# 便于离线分析
peeka-cli watch "func" > data.jsonl
```

### 4. 结合工具链

```bash
# 充分利用 Unix 工具
peeka-cli watch "func" | jq | awk | gnuplot
```

### 5. 自动化集成

```python
# 集成到 CI/CD
python -m peeka.analyze --baseline baseline.jsonl --current current.jsonl
```

---

## 更多资源

- [命令参考]({% link commands/index.md %}) - 详细命令文档
- [架构设计]({% link architecture.md %}) - 了解实现原理
- [故障排除]({% link troubleshooting.md %}) - 常见问题解决
