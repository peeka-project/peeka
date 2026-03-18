---
layout: default
title: watch 命令
parent: 命令参考
nav_order: 2
---

# watch 命令
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}


## 简介

`watch` 命令用于观测指定 Python 函数的执行情况，能够捕获函数的**入参**、**返回值**、**异常信息**、**执行耗时**等数据。这是
Peeka 最核心的诊断命令，适用于生产环境的实时故障排查和性能分析。


## TUI 使用

在 TUI 模式下，按 **`2`** 键切换到 **Watch 视图**，提供以下交互式功能：

- **模式输入**：支持函数名自动补全（从目标进程实时获取）
- **参数配置**：可视化配置深度、次数、观测点、条件表达式
- **实时流式观测**：观测数据以流式表格展示，自动更新
- **快捷操作**：
  - 输入模式后按 Enter 开始观测
  - 按 `s` 停止当前观测
  - 按 `c` 清空观测记录
  - 按 `r` 刷新视图

**CLI 等效命令**：下文所有示例使用 CLI 命令演示，TUI 提供了相同功能的图形化界面。

## 使用场景

- **故障排查**：观察函数是否被调用、调用参数是否正确、返回值是否符合预期
- **性能分析**：统计函数执行耗时，定位慢调用
- **条件诊断**：只观察满足特定条件的调用（如参数大于某个值时）
- **异常分析**：捕获函数抛出的异常信息和堆栈
- **实时监控**：流式输出观测数据，支持 JSON 格式便于集成到监控系统

## 命令格式

```bash
peeka-cli attach <pid>    # 首先附加到目标进程
peeka-cli watch <pattern> [options]
```

### 参数说明

| 参数                    | 说明                         | 默认值     | 示例                                      |
|-----------------------|----------------------------|---------|-----------------------------------------|
| `pattern`             | 函数匹配模式                     | -       | `module.Class.method`                   |
| `-x, --depth`         | 输出对象深度                     | `2`     | `-x 3`                                  |
| `-n, --times`         | 观测次数（-1 表示无限）              | `-1`    | `-n 10`                                 |
| `--condition` | 条件表达式（支持 `cost` 变量）        | 无       | `--condition "params[0] > 100"` |
| `-b, --before`        | 在函数调用前观测（AtEnter）          | `false` | `-b`                                    |
| `-e, --exception`     | 仅在抛出异常时观测（AtExceptionExit） | `false` | `-e`                                    |
| `-s, --success`       | 仅在成功返回时观测（AtExit）          | `false` | `-s`                                    |
| `-f, --finish`        | 在函数结束后观测（成功或异常）            | `true`  | `-f`                                    |

**注意**：

- 如果不指定 `-b/-e/-s/-f` 任何标志，默认为 `-f`（观测所有结束情况）
- `--condition` 参数仍然支持（为了向后兼容），但推荐使用 `--condition`

### 函数匹配模式 (pattern)

支持以下格式：

```python
# 1. 模块级函数
"mymodule.my_function"

# 2. 类方法
"mymodule.MyClass.my_method"

# 3. 嵌套类方法
"mypackage.mymodule.OuterClass.InnerClass.method"

# 4. 模块路径
"package.subpackage.module.function"
```

**注意**：必须使用完整的模块路径（从导入根开始），不支持通配符匹配。

## 基本用法

### 1. 观测函数调用

```bash
# 首先附加到目标进程
peeka-cli attach 12345

# 观测 5 次调用
peeka-cli watch "calculator.Calculator.add" -n 5
```

**输出示例**：

