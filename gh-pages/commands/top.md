---
layout: default
title: top 命令
parent: 命令参考
nav_order: 12
---

# top 命令
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}


## 简介

`top` 命令是一个函数级采样性能分析器（sampling profiler），类似于 Linux 的 `top` 命令和 `py-spy top`。通过定期采样所有线程的调用栈，统计每个函数的 CPU 使用情况，帮助开发者快速定位性能瓶颈。

**设计特点**：
- **低开销**：采样模式，性能影响 < 5%
- **实时统计**：流式输出性能数据，支持实时监控
- **函数粒度**：精确到函数级别，展示 own time 和 total time
- **自动过滤**：默认过滤 Peeka 自身线程，避免干扰

## 使用场景

- **性能瓶颈定位**：找出 CPU 占用最高的函数
- **热点函数分析**：统计函数调用频率和耗时分布
- **实时监控**：持续采样，观察程序性能变化
- **优化验证**：对比优化前后的性能数据

## 命令格式

```bash
peeka-cli attach <pid>    # 首先附加到目标进程
peeka-cli top [options]
```

### 参数说明

| 参数                | 说明                                    | 默认值    | 示例                        |
|-------------------|---------------------------------------|--------|---------------------------|
| `-i, --interval`  | 采样间隔（秒）                               | `0.01` | `-i 0.02`（20ms 采样一次）       |
| `-c, --cycles`    | 显示周期数（-1 表示无限）                        | `-1`   | `-c 10`（显示 10 次后自动停止）      |
| `--sort`          | 排序列（own / total / own-time / total-time） | `own`  | `--sort total`            |
| `--no-filter-peeka` | 禁用 Peeka 线程过滤（默认启用）                   | `false` | `--no-filter-peeka`（显示所有线程） |

### 性能指标说明

| 指标           | 说明                           | 计算方式                     |
|--------------|------------------------------|--------------------------|
| `own_pct`    | 独占 CPU 百分比（该函数自身耗时占比）       | `own_count / total_samples * 100` |
| `total_pct`  | 总 CPU 百分比（包括调用的子函数）         | `total_count / total_samples * 100` |
| `own_time`   | 独占时间（秒）                      | `own_count * interval`   |
| `total_time` | 总时间（秒，包括子函数）                 | `total_count * interval` |
| `own_count`  | 独占采样次数（栈顶为该函数的次数）            | 直接统计                     |
| `total_count` | 总采样次数（调用栈中包含该函数的次数）          | 去重统计                     |

## 基本用法

### 1. 启动性能分析

```bash
# 首先附加到目标进程
peeka-cli attach 12345

# 启动 top 命令（默认 10ms 采样间隔）
peeka-cli top
```

**输出示例**（流式输出，每秒更新一次）：

```json
{
  "type": "top_snapshot",
  "top_id": "top_a1b2c3d4",
  "total_samples": 1000,
  "sample_interval": 0.01,
  "functions": [
    {
      "name": "compute_matrix",
      "filename": "/app/algorithm.py",
      "line": 156,
      "own_pct": 45.3,
      "total_pct": 58.7,
      "own_time": 0.453,
      "total_time": 0.587,
      "own_count": 453,
      "total_count": 587
    },
    {
      "name": "multiply",
      "filename": "/app/math_utils.py",
      "line": 42,
      "own_pct": 12.8,
      "total_pct": 13.4,
      "own_time": 0.128,
      "total_time": 0.134,
      "own_count": 128,
      "total_count": 134
    },
    {
      "name": "log_result",
      "filename": "/app/logger.py",
      "line": 89,
      "own_pct": 8.2,
      "total_pct": 8.9,
      "own_time": 0.082,
      "total_time": 0.089,
      "own_count": 82,
      "total_count": 89
    }
  ]
}
```

### 2. 调整采样间隔

```bash
# 20ms 采样间隔（更低开销，但精度降低）
peeka-cli top -i 0.02

# 5ms 采样间隔（更高精度，但开销增加）
peeka-cli top -i 0.005
```

**采样间隔选择建议**：
- **生产环境**：10-20ms（默认 10ms），性能影响 < 5%
- **开发环境**：5-10ms，更高精度
- **长时间监控**：20-50ms，降低开销

### 3. 限制显示周期

```bash
# 显示 10 次后自动停止
peeka-cli top -c 10

# 显示 60 次后自动停止（约 1 分钟）
peeka-cli top -c 60
```

### 4. 按不同字段排序

```bash
# 按独占 CPU 百分比排序（默认）
peeka-cli top --sort own

# 按总 CPU 百分比排序
peeka-cli top --sort total

# 按独占时间排序
peeka-cli top --sort own-time

# 按总时间排序
peeka-cli top --sort total-time
```

### 5. 包含 Peeka 线程

```bash
# 显示所有线程，包括 Peeka 自身
peeka-cli top --no-filter-peeka
```

**注意**：启用 `--no-filter-peeka` 会显示 Peeka Agent 和采样线程本身，通常用于调试 Peeka 或验证过滤逻辑。

## 输出格式

### 流式输出（每秒一次快照）

