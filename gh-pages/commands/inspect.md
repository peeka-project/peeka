---
layout: default
title: inspect 命令
parent: 命令参考
nav_order: 8
---

# inspect 命令
{: .no_toc }

## 目录
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## 命令简介

`inspect` 命令提供 **运行时对象检查** 功能，可以在不修改代码的情况下查看运行中 Python 进程的对象状态。支持三种操作：

| 操作            | 功能        | 典型用途         |
|---------------|-----------|--------------|
| **get**       | 获取模块/类属性值 | 查看配置、常量、状态变量 |
| **instances** | 查找类型实例    | 内存泄漏排查、对象追踪  |
| **count**     | 统计实例数量    | 快速评估对象数量     |



---

## 使用场景

### 1. 配置检查

生产环境运行时查看配置值，无需重启进程：

```bash
peeka inspect --action get --target "app.config.DEBUG"
```

### 2. 内存泄漏排查

找出特定类型的所有实例，检查是否有对象未释放：

```bash
peeka inspect --action instances --type myapp.User --limit 10
```

### 3. 对象统计

快速统计某类型对象数量，评估内存使用：

```bash
peeka inspect --action count --type list
```

### 4. 状态诊断

查看运行时状态变量，诊断应用行为：

```bash
peeka inspect --action get --target "sys.path"
```

---

## TUI 使用

在 TUI 模式下，按 **`8`** 键切换到 **Inspect 视图**，提供以下交互式功能：

- **操作选择**：可视化切换 get/instances/count 操作
- **get 操作**：
  - 输入目标路径（如 `sys.version`, `module.attr`）
  - 配置输出深度（depth）
  - 展示属性值和类型信息
- **instances 操作**：
  - 输入类名（如 `myapp.User`）
  - 配置结果数量限制、过滤表达式
  - 展示实例列表和属性
  - 支持 --gc-first（执行前先 GC）
- **count 操作**：
  - 输入类名（如 `list`, `dict`）
  - 快速统计实例数量
- **快捷操作**：
  - 输入参数后按 Enter 执行
  - 按 `c` 清空结果

**CLI 等效命令**：下文所有示例使用 CLI 命令演示，TUI 提供了相同功能的图形化界面。

## 命令格式

```bash
# 必须先附加到目标进程
peeka-cli attach <pid>

# 然后执行 inspect 命令
peeka-cli inspect --action <action> [options]
```

### 基本参数

| 参数          | 说明       | 必需 | 默认值   |
|-------------|----------|----|-------|
| `--action`  | 操作类型     | 否  | `get` |

### action 操作类型

| Action        | 说明    | 必需参数       |
|---------------|-------|------------|
| **get**       | 获取属性值 | `--target` |
| **instances** | 查找实例  | `--type`   |
| **count**     | 统计实例数 | `--type`   |

---

## 参数说明

### get 操作参数

| 参数         | 说明        | 示例            |
|------------|-----------|---------------|
| `--target` | 目标路径（点分隔） | `sys.version` |
| `--depth`  | 输出嵌套深度    | `--depth 3`   |

**target 解析规则**：

- 第一段必须是 `sys.modules` 中的模块
- 后续段通过 `getattr()` 链式查找
- **不支持**字典键查找（如 `config["debug"]`）

示例：

- `sys.version` → `getattr(sys.modules["sys"], "version")`
- `myapp.Config.DEBUG` → `getattr(getattr(sys.modules["myapp"], "Config"), "DEBUG")`

### instances 操作参数

| 参数                 | 说明       | 默认值     | 范围            |
|--------------------|----------|---------|---------------|
| `--type`           | 类型名称     | -       | 必需            |
| `--limit`          | 结果数量限制   | `10`    | 1-1000        |
| `--depth`          | 输出嵌套深度   | `2`     | 0-10          |
| `--filter-express` | 过滤表达式    | 无       | SimpleEval 语法 |
| `--gc-first`       | 扫描前执行 GC | `False` | -             |

**type 解析规则**：

- 内置类型：`str`, `int`, `list`, `dict`, `set`, `tuple`, `bytes`, `bool`, `float`
- 自定义类型：`module.ClassName`（模块必须已加载）
- **不支持**动态导入模块

### count 操作参数

| 参数                 | 说明       | 默认值     |
|--------------------|----------|---------|
| `--type`           | 类型名称     | -       |
| `--filter-express` | 过滤表达式    | 无       |
| `--gc-first`       | 扫描前执行 GC | `False` |

