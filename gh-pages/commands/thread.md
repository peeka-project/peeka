---
layout: default
title: thread 命令
parent: 命令参考
nav_order: 11
---

# thread 命令
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}


## 简介

`thread` 命令用于列出目标进程中的所有线程，并检查特定线程的调用栈信息。该命令能够帮助开发者快速定位线程状态、诊断死锁问题、分析线程阻塞原因等。



## 使用场景

- **线程枚举**：快速列出进程中的所有线程及其状态
- **状态过滤**：按线程状态（RUNNABLE/WAITING/TIMED_WAITING）筛选线程
- **堆栈检查**：查看特定线程的完整调用栈，定位代码执行位置
- **死锁诊断**：分析线程状态，发现潜在的死锁或阻塞问题
- **并发调试**：了解多线程程序的运行状态和线程分布

## 命令格式

```bash
peeka-cli attach <pid>    # 首先附加到目标进程
peeka-cli thread [options]
```

### 参数说明

| 参数           | 说明                                          | 默认值   | 示例                  |
|--------------|---------------------------------------------|-------|---------------------|
| `--tid`      | 线程 ID，用于查看特定线程的堆栈详情                        | 无     | `--tid 123456`      |
| `--state`    | 按状态过滤线程（RUNNABLE / WAITING / TIMED_WAITING） | 无     | `--state WAITING`   |
| `--sort-by`  | 排序字段（tid / name / state）                   | `tid` | `--sort-by name`    |
| `--depth`    | 堆栈深度限制（仅用于 detail 视图）                       | `50`  | `--depth 30`        |

### 线程状态说明

Peeka 通过分析线程的当前调用栈，自动推导线程状态：

| 状态             | 说明                                     | 典型场景                    |
|----------------|----------------------------------------|-------------------------|
| `RUNNABLE`     | 线程正在运行或可运行状态                           | 正常执行代码                  |
| `WAITING`      | 线程正在等待（无限期等待）                          | `wait()`, `join()`, `lock` 等 |
| `TIMED_WAITING` | 线程正在计时等待                               | `sleep()`, `poll()` 等     |

**状态推导算法**：检查线程栈顶 3 层调用帧，根据函数名和模块名匹配阻塞模式（如 `select`、`poll`、`wait`、`sleep` 等）。

## 基本用法

### 1. 列出所有线程

```bash
# 首先附加到目标进程
peeka-cli attach 12345

# 列出所有线程
peeka-cli thread
```

**输出示例**：

```json
{
  "status": "success",
  "action": "list",
  "total": 10,
  "threads": [
    {
      "tid": 140234567890,
      "native_id": 12345,
      "name": "MainThread",
      "daemon": false,
      "alive": true,
      "state": "RUNNABLE",
      "stack_depth": 15,
      "top_frame": {
        "filename": "/app/main.py",
        "lineno": 42,
        "funcname": "process_request"
      }
    },
    {
      "tid": 140234567891,
      "native_id": 12346,
      "name": "WorkerThread-1",
      "daemon": true,
      "alive": true,
      "state": "WAITING",
      "stack_depth": 8,
      "top_frame": {
        "filename": "/usr/lib/python3.12/threading.py",
        "lineno": 629,
        "funcname": "wait"
      }
    }
  ]
}
```

**字段说明**：

| 字段            | 说明                                  | 示例值                    |
|---------------|-------------------------------------|------------------------|
| `tid`         | 线程 ID（Python ident）                | `140234567890`         |
| `native_id`   | 原生线程 ID（Python 3.8+，可能为 None）     | `12345`                |
| `name`        | 线程名称                                | `"MainThread"`         |
| `daemon`      | 是否为守护线程                             | `false`                |
| `alive`       | 线程是否存活                              | `true`                 |
| `state`       | 推导的线程状态                             | `"RUNNABLE"`           |
| `stack_depth` | 调用栈深度                               | `15`                   |
| `top_frame`   | 栈顶帧信息（filename / lineno / funcname） | `{"filename": "...", ...}` |

### 2. 过滤特定状态的线程

```bash
# 只显示正在等待的线程
peeka-cli thread --state WAITING

# 只显示睡眠中的线程
peeka-cli thread --state TIMED_WAITING

# 只显示运行中的线程
peeka-cli thread --state RUNNABLE
```

