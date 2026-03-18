---
layout: default
title: detach 命令
parent: 命令参考
nav_order: 13
---

# detach 命令
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}


## 简介

`detach` 命令用于从目标进程中分离 Peeka Agent，停止所有诊断活动，恢复目标进程到原始状态。该命令会清理所有注入的观测逻辑、关闭 Agent 服务、删除临时文件，确保目标进程不受影响。

## 使用场景

- **完成诊断**：诊断工作完成后，干净地退出
- **避免资源占用**：释放 Agent 占用的内存和文件描述符
- **恢复原始状态**：移除所有函数增强和观测逻辑
- **切换目标进程**：从当前进程分离，准备附加到其他进程

## 命令格式

```bash
peeka-cli attach <pid>    # 首先附加到目标进程
# ... 执行诊断命令 ...
peeka-cli detach          # 完成后分离
```

**注意**：`detach` 命令没有任何参数。

## 分离过程

`detach` 命令执行以下清理操作：

1. **停止所有活动观测**：
   - 停止所有 `watch` 观测
   - 停止所有 `trace` 追踪
   - 停止所有 `stack` 捕获
   - 停止所有 `monitor` 监控
   - 停止 `top` 性能分析

2. **恢复增强函数**：
   - 调用 `injector.uninject_all()` 移除所有装饰器
   - 恢复函数到原始状态（去除 `__peeka_original__` 包装）

3. **清理观测数据**：
   - 清空观测缓冲区
   - 注销所有 watch ID

4. **关闭 Agent 服务**：
   - 关闭 Unix Domain Socket
   - 停止 Agent 监听线程
   - 删除 socket 文件（`/tmp/peeka_<pid>.sock`）

5. **释放资源**：
   - 清理内存缓冲区
   - 关闭文件描述符
   - 停止后台线程

## 基本用法

### 1. 正常分离

```bash
# 首先附加到目标进程
peeka-cli attach 12345

# 执行诊断命令
peeka-cli watch "mymodule.func" -n 10
peeka-cli monitor "mymodule.func" --interval 1 -c 5

# 完成后分离
peeka-cli detach
```

**输出示例**：

```json
{
  "type": "success",
  "command": "detach",
  "data": {
    "pid": 12345,
    "message": "Detached from process 12345"
  }
}
```

### 2. 分离失败

如果分离过程中发生错误：

```json
{
  "type": "error",
  "command": "detach",
  "error": "Failed to restore function: mymodule.func"
}
```

**处理方式**：
- 如果错误是非关键性的（如某个函数恢复失败），Agent 会继续清理其他资源
- 如果错误是关键性的（如 socket 关闭失败），建议重启目标进程

## TUI 使用

在 TUI 模式下：

1. 启动 TUI：
   ```bash
   peeka  # 或 python -m peeka.tui
   ```

2. 连接到目标进程后，按 **`1`** 键返回 Dashboard 视图

3. 在 Dashboard 中，输入命令：
   ```
   detach
   ```

4. 或者直接按 **`q`** 键退出 TUI（会自动执行 detach）

## 注意事项

1. **自动清理**：
   - Peeka Agent 在异常退出时会尽力执行清理（best-effort）
   - 但不保证 100% 恢复，建议使用 `detach` 命令正常退出

2. **函数恢复**：
   - 大多数情况下，函数会完全恢复到原始状态
   - 极少数情况下，如果函数被其他代码同时修改，可能无法完全恢复

3. **观测数据丢失**：
   - `detach` 后，所有未消费的观测数据会被清空
   - 如果需要保留数据，请在 `detach` 前确保所有数据已保存

4. **Socket 文件清理**：
   - Socket 文件（`/tmp/peeka_<pid>.sock`）会被自动删除
   - 如果进程异常退出，可能需要手动清理

5. **性能恢复**：
   - `detach` 后，目标进程性能应立即恢复到原始水平
   - 如果仍有性能问题，可能是目标进程本身的问题

6. **重新附加**：
   - `detach` 后可以再次 `attach` 到同一进程
   - 每次 `attach` 会创建新的 socket 文件和 Agent 实例

7. **进程终止**：
   - 如果目标进程在 `detach` 之前终止，Agent 会自动清理
   - 不需要手动执行 `detach`

## 与 attach 命令的关系

`attach` 和 `detach` 是成对的操作：

```bash
# 生命周期
peeka-cli attach <pid>    # 注入 Agent，启动服务
# ... 诊断操作 ...
peeka-cli detach          # 清理 Agent，恢复原状
```

**资源使用对比**：

| 状态        | Socket 文件 | 内存占用   | 函数增强 | 后台线程 |
|-----------|---------|--------|------|------|
| attach 前  | 无       | 0      | 无    | 0    |
| attach 后  | 存在      | ~10MB  | 根据命令 | 1-5  |
| detach 后  | 无       | 0      | 无    | 0    |

## 故障排除

### 1. detach 命令无响应

```bash
# 强制终止 Agent（不推荐）
kill -9 <pid_of_agent_thread>
```

### 2. Socket 文件未清理

```bash
# 手动删除 socket 文件
rm /tmp/peeka_<pid>.sock
```

### 3. 函数未恢复

如果 `detach` 后函数行为异常：

1. 检查是否有其他诊断工具同时附加
2. 重启目标进程
3. 检查 Peeka 版本是否与目标 Python 版本兼容

### 4. 内存未释放

如果 `detach` 后目标进程内存未下降：

- 这可能是 Python 内存管理的正常行为
- Python 解释器不会立即释放内存给操作系统
- 可以手动触发垃圾回收：`peeka-cli memory --action gc`（在 detach 之前）

## 权限要求

`detach` 命令需要：
- 已成功 `attach` 到目标进程
- 与目标进程保持连接（socket 可用）

**不需要**额外权限，因为清理操作在目标进程内部执行。
