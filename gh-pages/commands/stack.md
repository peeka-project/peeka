---
layout: default
title: Peeka Stack 命令详解
parent: 命令参考
nav_order: 4
---

# Peeka Stack 命令详解
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 命令简介

`stack` 命令用于在函数被调用时捕获完整的调用栈信息，帮助开发者追踪函数的调用路径。这是一个强大的调试工具，特别适合分析复杂调用链、定位问题根源。

**核心功能**：
- 捕获函数调用时的完整调用栈
- 显示调用链上的文件名、行号、函数名、代码片段
- 支持条件过滤（仅在特定条件下捕获）
- 可配置栈深度（避免输出过长）
- 实时流式输出（JSON 格式）

**与 watch 命令的区别**：
- `watch`：观测函数的**参数、返回值、执行时间**
- `stack`：观测函数的**调用路径**（从哪里被调用的）

## TUI 使用

在 TUI 模式下，按 **`4`** 键切换到 **Stack 视图**，提供以下交互式功能：

- **模式输入**：支持函数名自动补全（从目标进程实时获取）
- **参数配置**：可视化配置捕获次数、条件表达式、栈深度
- **调用栈可视化**：以表格形式实时展示调用栈
  - 显示文件名、行号、函数名、代码片段
  - 每次捕获展示完整调用链（从最内层到最外层）
- **快捷操作**：
  - 输入模式后按 Enter 开始捕获
  - 按 `c` 清空捕获记录
  - 按 Delete 删除选中记录
  - 上下方向键浏览调用栈层级

**CLI 等效命令**：下文所有示例使用 CLI 命令演示，TUI 提供了相同功能的图形化界面。
---

## 使用场景

### 1. 追踪调用来源

**场景**：某个函数被多处调用，需要定位特定调用路径。

```bash
# 查看 process_order 函数是从哪里被调用的
peeka-cli stack "myapp.orders.process_order"
```

**输出示例**：
```json
{
  "location": "AtEnter",
  "pattern": "myapp.orders.process_order",
  "params": [{"order_id": 12345}],
  "stack": [
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 156,
      "function": "create_order_view",
      "code_context": "result = process_order(order_data)"
    },
    {
      "filename": "/app/myapp/middleware/auth.py",
      "lineno": 45,
      "function": "check_permissions",
      "code_context": "return handler(request)"
    },
    {
      "filename": "/usr/lib/python3.14/http/server.py",
      "lineno": 89,
      "function": "handle_request",
      "code_context": "self.handle_one_request()"
    }
  ],
  "thread_id": 140234567890,
  "thread_name": "Thread-5"
}
```

### 2. 分析递归调用

**场景**：递归函数导致栈溢出，需要分析递归深度和调用模式。

```bash
# 限制栈深度为 20 层，避免输出过长
peeka-cli stack "myapp.utils.recursive_func" --depth 20
```

### 3. 定位异常调用路径

**场景**：函数在特定条件下出错，需要追踪错误发生时的调用链。

```bash
# 仅在 user_id 为 999 时捕获调用栈
peeka-cli stack "myapp.auth.check_permission" \
  --condition "params[0] == 999"
```

### 4. 分析热点调用路径

**场景**：性能分析，找出哪些路径最频繁地调用某个函数。

```bash
# 捕获前 100 次调用，然后统计路径分布
peeka-cli stack "myapp.db.execute_query" -n 100 | \
  jq -r '.stack[0] | "\(.filename):\(.lineno)"' | \
  sort | uniq -c | sort -rn
```

### 5. 跨模块调用追踪

**场景**：微服务架构中，追踪请求在不同模块间的传递路径。

```bash
# 追踪 API 入口函数的调用链
peeka-cli stack "myapp.api.handle_request"
```

---

## 命令格式


**必需参数**：
- `pattern`：目标函数的模式（如 `module.Class.method`）

**可选参数**：
- `-n, --times`：捕获次数（-1 表示无限，默认 -1）
- `--condition`：条件表达式（仅在满足条件时捕获）
- `--depth`：栈深度限制（默认 10）

