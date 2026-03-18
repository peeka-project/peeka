---
layout: default
title: Peeka Logger 命令详解
parent: 命令参考
nav_order: 6
---

# Peeka Logger 命令详解
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 命令简介

`logger` 命令用于在运行时动态查看和调整 Python 应用程序的日志级别，无需重启进程或修改配置文件。这是生产环境排查问题的强大工具。

**核心功能**：
- 列出所有 logger 及其当前日志级别
- 查询特定 logger 的配置信息
- 动态修改 logger 的日志级别
- 支持通配符模式匹配多个 logger
- 无需重启进程即时生效

**典型场景**：
- 生产环境临时启用 DEBUG 日志排查问题
- 关闭过于冗长的第三方库日志
- 动态调整日志级别进行性能优化
- 排查日志缺失问题（检查 logger 配置）

## TUI 使用

在 TUI 模式下，按 **`7`** 键切换到 **Logger 视图**，提供以下交互式功能：

- **Logger 列表显示**：自动加载并展示所有 logger 及其当前级别
  - 按 logger 名称排序
  - 显示 logger 名称、当前级别、级别数值
  - 实时刷新按钮（Refresh）
- **级别修改**：选中 logger 后可快速调整级别
  - 支持 DEBUG, INFO, WARNING, ERROR, CRITICAL
  - 修改后立即生效
- **模式过滤**：支持 fnmatch 通配符（`*` 和 `?`）过滤 logger
- **快捷操作**：
  - 上下方向键选择 logger
  - Enter 修改选中 logger 的级别
  - 按 `r` 刷新 logger 列表

**CLI 等效命令**：下文所有示例使用 CLI 命令演示，TUI 提供了相同功能的图形化界面。
---

## 使用场景

### 1. 生产环境临时开启调试日志

**场景**：生产环境出现问题，需要临时启用 DEBUG 日志来排查，但不能重启服务。

```bash
# 步骤 1：查看当前日志级别
peeka-cli logger --action get --logger myapp.payment

# 输出：
# {"status": "success", "name": "myapp.payment", "level": "INFO", "level_num": 20}

# 步骤 2：临时开启 DEBUG 级别
peeka-cli logger --action set --logger myapp.payment --level DEBUG

# 输出：
# {"status": "success", "name": "myapp.payment", "old_level": "INFO", "new_level": "DEBUG"}

# 步骤 3：排查完成后恢复原级别
peeka-cli logger --action set --logger myapp.payment --level INFO
```

**效果**：立即生效，无需重启进程，日志文件开始输出详细调试信息。

### 2. 关闭第三方库的冗长日志

**场景**：第三方库（如 urllib3、boto3）输出大量 DEBUG 日志，淹没了应用日志。

```bash
# 查看所有包含 "urllib3" 的 logger
peeka-cli logger --action list --pattern "urllib3*"

# 关闭 urllib3 的调试日志
peeka-cli logger --action set --logger urllib3 --level WARNING

# 同样处理 boto3
peeka-cli logger --action set --logger botocore --level WARNING
```

**效果**：第三方库只输出 WARNING 及以上级别的日志，应用日志清晰可见。

### 3. 诊断日志缺失问题

**场景**：某个模块的日志没有输出，怀疑是 logger 配置问题。

```bash
# 步骤 1：检查 logger 是否存在
peeka-cli logger --action get --logger myapp.missing_logs

# 如果输出 "Logger not found"，说明该 logger 未被初始化
# 如果输出 level 为 ERROR，说明日志级别设置过高

# 步骤 2：查看所有 logger，找到可能相关的
peeka-cli logger --action list --pattern "myapp.*"

# 步骤 3：降低级别或创建 logger（通过 set 动作会自动创建）
peeka-cli logger --action set --logger myapp.missing_logs --level DEBUG
```

### 4. 批量查看模块日志级别

**场景**：检查应用所有模块的日志配置是否符合预期。

```bash
# 查看所有应用 logger（假设都以 "myapp" 开头）
peeka-cli logger --action list --pattern "myapp.*" | jq .

# 输出格式化的 logger 列表，便于检查配置
```

### 5. 性能优化：关闭不必要的日志