**特殊说明**：`count` 操作会**遍历所有**对象（无 limit 限制），仅统计计数不存储对象，内存开销极小。

### 过滤表达式

过滤表达式使用 **SimpleEval** 安全求值器，支持的语法：

| 语法      | 说明                                  | 示例                            |
|---------|-------------------------------------|-------------------------------|
| `obj.*` | 对象属性                                | `obj.value`                   |
| 比较运算    | `>`, `<`, `==`, `!=`                | `obj.age > 18`                |
| 逻辑运算    | `and`, `or`, `not`                  | `obj.active and obj.age > 18` |
| 算术运算    | `+`, `-`, `*`, `/`                  | `obj.score * 2 > 100`         |
| 函数调用    | `len()`, `str()`, `int()`, `bool()` | `len(obj.items) > 0`          |

**安全限制**：

- ❌ 禁止 `eval()`, `exec()`, `compile()`
- ❌ 禁止 `__import__`, `open()`, `__class__`
- ❌ 禁止访问私有属性（`__*__`）

**错误处理**：

- 语法错误：**整个命令失败**
- 运行时错误（如属性不存在）：**跳过该对象**

---

## 输出格式

### get 响应

```json
{
  "status": "success",
  "action": "get",
  "target": "sys.version",
  "type": "str",
  "value": "3.14.2 (main, Jan  1 2026, 10:00:00) [GCC 11.4.0]"
}
```

| 字段       | 说明                     |
|----------|------------------------|
| `status` | 状态：`success` 或 `error` |
| `action` | 操作类型                   |
| `target` | 查询的目标路径                |
| `type`   | 值的类型名称                 |
| `value`  | 属性值（深度限制）              |

### instances 响应

```json
{
  "status": "success",
  "action": "instances",
  "class_name": "list",
  "count": 5,
  "limit": 10,
  "truncated": false,
  "instances": [
    {
      "type": "list",
      "value": [
        1,
        2,
        3
      ]
    },
    {
      "type": "list",
      "value": [
        "a",
        "b"
      ]
    }
  ]
}
```

| 字段           | 说明                           |
|--------------|------------------------------|
| `class_name` | 查询的类型                        |
| `count`      | 返回的实例数量（`== len(instances)`） |
| `limit`      | 请求的限制数量                      |
| `truncated`  | 是否有更多实例（`true`/`false`）      |
| `instances`  | 实例数组（深度限制）                   |

**truncated 语义**：

- `true`：堆中还有更多匹配实例（数量未知）
- `false`：已返回所有匹配的 GC 追踪对象

### count 响应

```json
{
  "status": "success",
  "action": "count",
  "class_name": "list",
  "count": 240
}
```

| 字段           | 说明         |
|--------------|------------|
| `class_name` | 查询的类型      |
| `count`      | GC 追踪的实例总数 |

### error 响应

```json
{
  "status": "error",
  "action": "get",
  "error": "Cannot resolve target: Module 'nonexistent' not loaded in target process"
}
```

---

## 使用示例

### 示例 1：查看系统信息

```bash
# 查看 Python 版本
peeka inspect --action get --target "sys.version"

# 查看 sys.path
peeka inspect --action get --target "sys.path" --depth 3
```

**输出**：

```json
{
  "status": "success",
  "action": "get",
  "target": "sys.path",
  "type": "list",
  "value": [
    "/usr/lib/python3.14",
    "/home/user/project",
    "... (truncated)"
  ]
}
```

### 示例 2：查看配置值

```bash
# 查看应用配置
peeka inspect --action get --target "myapp.config.DEBUG"

# 查看类常量
peeka inspect --action get --target "myapp.Database.POOL_SIZE"
```

### 示例 3：内存泄漏排查

```bash
# 查找所有 User 实例
peeka inspect --action instances --type myapp.User --limit 20

# 过滤活跃用户
peeka inspect --action instances --type myapp.User \
  --filter-express "obj.active == True" --limit 10

# 过滤大对象
peeka inspect --action instances --type list \
  --filter-express "len(obj) > 100" --limit 5
```

**输出**：

```json
{
  "status": "success",
  "action": "instances",
  "class_name": "myapp.User",
  "count": 20,
  "limit": 20,
  "truncated": true,
  "instances": [
    {
      "type": "myapp.User",
      "value": "<User(id=1, name='Alice', active=True)>"
    }
  ]
}
```

### 示例 4：对象统计

