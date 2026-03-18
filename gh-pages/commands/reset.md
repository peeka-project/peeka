---
layout: default
title: reset 命令
parent: 命令参考
nav_order: 10
---

# reset 命令
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}


## 简介

`reset` 命令用于**恢复被增强的方法到原始状态**，移除 `watch`、`stack` 等命令注入的观测逻辑。这是一个清理命令，可以选择性地重置所有增强或仅重置匹配特定模式的增强。



## 使用场景

- **诊断结束后清理**：完成故障排查后，移除所有注入的观测逻辑
- **重新配置观测**：在使用不同参数重新观测前，先重置现有增强
- **选择性清理**：只移除特定模块或类的增强，保留其他观测
- **查看当前状态**：列出所有当前活跃的增强，了解系统状态
- **性能恢复**：移除观测逻辑以消除性能开销

## TUI 使用

**注意**：reset 命令在 TUI 中**暂无独立视图**，但可以通过命令输入框执行：

- 在 TUI 主界面按 `:` 进入命令模式
- 输入 `reset` 命令执行重置

**常用操作**：
- 列出所有增强：`: reset --list` 或 `: reset -l`
- 重置所有增强：`: reset`
- 重置特定模式：`: reset "myapp.service.*"`

**快捷方式**：各个视图内通常有独立的“停止”按钮，无需手动输入 reset 命令。

**CLI 等效命令**：下文所有示例使用 CLI 命令演示。
## 命令格式

```bash
peeka-cli reset [pattern] [options]
```

**使用前提**：需要先使用 `peeka-cli attach <pid>` 附加到目标进程

### 参数说明

| 参数           | 说明                    | 默认值 | 示例                  |
|--------------|------------------------|-----|---------------------|
| `pattern`    | 可选的匹配模式（支持通配符）      | 无   | `"myapp.service.*"` |
| `-l, --list` | 列出当前增强而不是重置它们       | -   | `--list`            |

### 模式匹配规则

`pattern` 参数支持 Unix shell 风格的通配符（基于 fnmatch）：

| 通配符 | 含义     | 示例                                | 匹配                               |
|-----|--------|-----------------------------------|----------------------------------|
| `*` | 匹配任意字符 | `myapp.service.*`                 | `myapp.service.UserService`      |
| `?` | 匹配单个字符 | `myapp.?.query`                   | `myapp.a.query`, `myapp.b.query` |
| 无   | 精确匹配   | `myapp.service.UserService.query` | 仅匹配完全相同的模式                       |

**注意**：模式匹配是对**存储的模式**进行匹配，而不是对函数名进行匹配。

## 输出格式

### reset 操作响应

```json
{
  "status": "success",
  "action": "reset",
  "affected": [
    {
      "watch_id": "watch_a1b2c3d4",
      "pattern": "myapp.service.UserService.query"
    },
    {
      "watch_id": "watch_e5f6g7h8",
      "pattern": "myapp.service.UserService.update"
    }
  ],
  "count": 2
}
```

**字段说明**：

| 字段         | 类型     | 说明                      |
|------------|--------|-------------------------|
| `status`   | string | 操作状态（`success`/`error`） |
| `action`   | string | 操作类型（`reset`）           |
| `affected` | array  | 被重置的增强列表                |
| `count`    | int    | 成功重置的数量                 |

**affected 数组元素**：

| 字段         | 类型     | 说明           |
|------------|--------|--------------|
| `watch_id` | string | 观测会话 ID      |
| `pattern`  | string | 原始的函数匹配模式    |
| `error`    | string | （可选）重置失败时的错误 |

### list 操作响应

```json
{
  "status": "success",
  "action": "list",
  "enhanced": [
    {
      "watch_id": "watch_a1b2c3d4",
      "pattern": "myapp.service.UserService.query",
      "command": "watch",
      "count": 42
    },
    {
      "watch_id": "stack_i9j0k1l2",
      "pattern": "myapp.handler.process",
      "command": "stack",
      "count": 15
    }
  ],
  "total": 2
}
```

**字段说明**：

| 字段         | 类型     | 说明           |
|------------|--------|--------------|
| `status`   | string | 操作状态         |
| `action`   | string | 操作类型（`list`） |
| `enhanced` | array  | 当前增强列表       |
| `total`    | int    | 增强总数         |

**enhanced 数组元素**：

| 字段         | 类型     | 说明                       |
|------------|--------|--------------------------|
| `watch_id` | string | 观测会话 ID                  |
| `pattern`  | string | 函数匹配模式                   |
| `command`  | string | 创建增强的命令（`watch`/`stack`） |
| `count`    | int    | 已捕获的观测次数                 |