**场景**：生产环境发现日志 I/O 成为性能瓶颈，需要临时关闭部分日志。

```bash
# 将所有非核心模块的日志级别提升到 WARNING
peeka-cli logger --action set --logger myapp.analytics --level WARNING
peeka-cli logger --action set --logger myapp.reporting --level WARNING
peeka-cli logger --action set --logger myapp.metrics --level WARNING
```

---

## 命令格式

```bash
peeka-cli logger [--action ACTION] [options]
```

**必需**：
- 需要先使用 `peeka-cli attach <pid>` 附加到目标进程

**可选参数**：
- `--action`：操作类型（`list`、`get`、`set`，默认 `list`）
- `--logger`：logger 名称（`get` 和 `set` 动作必需）
- `--level`：日志级别（`set` 动作必需）
- `--pattern`：匹配模式（`list` 动作可选）

---

## Actions 说明

### 1. list - 列出所有 logger

**用途**：查看进程中所有已初始化的 logger 及其当前日志级别。

**语法**：
```bash
peeka-cli logger --action list [--pattern <pattern>]
```

**参数**：
- `--pattern`（可选）：fnmatch 风格的模式（支持 `*` 和 `?` 通配符）

**示例**：
```bash
# 列出所有 logger
peeka-cli logger --action list

# 只列出 myapp 命名空间下的 logger
peeka-cli logger --action list --pattern "myapp.*"

# 列出所有包含 "db" 的 logger
peeka-cli logger --action list --pattern "*db*"
```

**输出**：
```json
{
  "status": "success",
  "loggers": [
    {"name": "myapp.auth", "level": "INFO", "level_num": 20},
    {"name": "myapp.db", "level": "WARNING", "level_num": 30},
    {"name": "myapp.api", "level": "DEBUG", "level_num": 10}
  ],
  "count": 3
}
```

### 2. get - 查询特定 logger

**用途**：查看某个 logger 的详细配置。

**语法**：
```bash
peeka-cli logger --action get --logger <name>
```

**参数**：
- `--logger`（必需）：完整的 logger 名称（不支持通配符）

**示例**：
```bash
peeka-cli logger --action get --logger myapp.payment
```

**输出（成功）**：
```json
{
  "status": "success",
  "name": "myapp.payment",
  "level": "INFO",
  "level_num": 20
}
```

**输出（失败）**：
```json
{
  "status": "error",
  "error": "Logger not found: myapp.payment"
}
```

### 3. set - 修改 logger 级别

**用途**：动态修改 logger 的日志级别，立即生效。

**语法**：
```bash
peeka-cli logger --action set --logger <name> --level <level>
```

**参数**：
- `--logger`（必需）：logger 名称（如果不存在会自动创建）
- `--level`（必需）：新的日志级别（见下方支持的级别）

**支持的日志级别**：
| 级别 | 数值 | 说明 |
|------|------|------|
| `DEBUG` | 10 | 详细的调试信息 |
| `INFO` | 20 | 一般信息性消息 |
| `WARNING` | 30 | 警告信息（默认级别） |
| `ERROR` | 40 | 错误信息 |
| `CRITICAL` | 50 | 严重错误 |
| `NOTSET` | 0 | 未设置（继承父 logger） |

**示例**：
```bash
# 启用 DEBUG 日志
peeka-cli logger --action set --logger myapp.auth --level DEBUG

# 关闭 INFO 级别日志（只保留警告和错误）
peeka-cli logger --action set --logger myapp.reporting --level WARNING

# 恢复默认级别
peeka-cli logger --action set --logger myapp.auth --level INFO
```

**输出**：
```json
{
  "status": "success",
  "name": "myapp.auth",
  "old_level": "INFO",
  "new_level": "DEBUG",
  "old_level_num": 20,
  "new_level_num": 10
}
```

**注意**：
- logger 名称不区分大小写（内部会转换为大写）
- 如果 logger 不存在，会自动创建（使用 `logging.getLogger(name)`）
- 修改立即生效，无需重启进程
- 不会持久化（进程重启后恢复原配置）

---

## 参数说明

### --pattern - 匹配模式