```bash
# 统计所有 list 实例
peeka inspect --action count --type list

# 统计 dict 实例
peeka inspect --action count --type dict

# 统计特定条件的对象
peeka inspect --action count --type myapp.Connection \
  --filter-express "obj.closed == False"
```

**输出**：

```json
{
  "status": "success",
  "action": "count",
  "class_name": "list",
  "count": 240
}
```

### 示例 5：与 jq 结合使用

```bash
# 提取 value 字段
peeka inspect --action get --target "sys.version" | jq -r '.value'

# 统计实例数
peeka inspect --action count --type list | jq '.count'

# 美化输出
peeka inspect --action instances --type dict --limit 3 | jq .
```

---

## 完整诊断流程

### 场景：排查内存泄漏

**问题**：生产环境内存持续增长，怀疑某个类的实例未释放。

**步骤 1：统计对象数量**

```bash
# 定期统计可疑类型
peeka inspect --action count --type myapp.Cache
# 输出: {"count": 1500}

# 5 分钟后再次统计
peeka inspect --action count --type myapp.Cache
# 输出: {"count": 1800}  ← 持续增长!
```

**步骤 2：查看实例样本**

```bash
# 获取前 10 个实例
peeka inspect --action instances --type myapp.Cache --limit 10 | jq .

# 查看大对象
peeka inspect --action instances --type myapp.Cache \
  --filter-express "len(obj.data) > 1000" --limit 5
```

**步骤 3：检查配置**

```bash
# 查看缓存配置
peeka inspect --action get --target "myapp.cache_config.MAX_SIZE"
# 发现 MAX_SIZE 未生效!
```

**步骤 4：修复验证**

修复代码后重新部署，再次统计：

```bash
peeka inspect --action count --type myapp.Cache
# 输出: {"count": 100}  ← 恢复正常
```

---

## 注意事项

### ⚠️ GC 追踪对象限制

`gc.get_objects()` **仅返回 GC 追踪的对象**：

| 类型                             | 是否追踪 | instances/count 结果 |
|--------------------------------|------|--------------------|
| `list`, `dict`, `set`, `tuple` | ✅ 是  | 可靠                 |
| 自定义类实例                         | ✅ 是  | 可靠                 |
| `str`, `int`, `float`, `bytes` | ❌ 否  | 可能为 0 或不完整         |

**建议**：

- 排查内存泄漏：优先使用 **容器类型** 或 **自定义类**
- 统计字符串/整数：结果**不可靠**，仅供参考

### ⚠️ Target 解析规则

`--target` 参数使用 `getattr()` 链，**不支持字典键**：

```bash
# ❌ 错误：不支持字典键语法
peeka inspect --action get --target 'config["debug"]'

# ✅ 正确：先获取字典，手动查看
peeka inspect --action get --target "config" | jq '.value.debug'
```

### ⚠️ 模块加载限制

`--type` 参数**不会动态导入模块**：

```bash
# ❌ 错误：myapp 未加载时查询会失败
peeka inspect --action instances --type myapp.User

# ✅ 正确：确保目标进程已导入 myapp 模块
# （在目标代码中必须有 import myapp）
```

### ⚠️ 性能影响

| 操作          | 堆遍历            | 性能影响         |
|-------------|----------------|--------------|
| `get`       | ❌ 否            | 极低（< 1ms）    |
| `instances` | ✅ 部分（直到 limit） | 中等（10-100ms） |
| `count`     | ✅ 全部           | 较高（50-500ms） |

**建议**：

- `count` 操作在大内存进程中可能耗时较长
- 生产环境使用时注意频率，避免影响性能

### ⚠️ 过滤表达式安全

过滤表达式使用 **SimpleEval** 防止代码注入：

```bash
# ✅ 安全：SimpleEval 允许的操作
peeka inspect --action instances --type myapp.User \
  --filter-express "obj.age > 18 and obj.active"

# ❌ 禁止：代码注入攻击
peeka inspect --action instances --type myapp.User \
  --filter-express "__import__('os').system('rm -rf /')"
# 错误: Invalid filter expression: __import__ not allowed
```

---

## 常见问题

### Q1: instances 返回 count: 0，但我确定有对象

**A**: 可能是以下原因：

1. **对象未被 GC 追踪**（如 `str`, `int`）
   ```bash
   # str/int 可能不可靠
   peeka inspect --action count --type str  # 可能为 0
   
   # 改用容器类型
   peeka inspect --action count --type list  # 可靠
   ```

2. **模块未加载**
   ```bash
   # 确认模块已导入
   peeka inspect --action get --target "sys.modules.keys()" | grep myapp
   ```