### 3. 查看特定线程的堆栈详情

```bash
# 查看线程 140234567890 的完整堆栈
peeka-cli thread --tid 140234567890

# 限制堆栈深度为 30 层
peeka-cli thread --tid 140234567890 --depth 30
```

**输出示例**（detail 视图）：

```json
{
  "status": "success",
  "action": "detail",
  "thread": {
    "tid": 140234567890,
    "native_id": 12345,
    "name": "MainThread",
    "daemon": false,
    "alive": true,
    "state": "WAITING",
    "stack_depth": 8,
    "stack": [
      {
        "filename": "/usr/lib/python3.12/queue.py",
        "lineno": 171,
        "funcname": "get",
        "locals_keys": ["self", "block", "timeout"]
      },
      {
        "filename": "/app/worker.py",
        "lineno": 25,
        "funcname": "worker_loop",
        "locals_keys": ["queue", "item", "result"]
      },
      {
        "filename": "/app/main.py",
        "lineno": 100,
        "funcname": "run",
        "locals_keys": ["self", "config"]
      }
    ]
  }
}
```

**stack 字段说明**：

| 字段           | 说明              | 示例值                            |
|--------------|-----------------|--------------------------------|
| `filename`   | 源文件路径           | `"/app/worker.py"`             |
| `lineno`     | 行号              | `25`                           |
| `funcname`   | 函数名             | `"worker_loop"`                |
| `locals_keys` | 局部变量名列表（限制 20 个） | `["queue", "item", "result"]`  |

### 4. 按字段排序

```bash
# 按线程名称排序
peeka-cli thread --sort-by name

# 按线程状态排序
peeka-cli thread --sort-by state

# 按线程 ID 排序（默认）
peeka-cli thread --sort-by tid
```

## 输出格式

### list 输出（列表模式）

```json
{
  "status": "success",
  "action": "list",
  "total": 10,
  "threads": [
    {
      "tid": 140234567890,
      "native_id": 12345,
      "name": "MainThread",
      "daemon": false,
      "alive": true,
      "state": "RUNNABLE",
      "stack_depth": 15,
      "top_frame": {
        "filename": "/app/main.py",
        "lineno": 42,
        "funcname": "process_request"
      }
    }
  ]
}
```

### detail 输出（详情模式）

```json
{
  "status": "success",
  "action": "detail",
  "thread": {
    "tid": 140234567890,
    "native_id": 12345,
    "name": "MainThread",
    "daemon": false,
    "alive": true,
    "state": "WAITING",
    "stack_depth": 8,
    "stack": [
      {
        "filename": "/usr/lib/python3.12/queue.py",
        "lineno": 171,
        "funcname": "get",
        "locals_keys": ["self", "block", "timeout"]
      }
    ]
  }
}
```

## TUI 使用

在 TUI 模式下，可以通过交互界面查看线程信息：

1. 启动 TUI：
   ```bash
   peeka  # 或 python -m peeka.tui
   ```

2. 连接到目标进程（输入 PID 或选择进程）

3. 按 **`9`** 键切换到 **Threads 视图**

4. 功能：
   - 实时显示所有线程列表
   - 按状态筛选线程
   - 选中线程查看堆栈详情
   - 支持按名称、状态、ID 排序

## 注意事项

1. **状态推导准确性**：
   - 线程状态是通过分析调用栈推导而来，可能存在误判
   - 仅检查栈顶 3 层帧，深层阻塞可能无法识别
   - RUNNABLE 状态包括正在运行和可运行两种情况

2. **native_id 可用性**：
   - `native_id` 字段仅在 Python 3.8+ 可用
   - 旧版本 Python 中该字段为 `null`

3. **局部变量限制**：
   - detail 视图的 `locals_keys` 字段最多显示 20 个局部变量名
   - 变量值不会被获取，避免触发副作用

4. **性能影响**：
   - 获取线程信息使用 `sys._current_frames()` 和 `threading.enumerate()`
   - 性能开销极低，但在线程数量极大（>1000）时可能有延迟

5. **权限要求**：
   - 需要先使用 `attach` 命令附加到目标进程
   - 附加权限要求请参考 [attach 命令文档](attach.html)