---

## 参数说明

### pattern - 函数模式

指定要追踪的目标函数，支持以下格式：

| 格式 | 说明 | 示例 |
|------|------|------|
| `module.function` | 模块级函数 | `myapp.utils.calculate` |
| `module.Class.method` | 类方法 | `myapp.models.User.save` |
| `module.Class.static_method` | 静态方法 | `myapp.utils.Helper.validate` |

**注意事项**：
- 必须使用完整限定名（从模块根开始）
- 不支持通配符（与 `watch` 命令一致）
- 目标函数必须已被加载到内存中

### --times, -n - 捕获次数

控制捕获的次数，避免产生海量数据。

| 值 | 行为 | 适用场景 |
|----|------|----------|
| `-1`（默认）| 无限捕获 | 持续监控、生产环境问题排查 |
| `1` | 捕获 1 次后自动停止 | 只需要看一次调用栈 |
| `N` | 捕获 N 次后自动停止 | 采样分析、统计路径分布 |

**示例**：
```bash
# 只看第一次调用
peeka-cli stack "myapp.func" -n 1

# 捕获 50 次样本
peeka-cli stack "myapp.func" -n 50
```

### --condition - 条件表达式

仅在满足条件时捕获调用栈，避免输出无关数据。

**可用变量**：
- `params`：函数的位置参数（tuple）
- `kwargs`：函数的关键字参数（dict）
- `target`：实例方法的 `self` 对象

**支持的操作符**：
- 比较：`==`, `!=`, `>`, `<`, `>=`, `<=`
- 逻辑：`and`, `or`, `not`
- 成员检查：`in`, `not in`
- 字符串：`str(x).startswith()`, `str(x).endswith()`
- 长度：`len(params)`, `len(kwargs)`
- 索引访问：`params[0]`, `kwargs.get('key')`

**示例**：
```bash
# 仅当第一个参数大于 100 时捕获
peeka-cli stack "myapp.func" --condition "params[0] > 100"

# 仅当参数个数大于 2 时捕获
peeka-cli stack "myapp.func" --condition "len(params) > 2"

# 仅当用户 ID 为指定值时捕获
peeka-cli stack "myapp.check_permission" \
  --condition "kwargs.get('user_id') == 999"

# 复合条件
peeka-cli stack "myapp.process" \
  --condition "params[0] > 10 and len(params) < 5"
```

**安全性**：
- 基于 `simpleeval` 库实现，禁用了所有危险操作
- 不允许：`eval`, `exec`, `__import__`, `open`, `compile`
- 不允许访问：`__class__`, `__subclasses__`
- 只支持白名单内的安全操作

### --depth - 栈深度限制

控制捕获的调用栈层数，避免输出过长。

| 值 | 说明 | 适用场景 |
|----|------|----------|
| `10`（默认）| 10 层调用栈 | 一般调试场景 |
| `5` | 5 层调用栈 | 只关心最近几层调用 |
| `20` | 20 层调用栈 | 深度递归分析 |
| `50` | 50 层调用栈 | 极端场景（不推荐） |

**注意**：
- 栈深度从目标函数的**调用者**开始计算（不包括目标函数本身）
- 深度越大，输出数据量越大
- 建议根据实际需求设置合理的深度（5-20 层）

**示例**：
```bash
# 只看最近 3 层调用者
peeka-cli stack "myapp.func" --depth 3

# 深度递归分析（最多 30 层）
peeka-cli stack "myapp.recursive_func" --depth 30
```

---

## 输出格式

`stack` 命令输出 JSON Lines 格式（每行一个 JSON 对象），便于流式处理和工具集成。

### 完整输出示例