```json
{
  "watch_id": "watch_a1b2c3d4",
  "timestamp": 1705586200.123,
  "location": "AtExit",
  "func_name": "calculator.Calculator.add",
  "params": [
    10,
    20
  ],
  "kwargs": {},
  "target": {
    "__attrs__": {
      "name": "calc1"
    }
  },
  "returnObj": 30,
  "success": true,
  "throwExp": null,
  "cost": 0.045,
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**字段说明**：

| 字段            | 说明                 | 示例值                                            |
|---------------|--------------------|------------------------------------------------|
| `watch_id`    | 观测 ID              | `"watch_a1b2c3d4"`                             |
| `timestamp`   | 时间戳                | `1705586200.123`                               |
| `location`    | 观测位置               | `"AtEnter"` / `"AtExit"` / `"AtExceptionExit"` |
| `func_name`   | 函数名                | `"module.Class.method"`                        |
| `params`      | 位置参数                | `[10, 20]`                                     |
| `kwargs`      | 关键字参数              | `{"debug": true}`                              |
| `target`      | 目标对象（self，仅实例方法）   | `{"__attrs__": {...}}`                         |
| `returnObj`   | 返回值                  | `30`                                           |
| `success`     | 是否成功               | `true` / `false`                               |
| `throwExp`    | 异常信息                | `"ValueError: ..."`                            |
| `cost`        | 执行耗时（毫秒）        | `0.045`                                        |
| `thread_id`   | 线程 ID              | `140234567890`                                 |
| `thread_name` | 线程名                | `"MainThread"`                                 |

### 2. 调整输出深度

```bash
# 深度为 1：只展示对象类型
peeka-cli watch "service.UserService.get_user" -x 1

# 深度为 3：展示 3 层嵌套结构
peeka-cli watch "service.UserService.get_user" -x 3
```

**深度对比**：

```python
# 原始对象
user = {
    "id": 1,
    "name": "Alice",
    "profile": {
        "age": 25,
        "address": {
            "city": "Beijing"
        }
    }
}

# depth=1
{"id": 1, "name": "Alice", "profile": "{'age': 25, 'address': {...}}"}

# depth=2
{"id": 1, "name": "Alice", "profile": {"age": 25, "address": "{'city': 'Beijing'}"}}

# depth=3
{"id": 1, "name": "Alice", "profile": {"age": 25, "address": {"city": "Beijing"}}}
```

### 3. 无限观测（流式输出）

```bash
# 持续观测，直到手动停止（Ctrl+C）
peeka-cli watch "api.handler.process_request"
```

适用于：

- 实时监控生产环境
- 等待复现间歇性问题
- 长时间数据采集和分析

### 4. 观测静态方法和类方法

```bash
# 静态方法
peeka-cli watch "utils.Helper.static_method"

# 类方法
peeka-cli watch "models.User.from_dict"
```

## 观测时机控制

Peeka 支持多种观测时机控制，可以在函数执行的不同阶段进行观测。

### 观测时机标志

| 标志                | 说明    | 观测时机   | location 字段                  | 可用数据                         |
|-------------------|-------|--------|------------------------------|------------------------------|
| `-b, --before`    | 函数调用前 | 进入函数时  | `AtEnter`                    | `params`, `kwargs`, `target` |
| `-s, --success`   | 成功返回时 | 正常返回后  | `AtExit`                     | 上述 + `returnObj`, `cost`     |
| `-e, --exception` | 异常抛出时 | 抛出异常后  | `AtExceptionExit`            | 上述 + `throwExp`, `cost`      |
| `-f, --finish`    | 函数结束时 | 成功或异常后 | `AtExit` / `AtExceptionExit` | 所有字段                         |

**默认行为**：如果不指定任何标志，默认为 `-f`（观测所有结束情况）

### 使用示例

#### 1. 观测函数入口状态（-b）

```bash
# 观测函数被调用时的参数
peeka-cli watch "service.UserService.update_user" -b
```

**输出**：

```json
{
  "location": "AtEnter",
  "params": [{"id": 1, "name": "Alice"}],
  "kwargs": {"force": true},
  "target": {"__attrs__": {"db": "..."}},
  "returnObj": null,
  "cost": 0.0
}
```

**用途**：

- 确认函数是否被调用
- 检查传入参数是否正确
- 调试函数入口逻辑

#### 2. 仅观测成功返回（-s）

```bash
# 只观测成功的调用，忽略异常
peeka-cli watch "api.handler.process" -s
```

**输出**（仅成功时）：

```json
{
  "location": "AtExit",
  "params": [{"user_id": 123}],
  "returnObj": {"status": "ok"},
  "success": true,
  "cost": 45.2
}
```

**用途**：

- 分析成功调用的返回值
- 统计成功调用的性能
- 忽略异常情况

#### 3. 仅观测异常情况（-e）

```bash
# 只观测抛出异常的调用
peeka-cli watch "database.query" -e
```

**输出**（仅异常时）：

```json
{
  "location": "AtExceptionExit",
  "params": ["SELECT * FROM users"],
  "throwExp": "DatabaseError: Connection timeout",
  "success": false,
  "cost": 5000.0
}
```

**用途**：

- 专注于错误情况
- 分析异常发生的条件
- 监控错误率

#### 4. 观测完整执行过程（-b -s）

```bash
# 同时观测入口和成功返回
peeka-cli watch "calculator.calculate" -b -s
```

**输出**（每次调用产生 2 条记录）：

```json
// 第 1 条：入口
{
  "location": "AtEnter",
  "params": [
    10,
    20
  ],
  "returnObj": null
}