3. **filter-express 过滤掉了所有对象**
   ```bash
   # 先不用过滤器测试
   peeka inspect --action instances --type myapp.User --limit 5
   ```

### Q2: target 查询失败 "Module not loaded"

**A**: 目标模块未在进程中导入。

**解决方法**：

```bash
# 检查已加载模块
peeka inspect --action get --target "list(sys.modules.keys())" | grep myapp

# 如果模块未加载，需要在目标代码中添加 import
```

### Q3: filter-express 语法错误

**A**: SimpleEval 仅支持有限的语法。

**常见错误**：

```bash
# ❌ 不支持列表推导
--filter-express "[x for x in obj.items]"

# ✅ 使用 len() 代替
--filter-express "len(obj.items) > 0"

# ❌ 不支持字典键语法
--filter-express "obj['key'] > 0"

# ✅ 使用属性语法
--filter-express "obj.key > 0"
```

### Q4: count 操作很慢

**A**: `count` 会遍历整个堆，对象数量多时较慢。

**优化建议**：

```bash
# 使用 instances 代替（有 limit）
peeka inspect --action instances --type list --limit 10

# 或者在业务低峰期执行 count
```

### Q5: instances 的 truncated 总是 true

**A**: 说明匹配对象超过 `limit`。

**解决方法**：

```bash
# 增加 limit（最大 1000）
peeka inspect --action instances --type list --limit 1000

# 或使用过滤器缩小范围
peeka inspect --action instances --type list \
  --filter-express "len(obj) > 100" --limit 10
```

---

## 高级技巧

### 技巧 1：定期监控对象数量

```bash
#!/bin/bash
# monitor_objects.sh - 监控对象数量变化

PID=12345
TYPE="myapp.Connection"

while true; do
  COUNT=$(peeka inspect --action count --type $TYPE | jq '.count')
  echo "$(date): $TYPE count = $COUNT"
  sleep 60
done
```

### 技巧 2：组合使用 get 和 instances

```bash
# 先查询配置
CONFIG=$(peeka inspect --action get --target "myapp.config.MAX_CONNECTIONS" | jq '.value')

# 再统计实际连接数
ACTUAL=$(peeka inspect --action count --type myapp.Connection | jq '.count')

# 比较
echo "配置: $CONFIG, 实际: $ACTUAL"
```

### 技巧 3：使用 gc-first 获取准确计数

```bash
# GC 前
peeka inspect --action count --type myapp.Cache
# 输出: {"count": 1500}

# 强制 GC 后
peeka inspect --action count --type myapp.Cache --gc-first
# 输出: {"count": 1200}  ← 清理了未引用对象
```

### 技巧 4：复杂过滤表达式

```bash
# 多条件过滤
peeka inspect --action instances --type myapp.User \
  --filter-express "obj.age > 18 and obj.active and len(obj.name) > 0" \
  --limit 10

# 算术运算
peeka inspect --action instances --type myapp.Score \
  --filter-express "obj.math + obj.english > 180" \
  --limit 5
```

### 技巧 5：导出分析

```bash
# 导出 instances 到文件
peeka inspect --action instances --type myapp.User --limit 100 > users.json

# 离线分析
jq '.instances | map(.value.age) | add / length' users.json  # 平均年龄
jq '.instances | map(select(.value.active == true)) | length' users.json  # 活跃用户数
```

---



## 总结

### 核心功能

| 操作            | 用途      | 性能 | 堆遍历 |
|---------------|---------|----|-----|
| **get**       | 查看属性/配置 | 极快 | ❌   |
| **instances** | 内存排查    | 中等 | 部分  |
| **count**     | 对象统计    | 较慢 | 全部  |

### 典型使用流程

1. **快速检查**：`get` 查看配置和状态
2. **数量评估**：`count` 统计对象数量
3. **详细分析**：`instances` 获取实例样本
4. **过滤筛选**：`--filter-express` 缩小范围

### 最佳实践

✅ **推荐**：

- 使用容器类型（list, dict）进行 instances/count
- 组合使用 jq 处理 JSON 输出
- 定期监控关键对象数量
- 使用过滤表达式精确定位问题

❌ **避免**：

- 频繁执行 count（性能影响）
- 对 str/int 使用 instances（不可靠）
- 在过滤表达式中使用复杂逻辑
- 忘记检查模块是否已加载

### 相关命令

- `memory` - 内存分析和追踪
- `sc` - 搜索类
- `sm` - 搜索方法