```json
{
  "watch_id": "watch_20260131_001",
  "timestamp": 1738339200.123456,
  "location": "AtEnter",
  "pattern": "myapp.orders.process_order",
  "params": [
    {"order_id": 12345, "amount": 99.99}
  ],
  "kwargs": {
    "priority": "high"
  },
  "target": {
    "__attrs__": {
      "user_id": 999,
      "session": "<Session object>"
    }
  },
  "stack": [
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 156,
      "function": "create_order_view",
      "code_context": "result = process_order(order_data)"
    },
    {
      "filename": "/app/myapp/middleware/rate_limiter.py",
      "lineno": 78,
      "function": "rate_limit_decorator",
      "code_context": "return func(*args, **kwargs)"
    },
    {
      "filename": "/app/myapp/middleware/auth.py",
      "lineno": 45,
      "function": "check_permissions",
      "code_context": "return handler(request)"
    }
  ],
  "thread_id": 140234567890,
  "thread_name": "ThreadPoolExecutor-3",
  "cost": 0.0
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `watch_id` | string | 观测任务的唯一标识符 |
| `timestamp` | float | Unix 时间戳（秒，带小数） |
| `location` | string | 观测点位置（`AtEnter` 表示函数入口） |
| `pattern` | string | 目标函数的模式 |
| `params` | array | 函数的位置参数 |
| `kwargs` | object | 函数的关键字参数 |
| `target` | object | 实例方法的 `self` 对象（仅类方法有） |
| `stack` | array | 调用栈帧数组（最重要的字段） |
| `thread_id` | int | 线程 ID |
| `thread_name` | string | 线程名称 |
| `cost` | float | 执行时间（毫秒，`AtEnter` 时为 0.0） |

### stack 数组元素

每个栈帧（frame）包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `filename` | string | 源代码文件的绝对路径 |
| `lineno` | int | 源代码行号 |
| `function` | string | 函数/方法名称 |
| `code_context` | string | 该行的源代码内容（去除首尾空白） |

**栈帧顺序**：
- `stack[0]`：**最近的调用者**（直接调用目标函数的地方）
- `stack[1]`：调用者的调用者
- `stack[n]`：越靠后越接近调用链的根部

---

## 使用示例

### 示例 1：基本调用栈追踪

**场景**：查看 `calculate_price` 函数是从哪里被调用的。

```bash
peeka-cli stack "myapp.pricing.calculate_price"
```

**输出**：
```json
{
  "watch_id": "watch_001",
  "timestamp": 1738339200.123,
  "location": "AtEnter",
  "pattern": "myapp.pricing.calculate_price",
  "params": [{"product_id": 789, "quantity": 5}],
  "stack": [
    {
      "filename": "/app/myapp/api/cart.py",
      "lineno": 234,
      "function": "checkout",
      "code_context": "total = calculate_price(cart_items)"
    },
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 89,
      "function": "checkout_view",
      "code_context": "result = cart.checkout()"
    }
  ],
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**解读**：
- `calculate_price` 被 `cart.py:234` 的 `checkout` 函数调用
- `checkout` 又被 `views.py:89` 的 `checkout_view` 调用

### 示例 2：条件过滤追踪

**场景**：只追踪参数为负数的调用（可能是异常情况）。

```bash
peeka-cli stack "myapp.utils.process_value" \
  --condition "params[0] < 0" \
  -n 10
```

**输出**（仅在参数为负数时才输出）：
```json
{
  "watch_id": "watch_002",
  "timestamp": 1738339201.456,
  "location": "AtEnter",
  "pattern": "myapp.utils.process_value",
  "params": [-5],
  "stack": [
    {
      "filename": "/app/myapp/data/processor.py",
      "lineno": 67,
      "function": "validate_input",
      "code_context": "result = process_value(user_input)"
    }
  ],
  "thread_id": 140234567891,
  "thread_name": "WorkerThread-2"
}
```

**用途**：快速定位异常输入的来源。

### 示例 3：限制栈深度

**场景**：只关心最近的 3 层调用者。

```bash
peeka-cli stack "myapp.db.execute_query" --depth 3
```