用于 `list` 动作，过滤 logger 列表。

**支持的通配符**：
- `*`：匹配任意长度的字符（包括空字符串）
- `?`：匹配单个字符
- `[seq]`：匹配 seq 中的任意字符
- `[!seq]`：匹配不在 seq 中的任意字符

**示例**：
| 模式 | 匹配示例 | 不匹配示例 |
|------|----------|------------|
| `myapp.*` | `myapp.auth`, `myapp.db` | `myapp`, `webapp.auth` |
| `*db*` | `myapp.db`, `database`, `mongodb` | `myapp.cache` |
| `myapp.api.v?` | `myapp.api.v1`, `myapp.api.v2` | `myapp.api.v10` |
| `myapp.[ad]*` | `myapp.auth`, `myapp.db` | `myapp.cache` |

**用法**：
```bash
# 列出所有 myapp 命名空间下的 logger
peeka-cli logger --action list --pattern "myapp.*"

# 列出所有与数据库相关的 logger
peeka-cli logger --action list --pattern "*db*"

# 列出所有 API 版本的 logger
peeka-cli logger --action list --pattern "*.api.v?"
```

### --logger - Logger 名称

指定要操作的 logger 完整名称。

**命名规范**：
- 通常使用模块路径（如 `myapp.module.submodule`）
- Python 标准做法：`logger = logging.getLogger(__name__)`
- 第三方库通常使用包名（如 `urllib3`, `boto3`）

**查找 logger 名称的方法**：
```bash
# 方法 1：列出所有 logger，找到目标
peeka-cli logger --action list | jq -r '.loggers[].name'

# 方法 2：使用模式匹配缩小范围
peeka-cli logger --action list --pattern "myapp.payment*"

# 方法 3：查看代码中的 getLogger 调用
grep -r "getLogger" myapp/ | grep -v ".pyc"
```

### --level - 日志级别

指定新的日志级别（仅用于 `set` 动作）。

**级别选择建议**：
| 场景 | 推荐级别 | 说明 |
|------|----------|------|
| 生产环境正常运行 | `INFO` | 记录关键业务信息 |
| 生产环境排查问题 | `DEBUG` | 临时启用详细日志 |
| 性能优化（减少日志） | `WARNING` | 只记录异常情况 |
| 关闭第三方库日志 | `ERROR` 或 `CRITICAL` | 仅记录严重错误 |
| 继承父 logger 配置 | `NOTSET` | 使用父 logger 的级别 |

**级别继承关系**：
```
root logger (默认 WARNING)
  └─ myapp (INFO)
       ├─ myapp.auth (DEBUG) ← 使用自己的级别
       └─ myapp.db (NOTSET)  ← 继承 myapp 的 INFO
```

---

## 输出格式

### list 动作输出

```json
{
  "status": "success",
  "loggers": [
    {
      "name": "myapp.auth",
      "level": "INFO",
      "level_num": 20
    },
    {
      "name": "myapp.db",
      "level": "DEBUG",
      "level_num": 10
    }
  ],
  "count": 2
}
```

**字段说明**：
- `status`：操作状态（`success` 或 `error`）
- `loggers`：logger 列表（按名称排序）
- `name`：logger 完整名称
- `level`：日志级别名称（如 `INFO`）
- `level_num`：日志级别数值（如 `20`）
- `count`：匹配到的 logger 数量

### get 动作输出

**成功**：
```json
{
  "status": "success",
  "name": "myapp.payment",
  "level": "INFO",
  "level_num": 20
}
```

**失败**（logger 不存在）：
```json
{
  "status": "error",
  "error": "Logger not found: myapp.payment"
}
```

### set 动作输出

**成功**：
```json
{
  "status": "success",
  "name": "myapp.auth",
  "old_level": "INFO",
  "new_level": "DEBUG",
  "old_level_num": 20,
  "new_level_num": 10
}
```

**失败**（无效级别）：
```json
{
  "status": "error",
  "error": "Invalid level: INVALID. Valid levels: DEBUG, INFO, WARNING, ERROR, CRITICAL, NOTSET"
}
```

---

## 使用示例

### 示例 1：查看所有 logger 配置