// 第 2 条：出口
{
  "location": "AtExit",
  "params": [
    10,
    20
  ],
  "returnObj": 30,
  "cost": 0.123
}
```

**用途**：

- 观察参数是否在函数执行中被修改
- 完整追踪函数执行流程
- 分析函数的副作用

#### 5. 观测所有情况（-b -e -s）

```bash
# 观测入口、成功、异常所有情况
peeka-cli watch "service.critical_operation" -b -e -s
```

**输出**（根据执行结果产生 2 或 3 条记录）：

- 总是产生 1 条 `AtEnter` 记录
- 成功时产生 1 条 `AtExit` 记录
- 异常时产生 1 条 `AtExceptionExit` 记录

**用途**：

- 完整诊断复杂函数
- 开发环境调试
- 生产环境深度分析

## 条件过滤

### 条件表达式语法

Peeka 使用 **simpleeval** 库实现安全的条件表达式评估，支持以下语法：

#### 支持的操作

| 类型      | 操作符/函数                                                 | 示例                                   |
|---------|--------------------------------------------------------|--------------------------------------|
| **比较**  | `>`, `<`, `>=`, `<=`, `==`, `!=`                       | `params[0] > 100`                    |
| **逻辑**  | `and`, `or`, `not`                                     | `params[0] > 10 and params[1] < 100` |
| **算术**  | `+`, `-`, `*`, `/`, `%`, `**`                          | `params[0] + params[1] > 100`        |
| **成员**  | `in`, `not in`                                         | `'error' in str(result)`             |
| **函数**  | `len()`, `str()`, `int()`, `float()`, `bool()`         | `len(params) > 2`                    |
| **字符串** | `.startswith()`, `.endswith()`, `.upper()`, `.lower()` | `str(params[0]).startswith('test_')` |
| **访问**  | `[]`, `.get()`                                         | `kwargs.get('debug') == True`        |

#### 可用变量

| 变量       | 说明         | 类型     | 可用时机             |
|----------|------------|--------|------------------|
| `params` | 位置参数       | tuple  | 所有时机             |
| `kwargs` | 关键字参数      | dict   | 所有时机             |
| `target` | 目标对象（self） | object | 所有时机（仅实例方法）      |
| `cost`   | 执行耗时（毫秒）   | float  | 仅 `-s/-e/-f` 时可用 |

**注意**：

- `cost` 变量仅在函数执行完成后（`-s/-e/-f`）可用，在 `-b` 时不可用
- `target` 仅在观测实例方法时可用，对于模块级函数或静态方法为 `None`

**安全保障**：

- ❌ 禁止 `__import__`, `eval`, `exec`, `compile`, `open`
- ❌ 禁止访问 `__class__`, `__subclasses__` 等反射属性
- ❌ 禁止执行任意代码

### 条件过滤示例

#### 1. 参数过滤

```bash
# 只观测第一个参数 > 100 的调用
peeka-cli watch "calculator.multiply" --condition "params[0] > 100"

# 参数数量过滤
peeka-cli watch "api.handler" --condition "len(params) > 3"

