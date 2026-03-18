---
layout: default
title: memory 命令
parent: 命令参考
nav_order: 7
---

# memory 命令
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}


## 简介

`memory` 命令用于分析运行中 Python 进程的**内存使用情况**，提供 10 种诊断操作：内存概览、追踪控制、分配分析、快照管理、快照对比、引用链查询、快照导出和 GC 统计。这是 Peeka 的核心内存诊断工具，适用于生产环境的内存泄漏排查和性能优化。



## 使用场景

- **内存泄漏诊断**：查看哪些代码位置分配了最多内存
- **性能优化**：定位内存分配热点，优化内存使用
- **GC 分析**：统计对象类型数量，发现对象数量异常
- **快照对比**：导出多个快照，离线对比分析内存增长
- **RSS 监控**：查看进程物理内存（RSS）使用情况

## TUI 使用

在 TUI 模式下，按 **`6`** 键切换到 **Memory 视图**，提供 4 个 Tab 页和丰富的交互式功能：

#### Overview Tab（内存概览）

- 进程 RSS（物理内存）显示，单位 MB
- RSS 趋势 Sparkline 图表（最近 100 个采样点）
- tracemalloc 当前追踪内存 / 峰值内存
- GC 三代计数（gen0, gen1, gen2）
- **Top Objects by Size** 表格：类型、数量、Δ数量、大小、Δ大小
  - 每次刷新自动计算增量（红色 = 增长，绿色 = 减少）
  - 支持点击列头排序

#### Allocations Tab（分配热点）

- 需要先启动 Track 追踪
- 展示 Top N 内存分配：Rank、Size、Count、Location（文件:行号）
- 自动刷新时同步更新

#### Diff Tab（快照对比）

- **Snap 按钮**：拍摄 tracemalloc 快照（最多 2 个，FIFO）
- **Diff 按钮**：对比两个快照，表格展示 Location、Size Δ、New、Old、Count Δ
- 增量数据带颜色标记（红色增长、绿色减少）

#### References Tab（引用链分析）

- 输入类型名（如 `dict`、`MyClass`）
- **Referrers 按钮**：树形展示谁引用了该类型对象（排查泄漏根因）
- **Referents 按钮**：树形展示该类型对象引用了什么（分析对象结构）

#### 控制栏和快捷键

| 控件 | 快捷键 | 功能 |
|------|:------:|------|
| Refresh | `r` | 手动刷新 overview + allocations |
| Track | `T` | 启动/停止 tracemalloc 追踪 |
| GC | `g` | 触发 GC 统计刷新 |
| Dump | — | 导出 snapshot 文件到磁盘 |
| Auto | `a` | 自动刷新（5 秒间隔） |
| nframe 输入框 | — | 设置 tracemalloc 栈深度（1-50） |
| limit 输入框 | — | 设置 GC/allocation 显示条数（1-100） |
**CLI 等效命令**：下文所有示例使用 CLI 命令演示，TUI 提供了相同功能的图形化界面。
## 命令格式

```bash
# 必须先附加到目标进程
peeka-cli attach <pid>

# 然后执行 memory 命令
peeka-cli memory [options]
```

### 参数说明

| 参数 | 说明 | 默认值 | 示例 |
|------|------|--------|------|
| `--action` | 内存操作类型 | `overview` | `--action start` |
| `--nframe` | tracemalloc 调用栈深度 | `25` | `--nframe 50` |
| `--group-by` | 分配分组方式 | `lineno` | `--group-by filename` |
| `--limit` | 结果数量限制 | `20` | `--limit 50` |
| `--filename` | 快照文件名 | 自动生成 | `--filename snapshot1` |
| `--type-name` | 类型名（referrers/referents 用） | - | `--type-name dict` |
| `--max-depth` | 引用链递归深度 | `2` | `--max-depth 3` |
| `--max-per-level` | 每层最大条目数 | `10` | `--max-per-level 20` |

### action 操作类型