```bash
peeka-cli logger --action list | jq .
```

**输出**：
```json
{
  "status": "success",
  "loggers": [
    {"name": "root", "level": "WARNING", "level_num": 30},
    {"name": "myapp", "level": "INFO", "level_num": 20},
    {"name": "myapp.auth", "level": "INFO", "level_num": 20},
    {"name": "myapp.db", "level": "WARNING", "level_num": 30},
    {"name": "urllib3.connectionpool", "level": "WARNING", "level_num": 30}
  ],
  "count": 5
}
```

### 示例 2：临时开启 DEBUG 日志排查问题

```bash
# 1. 查看当前级别
peeka-cli logger --action get --logger myapp.payment
# 输出：{"status": "success", "name": "myapp.payment", "level": "INFO", ...}

# 2. 开启 DEBUG
peeka-cli logger --action set --logger myapp.payment --level DEBUG
# 输出：{"status": "success", "old_level": "INFO", "new_level": "DEBUG"}

# 3. 观察日志文件（另一个终端）
tail -f /var/log/myapp.log | grep payment

# 4. 排查完成后恢复
peeka-cli logger --action set --logger myapp.payment --level INFO
```

### 示例 3：关闭第三方库的冗长日志

```bash
# 查看所有第三方库 logger
peeka-cli logger --action list --pattern "*" | \
  jq -r '.loggers[] | select(.level == "DEBUG") | .name'

# 批量关闭（只保留 WARNING 及以上）
for logger in urllib3 botocore requests; do
  peeka-cli logger --action set --logger "$logger" --level WARNING
done
```

### 示例 4：检查 logger 是否存在

```bash
# 方法 1：使用 get 动作
result=$(peeka-cli logger --action get --logger myapp.missing 2>&1)
echo "$result" | jq -r .status
# 输出：error（如果不存在）

# 方法 2：列出所有并搜索
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.name == "myapp.missing")'
# 无输出（如果不存在）
```

### 示例 5：创建新的 logger 并设置级别

```bash
# set 动作会自动创建不存在的 logger
peeka-cli logger --action set --logger myapp.new_module --level DEBUG

# 验证创建成功
peeka-cli logger --action get --logger myapp.new_module
# 输出：{"status": "success", "name": "myapp.new_module", "level": "DEBUG", ...}
```

### 示例 6：批量查看特定模块的配置

```bash
# 查看所有 myapp.api 子模块的日志级别
peeka-cli logger --action list --pattern "myapp.api.*" | \
  jq -r '.loggers[] | "\(.name): \(.level)"'
```

**输出**：
```
myapp.api.v1: INFO
myapp.api.v2: DEBUG
myapp.api.auth: WARNING
```

---

## 完整诊断流程

### 流程 1：生产环境问题排查

**场景**：生产环境出现支付失败，需要临时启用调试日志定位问题。

```bash
# 步骤 1：查看支付模块当前日志级别
peeka-cli logger --action get --logger myapp.payment
# 输出：{"level": "INFO"}

# 步骤 2：启用 DEBUG 日志
peeka-cli logger --action set --logger myapp.payment --level DEBUG

# 步骤 3：同时监控日志文件
tail -f /var/log/myapp.log | grep -A 5 -B 5 "payment"

# 步骤 4：复现问题（触发支付流程）

# 步骤 5：查看调试日志，定位问题

# 步骤 6：问题解决后恢复原级别
peeka-cli logger --action set --logger myapp.payment --level INFO
```

### 流程 2：日志缺失诊断

**场景**：某个模块的日志完全没有输出，需要检查原因。

```bash
# 步骤 1：检查 logger 是否存在
peeka-cli logger --action get --logger myapp.analytics
# 如果输出 "Logger not found"，说明未初始化

# 步骤 2：查看父 logger 的级别
peeka-cli logger --action get --logger myapp
# 输出：{"level": "WARNING"}

# 步骤 3：创建 logger 并设置为 DEBUG
peeka-cli logger --action set --logger myapp.analytics --level DEBUG

# 步骤 4：验证日志开始输出
tail -f /var/log/myapp.log | grep analytics
```

### 流程 3：性能优化 - 减少日志 I/O