# 多条件组合
peeka-cli watch "service.query" --condition "params[0] > 10 and params[1] < 100"
```

#### 2. 关键字参数过滤

```bash
# 只观测带 debug 参数的调用
peeka-cli watch "logger.log" --condition "kwargs.get('debug') == True"

# 检查参数是否存在
peeka-cli watch "api.request" --condition "'user_id' in kwargs"
```

#### 3. 字符串匹配

```bash
# 参数以特定前缀开头
peeka-cli watch "db.query" --condition "str(params[0]).startswith('SELECT')"

# 参数包含特定子串
peeka-cli watch "handler.process" --condition "'error' in str(params[0])"
```

#### 4. 类型检查

```bash
# 参数类型过滤
peeka-cli watch "converter.convert" --condition "isinstance(params[0], dict)"
```

#### 5. 复杂条件

```bash
# 组合多个条件
peeka-cli watch "service.process" \
  --condition "len(params) > 2 and params[0] > 100 and 'debug' in kwargs"

# 字符串操作
peeka-cli watch "parser.parse" \
  --condition "len(str(params[0])) > 50 and str(params[0]).endswith('.json')"
```

#### 6. 性能过滤（cost 变量）

```bash
# 只观测执行时间超过 100ms 的调用
peeka-cli watch "database.query" --condition "cost > 100"

# 组合性能和参数条件
peeka-cli watch "api.handler" --condition "cost > 50 and len(params) > 0"

# 观测慢调用的返回值
peeka-cli watch "service.process" -s --condition "cost > 200"
```

**注意**：

- `cost` 变量仅在 `-s/-e/-f` 时可用（函数执行完成后）
- 在 `-b` 时使用 `cost` 会导致条件始终返回 True（cost=0）

#### 7. 对象状态过滤（target 变量）

```bash
# 只观测特定对象状态的调用（仅实例方法）
# 注意：当前版本 target 可用，但不支持属性导航（target.attr）
# 可以在条件中检查 target 是否存在
peeka-cli watch "service.UserService.update" --condition "params[0] > 0"
```

**限制**：

- 当前版本 `target` 变量可用，但 simpleeval 不支持属性导航（如 `target.field_name`）
- 未来版本可能会扩展支持对象属性访问

### 条件表达式调试

如果条件表达式不生效，检查：

1. **语法错误**：检查表达式是否符合 Python 语法
2. **变量拼写**：确认使用 `params` 和 `kwargs`（不是 `args`）
3. **索引越界**：确保 `params[i]` 不会越界
4. **类型错误**：注意参数的实际类型
5. **打印调试**：不加条件先观测一次，查看实际的 params 和 kwargs 内容

**示例**：查看实际参数内容

```bash
# 先不加条件，观测一次调用
peeka-cli watch "mymodule.func" -n 1

# 输出：
# {"args": [100, "test"], "kwargs": {"debug": true}, ...}