| Action | 说明 | 需要先 start | 主要用途 |
|--------|------|-------------|----------|
| **overview** | 内存概览 | ❌ 否 | 查看 RSS、GC 状态、tracemalloc 状态 |
| **start** | 开启追踪 | - | 启用 tracemalloc 内存追踪 |
| **stop** | 停止追踪 | ❌ 否 | 关闭 tracemalloc，释放追踪开销 |
| **top** | Top N 分配 | ✅ 是 | 查看内存分配热点（按代码位置） |
| **dump** | 导出快照 | ✅ 是 | 保存快照供离线分析 |
| **gc** | GC 统计 | ❌ 否 | 统计对象类型数量和大小 |
| **snapshot** | 内存快照 | ✅ 是 | 在内存中保存快照（FIFO，最多 2 个） |
| **diff** | 快照对比 | ✅ 是 | 对比最近两个 snapshot，查看内存增量变化 |
| **referrers** | 引用者查询 | ❌ 否 | 查找谁持有指定类型的对象（排查泄漏） |
| **referents** | 被引用者查询 | ❌ 否 | 查找指定类型对象引用了什么（分析结构） |

## 基本用法

### 1. 内存概览（overview）

查看进程当前内存状态，**无需启动追踪**。

```bash
# 查看内存概览（默认 action）
peeka-cli memory --action overview

# 或使用其他 action
peeka-cli memory --action start
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
peeka-cli memory --action start

# 自定义调用栈深度（1-50）
peeka-cli memory --action start --nframe 50
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
peeka-cli memory --action stop
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
peeka-cli memory --action dump --filename production_snapshot
peeka-cli memory --action stop
```

### 4. 查看 Top N 内存分配（top）

显示占用内存最多的代码位置（**需要先 start**）。

```bash
# 查看 top 20 分配（默认按行号分组）
peeka-cli memory --action top

# 查看 top 50 分配
peeka-cli memory --action top --limit 50

# 按文件名分组（查看哪个模块占用多）
peeka-cli memory --action top --group-by filename --limit 30
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
peeka-cli memory --action top --group-by filename --limit 10
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
peeka-cli memory --action dump

# 指定文件名
peeka-cli memory --action dump --filename my_snapshot

# 带路径遍历保护（自动提取 basename）
peeka-cli memory --action dump --filename "../etc/passwd"
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
peeka-cli memory --action gc

# 查看 top 50 对象类型
peeka-cli memory --action gc --limit 50
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


### 7. 内存快照（snapshot）

在内存中保存 tracemalloc 快照，用于后续 diff 对比（**需要先 start**）。

```bash
# 拍摄快照（最多保存 2 个，FIFO）
peeka-cli memory --action snapshot
```

**输出示例**：

```json
{
  "status": "success",
  "action": "snapshot",
  "snapshot_count": 1,
  "timestamp": 1738328400.0
}
```

**使用说明**：

- 快照保存在 Agent 内存中（不写入磁盘），最多保存 2 个
- 当超过 2 个时，自动丢弃最旧的快照（FIFO）
- 配合 `diff` 使用，用于分析一段时间内的内存变化
- 如需持久化快照到磁盘，请使用 `dump`

### 8. 快照对比（diff）

对比最近两个 snapshot 的内存变化（**需要先拍摄至少 2 个 snapshot**）。

```bash
# 先拍摄两个快照
peeka-cli memory --action snapshot
# ... 等待一段时间 ...
peeka-cli memory --action snapshot