**场景**：系统负载高，日志 I/O 成为瓶颈，需要临时关闭部分日志。

```bash
# 步骤 1：查看所有 DEBUG 级别的 logger
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.level == "DEBUG") | .name'

# 输出：
# myapp.api
# myapp.cache
# myapp.db
# myapp.reporting

# 步骤 2：保留核心模块（api, db）的 DEBUG，关闭其他
peeka-cli logger --action set --logger myapp.cache --level WARNING
peeka-cli logger --action set --logger myapp.reporting --level WARNING

# 步骤 3：观察系统负载变化
# （使用 top、htop 或监控系统）

# 步骤 4：如果需要恢复
peeka-cli logger --action set --logger myapp.cache --level DEBUG
peeka-cli logger --action set --logger myapp.reporting --level DEBUG
```

### 流程 4：批量调整第三方库日志

**场景**：多个第三方库输出大量调试日志，需要批量关闭。

```bash
# 步骤 1：列出所有非应用 logger（通常是第三方库）
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.name | startswith("myapp") | not) | .name'

# 输出：
# urllib3
# urllib3.connectionpool
# botocore
# requests

# 步骤 2：批量设置为 WARNING
cat <<'EOF' | bash
for logger in urllib3 urllib3.connectionpool botocore requests; do
  peeka-cli logger --action set --logger "$logger" --level WARNING
  echo "Set $logger to WARNING"
done
EOF

# 步骤 3：验证
peeka-cli logger --action list --pattern "*" | \
  jq -r '.loggers[] | select(.name | startswith("myapp") | not) | "\(.name): \(.level)"'
```

---

## 注意事项

### 1. 修改的临时性

**重要**：logger 命令的修改**不会持久化**。

- 修改立即生效，但进程重启后会恢复原配置
- 需要永久修改请更新配置文件（如 `logging.conf` 或代码中的 `logging.basicConfig()`）

### 2. root logger 的影响

**root logger** 是所有 logger 的默认父级：
- 默认级别为 `WARNING`
- 所有未显式设置级别的 logger 会继承 root logger
- 修改 root logger 会影响所有子 logger（除非子 logger 有显式级别）

**示例**：
```bash
# 查看 root logger
peeka-cli logger --action get --logger root

# 全局开启 DEBUG（谨慎使用！）
peeka-cli logger --action set --logger root --level DEBUG
```

**警告**：修改 root logger 可能导致日志爆炸，仅在必要时使用。

### 3. Logger 的创建时机

**注意**：`list` 和 `get` 只能查看**已初始化**的 logger。

- Logger 在首次调用 `logging.getLogger(name)` 时创建
- 如果代码尚未执行到相关模块，logger 不会出现在列表中
- `set` 动作会自动创建不存在的 logger

### 4. 级别继承机制

Python logging 的级别继承规则：
```
root (WARNING)
  └─ myapp (INFO)
       ├─ myapp.auth (DEBUG)    ← 使用自己的级别
       ├─ myapp.db (NOTSET)     ← 继承 myapp 的 INFO
       └─ myapp.cache (NOTSET)  ← 继承 myapp 的 INFO
```

**实际生效级别**：
- `myapp.auth`：DEBUG（自己的级别）
- `myapp.db`：INFO（继承自 myapp）
- `myapp.cache`：INFO（继承自 myapp）

### 5. Handler 的影响

**注意**：logger 命令只修改 logger 的**级别**，不修改 handler 配置。

- 即使 logger 级别为 DEBUG，如果 handler 级别为 INFO，DEBUG 日志仍不会输出
- 检查 handler 配置：`logger.handlers[0].level`（需要在代码中查看）

### 6. 性能影响

修改 logger 级别本身**没有性能开销**，但日志级别的变化会影响：
- **降低级别**（如 INFO → DEBUG）：日志量增加，I/O 开销上升
- **提升级别**（如 DEBUG → WARNING）：日志量减少，性能提升

**建议**：
- 调试完成后立即恢复原级别
- 避免长时间开启 DEBUG 级别
- 定期检查日志文件大小

---

## 常见问题

### Q1: 为什么修改 logger 级别后日志仍然没有输出？

