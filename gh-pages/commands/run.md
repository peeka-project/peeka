---
layout: default
title: run 命令
parent: 命令参考
nav_order: 14
---

# run 命令
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}


## 简介

`run` 命令用于**启动 Python 脚本时即注入 Peeka**，无需目标进程已在运行。适用于需要观测**导入期代码**、**初始化逻辑**或**短生命周期脚本**的场景。

与先 `attach` 再观测的方式不同，`run` 命令从脚本第一行开始就具备完整的诊断能力。


## 使用场景

- **观测导入期逻辑**：捕获模块加载、类初始化等只在启动时执行一次的代码
- **短生命周期脚本**：进程运行时间太短，来不及手动 attach
- **批处理任务**：Cron 任务、数据管道、一次性脚本的诊断
- **CI/CD 调试**：在自动化流水线中捕获函数行为而无需修改代码
- **复现问题**：精确控制启动条件，复现只在启动时出现的 bug

## 命令格式

```bash
peeka-cli run <script> [script_args] -- <command> [command_options]
```

`--` 是分隔符，左边是脚本及其参数，右边是 Peeka 命令及其选项。

### 参数说明

| 参数               | 说明                              | 默认值 |
|--------------------|-----------------------------------|--------|
| `script`           | 要运行的 Python 脚本路径           | —      |
| `script_args`      | 传递给脚本的参数（可选）           | —      |
| `--`               | 必须的分隔符                       | —      |
| `command`          | Peeka 命令（watch / trace / stack）| —      |
| `command_options`  | 该命令的选项                       | —      |
| `--output-file`    | 将 JSONL 输出写入文件而非 stdout   | —      |

### 支持的子命令

`run` 后的 Peeka 命令支持与独立使用时相同的所有选项：

| 子命令  | 用途                          |
|---------|-------------------------------|
| `watch` | 观测函数调用（入参、返回值、耗时） |
| `trace` | 追踪调用树及时序               |
| `stack` | 在函数入口捕获调用栈           |

## 使用示例

### 示例 1：最简单的用法

```bash
peeka-cli run myscript.py -- watch "mymodule.MyClass.init_db"
```

从脚本启动即观测 `init_db` 方法，捕获所有调用。

### 示例 2：传递脚本参数

```bash
peeka-cli run myscript.py --env production --config /etc/app.yml -- watch "mymodule.func"
```

`--env` 和 `--config` 传给脚本，`watch "mymodule.func"` 是 Peeka 命令。

### 示例 3：使用 trace 追踪调用树

```bash
peeka-cli run myscript.py -- trace "mymodule.func" -d 3
```

追踪 `mymodule.func` 的调用树，最大深度 3 层。

### 示例 4：带条件过滤

```bash
peeka-cli run myscript.py -- watch "mymodule.func" --condition "params[0] > 100"
```

只捕获第一个参数大于 100 的调用。

### 示例 5：输出到文件

```bash
peeka-cli run myscript.py -- watch "mymodule.func" --output-file observations.jsonl
```

将所有观测数据写入 `observations.jsonl`，脚本的 stdout 不受影响。

### 示例 6：限制观测次数

```bash
peeka-cli run myscript.py -- watch "mymodule.func" -n 10
```

捕获 10 次后自动停止观测。

### 示例 7：捕获调用栈

```bash
peeka-cli run myscript.py -- stack "mymodule.func" -n 3
```

在 `mymodule.func` 入口处捕获调用栈，共 3 次。

## 输出格式

输出格式与 `watch`/`trace`/`stack` 命令完全相同——每行一个 JSON 对象（JSONL），带有 `type` 字段：

```json
{"type": "event", "event": "watch_started", "data": {"watch_id": "watch_001", "pattern": "mymodule.func"}}
{
  "type": "observation",
  "watch_id": "watch_001",
  "timestamp": 1705586200.123,
  "func_name": "mymodule.MyClass.func",
  "args": ["hello", 42],
  "kwargs": {},
  "result": true,
  "success": true,
  "duration_ms": 1.23,
  "count": 1
}
{"type": "event", "event": "watch_stopped", "data": {"watch_id": "watch_001"}}
```

### 使用 jq 处理输出

```bash
# 只看观测数据
peeka-cli run myscript.py -- watch "mymodule.func" | jq 'select(.type == "observation")'

# 找慢调用
peeka-cli run myscript.py -- watch "mymodule.func" | jq 'select(.type == "observation" and .data.duration_ms > 100)'

# 保存并分析
peeka-cli run myscript.py -- watch "mymodule.func" --output-file out.jsonl
jq '.args' out.jsonl
```

## run 与 attach 的区别

| 特性               | `run`                          | `attach`                        |
|--------------------|--------------------------------|---------------------------------|
| 目标进程状态       | 由 Peeka 启动                  | 进程已在运行                    |
| 观测范围           | 从第一行代码开始                | 从 attach 时刻开始              |
| 适用场景           | 短生命周期、导入期逻辑          | 长期运行的服务                  |
| 启动方式           | `peeka-cli run script.py -- …` | `peeka-cli attach <pid>`        |
| 需要 ptrace/PEP768 | 否（直接注入）                  | 是                              |

**选择建议**：
- 生产服务、守护进程 → 使用 `attach`
- 脚本、批处理任务、启动期诊断 → 使用 `run`

## 注意事项

### ⚠️ `--` 分隔符是必须的

```bash
# ✅ 正确：-- 分隔脚本参数与 Peeka 命令
peeka-cli run myscript.py arg1 -- watch "mymodule.func"

# ❌ 错误：缺少 -- 会导致解析错误
peeka-cli run myscript.py arg1 watch "mymodule.func"
```

### ⚠️ 脚本退出后观测自动结束

当脚本正常退出或异常退出时，观测自动停止。如需持续观测，请使用 `attach` 模式连接长期运行的进程。

### ⚠️ --output-file 只影响 Peeka 输出

`--output-file` 将 Peeka 的 JSONL 诊断数据写入指定文件，不影响脚本本身的 stdout/stderr。

```bash
# 脚本的 print() 输出到终端，Peeka 数据写到文件
peeka-cli run myscript.py -- watch "mymodule.func" --output-file peeka.jsonl
```

## 典型工作流程

### 工作流程：诊断批处理脚本

```bash
# 1. 运行脚本并观测关键函数
peeka-cli run batch_job.py --date 2024-01-15 -- watch "etl.transform" --output-file etl_obs.jsonl

# 2. 分析结果
jq 'select(.type == "observation")' etl_obs.jsonl | jq -s 'sort_by(.data.duration_ms) | reverse | .[0:5]'

# 3. 找出慢调用
jq 'select(.type == "observation" and .data.duration_ms > 500)' etl_obs.jsonl
```

### 工作流程：观测初始化逻辑

```bash
# 观测应用启动时的数据库连接
peeka-cli run app.py -- watch "db.DatabasePool.connect" -n 5

# 追踪配置加载调用树
peeka-cli run app.py -- trace "config.load_settings" -d 4
```

## 相关命令

- [`attach`](attach.md) - 附加到已运行的进程
- [`watch`](watch.md) - 观测函数调用
- [`trace`](trace.md) - 追踪调用树
- [`stack`](stack.md) - 捕获调用栈

## 更新日志

| 版本    | 日期         | 更新内容        |
|-------|------------|---------------|
| 0.1.8 | 2025-04-28 | 新增 run 命令文档 |