**输出**：
```json
{
  "watch_id": "watch_003",
  "timestamp": 1738339202.789,
  "location": "AtEnter",
  "pattern": "myapp.db.execute_query",
  "params": ["SELECT * FROM users WHERE id = ?", [999]],
  "stack": [
    {
      "filename": "/app/myapp/models/user.py",
      "lineno": 123,
      "function": "get_by_id",
      "code_context": "return db.execute_query(sql, params)"
    },
    {
      "filename": "/app/myapp/api/users.py",
      "lineno": 45,
      "function": "get_user",
      "code_context": "user = User.get_by_id(user_id)"
    },
    {
      "filename": "/app/myapp/api/views.py",
      "lineno": 78,
      "function": "user_profile_view",
      "code_context": "return get_user(request.user_id)"
    }
  ]
}
```

### 示例 4：捕获一次后停止

**场景**：只需要看一次调用栈，确认调用路径即可。

```bash
peeka-cli stack "myapp.cache.get" -n 1
```

**行为**：捕获第一次调用后自动停止追踪，不会继续输出。

### 示例 5：与 jq 结合分析

**场景**：提取所有调用来源，统计哪个文件最频繁地调用目标函数。

```bash
peeka-cli stack "myapp.logger.log" -n 100 | \
  jq -r '.stack[0] | "\(.filename):\(.lineno)"' | \
  sort | uniq -c | sort -rn | head -10
```

**输出**：
```
     45 /app/myapp/api/views.py:123
     23 /app/myapp/middleware/auth.py:67
     12 /app/myapp/utils/helper.py:234
     ...
```

**解读**：`views.py:123` 是最频繁的调用来源（45 次）。

### 示例 6：追踪多线程调用

**场景**：分析哪些线程调用了目标函数。

```bash
peeka-cli stack "myapp.shared.resource.access" -n 50 | \
  jq -r '.thread_name' | sort | uniq -c
```

**输出**：
```
     30 WorkerThread-1
     15 WorkerThread-2
      5 MainThread
```

---

## 完整诊断流程

### 流程 1：定位异常调用路径

**问题**：某个函数在特定情况下抛出异常，需要找出是哪个调用路径触发的。

```bash
# 步骤 1：启动追踪（仅捕获异常参数的调用）
peeka-cli stack "myapp.payment.charge" \
  --condition "params[0] <= 0" \
  -n 20

# 步骤 2：等待问题复现（持续输出到文件）
peeka-cli stack "myapp.payment.charge" \
  --condition "params[0] <= 0" > stack_trace.jsonl

# 步骤 3：分析调用路径
jq -r '.stack[] | "\(.filename):\(.lineno) - \(.function)"' stack_trace.jsonl

# 步骤 4：找到最频繁的异常来源
jq -r '.stack[0] | "\(.filename):\(.lineno)"' stack_trace.jsonl | \
  sort | uniq -c | sort -rn
```

**结果示例**：
```
     12 /app/myapp/api/refund.py:89
      3 /app/myapp/jobs/reconcile.py:234
```

**结论**：`refund.py:89` 是主要问题来源，检查该处的输入验证逻辑。

### 流程 2：性能热点路径分析

**问题**：某个数据库查询函数被频繁调用，需要找出哪些路径最耗时。

```bash
# 步骤 1：捕获 200 次调用的调用栈
peeka-cli stack "myapp.db.query" -n 200 > query_stacks.jsonl

# 步骤 2：统计调用路径分布
jq -r '.stack[0:3] | map("\(.filename):\(.lineno)") | join(" -> ")' \
  query_stacks.jsonl | sort | uniq -c | sort -rn | head -10

# 步骤 3：针对高频路径优化（如添加缓存）
```

**输出示例**：
```
     89 /app/myapp/api/list.py:123 -> /app/myapp/models/user.py:45
     34 /app/myapp/api/search.py:67 -> /app/myapp/models/user.py:45
     12 /app/myapp/jobs/sync.py:234 -> /app/myapp/models/user.py:45
```

**结论**：`list.py:123` 路径占比最高（89 次），优先优化该路径。

### 流程 3：递归深度分析

**问题**：递归函数导致栈溢出，需要分析递归深度。