## 使用示例

### 示例 1：重置所有增强

```bash
# 重置所有增强
peeka-cli reset
```

**输出**：

```json
{
  "status": "success",
  "action": "reset",
  "affected": [
    {"watch_id": "watch_001", "pattern": "myapp.service.query"},
    {"watch_id": "watch_002", "pattern": "myapp.handler.process"},
    {"watch_id": "stack_003", "pattern": "myapp.api.handle"}
  ],
  "count": 3
}
```

**用途**：

- 诊断结束后的完整清理
- 恢复系统到无观测状态
- 消除所有性能开销

### 示例 2：按模式重置

```bash
# 只重置 myapp.service 模块的增强
peeka-cli reset "myapp.service.*"

# 重置特定类的所有方法
peeka-cli reset "myapp.service.UserService.*"

# 重置特定方法
peeka-cli reset "myapp.service.UserService.query"
```

**输出**（匹配 2 个增强）：

```json
{
  "status": "success",
  "action": "reset",
  "affected": [
    {"watch_id": "watch_001", "pattern": "myapp.service.UserService.query"},
    {"watch_id": "watch_002", "pattern": "myapp.service.UserService.update"}
  ],
  "count": 2
}
```

**用途**：

- 选择性清理特定模块
- 保留其他模块的观测
- 重新配置特定函数的观测参数

### 示例 3：无匹配的模式

```bash
# 模式不匹配任何增强
peeka-cli reset "nonexistent.*"
```

**输出**：

```json
{
  "status": "success",
  "action": "reset",
  "affected": [],
  "count": 0
}
```

### 示例 4：列出当前增强

```bash
# 查看所有活跃的增强
peeka-cli reset --list
```

**输出**：

```json
{
  "status": "success",
  "action": "list",
  "enhanced": [
    {
      "watch_id": "watch_a1b2c3d4",
      "pattern": "myapp.service.UserService.query",
      "command": "watch",
      "count": 42
    },
    {
      "watch_id": "stack_i9j0k1l2",
      "pattern": "myapp.handler.process",
      "command": "stack",
      "count": 15
    }
  ],
  "total": 2
}
```

**用途**：

- 了解当前系统状态
- 确认观测是否仍然活跃
- 决定需要重置哪些增强

### 示例 5：列出空增强

```bash
# 当没有活跃增强时
peeka-cli reset --list
```

**输出**：

```json
{
  "status": "success",
  "action": "list",
  "enhanced": [],
  "total": 0
}
```

### 示例 6：与 jq 结合使用

```bash
# 提取重置计数
peeka-cli reset | jq '.count'
# 输出: 3

# 提取受影响的模式列表
peeka-cli reset "myapp.*" | jq -r '.affected[].pattern'
# 输出:
# myapp.service.query
# myapp.handler.process

# 统计当前增强数量
peeka-cli reset --list | jq '.total'
# 输出: 5

# 查看特定命令的增强
peeka-cli reset --list | jq '.enhanced[] | select(.command == "watch")'

# 按观测次数排序
peeka-cli reset --list | jq '.enhanced | sort_by(.count) | reverse'
```

## 典型工作流程

### 工作流程 1：诊断后清理

```bash
# 1. 开始诊断
peeka-cli watch "myapp.service.query" -n 100

# 2. 查看观测数据（100 次后自动停止）
# ... 分析数据 ...

# 3. 诊断结束，清理所有增强
peeka-cli reset

# 验证
peeka-cli reset --list
# 输出: {"total": 0}
```

### 工作流程 2：重新配置观测

```bash
# 1. 当前正在观测（深度为 2）
peeka-cli watch "myapp.service.query" -x 2

# 2. 发现需要更深的输出（深度 3）
# 先重置当前观测
peeka-cli reset "myapp.service.query"

# 3. 使用新参数重新观测
peeka-cli watch "myapp.service.query" -x 3
```

### 工作流程 3：多模块诊断

```bash
# 1. 观测多个模块
peeka-cli watch "myapp.service.*" &
peeka-cli watch "myapp.handler.*" &
peeka-cli watch "myapp.api.*" &

# 2. 诊断完 service 模块后，只清理 service
peeka-cli reset "myapp.service.*"

# 3. 继续观测其他模块
# handler 和 api 的观测继续运行

# 4. 全部结束后清理
peeka-cli reset
```

### 工作流程 4：定期检查状态