**可能原因**：
1. **Handler 级别过高**：logger 级别是 DEBUG，但 handler 级别是 INFO
2. **日志未刷新**：某些 handler 有缓冲，需要等待刷新
3. **Logger 名称错误**：实际使用的 logger 名称与修改的不一致
4. **父 logger 级别过高**：即使子 logger 是 DEBUG，父 logger 过滤了消息

**诊断方法**：
```bash
# 1. 确认 logger 级别已修改
peeka-cli logger --action get --logger myapp.target

# 2. 检查父 logger 级别
peeka-cli logger --action get --logger myapp

# 3. 检查 root logger 级别
peeka-cli logger --action get --logger root

# 4. 查看所有 logger（确认名称正确）
peeka-cli logger --action list --pattern "myapp.*"
```

### Q2: 如何批量修改多个 logger？

**方法 1**：使用 shell 循环
```bash
for logger in myapp.auth myapp.db myapp.cache; do
  peeka-cli logger --action set --logger "$logger" --level DEBUG
done
```

**方法 2**：从文件读取
```bash
# loggers.txt 文件内容：
# myapp.auth
# myapp.db
# myapp.cache

while read logger; do
  peeka-cli logger --action set --logger "$logger" --level DEBUG
done < loggers.txt
```

**方法 3**：动态查询后批量修改
```bash
# 将所有 INFO 级别的 logger 改为 DEBUG
peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.level == "INFO") | .name' | \
  while read logger; do
    peeka-cli logger --action set --logger "$logger" --level DEBUG
  done
```

### Q3: 修改会影响其他进程吗？

**答案**：不会。

- 每个进程的 logger 配置独立
- 修改只影响指定 PID 的进程
- 其他进程的 logger 不受影响

### Q4: 如何恢复所有 logger 到原始状态？

**方法**：重启进程（logger 配置会重新加载）。

**注意**：logger 命令不提供"恢复快照"功能，建议：
1. 修改前记录原始级别
2. 或者直接重启进程恢复配置

**示例（记录原始级别）**：
```bash
# 修改前保存当前配置
peeka-cli logger --action list > logger_backup.json

# 修改后恢复
jq -r '.loggers[] | "\(.name) \(.level)"' logger_backup.json | \
  while read name level; do
    peeka-cli logger --action set --logger "$name" --level "$level"
  done
```

### Q5: 为什么 pattern 匹配不到 logger？

**可能原因**：
1. **Pattern 语法错误**：fnmatch 不支持正则表达式，只支持 `*` 和 `?`
2. **Logger 未初始化**：代码尚未执行到该模块
3. **大小写问题**：logger 名称区分大小写

**调试方法**：
```bash
# 1. 列出所有 logger（不使用 pattern）
peeka-cli logger --action list | jq -r '.loggers[].name'

# 2. 确认目标 logger 的确切名称

# 3. 使用正确的 pattern
peeka-cli logger --action list --pattern "myapp.*"
```

### Q6: 可以创建不存在的 logger 吗？

**答案**：可以，使用 `set` 动作。

```bash
# 创建新 logger 并设置级别
peeka-cli logger --action set --logger myapp.new_logger --level DEBUG

# 验证
peeka-cli logger --action get --logger myapp.new_logger
# 输出：{"status": "success", "name": "myapp.new_logger", "level": "DEBUG"}
```

**注意**：
- 新创建的 logger 在进程重启后不会自动重新创建
- 应用代码需要显式调用 `logging.getLogger(name)` 才能使用该 logger

---

## 高级技巧

### 1. 动态日志级别切换脚本

**场景**：频繁开启/关闭调试日志，编写自动化脚本。

```bash
#!/bin/bash
# toggle_debug.sh - 切换 myapp.payment 的日志级别

PID=12345
LOGGER="myapp.payment"

current=$(peeka-cli logger --action get --logger $LOGGER | jq -r .level)

if [ "$current" == "DEBUG" ]; then
  echo "Disabling DEBUG..."
  peeka-cli logger --action set --logger $LOGGER --level INFO
else
  echo "Enabling DEBUG..."
  peeka-cli logger --action set --logger $LOGGER --level DEBUG
fi
```