# 然后根据实际输出编写条件
peeka-cli watch "mymodule.func" --condition "params[0] > 50"
```

## 输出格式

### JSON 字段说明

每次函数调用会输出一条 JSON 记录：

```json
{
  "watch_id": "watch_a1b2c3d4",
  "timestamp": 1705586200.123,
  "location": "AtExit",
  "func_name": "module.Class.method",
  "params": [1, 2],
  "kwargs": {"key": "value"},
  "target": {"__attrs__": {"field": "value"}},
  "returnObj": 42,
  "success": true,
  "throwExp": null,
  "cost": 1.234,
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**字段说明**：

| 字段            | 类型      | 说明                                   |
|---------------|---------|--------------------------------------|
| `watch_id`    | string  | 观测会话 ID                              |
| `timestamp`   | float   | 调用时间戳（Unix 时间）                       |
| `location`    | string  | 观测位置（AtEnter/AtExit/AtExceptionExit） |
| `func_name`   | string  | 函数完整名称                               |
| `params`      | array   | 位置参数列表                               |
| `kwargs`      | object  | 关键字参数字典                              |
| `target`      | object  | 目标对象（self，仅实例方法）                     |
| `returnObj`   | any     | 返回值（成功时）                             |
| `success`     | boolean | 是否成功执行                               |
| `throwExp`    | string  | 异常信息（失败时）                            |
| `cost`        | float   | 执行耗时（毫秒）                             |
| `thread_id`   | int     | 线程 ID                                |
| `thread_name` | string  | 线程名称                                 |

### 异常捕获

当函数抛出异常时：

```json
{
  "watch_id": "watch_a1b2c3d4",
  "timestamp": 1705586200.123,
  "location": "AtExceptionExit",
  "func_name": "calculator.Calculator.divide",
  "params": [
    10,
    0
  ],
  "kwargs": {},
  "returnObj": null,
  "success": false,
  "throwExp": "ZeroDivisionError: division by zero",
  "cost": 0.032,
  "thread_id": 140234567890,
  "thread_name": "MainThread"
}
```

**注意**：Peeka 会捕获异常信息但**不会抑制异常**，异常仍会正常抛出。

## 数据处理与分析

### 使用 jq 处理 JSON

```bash
# 1. 提取返回值
peeka-cli watch "calculator.add" | jq '.returnObj'

# 2. 提取耗时
peeka-cli watch "api.handler" | jq '.cost'

# 3. 过滤慢调用（耗时 > 100ms）
peeka-cli watch "db.query" | jq 'select(.cost > 100)'

# 4. 只显示失败的调用
peeka-cli watch "service.process" | jq 'select(.success == false)'

# 5. 格式化输出
peeka-cli watch "func" | jq '{time: .timestamp, cost: .cost, result: .returnObj}'
```

### 统计分析

```bash
# 统计调用次数
peeka-cli watch "func" -n 100 | wc -l

# 计算平均耗时
peeka-cli watch "func" -n 100 | jq '.duration_ms' | \
  awk '{sum+=$1; count++} END {print "avg:", sum/count, "ms"}'

# 计算成功率
peeka-cli watch "func" -n 100 | jq '.success' | \
  awk '{total++; if($1=="true") success++} END {print "success rate:", success/total*100, "%"}'

# 找出最慢的调用
peeka-cli watch "func" -n 100 | jq -s 'max_by(.duration_ms)'
```

### 保存到文件

```bash
# 保存为 JSONL 格式（每行一个 JSON）
peeka-cli watch "func" > observations.jsonl

# 后续分析
cat observations.jsonl | jq 'select(.duration_ms > 10)'
```

### 实时监控

```bash
# 实时监控错误率
peeka-cli watch "api.handler" | \
  jq -r 'if .success then "✓" else "✗ " + .error end'

# 实时监控耗时
peeka-cli watch "db.query" | \
  jq -r '"\(.timestamp | strftime("%H:%M:%S")) - \(.duration_ms)ms"'
```

## 性能影响

### 性能开销

| 场景                  | 开销    | 说明          |
|---------------------|-------|-------------|
| **无条件观测**           | < 2%  | 基本的参数捕获和序列化 |
| **条件过滤**            | < 3%  | 增加条件表达式评估开销 |
| **深度遍历（depth=3）**   | < 5%  | 深度遍历嵌套对象    |
| **高频调用（>1000 QPS）** | 5-10% | 高频序列化和网络传输  |

### 性能优化建议

1. **使用条件过滤**：避免捕获所有调用
   ```bash
   # 只捕获慢调用（实际上是捕获后再过滤，建议用其他方式）
   # 更好的方式是结合参数过滤
   peeka-cli watch "func" --condition "params[0] > 1000" -n 100
   ```

2. **限制观测次数**：使用 `-n` 参数
   ```bash
   peeka-cli watch "func" -n 50  # 只观测 50 次
   ```

3. **降低输出深度**：对于复杂对象
   ```bash
   peeka-cli watch "func" -x 1  # 只展示一层
   ```

4. **避免高频函数**：不要观测每秒调用数千次的函数（如基础工具函数）

5. **及时停止观测**：排查完毕后立即停止
   ```bash
   # Ctrl+C 停止观测
   ```

### 内存影响

- **缓冲区大小**：默认 10000 条观测记录（约 10-50MB）
- **自动淘汰**：超过限制时自动丢弃旧数据

## 常见问题

### 1. 观测不到数据

**可能原因**：

- 函数没有被调用
- 函数名拼写错误
- 条件表达式过于严格
- 已达到观测次数限制（-n 参数）

**排查步骤**：

```bash
# 1. 确认函数名是否正确（使用 Python 交互式检查）
python3 -c "import mymodule; print(mymodule.MyClass.my_method)"

# 2. 去掉条件表达式，先观测一次
peeka-cli watch "mymodule.func" -n 1

# 3. 检查进程是否存在
ps aux | grep 12345
```

### 2. 条件表达式报错

**常见错误**：

```bash
# ❌ 错误：使用了禁止的操作
--condition "__import__('os').system('ls')"  # 安全拦截

# ❌ 错误：索引越界
--condition "params[5] > 10"  # 函数只有 3 个参数

# ❌ 错误：变量名错误
--condition "args[0] > 10"  # 应该用 params 而不是 args

# ✓ 正确
--condition "len(params) > 2 and params[0] > 10"
```

**调试方法**：

1. 先观测一次不加条件的调用，查看实际参数
2. 使用简单条件测试（如 `len(params) > 0`）
3. 逐步增加条件复杂度

### 3. 输出深度不够

```bash
# 问题：对象显示为 "{'key': {...}}"
peeka-cli watch "func" -x 2

# 解决：增加深度
peeka-cli watch "func" -x 3
```

**注意**：深度最大为 4，防止过深遍历导致性能问题。

### 4. 观测会影响业务吗？

**安全保障**：

- ✓ 异常不会被抑制（正常抛出）
- ✓ 观测失败不影响原函数执行
- ✓ 自动资源清理（内存、连接）
- ✓ 低性能开销（< 5%）

**最佳实践**：

- 在低峰期首次使用
- 从低频函数开始观测
- 使用条件过滤减少数据量
- 观测后及时停止

### 5. 如何停止观测？

```bash
# 方法 1：Ctrl+C 停止当前观测

# 方法 2：使用 reset 命令移除观测增强
peeka-cli reset "pattern"

# 方法 3：停止所有观测（在交互模式中）
# 当前 CLI 不直接支持，需要通过 Ctrl+C 停止当前会话
```

## 高级技巧

### 1. 多进程观测

```bash
# 并行观测多个进程
for pid in 12345 12346 12347; do
  peeka-cli attach $pid
  peeka-cli watch "api.handler" > "logs/watch_$pid.jsonl" 2>&1 &
done
```

### 2. 定时观测

```bash
# 每小时观测 100 次
while true; do
  peeka-cli watch "scheduler.task" -n 100 >> hourly_samples.jsonl
  sleep 3600
done
```

### 3. 告警集成

```bash
# 监控错误率，超过阈值告警
peeka-cli watch "api.handler" | \
  jq -r 'select(.success == false) | .error' | \
  while read error; do
    echo "Alert: $error" | mail -s "API Error" admin@example.com
  done
```

### 4. 与 Prometheus 集成

```python
# 将观测数据转换为 Prometheus 指标
import json
from prometheus_client import Counter, Histogram

call_counter = Counter('function_calls_total', 'Total calls', ['function', 'status'])
duration_histogram = Histogram('function_duration_seconds', 'Duration', ['function'])

for line in sys.stdin:
    data = json.loads(line)
    func = data['func_name']
    status = 'success' if data['success'] else 'error'
    
    call_counter.labels(function=func, status=status).inc()
    duration_histogram.labels(function=func).observe(data['duration_ms'] / 1000)
```

## 参考资料

- [simpleeval 文档](https://github.com/danthedeckie/simpleeval)
- [Peeka 架构设计](../ARCHITECTURE.md)
- [Peeka 开发指南](../AGENTS.md)

## 更新日志

| 版本    | 日期      | 更新内容               |
|-------|---------|--------------------|
| 0.1.0 | 2025-01 | 初始版本，支持基本 watch 功能 |