```bash
#!/bin/bash
# check_enhancements.sh - 定期检查增强状态

while true; do
  TOTAL=$(peeka-cli reset --list | jq '.total')
  echo "$(date): 活跃增强数量 = $TOTAL"
  
  if [ "$TOTAL" -gt 10 ]; then
    echo "警告：增强数量过多，考虑清理"
  fi
  
  sleep 300  # 每 5 分钟检查一次
done
```

## 注意事项

### ⚠️ Monitor 命令不受影响

`reset` 命令**仅影响 `watch` 和 `stack` 命令**创建的增强。`monitor` 命令使用独立的追踪机制，不会被 reset 清理。

```bash
# monitor 不受影响
peeka-cli monitor 12345 "myapp.service.query"  # 启动监控

peeka-cli reset                        # 重置不会停止 monitor

# 需要单独停止 monitor
peeka-cli reset "myapp.service.*"
```

### ⚠️ 模式匹配规则

模式是对**存储的模式**进行匹配，而不是对函数名：

```bash
# 假设之前执行了：
peeka-cli watch "myapp.service.UserService.query"

# ✅ 正确：匹配存储的模式
peeka-cli reset "myapp.service.*"              # 匹配成功
peeka-cli reset "myapp.service.UserService.*"  # 匹配成功

# ❌ 错误：尝试匹配类名（不会工作）
peeka-cli reset "UserService.*"                # 不匹配
```

### ⚠️ 重置不可撤销

重置操作会立即移除增强逻辑，**无法撤销**。如果需要继续观测，必须重新执行 `watch` 或 `stack` 命令。

```bash
# 重置后需要重新观测
peeka-cli reset "myapp.service.query"
peeka-cli watch "myapp.service.query" -n 100  # 重新开始观测
```

### ⚠️ 性能恢复

重置后，函数会恢复到原始状态，性能开销会立即消失：

| 状态        | 性能开销 |
|-----------|------|
| 增强前       | 0%   |
| watch 观测中 | 2-5% |
| 重置后       | 0%   |

### ⚠️ 并发安全

reset 命令是线程安全的，但在高并发场景下可能出现边缘情况：

- 重置时，正在进行的观测可能仍会产生数据
- 重置后立即发生的调用会使用原始函数

## 常见问题

### Q1: reset 和停止流式观测有什么区别？

**A**:

- `reset`：移除函数上注入的装饰器，永久删除增强逻辑
- `Ctrl+C`（或关闭 CLI）：停止客户端流式接收数据，但增强逻辑仍在目标进程中

**时序说明**：

```
Ctrl+C 停止流式客户端：观测数据停止返回，但增强仍运行
reset 移除增强：删除目标进程中的装饰器，完全恢复原始函数
```

**推荐使用**：

- 临时暂停观测：使用 `Ctrl+C`（只断开客户端连接）
- 彻底清理增强：使用 `reset` 命令（删除注入的逻辑）
- 后续不再观测某函数：先 `reset`，再启动其他诊断

```bash
# 方法 1：临时停止（客户端断开）
# Ctrl+C

# 方法 2：彻底清理（移除增强）
peeka-cli reset "myapp.service.*"
```

### Q2: 如何重置特定 watch_id？

**A**: reset 不直接支持 watch_id 参数，但可以通过精确模式匹配：

```bash
# 1. 查看 watch_id 对应的模式
peeka-cli reset --list | jq '.enhanced[] | select(.watch_id == "watch_001")'
# 输出: {"watch_id": "watch_001", "pattern": "myapp.service.query", ...}

# 2. 使用精确模式重置
peeka-cli reset "myapp.service.query"
```

**或者直接使用 watch stop**：

```bash
peeka-cli reset "watch_001"
```

### Q3: reset 会影响正在运行的函数吗？

**A**: 不会。reset 只替换函数引用，不会中断正在执行的调用。

**时序说明**：

```
时刻 T0: 函数 A 开始执行（使用增强版本）
时刻 T1: 执行 reset（替换函数引用）
时刻 T2: 函数 A 继续执行（仍使用增强版本，因为已经进入）
时刻 T3: 函数 A 结束（产生观测数据）
时刻 T4: 新的函数 A 调用（使用原始版本）
```

### Q4: 模式不匹配任何增强是错误吗？

**A**: 不是错误，返回 `count: 0`。

```bash
peeka-cli reset "nonexistent.*"
# 输出: {"status": "success", "count": 0}
```

这是预期行为，便于脚本使用（不会因为无匹配而报错）。

### Q5: 如何重置所有 watch 但保留 stack？