```bash
# 步骤 1：捕获深层调用栈（depth 设为 50）
peeka-cli stack "myapp.tree.traverse" --depth 50 -n 10 > recursion.jsonl

# 步骤 2：计算每次调用的栈深度
jq '.stack | length' recursion.jsonl

# 步骤 3：找出最深的调用
jq -s 'max_by(.stack | length)' recursion.jsonl > deepest.json

# 步骤 4：分析最深调用的路径
jq '.stack[] | "\(.function) at \(.filename):\(.lineno)"' deepest.json
```

**输出示例**：
```
traverse at /app/myapp/tree.py:45
traverse at /app/myapp/tree.py:45
traverse at /app/myapp/tree.py:45
... (重复 48 次)
process_tree at /app/myapp/api/views.py:123
```

**结论**：递归深度达到 48 层，需要优化递归终止条件或改用迭代实现。

---

## 注意事项

### 1. 性能影响

**影响程度**：
- **捕获栈帧**：每次捕获约 0.5-2ms 额外开销（取决于栈深度）
- **JSON 序列化**：每次约 0.2-0.5ms
- **网络传输**：每次约 0.1-0.3ms（Unix Domain Socket）

**总体开销**：约 1-3ms/次（高频函数可能累积到 5-10% CPU）

**优化建议**：
- 使用 `--condition` 减少捕获次数
- 合理设置 `--depth`（默认 10 层通常足够）
- 避免追踪超高频函数（如每秒调用上万次的函数）
- 使用 `-n` 限制捕获次数（完成调试后立即停止）

### 2. 输出数据量

**数据量估算**：
- 每个栈帧约 200-300 字节（JSON）
- 10 层调用栈约 2-3 KB
- 1000 次捕获约 2-3 MB

**管理建议**：
- 输出到文件：`peeka-cli stack ... > output.jsonl`
- 定期清理输出文件
- 使用流式处理（`jq`）而非一次性加载全部数据

### 3. 线程安全

**注意事项**：
- 多线程环境下，不同线程的调用栈会交织输出
- 使用 `thread_id` 和 `thread_name` 字段区分线程
- 可以用 `jq` 过滤特定线程：
  ```bash
  peeka-cli stack "myapp.func" | \
    jq 'select(.thread_name == "WorkerThread-1")'
  ```

### 4. 条件表达式限制

**限制**：
- 不支持 `cost` 变量（因为 `stack` 只在函数入口捕获，执行尚未完成）
- 不支持访问返回值（`returnObj` 不可用）
- 不支持复杂的对象方法调用（如 `params[0].some_method()`）

**可用变量**：仅 `params`、`kwargs`、`target`

### 5. 栈帧数量限制

**限制**：
- 默认最多捕获 10 层（可通过 `--depth` 调整）
- Python 解释器默认最大递归深度为 1000（`sys.getrecursionlimit()`）
- 不建议设置 `--depth` 超过 50（数据量过大）

---

## 常见问题

### Q3: 如何停止正在运行的 stack 追踪？

**方法 1**：使用 Ctrl+C 中断客户端（不影响目标进程）


**注意**：
- 停止追踪后，目标函数恢复原样（无性能影响）
- 目标进程不受影响

### Q4: 为什么 code_context 字段是 None？

**原因**：
- 源代码文件不可访问（如 `.pyc` 编译后的代码）
- 源代码文件已被删除或移动
- Python 内置模块（C 扩展）

**解决方法**：
- 确保源代码文件存在且可访问
- 对于 C 扩展模块，无法获取源代码内容（正常现象）

### Q5: stack 命令与 watch 命令可以同时使用吗？

**答案**：是的，可以同时使用。

**示例**：
```bash
# 终端 1：追踪调用栈
peeka-cli stack "myapp.func" > stack.jsonl

# 终端 2：观测参数和返回值
peeka-cli watch "myapp.func" > watch.jsonl
```

**注意**：
- 两个命令会注入两个装饰器（性能影响累加）
- 建议按需使用，避免过度追踪

### Q6: 如何追踪标准库函数的调用栈？

**答案**：可以追踪，但需要使用完整模块路径。