# 对比差异
peeka-cli memory --action diff
```

**输出示例**：

```json
{
  "status": "success",
  "action": "diff",
  "diffs": [
    {
      "location": "/app/models.py:145",
      "size_diff": 1048576,
      "size_new": 2097152,
      "size_old": 1048576,
      "count_diff": 512,
      "count_new": 1024,
      "count_old": 512
    },
    {
      "location": "/app/cache.py:89",
      "size_diff": -524288,
      "size_new": 524288,
      "size_old": 1048576,
      "count_diff": -256,
      "count_new": 256,
      "count_old": 512
    }
  ]
}
```

**字段说明**：

| 字段 | 说明 |
|------|------|
| `location` | 代码位置（文件名:行号） |
| `size_diff` | 内存大小变化（正 = 增长，负 = 减少） |
| `size_new` | 新快照中的内存大小 |
| `size_old` | 旧快照中的内存大小 |
| `count_diff` | 分配块数变化 |
| `count_new` | 新快照中的分配块数 |
| `count_old` | 旧快照中的分配块数 |

**注意事项**：

- 结果按 `lineno` 分组，最多返回 50 条
- `size_diff > 0` 表示内存增长，是排查泄漏的重点
- 与 `dump` 离线对比不同，`diff` 在线完成，无需导出文件

### 9. 引用者查询（referrers）

查找谁持有指定类型的对象（**无需 start**）。适用于排查内存泄漏时追踪对象被谁引用。

```bash
# 查找谁引用了 dict 类型对象
peeka-cli memory --action referrers --type-name dict

# 增加递归深度和每层数量
peeka-cli memory --action referrers --type-name MyClass --max-depth 3 --max-per-level 15
```

**输出示例**：

```json
{
  "status": "success",
  "action": "referrers",
  "target": {
    "type": "MyClass",
    "repr_short": "<MyClass object at 0x7f...>",
    "count": 500
  },
  "referrers": [
    {
      "type": "dict",
      "repr_short": "{'user': <MyClass object at 0x7f...>, ...}",
      "referrers": [
        {
          "type": "list",
          "repr_short": "[{'user': <MyClass ...>}, ...] (len=500)"
        }
      ]
    }
  ]
}
```

**参数说明**：

| 参数 | 说明 | 范围 | 默认值 |
|------|------|------|--------|
| `--type-name` | 目标对象类型名 | 任意类型名 | **必填** |
| `--max-depth` | 递归查找深度 | 1-3 | 2 |
| `--max-per-level` | 每层最大引用者数 | 1-20 | 10 |

**使用场景**：

- 发现某类型对象数量异常增长后，用 `referrers` 追踪是谁持有这些对象
- 结合 `gc` 命令使用：先用 `gc` 发现异常类型，再用 `referrers` 追踪引用链

### 10. 被引用者查询（referents）

查找指定类型的对象引用了什么（**无需 start**）。适用于分析对象内部结构和持有关系。

```bash
# 查找 dict 类型对象引用了什么
peeka-cli memory --action referents --type-name dict

# 自定义深度
peeka-cli memory --action referents --type-name MyCache --max-depth 3
```

**输出示例**：

```json
{
  "status": "success",
  "action": "referents",
  "target": {
    "type": "MyCache",
    "repr_short": "<MyCache object at 0x7f...>",
    "count": 1
  },
  "referents": [
    {
      "type": "dict",
      "repr_short": "{'items': [...], 'max_size': 10000}",
      "referents": [
        {
          "type": "list",
          "repr_short": "[<Item ...>, <Item ...>, ...] (len=9500)"
        }
      ]
    }
  ]
}
```

**与 referrers 的区别**：

| 维度 | `referrers` | `referents` |
|------|------------|------------|
| **方向** | 向上：谁引用了我 | 向下：我引用了谁 |
| **用途** | 排查泄漏根因 | 分析对象结构 |
| **典型问题** | 为什么对象没被回收？ | 对象内部持有了什么？ |

## 完整诊断流程

### 场景 1：内存泄漏排查

```bash
# 1. 查看当前内存状态
peeka-cli memory --action overview

# 2. 用 GC 统计检查对象数量是否异常
peeka-cli memory --action gc --limit 50

# 3. 启动追踪
peeka-cli memory --action start --nframe 50

# 4. 等待一段时间（让问题复现）
sleep 300  # 5 分钟

# 5. 拍摄第一个内存快照
peeka-cli memory --action snapshot

# 6. 继续等待
sleep 300

# 7. 拍摄第二个内存快照
peeka-cli memory --action snapshot