**A**: 当前版本不支持按命令类型过滤，但可以通过模式匹配间接实现：

```bash
# 如果 watch 和 stack 使用不同的模块
peeka-cli reset "myapp.service.*"  # 假设只有 watch 观测这个模块
```

**未来计划**：支持 `--command watch` 参数进行过滤。

### Q6: reset --list 输出太多怎么办？

**A**: 使用 jq 过滤：

```bash
# 只看 watch 命令的增强
peeka-cli reset --list | jq '.enhanced[] | select(.command == "watch")'

# 只看特定模块的增强
peeka-cli reset --list | jq '.enhanced[] | select(.pattern | startswith("myapp.service"))'

# 按观测次数排序
peeka-cli reset --list | jq '.enhanced | sort_by(.count) | reverse'
```


## 高级技巧

### 技巧 1：自动清理脚本

```bash
#!/bin/bash
# auto_cleanup.sh - 诊断结束后自动清理

PID=$1
PATTERN=${2:-"*"}  # 默认清理所有

# 执行诊断
peeka-cli watch "$PATTERN" -n 100

# 等待完成（100 次后自动停止）
sleep 5

# 自动清理
peeka-cli reset "$PATTERN"
echo "已清理 $PATTERN 的增强"
```

### 技巧 2：增强状态监控

```bash
#!/bin/bash
# monitor_enhancements.sh - 监控增强状态

while true; do
  LIST=$(peeka-cli reset --list)
  TOTAL=$(echo "$LIST" | jq '.total')
  
  echo "$(date): 活跃增强: $TOTAL"
  
  if [ "$TOTAL" -gt 0 ]; then
    echo "$LIST" | jq -r '.enhanced[] | "\(.pattern): \(.count) 次观测"'
  fi
  
  sleep 60
done
```

### 技巧 3：选择性批量重置

```bash
# 重置多个特定模块
for module in service handler api; do
  echo "重置 myapp.$module"
  peeka-cli reset "myapp.$module.*"
done
```

### 技巧 4：条件清理

```bash
# 只清理观测次数超过 1000 的增强
peeka-cli reset --list | \
  jq -r '.enhanced[] | select(.count > 1000) | .pattern' | \
  while read pattern; do
    peeka-cli reset "$pattern"
  done
```

### 技巧 5：导出增强状态

```bash
# 导出当前增强状态（用于恢复）
peeka-cli reset --list > enhancements_backup.json

# 分析历史数据
jq '.enhanced[] | {pattern, count}' enhancements_backup.json
```

## 最佳实践

### ✅ 推荐

1. **诊断前记录状态**
   ```bash
   peeka-cli reset --list > before.json
   ```

2. **使用模式匹配进行模块级清理**
   ```bash
   peeka-cli reset "myapp.service.*"  # 清理整个模块
   ```

3. **诊断结束后立即清理**
   ```bash
   peeka-cli watch "func" -n 100  # 观测 100 次
   peeka-cli reset             # 立即清理
   ```

4. **定期检查增强状态**
   ```bash
   peeka-cli reset --list | jq '.total'
   ```

5. **使用 jq 处理输出**
   ```bash
   peeka-cli reset | jq -r '.affected[].pattern'
   ```

### ❌ 避免

1. **长期保留增强不清理**
    - 性能开销持续存在
    - 内存占用增加
    - 可能影响业务

2. **忘记重置 monitor**
   ```bash
   # ❌ reset 不会停止 monitor
   peeka-cli reset
   
   # ✅ 需要单独停止
   peeka-cli reset "myapp.service.*"
   ```

3. **过度使用精确模式**
   ```bash
   # ❌ 逐个重置（效率低）
   peeka-cli reset "myapp.service.func1"
   peeka-cli reset "myapp.service.func2"
   
   # ✅ 使用通配符（效率高）
   peeka-cli reset "myapp.service.*"
   ```

4. **不检查重置结果**
   ```bash
   # ❌ 假设重置成功
   peeka-cli reset "pattern"
   
   # ✅ 验证结果
   RESULT=$(peeka-cli reset "pattern")
   echo "$RESULT" | jq '.count'
   ```

## 相关命令

- [`watch`](watch.md) - 观测函数调用
- [`stack`](stack.md) - 追踪函数调用栈
- [`monitor`](monitor.md) - 性能统计监控

## 更新日志

| 版本    | 日期         | 更新内容                    |
|-------|------------|-------------------------|
| 0.1.0 | 2025-01-31 | 初始版本，支持 reset 和 list 功能 |