**示例**：
```bash
# 追踪 json.dumps 的调用栈
peeka-cli stack "json.dumps" --depth 5

# 追踪 logging 模块的 info 方法
peeka-cli stack "logging.Logger.info" --depth 3
```

**注意**：
- 标准库函数通常调用频率极高，建议使用条件过滤和次数限制
- 部分 C 扩展函数无法追踪（如 `time.sleep`）

---

## 高级技巧

### 1. 调用路径去重与排序

**场景**：统计所有不同的调用路径，按频率排序。

```bash
peeka-cli stack "myapp.db.query" -n 500 | \
  jq -r '.stack[0:3] | map("\(.filename):\(.lineno)") | join(" -> ")' | \
  sort | uniq -c | sort -rn > call_paths.txt
```

**输出示例**：
```
    123 /app/api/users.py:45 -> /app/models/user.py:78
     67 /app/api/orders.py:123 -> /app/models/order.py:56
     34 /app/jobs/sync.py:234 -> /app/models/user.py:78
```

### 2. 可视化调用树

**场景**：生成调用树图（需要额外工具如 `graphviz`）。

```bash
# 步骤 1：提取调用关系
peeka-cli stack "myapp.func" -n 100 | \
  jq -r '.stack[] | "\(.function) -> \(.filename):\(.lineno)"' > edges.txt

# 步骤 2：使用 graphviz 生成图（需要自行编写脚本）
# 或使用在线工具如 https://dreampuf.github.io/GraphvizOnline/
```

### 3. 实时监控调用频率

**场景**：实时显示每秒的调用次数。

```bash
peeka-cli stack "myapp.api.handle_request" | \
  jq -r .timestamp | \
  awk '{
    sec = int($1)
    count[sec]++
  } END {
    for (s in count) print s, count[s]
  }'
```

### 4. 过滤第三方库栈帧

**场景**：只关心应用代码，忽略第三方库（如 Django、Flask）。

```bash
peeka-cli stack "myapp.views.index" --depth 20 | \
  jq '.stack |= map(select(.filename | startswith("/app/myapp")))'
```

### 5. 跨进程调用链分析

**场景**：结合日志追踪跨进程调用链。

**方法**：
1. 在每个服务中启动 `stack` 追踪
2. 使用统一的 `trace_id`（从 `params` 或 `kwargs` 中提取）
3. 合并不同服务的输出，按 `trace_id` 分组

```bash
# 服务 A
peeka-cli stack "service_a.process" | \
  jq --arg service "A" '. + {service: $service}' > trace_a.jsonl

# 服务 B
peeka-cli stack "service_b.handle" | \
  jq --arg service "B" '. + {service: $service}' > trace_b.jsonl

# 合并分析
cat trace_a.jsonl trace_b.jsonl | \
  jq -s 'group_by(.params[0].trace_id)'
```

### 6. 与 Prometheus 集成

**场景**：将调用路径统计导出到 Prometheus 监控。

```bash
# 脚本示例（需要自行实现）
peeka-cli stack "myapp.api.endpoint" -n 1000 | \
  jq -r '.stack[0] | "\(.filename):\(.lineno)"' | \
  sort | uniq -c | \
  awk '{print "call_path_count{path=\""$2"\"} "$1}' > metrics.prom
```

**输出示例**（Prometheus 格式）：
```
call_path_count{path="/app/api/users.py:45"} 123
call_path_count{path="/app/api/orders.py:67"} 78
```

---


## 总结

`stack` 命令是追踪函数调用路径的强大工具，特别适合：
- 定位异常调用来源
- 分析复杂调用链
- 性能热点路径分析
- 递归深度诊断

**最佳实践**：
- 使用条件过滤减少无关数据
- 合理设置栈深度（5-20 层）
- 限制捕获次数（避免产生海量数据）
- 结合 `jq` 进行强大的数据分析
- 调试完成后及时停止追踪

**下一步**：
- 了解 [`watch`](watch.md) 命令（观测参数和返回值）
- 了解 [`memory`](memory.md) 命令（内存分析）
- 参考 [AGENTS.md](../AGENTS.md)（开发者指南）

