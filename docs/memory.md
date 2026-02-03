# memory 命令

## 简介

`memory` 命令用于分析运行中 Python 进程的**内存使用情况**，提供 6 种诊断操作：内存概览、追踪控制、分配分析、快照导出和 GC 统计。这是 Peeka 的核心内存诊断工具，适用于生产环境的内存泄漏排查和性能优化。

**设计灵感**：Peeka 的 `memory` 命令借鉴了 [Arthas](https://arthas.aliyun.com/) 的 `memory` 命令，针对 Python 语言特性使用 `tracemalloc` 和 `gc` 模块实现。

## 使用场景

- **内存泄漏诊断**：查看哪些代码位置分配了最多内存
- **性能优化**：定位内存分配热点，优化内存使用
- **GC 分析**：统计对象类型数量，发现对象数量异常
- **快照对比**：导出多个快照，离线对比分析内存增长
- **RSS 监控**：查看进程物理内存（RSS）使用情况

## 命令格式

```bash
peeka-cli memory <pid> [options]
```

### 参数说明

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `pid` | 目标进程 ID | - | `12345` |
| `--action` | 内存操作类型 | `overview` | `--action start` |
| `--nframe` | tracemalloc 调用栈深度 | `25` | `--nframe 50` |
| `--group-by` | 分配分组方式 | `lineno` | `--group-by filename` |
| `--limit` | 结果数量限制 | `20` | `--limit 50` |
| `--filename` | 快照文件名 | 自动生成 | `--filename snapshot1` |

### action 操作类型

| Action | 说明 | 需要先 start | 主要用途 |
|--------|------|-------------|----------|
| **overview** | 内存概览 | ❌ 否 | 查看 RSS、GC 状态、tracemalloc 状态 |
| **start** | 开启追踪 | - | 启用 tracemalloc 内存追踪 |
| **stop** | 停止追踪 | ❌ 否 | 关闭 tracemalloc，释放追踪开销 |
| **top** | Top N 分配 | ✅ 是 | 查看内存分配热点（按代码位置） |
| **dump** | 导出快照 | ✅ 是 | 保存快照供离线分析 |
| **gc** | GC 统计 | ❌ 否 | 统计对象类型数量 |

## 基本用法

### 1. 内存概览（overview）

查看进程当前内存状态，**无需启动追踪**。

```bash
# 查看内存概览（默认 action）
peeka-cli memory --pid 12345

# 或显式指定 action
peeka-cli memory --pid 12345 --action overview
```

**输出示例**：

```json
{
  "status": "success",
  "action": "overview",
  "timestamp": 1738328400.0,
  "pid": 12345,
  "rss_bytes": 524288000,
  "rss_source": "procfs",
  "tracemalloc": {
    "enabled": false,
    "current_bytes": null,
    "peak_bytes": null
  },
  "gc": {
    "enabled": true,
    "counts": [150, 10, 2],
    "stats": [
      {"collections": 45, "collected": 1234, "uncollectable": 0},
      {"collections": 4, "collected": 89, "uncollectable": 0},
      {"collections": 0, "collected": 0, "uncollectable": 0}
    ]
  }
}
```

**字段说明**：

| 字段 | 说明 | 示例值 |
|------|------|--------|
| `rss_bytes` | 进程物理内存（字节） | `524288000` (500 MB) |
| `rss_source` | RSS 来源 | `"procfs"` 或 `"resource_maxrss"` |
| `tracemalloc.enabled` | tracemalloc 是否运行 | `true` / `false` |
| `tracemalloc.current_bytes` | 当前追踪的内存（仅追踪时） | `123456789` |
| `tracemalloc.peak_bytes` | 峰值内存（仅追踪时） | `234567890` |
| `gc.enabled` | GC 是否启用 | `true` / `false` |
| `gc.counts` | GC 计数器（gen0, gen1, gen2） | `[150, 10, 2]` |
| `gc.stats` | 各代 GC 统计 | 见下表 |

**GC stats 字段**：

| 字段 | 说明 |
|------|------|
| `collections` | 该代 GC 次数 |
| `collected` | 回收的对象数 |
| `uncollectable` | 无法回收的对象数（警告：可能泄漏） |

### 2. 启动内存追踪（start）

启用 Python 的 `tracemalloc` 模块，开始追踪内存分配。

```bash
# 使用默认深度（25 层调用栈）
peeka-cli memory --pid 12345 --action start

# 自定义调用栈深度（1-50）
peeka-cli memory --pid 12345 --action start --nframe 50
```

**输出示例**：

```json
{
  "status": "success",
  "action": "start",
  "message": "tracemalloc started successfully",
  "nframe": 25
}
```

**参数说明**：

- `--nframe`：调用栈深度（1-50），默认 25
  - 深度越大，追踪越详细，但开销越高
  - 推荐值：生产环境 25，开发调试 50

**幂等性**：

如果 tracemalloc 已经在运行，再次调用 `start` 不会报错：

```json
{
  "status": "success",
  "action": "start",
  "message": "tracemalloc is already running",
  "was_already_running": true
}
```

**性能影响**：

- **开销**：约 5-10% 性能和内存开销
- **建议**：在低峰期启动，或仅短时间启用

### 3. 停止内存追踪（stop）

关闭 `tracemalloc`，释放追踪开销。

```bash
peeka-cli memory --pid 12345 --action stop
```

**输出示例**：

```json
{
  "status": "success",
  "action": "stop",
  "message": "tracemalloc stopped successfully",
  "was_running": true
}
```

**注意事项**：

- ⚠️ **停止后数据丢失**：stop 会清空所有追踪数据
- 📝 **先导出再停止**：如需保留数据，请先执行 `dump`
- ✅ **幂等操作**：即使未运行，stop 也不会报错

```bash
# 正确流程：先导出，再停止
peeka-cli memory --pid 12345 --action dump --filename production_snapshot
peeka-cli memory --pid 12345 --action stop
```

### 4. 查看 Top N 内存分配（top）

显示占用内存最多的代码位置（**需要先 start**）。

```bash
# 查看 top 20 分配（默认按行号分组）
peeka-cli memory --pid 12345 --action top

# 查看 top 50 分配
peeka-cli memory --pid 12345 --action top --limit 50

# 按文件名分组（查看哪个模块占用多）
peeka-cli memory --pid 12345 --action top --group-by filename --limit 30
```

**输出示例**（按行号分组）：

```json
{
  "status": "success",
  "action": "top",
  "group_by": "lineno",
  "limit": 20,
  "total_size_bytes": 245760000,
  "allocations": [
    {
      "rank": 1,
      "size_bytes": 24641536,
      "count": 1024,
      "traceback": [
        {"filename": "/app/models.py", "lineno": 145}
      ]
    },
    {
      "rank": 2,
      "size_bytes": 15925248,
      "count": 512,
      "traceback": [
        {"filename": "/app/cache.py", "lineno": 89}
      ]
    }
  ]
}
```

**字段说明**：

| 字段 | 说明 |
|------|------|
| `rank` | 排名（按 size_bytes 降序） |
| `size_bytes` | 该分配点占用的总字节数 |
| `count` | 分配块的数量 |
| `traceback` | 调用栈（数组，最老的在前） |

**group-by 模式对比**：

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| `lineno` | 按代码行分组 | 定位具体代码行 |
| `filename` | 按文件分组 | 定位问题模块 |

**示例**（按文件名分组）：

```bash
peeka-cli memory --pid 12345 --action top --group-by filename --limit 10
```

```json
{
  "allocations": [
    {
      "rank": 1,
      "size_bytes": 104857600,
      "count": 5120,
      "traceback": [
        {"filename": "/app/models.py", "lineno": 1}
      ]
    }
  ]
}
```

> 注意：按 filename 分组时，`lineno` 字段为 1（无实际意义）

**错误处理**：

如果未启动追踪就调用 `top`：

```json
{
  "status": "error",
  "action": "top",
  "error": "tracemalloc is not running. Run 'memory start' first."
}
```

### 5. 导出内存快照（dump）

将当前内存快照保存到文件（**需要先 start**）。

```bash
# 自动生成文件名（时间戳）
peeka-cli memory --pid 12345 --action dump

# 指定文件名
peeka-cli memory --pid 12345 --action dump --filename my_snapshot

# 带路径遍历保护（自动提取 basename）
peeka-cli memory --pid 12345 --action dump --filename "../etc/passwd"
# 实际保存为：/tmp/passwd.snapshot
```

**输出示例**：

```json
{
  "status": "success",
  "action": "dump",
  "file_path": "/tmp/peeka_dump_20260131_165420.snapshot",
  "size_bytes": 1048576
}
```

**文件格式**：

- **格式**：Python tracemalloc 二进制快照（`.snapshot`）
- **加载**：使用 `tracemalloc.Snapshot.load()` 加载
- **位置**：`PEEKA_DUMP_DIR` 环境变量指定的目录，默认 `/tmp`

**快照内容**：

- ✅ 所有当前存活的内存分配
- ✅ 每个分配点的调用栈
- ✅ 分配大小和数量
- ❌ **不是增量**：是当前时刻的完整快照

**离线分析示例**：

```python
import tracemalloc

# 加载快照
snapshot = tracemalloc.Snapshot.load('/tmp/peeka_dump_20260131_165420.snapshot')

# 按行号分组，查看 top 10
stats = snapshot.statistics('lineno')
for stat in stats[:10]:
    print(f"{stat.size / 1024 / 1024:.1f} MB - {stat.count} blocks")
    print(f"  {stat.traceback[0].filename}:{stat.traceback[0].lineno}")
```

**快照对比**（增量分析）：

```python
# 加载两个快照
snapshot1 = tracemalloc.Snapshot.load('before.snapshot')
snapshot2 = tracemalloc.Snapshot.load('after.snapshot')

# 计算差异
diff = snapshot2.compare_to(snapshot1, 'lineno')

# 查看内存增长
for stat in diff[:10]:
    print(f"{stat.size_diff / 1024 / 1024:+.1f} MB - {stat.filename}:{stat.lineno}")
```

**安全保护**：

- ✅ **路径遍历防护**：自动使用 `os.path.basename()` 提取文件名
- ✅ **目录限制**：只能写入 `PEEKA_DUMP_DIR` 或 `/tmp`
- ✅ **自动扩展名**：文件名自动加 `.snapshot` 后缀

### 6. GC 对象统计（gc）

统计各类型对象的数量（**无需 start**）。

```bash
# 查看 top 20 对象类型（默认）
peeka-cli memory --pid 12345 --action gc

# 查看 top 50 对象类型
peeka-cli memory --pid 12345 --action gc --limit 50
```

**输出示例**：

```json
{
  "status": "success",
  "action": "gc",
  "limit": 20,
  "total_objects": 1523891,
  "objects_by_type": [
    {"rank": 1, "type": "dict", "count": 345612},
    {"rank": 2, "type": "list", "count": 198234},
    {"rank": 3, "type": "tuple", "count": 156789},
    {"rank": 4, "type": "str", "count": 123456},
    {"rank": 5, "type": "function", "count": 89012},
    {"rank": 6, "type": "User", "count": 50000}
  ]
}
```

**字段说明**：

| 字段 | 说明 |
|------|------|
| `total_objects` | GC 追踪的对象总数 |
| `objects_by_type` | 按数量排序的对象类型列表 |
| `rank` | 排名（按 count 降序，count 相同按 type 升序） |
| `type` | 对象类型名（`type(obj).__name__`） |
| `count` | 该类型对象的数量 |

**使用场景**：

- **内存泄漏排查**：发现对象数量异常增长
  ```bash
  # 示例：发现 50000 个 User 对象（可能未释放）
  ```
- **对象生命周期分析**：观察对象创建和销毁
- **缓存监控**：检查缓存对象是否过多

**性能注意**：

- ⚠️ **开销较大**：`gc.get_objects()` 返回所有对象（可能数百万）
- 📊 **生产环境谨慎使用**：建议在低峰期或小流量时使用
- ✅ **有硬限制**：最多返回 100 项（防止输出过大）

**与 top 的区别**：

| 维度 | `top` 命令 | `gc` 命令 |
|------|-----------|----------|
| **需要 start** | ✅ 是 | ❌ 否 |
| **显示内容** | 内存分配**位置**（代码行） | 对象**类型**数量 |
| **能知道什么** | 哪行代码分配了多少内存 | 有多少个某类型对象 |
| **不能知道什么** | 对象类型 | 每个对象占多少内存 |
| **数据来源** | `tracemalloc` | `gc.get_objects()` |

## 完整诊断流程

### 场景 1：内存泄漏排查

```bash
# 1. 查看当前内存状态
peeka-cli memory --pid 12345 --action overview

# 2. 启动追踪
peeka-cli memory --pid 12345 --action start --nframe 50

# 3. 等待一段时间（让问题复现）
sleep 300  # 5 分钟

# 4. 导出第一个快照
peeka-cli memory --pid 12345 --action dump --filename snapshot_before

# 5. 继续等待
sleep 300

# 6. 导出第二个快照
peeka-cli memory --pid 12345 --action dump --filename snapshot_after

# 7. 查看 top 分配
peeka-cli memory --pid 12345 --action top --limit 30

# 8. 查看对象统计
peeka-cli memory --pid 12345 --action gc --limit 50

# 9. 停止追踪
peeka-cli memory --pid 12345 --action stop

# 10. 离线对比快照（Python 脚本）
python analyze_snapshots.py snapshot_before.snapshot snapshot_after.snapshot
```

### 场景 2：性能优化

```bash
# 1. 启动追踪
peeka-cli memory --pid 12345 --action start

# 2. 运行性能测试
# ... 触发业务操作 ...

# 3. 查看内存热点（按文件分组）
peeka-cli memory --pid 12345 --action top --group-by filename --limit 20

# 4. 查看具体代码行（按行号分组）
peeka-cli memory --pid 12345 --action top --group-by lineno --limit 50

# 5. 停止追踪
peeka-cli memory --pid 12345 --action stop
```

### 场景 3：定期监控

```bash
#!/bin/bash
# 定时内存快照脚本

PID=12345
SNAPSHOT_DIR="/data/memory_snapshots"

# 启动追踪（首次）
peeka-cli memory --pid $PID --action start

# 每小时导出快照
while true; do
  timestamp=$(date +%Y%m%d_%H%M%S)
  peeka-cli memory --pid $PID --action dump --filename "snapshot_$timestamp"
  sleep 3600
done
```

## 输出格式

所有 action 都返回 JSON 格式，字段包含：

### 通用字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | string | `"success"` 或 `"error"` |
| `action` | string | 执行的操作类型 |
| `error` | string | 错误信息（仅失败时） |

### 错误响应示例

```json
{
  "status": "error",
  "action": "top",
  "error": "tracemalloc is not running. Run 'memory start' first."
}
```

## 性能影响

### tracemalloc 开销

| 场景 | 开销 | 说明 |
|------|------|------|
| **未启动 tracemalloc** | 0% | overview/gc 无额外开销 |
| **启动 tracemalloc（nframe=25）** | 5-8% | 追踪内存分配和调用栈 |
| **启动 tracemalloc（nframe=50）** | 8-12% | 深度调用栈开销更大 |
| **dump 操作** | < 1% | 快照导出瞬时开销 |
| **gc 操作** | 2-5% | 遍历所有对象，瞬时开销 |

### 最佳实践

1. **按需启动**：
   ```bash
   # ❌ 错误：长期开启追踪
   peeka-cli memory --pid 12345 --action start
   # ... 永久运行 ...
   
   # ✅ 正确：短时间启动，诊断后立即停止
   peeka-cli memory --pid 12345 --action start
   sleep 300  # 5 分钟
   peeka-cli memory --pid 12345 --action dump --filename snapshot
   peeka-cli memory --pid 12345 --action stop
   ```

2. **选择合适的 nframe**：
   ```bash
   # 生产环境：使用默认值 25
   peeka-cli memory --pid 12345 --action start
   
   # 开发调试：使用更深的调用栈
   peeka-cli memory --pid 12345 --action start --nframe 50
   ```

3. **低峰期使用 gc**：
   ```bash
   # gc 操作开销较大，建议在低峰期执行
   peeka-cli memory --pid 12345 --action gc --limit 30
   ```

4. **定期导出快照**：
   ```bash
   # 每 1 小时导出一次，用于趋势分析
   while true; do
     peeka-cli memory --pid 12345 --action dump --filename "snapshot_$(date +%H)"
     sleep 3600
   done
   ```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `PEEKA_DUMP_DIR` | `/tmp` | 快照文件保存目录 |

**示例**：

```bash
# 自定义快照目录
export PEEKA_DUMP_DIR=/data/peeka_dumps
peeka-cli memory --pid 12345 --action dump
# 文件保存到：/data/peeka_dumps/peeka_dump_*.snapshot
```

## 常见问题

### 1. dump 失败："tracemalloc is not running"

**原因**：未启动 tracemalloc 就执行 dump。

**解决**：

```bash
# 先启动追踪
peeka-cli memory --pid 12345 --action start

# 再导出快照
peeka-cli memory --pid 12345 --action dump
```

### 2. top 结果为空

**可能原因**：

- 刚启动 tracemalloc，尚未捕获到分配
- 进程内存分配很少

**解决**：

```bash
# 等待一段时间后再查看
peeka-cli memory --pid 12345 --action start
sleep 60
peeka-cli memory --pid 12345 --action top
```

### 3. dump 文件过大

**原因**：追踪时间过长，分配记录过多。

**解决**：

- 减少追踪时间（及时 stop）
- 降低 nframe 深度
- 定期导出并清空（stop + start）

### 4. gc 命令很慢

**原因**：`gc.get_objects()` 需要遍历所有对象。

**解决**：

- 在低峰期执行
- 减少 limit 参数
- 避免高频调用

### 5. RSS 和 tracemalloc 数值差异大

**原因**：

- **RSS**：进程占用的物理内存（包括代码、栈、共享库）
- **tracemalloc**：只追踪 Python 堆分配

**正常现象**：

```
RSS: 500 MB
tracemalloc: 200 MB  # 只是 Python 对象的内存
```

**差异来源**：

- 共享库（如 numpy, torch）
- C 扩展直接分配的内存
- 解释器自身内存
- 栈内存

### 6. dump 文件在哪里？

**默认位置**：`/tmp/peeka_dump_*.snapshot`

**查找方法**：

```bash
# 查看最新的 dump 文件
ls -lt /tmp/peeka_dump_*.snapshot | head -1

# 自定义目录
export PEEKA_DUMP_DIR=/data/dumps
peeka-cli memory --pid 12345 --action dump
ls -lt /data/dumps/
```

## 高级技巧

### 1. 自动化内存监控脚本

```bash
#!/bin/bash
# memory_monitor.sh - 自动内存监控

PID=$1
ALERT_THRESHOLD=1000000000  # 1GB

peeka-cli memory --pid $PID --action overview | \
  jq -r '.rss_bytes' | \
  while read rss; do
    if [ $rss -gt $ALERT_THRESHOLD ]; then
      echo "Alert: RSS > 1GB, capturing snapshot..."
      peeka-cli memory --pid $PID --action start
      sleep 30
      peeka-cli memory --pid $PID --action dump --filename "alert_$(date +%s)"
      peeka-cli memory --pid $PID --action stop
    fi
  done
```

### 2. 内存增长率分析

```python
# analyze_growth.py
import json
import sys

snapshots = sys.argv[1:]  # 多个快照文件路径

sizes = []
for snapshot in snapshots:
    data = json.load(open(snapshot))
    sizes.append(data['rss_bytes'])

# 计算增长率
for i in range(1, len(sizes)):
    growth = (sizes[i] - sizes[i-1]) / sizes[i-1] * 100
    print(f"Snapshot {i}: +{growth:.2f}%")
```

### 3. 与 Prometheus 集成

```python
# prometheus_exporter.py
from prometheus_client import Gauge
import subprocess
import json
import time

rss_gauge = Gauge('process_rss_bytes', 'Process RSS memory', ['pid'])
tracemalloc_gauge = Gauge('tracemalloc_bytes', 'Tracemalloc memory', ['pid', 'type'])

def collect_metrics(pid):
    result = subprocess.check_output(['peeka', 'memory', '--pid', str(pid)])
    data = json.loads(result)
    
    rss_gauge.labels(pid=pid).set(data['rss_bytes'])
    
    if data['tracemalloc']['enabled']:
        tracemalloc_gauge.labels(pid=pid, type='current').set(
            data['tracemalloc']['current_bytes']
        )
        tracemalloc_gauge.labels(pid=pid, type='peak').set(
            data['tracemalloc']['peak_bytes']
        )

while True:
    collect_metrics(12345)
    time.sleep(15)
```

## 与 Arthas Memory 的对比

| 特性 | Peeka | Arthas | 说明 |
|------|-------|--------|------|
| **目标语言** | Python | Java | 核心差异 |
| **RSS 查看** | ✅ procfs/resource | ✅ 系统 API | 功能一致 |
| **堆内存分析** | ✅ tracemalloc | ✅ JVM heap | 实现机制不同 |
| **GC 统计** | ✅ gc 模块 | ✅ JVM GC | 功能一致 |
| **快照导出** | ✅ .snapshot 格式 | ✅ heap dump | 格式不同 |
| **内存分配热点** | ✅ top 命令 | ✅ memory 命令 | 功能相似 |
| **对象统计** | ✅ gc 命令 | ✅ dashboard | 功能相似 |
| **堆外内存** | ⏳ 部分支持（RSS vs tracemalloc） | ✅ 完整支持 | Python 无堆外概念 |
| **实时监控** | ❌ 需要轮询 | ✅ dashboard | Peeka 计划支持 |

## 参考资料

- [Python tracemalloc 文档](https://docs.python.org/3/library/tracemalloc.html)
- [Python gc 模块文档](https://docs.python.org/3/library/gc.html)
- [Arthas Memory 文档](https://arthas.aliyun.com/doc/memory.html)
- [Peeka 架构设计](../ARCHITECTURE.md)
- [Peeka 开发指南](../AGENTS.md)

## 更新日志

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 0.1.0 | 2026-01 | 初始版本，支持 6 种 memory 操作 |