### 2. 监控日志级别变化

**场景**：定期检查 logger 配置，确保生产环境没有意外开启 DEBUG。

```bash
#!/bin/bash
# check_debug_loggers.sh - 检查所有 DEBUG 级别的 logger

PID=12345

debug_loggers=$(peeka-cli logger --action list | \
  jq -r '.loggers[] | select(.level == "DEBUG") | .name')

if [ -n "$debug_loggers" ]; then
  echo "WARNING: Found DEBUG loggers in production:"
  echo "$debug_loggers"
  # 发送告警（如 Slack、邮件等）
else
  echo "All loggers are at safe levels."
fi
```

### 3. 与 Prometheus 集成

**场景**：导出 logger 配置到 Prometheus 监控。

```bash
#!/bin/bash
# export_logger_metrics.sh

PID=12345

peeka-cli logger --action list | \
  jq -r '.loggers[] | "logger_level{name=\"\(.name)\"} \(.level_num)"' \
  > /var/lib/node_exporter/textfile_collector/logger_levels.prom
```

**Prometheus 查询**：
```promql
# 查询所有 DEBUG 级别的 logger
logger_level{level="10"}

# 告警规则（检测生产环境 DEBUG logger）
ALERT ProductionDebugLogger
  IF logger_level{name=~"myapp.*", level="10"} > 0
  FOR 5m
  ANNOTATIONS {
    summary = "Production logger at DEBUG level",
    description = "Logger {{ $labels.name }} is at DEBUG level in production."
  }
```

### 4. 日志级别分析

**场景**：统计应用 logger 的级别分布。

```bash
peeka-cli logger --action list --pattern "myapp.*" | \
  jq -r '.loggers[] | .level' | sort | uniq -c
```

**输出**：
```
     12 DEBUG
     45 INFO
      8 WARNING
```

### 5. 临时日志重定向

**场景**：临时调整某个模块的日志级别，并将输出重定向到单独文件。

```bash
# 1. 启用 DEBUG 日志
peeka-cli logger --action set --logger myapp.payment --level DEBUG

# 2. 在另一个终端监控日志
tail -f /var/log/myapp.log | grep "payment" > payment_debug.log

# 3. 复现问题

# 4. 停止监控（Ctrl+C）

# 5. 恢复日志级别
peeka-cli logger --action set --logger myapp.payment --level INFO
```

### 6. 自动恢复脚本

**场景**：开启 DEBUG 后 5 分钟自动恢复，避免忘记关闭。

```bash
#!/bin/bash
# temp_debug.sh - 临时启用 DEBUG，5 分钟后自动恢复

PID=$1
LOGGER=$2
DURATION=${3:-300}  # 默认 5 分钟

# 保存原始级别
original=$(peeka-cli logger --action get --logger $LOGGER | jq -r .level)
echo "Original level: $original"

# 启用 DEBUG
peeka-cli logger --action set --logger $LOGGER --level DEBUG
echo "DEBUG enabled. Will auto-restore in $DURATION seconds..."

# 后台等待后恢复
(
  sleep $DURATION
  peeka-cli logger --action set --logger $LOGGER --level $original
  echo "Restored to $original"
) &
```

**使用方法**：
```bash
./temp_debug.sh 12345 myapp.payment 300
```

---


## 总结

`logger` 命令是生产环境日志诊断的强大工具，特别适合：
- 临时开启调试日志排查问题
- 关闭第三方库的冗长日志
- 动态调整日志级别进行性能优化
- 诊断日志缺失问题

**最佳实践**：
- 修改前记录原始级别（便于恢复）
- 调试完成后立即恢复原级别
- 避免长时间开启 DEBUG（日志爆炸）
- 使用 `--pattern` 过滤 logger（提高效率）
- 结合 `jq` 进行强大的数据分析

**下一步**：
- 了解 [`watch`](watch.md) 命令（观测函数调用）
- 了解 [`stack`](stack.md) 命令（追踪调用栈）
- 了解 [`memory`](memory.md) 命令（内存分析）
- 参考 [AGENTS.md](../AGENTS.md)（开发者指南）