```json
{
  "type": "top_snapshot",
  "top_id": "top_a1b2c3d4",
  "total_samples": 1000,
  "sample_interval": 0.01,
  "functions": [
    {
      "name": "compute_matrix",
      "filename": "/app/algorithm.py",
      "line": 156,
      "own_pct": 45.3,
      "total_pct": 58.7,
      "own_time": 0.453,
      "total_time": 0.587,
      "own_count": 453,
      "total_count": 587
    }
  ]
}
```

**字段说明**：

| 字段               | 说明                | 示例值                      |
|------------------|-------------------|--------------------------| 
| `top_id`         | 性能分析会话 ID        | `"top_a1b2c3d4"`         |
| `total_samples`  | 总采样次数             | `1000`                   |
| `sample_interval` | 采样间隔（秒）           | `0.01`                   |
| `functions`      | 函数统计列表（按 own_pct 降序） | `[...]`                  |

**functions 数组元素**：

| 字段           | 说明                 | 示例值                  |
|--------------|--------------------|----------------------|
| `name`       | 函数名                | `"compute_matrix"`   |
| `filename`   | 源文件路径              | `"/app/algorithm.py"` |
| `line`       | 函数定义行号             | `156`                |
| `own_pct`    | 独占 CPU 百分比        | `45.3`               |
| `total_pct`  | 总 CPU 百分比（含子函数）   | `58.7`               |
| `own_time`   | 独占时间（秒）            | `0.453`              |
| `total_time` | 总时间（秒，含子函数）        | `0.587`              |
| `own_count`  | 独占采样次数             | `453`                |
| `total_count` | 总采样次数（去重）          | `587`                |

## 实时监控示例

### 使用 jq 过滤 top 5 热点函数

```bash
peeka-cli top | jq 'select(.type == "top_snapshot") | .functions[:5]'
```

### 统计特定模块的 CPU 占用

```bash
peeka-cli top | jq '
  select(.type == "top_snapshot") |
  .functions[] |
  select(.filename | contains("/app/")) |
  {name, own_pct}
'
```

### 导出性能数据到文件

```bash
# 采集 100 次快照后停止，保存到文件
peeka-cli top -c 100 > performance.jsonl
```

## TUI 使用

在 TUI 模式下，`top` 命令提供可视化性能分析界面：

1. 启动 TUI：
   ```bash
   peeka  # 或 python -m peeka.tui
   ```

2. 连接到目标进程（输入 PID 或选择进程）

3. 按 **`0`** 键切换到 **Top 视图**

4. 功能：
   - 实时显示函数性能排行榜
   - 支持按 own_pct / total_pct / own_time / total_time 排序
   - 颜色编码：红色（high CPU）、黄色（medium）、绿色（low）
   - 显示采样统计（total_samples, interval）
   - 支持暂停/恢复采样

5. 快捷键：
   - `r`：刷新数据
   - `s`：切换排序字段
   - `Enter`：启动性能分析
   - `Delete`：停止性能分析
   - `c`：清空统计数据（reset）

## 工作原理

### 采样流程

1. **启动采样线程**：以指定间隔（默认 10ms）运行后台线程
2. **获取线程快照**：调用 `sys._current_frames()` 获取所有线程的当前栈帧
3. **过滤线程**：排除 Peeka 自身的线程（除非 `--no-filter-peeka`）
4. **遍历调用栈**：从栈顶（leaf frame）到栈底（root frame）逐帧统计
5. **更新统计**：
   - 栈顶帧：`own_count += 1`（函数自身执行）
   - 所有帧：`total_count += 1`（去重，包含调用链）
6. **生成快照**：每秒生成一次快照，推送到客户端

### 过滤策略

默认过滤以下线程（`--no-filter-peeka` 禁用）：
- 线程名以 `peeka-` 开头的线程
- 执行代码路径在 Peeka 包目录下的线程
- 采样线程自身

### 统计指标计算

```python
# 独占百分比
own_pct = (own_count / total_samples) * 100

# 总百分比
total_pct = (total_count / total_samples) * 100

# 独占时间
own_time = own_count * sample_interval

# 总时间
total_time = total_count * sample_interval
```

## 注意事项

1. **采样精度**：
   - 采样模式无法捕获所有函数调用，仅统计采样时刻的栈帧
   - 短时间执行的函数可能被遗漏
   - 适合长时间运行的性能分析，不适合微基准测试

2. **性能开销**：
   - 默认 10ms 间隔：性能影响 < 5%
   - 5ms 间隔：性能影响约 5-10%
   - 1ms 间隔：性能影响 10-20%（不推荐）

3. **线程过滤**：
   - 默认过滤 Peeka 线程，避免统计数据污染
   - 使用 `--no-filter-peeka` 可查看所有线程（包括 Peeka）

4. **输出频率**：
   - CLI 模式：每秒输出一次快照（固定）
   - 采样间隔和输出频率是独立的

5. **停止方式**：
   - Ctrl+C：正常停止，输出最终快照
   - `--cycles` 参数：自动停止
   - TUI 模式：按 `Delete` 键停止

6. **与 trace 命令的区别**：
   - `top`：采样模式，低开销，适合长时间监控
   - `trace`：插桩模式，高精度，适合短时间调用链分析
   - `top` 统计所有函数，`trace` 只跟踪指定函数

7. **权限要求**：
   - 需要先使用 `attach` 命令附加到目标进程
   - 附加权限要求请参考 [attach 命令文档](attach.html)