# 8. 在线对比两个快照（无需导出文件）
peeka-cli memory --action diff

# 9. 查看 top 分配热点
peeka-cli memory --action top --limit 30

# 10. 针对可疑类型追踪引用链
peeka-cli memory --action referrers --type-name MyClass --max-depth 3

# 11. 导出快照供离线分析（可选）
peeka-cli memory --action dump --filename snapshot_leak

# 12. 停止追踪
peeka-cli memory --action stop
```

### 场景 2：性能优化

```bash
# 1. 启动追踪
peeka-cli memory --action start

# 2. 运行性能测试
# ... 触发业务操作 ...

# 3. 查看内存热点（按文件分组）
peeka-cli memory --action top --group-by filename --limit 20

# 4. 查看具体代码行（按行号分组）
peeka-cli memory --action top --group-by lineno --limit 50

# 5. 停止追踪
peeka-cli memory --action stop
```

### 场景 3：定期监控

```bash
#!/bin/bash
# 定时内存快照脚本

PID=12345
SNAPSHOT_DIR="/data/memory_snapshots"

# 启动追踪（首次）
peeka-cli memory --action start

# 每小时导出快照
while true; do
  timestamp=$(date +%Y%m%d_%H%M%S)
  peeka-cli memory --action dump --filename "snapshot_$timestamp"
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
   peeka-cli memory --action start
   # ... 永久运行 ...
   
   # ✅ 正确：短时间启动，诊断后立即停止
   peeka-cli memory --action start
   sleep 300  # 5 分钟
   peeka-cli memory --action dump --filename snapshot
   peeka-cli memory --action stop
   ```

2. **选择合适的 nframe**：
   ```bash
   # 生产环境：使用默认值 25
   peeka-cli memory --action start
   
   # 开发调试：使用更深的调用栈
   peeka-cli memory --action start --nframe 50
   ```

3. **低峰期使用 gc**：
   ```bash
   # gc 操作开销较大，建议在低峰期执行
   peeka-cli memory --action gc --limit 30
   ```

4. **定期导出快照**：
   ```bash
   # 每 1 小时导出一次，用于趋势分析
   while true; do
     peeka-cli memory --action dump --filename "snapshot_$(date +%H)"
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
peeka-cli memory --action dump
# 文件保存到：/data/peeka_dumps/peeka_dump_*.snapshot
```

## 常见问题

### 1. dump 失败："tracemalloc is not running"

**原因**：未启动 tracemalloc 就执行 dump。

**解决**：

```bash
# 先启动追踪
peeka-cli memory --action start

# 再导出快照
peeka-cli memory --action dump
```

### 2. top 结果为空

**可能原因**：

- 刚启动 tracemalloc，尚未捕获到分配
- 进程内存分配很少

**解决**：

```bash
# 等待一段时间后再查看
peeka-cli memory --action start
sleep 60
peeka-cli memory --action top
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
peeka-cli memory --action dump
ls -lt /data/dumps/
```

## 高级技巧

### 1. 自动化内存监控脚本

```bash
#!/bin/bash
# memory_monitor.sh - 自动内存监控

PID=$1
ALERT_THRESHOLD=1000000000  # 1GB

peeka-cli memory --action overview | \
  jq -r '.rss_bytes' | \
  while read rss; do
    if [ $rss -gt $ALERT_THRESHOLD ]; then
      echo "Alert: RSS > 1GB, capturing snapshot..."
      peeka-cli memory --action start
      sleep 30
      peeka-cli memory --action dump --filename "alert_$(date +%s)"
      peeka-cli memory --action stop
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


## 参考资料

- [Python tracemalloc 文档](https://docs.python.org/3/library/tracemalloc.html)
- [Python gc 模块文档](https://docs.python.org/3/library/gc.html)

- [Peeka 架构设计](../ARCHITECTURE.md)
- [Peeka 开发指南](../AGENTS.md)

## 更新日志

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| 0.1.0 | 2026-01 | 初始版本，支持 10 种 memory 操作 |

