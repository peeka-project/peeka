# Peeka Search 命令详解（sc / sm）

## 目录

- [命令简介](#命令简介)
- [使用场景](#使用场景)
- [命令格式](#命令格式)
- [sc 命令 - 搜索类](#sc-命令---搜索类)
- [sm 命令 - 搜索方法](#sm-命令---搜索方法)
- [Pattern 模式语法](#pattern-模式语法)
- [输出格式](#输出格式)
- [使用示例](#使用示例)
- [完整探索流程](#完整探索流程)
- [注意事项](#注意事项)
- [常见问题](#常见问题)
- [高级技巧](#高级技巧)
- [与 Arthas 对比](#与-arthas-对比)

---

## 命令简介

`sc` (Search Class) 和 `sm` (Search Method) 命令用于在运行中的 Python 进程中搜索类和方法，帮助开发者快速了解代码结构、发现可用API、定位目标函数。

**核心功能**：
- **sc**：搜索已加载模块中的类
- **sm**：搜索类中的方法
- 支持通配符模式匹配（`*`, `?`）
- 显示类/方法的详细信息（文件路径、文档字符串等）
- 结果数量限制（避免输出过多）
- 适合代码探索和动态分析

**典型场景**：
- 探索未知代码库（找出有哪些类和方法）
- 查找特定功能的实现（如搜索所有 `*Handler` 类）
- 获取函数签名（用于 `watch`、`stack` 等命令）
- 验证模块是否已加载
- 学习第三方库的 API

---

## 使用场景

### 1. 探索未知代码库

**场景**：接手新项目，需要快速了解代码结构。

```bash
# 查看所有应用类（假设模块名为 myapp）
peeka-cli sc -p 12345 "myapp.*"

# 输出：
# myapp.api.UserHandler
# myapp.api.OrderHandler
# myapp.models.User
# myapp.models.Order
# myapp.utils.Helper
```

**用途**：快速了解项目有哪些模块和类。

### 2. 查找特定功能

**场景**：需要找出所有处理器类（Handler）。

```bash
# 搜索所有以 Handler 结尾的类
peeka-cli sc -p 12345 "*Handler"

# 输出：
# myapp.api.UserHandler
# myapp.api.OrderHandler
# myapp.api.PaymentHandler
```

### 3. 获取方法签名

**场景**：想使用 `watch` 命令监控某个方法，但不知道完整签名。

```bash
# 步骤 1：搜索类
peeka-cli sc -p 12345 "myapp.api.UserHandler"

# 步骤 2：搜索类的所有方法
peeka-cli sm -p 12345 "myapp.api.UserHandler.*"

# 输出：
# get (self, user_id: int) -> dict
# create (self, **data) -> dict
# update (self, user_id: int, **data) -> bool
# delete (self, user_id: int) -> bool

# 步骤 3：使用 watch 监控
peeka-cli watch -p 12345 "myapp.api.UserHandler.get"
```

### 4. 验证模块是否加载

**场景**：怀疑某个模块未被加载，导致功能不可用。

```bash
# 搜索目标模块的类
peeka-cli sc -p 12345 "myapp.plugins.payment.*"

# 如果输出为空，说明模块未加载
# 如果有输出，说明模块已加载
```

### 5. 学习第三方库 API

**场景**：想了解 `requests` 库有哪些类和方法。

```bash
# 查看 requests 模块的所有类
peeka-cli sc -p 12345 "requests.*" -d

# 查看 Session 类的所有方法
peeka-cli sm -p 12345 "requests.Session.*"

# 输出：
# get (self, url, **kwargs) -> Response
# post (self, url, data=None, json=None, **kwargs) -> Response
# put (self, url, data=None, **kwargs) -> Response
# ...
```

---

## 命令格式

### sc - 搜索类

```bash
peeka-cli sc [--pid PID | --name NAME] <pattern> [options]
```

**必需参数**：
- `--pid, -p`：目标进程 PID（与 `--name` 二选一）
- `--name`：目标进程名称（与 `--pid` 二选一）
- `pattern`：类模式（支持通配符）

**可选参数**：
- `-d, --detail`：显示详细信息（文件路径、文档字符串）
- `--limit`：结果数量限制（默认 50）

### sm - 搜索方法

```bash
peeka-cli sm [--pid PID | --name NAME] <class_pattern> [options]
```

**必需参数**：
- `--pid, -p`：目标进程 PID（与 `--name` 二选一）
- `--name`：目标进程名称（与 `--pid` 二选一）
- `class_pattern`：类模式（支持通配符）

**可选参数**：
- `--method-pattern`：方法模式（默认 `*`，匹配所有方法）
- `-d, --detail`：显示详细信息（模块、文档字符串）

---

## sc 命令 - 搜索类

### 基本用法

```bash
# 搜索特定类
peeka-cli sc -p 12345 "myapp.User"

# 搜索模块下的所有类
peeka-cli sc -p 12345 "myapp.models.*"

# 搜索所有以 Handler 结尾的类
peeka-cli sc -p 12345 "*Handler"

# 显示详细信息
peeka-cli sc -p 12345 "myapp.models.*" -d
```

### 输出字段

**基本模式**（不带 `-d`）：
```json
{
  "status": "success",
  "classes": [
    {"name": "myapp.models.User"},
    {"name": "myapp.models.Order"}
  ],
  "count": 2,
  "limit": 50
}
```

**详细模式**（带 `-d`）：
```json
{
  "status": "success",
  "classes": [
    {
      "name": "myapp.models.User",
      "module": "myapp.models",
      "file": "/app/myapp/models.py",
      "docstring": "User model class representing a system user."
    }
  ],
  "count": 1,
  "limit": 50
}
```

### Pattern 示例

| Pattern | 匹配示例 | 说明 |
|---------|----------|------|
| `json.*` | `json.JSONEncoder`, `json.JSONDecoder` | json 模块下的所有类 |
| `myapp.models.*` | `myapp.models.User`, `myapp.models.Order` | myapp.models 模块下的所有类 |
| `*Handler` | `UserHandler`, `OrderHandler` | 所有以 Handler 结尾的类 |
| `*Command` | `WatchCommand`, `StackCommand` | 所有以 Command 结尾的类 |
| `collections.Ordered*` | `collections.OrderedDict` | collections 模块下以 Ordered 开头的类 |

---

## sm 命令 - 搜索方法

### 基本用法

```bash
# 搜索类的所有方法
peeka-cli sm -p 12345 "myapp.User.*"

# 等价写法（使用 --method-pattern）
peeka-cli sm -p 12345 "myapp.User" --method-pattern "*"

# 搜索特定方法
peeka-cli sm -p 12345 "myapp.User.get"

# 搜索以 get_ 开头的方法
peeka-cli sm -p 12345 "myapp.User" --method-pattern "get_*"

# 显示详细信息
peeka-cli sm -p 12345 "myapp.User.*" -d
```

### 输出字段

**基本模式**（不带 `-d`）：
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict"
    },
    {
      "name": "create",
      "signature": "(self, **data) -> dict"
    }
  ],
  "count": 2,
  "limit": 50
}
```

**详细模式**（带 `-d`）：
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict",
      "module": "myapp.models",
      "class": "User",
      "docstring": "Get user by ID.\n\nArgs:\n    user_id: User ID\n\nReturns:\n    User dict or None"
    }
  ],
  "count": 1,
  "limit": 50
}
```

### Pattern 组合示例

| Class Pattern | Method Pattern | 匹配示例 |
|---------------|----------------|----------|
| `myapp.User` | `*` | User 类的所有方法 |
| `myapp.User` | `get*` | `get`, `get_by_id`, `get_all` |
| `myapp.User` | `*_by_id` | `get_by_id`, `delete_by_id` |
| `myapp.*Handler` | `handle` | 所有 Handler 类的 handle 方法 |
| `json.JSONEncoder` | `encode*` | `encode`, `encode_object` |

---

## Pattern 模式语法

### 支持的通配符

| 通配符 | 说明 | 示例 |
|--------|------|------|
| `*` | 匹配任意长度的字符（包括空） | `myapp.*` 匹配 `myapp.User`, `myapp.Order` |
| `?` | 匹配单个字符 | `User?` 匹配 `User1`, `User2` |
| `[seq]` | 匹配 seq 中的任意字符 | `User[12]` 匹配 `User1`, `User2` |
| `[!seq]` | 匹配不在 seq 中的任意字符 | `User[!0]` 匹配 `User1`, `User2`（不匹配 `User0`） |

### Pattern 类型

#### 1. 完整限定名

```bash
# 精确匹配
peeka-cli sc -p 12345 "myapp.models.User"
peeka-cli sm -p 12345 "myapp.models.User.get"
```

#### 2. 模块级通配符

```bash
# 模块下的所有类
peeka-cli sc -p 12345 "myapp.models.*"

# 多级通配符
peeka-cli sc -p 12345 "myapp.*.User"  # myapp 下任意子模块的 User 类
```

#### 3. 类名通配符

```bash
# 前缀匹配
peeka-cli sc -p 12345 "*Handler"       # 所有 Handler 类
peeka-cli sc -p 12345 "myapp.*Handler" # myapp 下的所有 Handler 类

# 后缀匹配
peeka-cli sc -p 12345 "User*"          # User, UserHandler, UserModel

# 中间匹配
peeka-cli sc -p 12345 "*User*"         # UserHandler, AdminUser, User
```

#### 4. 方法名通配符

```bash
# sm 命令的方法模式
peeka-cli sm -p 12345 "myapp.User" --method-pattern "get*"
peeka-cli sm -p 12345 "myapp.User" --method-pattern "*_by_id"
peeka-cli sm -p 12345 "myapp.User" --method-pattern "is_*"
```

---

## 输出格式

### sc 命令输出

**基本模式**：
```json
{
  "status": "success",
  "classes": [
    {"name": "myapp.models.User"},
    {"name": "myapp.models.Order"},
    {"name": "myapp.api.UserHandler"}
  ],
  "count": 3,
  "limit": 50
}
```

**详细模式**（`-d`）：
```json
{
  "status": "success",
  "classes": [
    {
      "name": "myapp.models.User",
      "module": "myapp.models",
      "file": "/app/myapp/models.py",
      "docstring": "User model representing a system user.\n\nAttributes:\n    id: User ID\n    username: Username"
    }
  ],
  "count": 1,
  "limit": 50
}
```

### sm 命令输出

**基本模式**：
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict"
    },
    {
      "name": "create",
      "signature": "(self, **data) -> dict"
    },
    {
      "name": "update",
      "signature": "(self, user_id: int, **data) -> bool"
    }
  ],
  "count": 3,
  "limit": 50
}
```

**详细模式**（`-d`）：
```json
{
  "status": "success",
  "methods": [
    {
      "name": "get",
      "signature": "(self, user_id: int) -> dict",
      "module": "myapp.models",
      "class": "User",
      "docstring": "Get user by ID.\n\nArgs:\n    user_id: User ID\n\nReturns:\n    User dict or None if not found"
    }
  ],
  "count": 1,
  "limit": 50
}
```

---

## 使用示例

### 示例 1：查找应用的所有模型类

```bash
peeka-cli sc -p 12345 "myapp.models.*" | jq -r '.classes[].name'
```

**输出**：
```
myapp.models.User
myapp.models.Order
myapp.models.Product
myapp.models.Payment
```

### 示例 2：查找所有 Handler 类并获取详细信息

```bash
peeka-cli sc -p 12345 "*Handler" -d | jq .
```

**输出**：
```json
{
  "status": "success",
  "classes": [
    {
      "name": "myapp.api.UserHandler",
      "module": "myapp.api",
      "file": "/app/myapp/api.py",
      "docstring": "Handles user-related API requests."
    },
    {
      "name": "myapp.api.OrderHandler",
      "module": "myapp.api",
      "file": "/app/myapp/api.py",
      "docstring": "Handles order-related API requests."
    }
  ],
  "count": 2
}
```

### 示例 3：查找类的所有方法

```bash
peeka-cli sm -p 12345 "myapp.User.*" | jq -r '.methods[] | "\(.name)\(.signature)"'
```

**输出**：
```
get(self, user_id: int) -> dict
create(self, **data) -> dict
update(self, user_id: int, **data) -> bool
delete(self, user_id: int) -> bool
is_active(self) -> bool
```

### 示例 4：查找所有 get_ 开头的方法

```bash
peeka-cli sm -p 12345 "myapp.User" --method-pattern "get_*" | jq -r '.methods[].name'
```

**输出**：
```
get_by_id
get_by_username
get_all
get_active_users
```

### 示例 5：探索第三方库（requests）

```bash
# 查看 requests 模块有哪些类
peeka-cli sc -p 12345 "requests.*" | jq -r '.classes[].name'

# 输出：
# requests.Session
# requests.Response
# requests.Request
# requests.PreparedRequest

# 查看 Session 类的方法
peeka-cli sm -p 12345 "requests.Session" --method-pattern "*" | \
  jq -r '.methods[] | "\(.name)\(.signature)"'

# 输出：
# get(self, url, **kwargs) -> Response
# post(self, url, data=None, json=None, **kwargs) -> Response
# ...
```

### 示例 6：与 watch 命令结合

**场景**：找到目标方法后，使用 `watch` 监控。

```bash
# 步骤 1：搜索所有处理订单的方法
peeka-cli sm -p 12345 "myapp.Order" --method-pattern "*process*"

# 输出：
# process_payment
# process_refund
# process_shipment

# 步骤 2：选择目标方法并监控
peeka-cli watch -p 12345 "myapp.Order.process_payment" -n 10
```

---

## 完整探索流程

### 流程 1：探索未知代码库

**目标**：快速了解项目结构和主要类。

```bash
# 步骤 1：列出所有应用模块的类
peeka-cli sc -p 12345 "myapp.*" > classes.json

# 步骤 2：按模块分组统计
jq -r '.classes[].name | split(".") | .[0:2] | join(".")' classes.json | \
  sort | uniq -c

# 输出：
#   12 myapp.api
#   8 myapp.models
#   5 myapp.utils
#   3 myapp.services

# 步骤 3：查看每个模块的详细类
peeka-cli sc -p 12345 "myapp.api.*" -d | \
  jq -r '.classes[] | "\(.name)\n  \(.docstring)\n"'
```

### 流程 2：定位特定功能的实现

**目标**：找出实现支付功能的所有类和方法。

```bash
# 步骤 1：搜索所有与 payment 相关的类
peeka-cli sc -p 12345 "*payment*" -d

# 步骤 2：找到目标类后，查看其方法
peeka-cli sm -p 12345 "myapp.payment.PaymentProcessor.*" -d

# 步骤 3：查看特定方法的详细信息
peeka-cli sm -p 12345 "myapp.payment.PaymentProcessor.charge" -d | \
  jq -r '.methods[0].docstring'
```

### 流程 3：验证代码重构

**目标**：重构后验证旧类是否已删除，新类是否已加载。

```bash
# 步骤 1：搜索旧类（应该找不到）
peeka-cli sc -p 12345 "myapp.OldUserHandler"
# 输出：{"status":"success","classes":[],"count":0}

# 步骤 2：搜索新类（应该能找到）
peeka-cli sc -p 12345 "myapp.NewUserHandler" -d

# 步骤 3：对比新旧类的方法
peeka-cli sm -p 12345 "myapp.NewUserHandler.*" > new_methods.json
# 对比 old_methods.json 和 new_methods.json
```

### 流程 4：学习第三方库 API

**目标**：学习 Flask 框架的核心类和方法。

```bash
# 步骤 1：查看 Flask 有哪些类
peeka-cli sc -p 12345 "flask.*" | jq -r '.classes[].name'

# 输出：
# flask.Flask
# flask.Blueprint
# flask.Request
# flask.Response

# 步骤 2：查看 Flask 类的所有方法
peeka-cli sm -p 12345 "flask.Flask.*" | \
  jq -r '.methods[] | "\(.name)\(.signature)"'

# 步骤 3：查看特定方法的文档
peeka-cli sm -p 12345 "flask.Flask.route" -d | \
  jq -r '.methods[0].docstring'
```

---

## 注意事项

### 1. 只能搜索已加载的模块

**重要**：`sc` 和 `sm` 命令只能搜索**已被导入的模块**。

```bash
# 如果 myapp.plugin 模块未被导入，搜索不到
peeka-cli sc -p 12345 "myapp.plugin.*"
# 输出：{"classes": [], "count": 0}
```

**解决方法**：
- 触发功能，让模块被导入（如访问相关 API）
- 或查看代码，确认模块确实会被导入

### 2. 魔法方法默认不显示

**默认行为**：`sm` 命令不显示魔法方法（`__init__`, `__str__` 等）。

```bash
# 不会显示 __init__, __str__, __repr__ 等
peeka-cli sm -p 12345 "myapp.User.*"
```

**原因**：魔法方法通常不是业务逻辑的入口，过滤掉可以减少噪音。

### 3. 结果数量限制

**默认限制**：最多返回 50 个结果。

```bash
# 如果匹配超过 50 个，只返回前 50 个
peeka-cli sc -p 12345 "*" --limit 50
```

**调整限制**：
```bash
# 增加限制到 200
peeka-cli sc -p 12345 "*" --limit 200
```

**注意**：
- 限制过大可能导致输出过多，性能下降
- 建议使用更具体的模式而非增加限制

### 4. 文件路径可能为 None

**原因**：部分类（如内置类、C 扩展）没有对应的 Python 文件。

```bash
peeka-cli sc -p 12345 "builtins.dict" -d

# 输出：
# {"name": "builtins.dict", "file": null, ...}
```

### 5. 签名可能无法获取

**原因**：部分方法（如 C 扩展、builtins）无法通过 `inspect.signature()` 获取签名。

```bash
peeka-cli sm -p 12345 "builtins.dict.get"

# 输出：
# {"name": "get", "signature": null}
```

### 6. 性能影响

**影响程度**：
- `sc` 和 `sm` 命令会遍历 `sys.modules`，可能需要几百毫秒
- 结果数量越多，输出时间越长
- 总体性能影响可忽略（一次性操作）

**建议**：
- 使用具体的模式减少搜索范围
- 避免频繁调用（如循环中）

---

## 常见问题

### Q1: 为什么搜索不到某个类？

**可能原因**：
1. **模块未导入**：类所在的模块未被加载到内存
2. **Pattern 错误**：模式不匹配类的完整限定名
3. **结果超出限制**：结果数量超过 `--limit`

**排查方法**：
```bash
# 方法 1：检查模块是否已导入
python3 -c "import sys; print('myapp.models' in sys.modules)"

# 方法 2：使用更宽松的模式
peeka-cli sc -p 12345 "*User*"

# 方法 3：增加限制
peeka-cli sc -p 12345 "myapp.*" --limit 200
```

### Q2: 如何搜索所有模块的所有类？

**答案**：使用 `*` 通配符。

```bash
peeka-cli sc -p 12345 "*" --limit 200
```

**警告**：
- 结果数量可能非常多（包括标准库和第三方库）
- 建议使用更具体的模式

### Q3: sm 命令为什么不显示 __init__ 方法？

**原因**：魔法方法默认被过滤掉。

**如需查看魔法方法**：
- 当前版本不支持（未来可能添加 `--show-magic` 参数）
- 可以使用 Python 代码查看：
  ```python
  import inspect
  print([m for m in dir(MyClass) if m.startswith('__')])
  ```

### Q4: 如何搜索方法时同时匹配类名和方法名？

**方法**：使用 `sm` 命令的两个参数组合。

```bash
# 搜索所有 Handler 类的 handle 方法
# 注意：需要知道具体的模块名
peeka-cli sm -p 12345 "myapp.api.*Handler" --method-pattern "handle"
```

**限制**：`class_pattern` 必须包含模块名，不能单独使用 `*Handler`。

### Q5: 如何导出搜索结果到文件？

**方法**：使用重定向或 `jq`。

```bash
# 导出所有类到文件
peeka-cli sc -p 12345 "myapp.*" > classes.json

# 导出类名列表（纯文本）
peeka-cli sc -p 12345 "myapp.*" | jq -r '.classes[].name' > class_names.txt

# 导出方法签名表
peeka-cli sm -p 12345 "myapp.User.*" | \
  jq -r '.methods[] | "\(.name)\(.signature)"' > user_methods.txt
```

### Q6: 可以搜索标准库的类吗？

**答案**：可以，只要模块已被导入。

```bash
# 搜索 json 模块的类
peeka-cli sc -p 12345 "json.*"

# 搜索 collections 模块的类
peeka-cli sc -p 12345 "collections.*"

# 搜索 logging 模块的类
peeka-cli sc -p 12345 "logging.*"
```

---

## 高级技巧

### 1. 生成项目 API 文档

**场景**：自动生成项目的类和方法清单。

```bash
#!/bin/bash
# generate_api_doc.sh

PID=12345
OUTPUT="api_documentation.md"

echo "# API Documentation" > $OUTPUT
echo "" >> $OUTPUT

# 获取所有类
classes=$(peeka-cli sc -p $PID "myapp.*" | jq -r '.classes[].name')

for class in $classes; do
  echo "## $class" >> $OUTPUT
  echo "" >> $OUTPUT
  
  # 获取类的详细信息
  peeka-cli sc -p $PID "$class" -d | \
    jq -r '.classes[0].docstring // "No description"' >> $OUTPUT
  echo "" >> $OUTPUT
  
  # 获取类的所有方法
  echo "### Methods" >> $OUTPUT
  echo "" >> $OUTPUT
  peeka-cli sm -p $PID "$class.*" -d | \
    jq -r '.methods[] | "- `\(.name)\(.signature)`\n  \(.docstring // "No description")\n"' >> $OUTPUT
  echo "" >> $OUTPUT
done

echo "Documentation generated: $OUTPUT"
```

### 2. 代码重构验证脚本

**场景**：重构后自动验证新旧类的方法是否一致。

```bash
#!/bin/bash
# verify_refactor.sh

PID=12345
OLD_CLASS="myapp.OldUserHandler"
NEW_CLASS="myapp.NewUserHandler"

# 获取旧类方法
old_methods=$(peeka-cli sm -p $PID "$OLD_CLASS.*" 2>/dev/null | \
  jq -r '.methods[].name' | sort)

# 获取新类方法
new_methods=$(peeka-cli sm -p $PID "$NEW_CLASS.*" | \
  jq -r '.methods[].name' | sort)

# 对比
if [ "$old_methods" == "$new_methods" ]; then
  echo "✅ PASS: Method signatures match"
else
  echo "❌ FAIL: Method signatures differ"
  echo "Old methods:"
  echo "$old_methods"
  echo "New methods:"
  echo "$new_methods"
fi
```

### 3. 查找未实现的抽象方法

**场景**：检查哪些类继承了抽象类但未实现所有抽象方法。

```bash
#!/bin/bash
# find_abstract_violations.sh

PID=12345
ABSTRACT_CLASS="myapp.BaseHandler"

# 获取抽象类的所有方法
abstract_methods=$(peeka-cli sm -p $PID "$ABSTRACT_CLASS.*" | \
  jq -r '.methods[].name' | sort)

# 查找所有子类
subclasses=$(peeka-cli sc -p $PID "*Handler" | \
  jq -r '.classes[].name' | grep -v "$ABSTRACT_CLASS")

for subclass in $subclasses; do
  # 获取子类的方法
  impl_methods=$(peeka-cli sm -p $PID "$subclass.*" | \
    jq -r '.methods[].name' | sort)
  
  # 检查是否实现了所有抽象方法
  missing=$(comm -23 <(echo "$abstract_methods") <(echo "$impl_methods"))
  
  if [ -n "$missing" ]; then
    echo "⚠️  $subclass missing methods:"
    echo "$missing"
  fi
done
```

### 4. 动态导入模块探索

**场景**：目标模块未加载，先导入再搜索。

```bash
#!/bin/bash
# explore_module.sh

PID=12345
MODULE="myapp.plugins.experimental"

# 通过 Python 代码导入模块（需要 Python 3.14+ 或 GDB 方式）
# 这里假设模块会被某个功能触发导入

# 等待模块加载（轮询）
for i in {1..10}; do
  classes=$(peeka-cli sc -p $PID "$MODULE.*" | jq -r '.count')
  if [ "$classes" -gt 0 ]; then
    echo "Module loaded successfully"
    peeka-cli sc -p $PID "$MODULE.*" -d
    break
  fi
  echo "Waiting for module to load... ($i/10)"
  sleep 2
done
```

### 5. 与 IDE 集成

**场景**：生成 IDE 可用的自动补全数据。

```bash
#!/bin/bash
# generate_autocomplete.sh

PID=12345

# 生成 JSON 格式的自动补全数据
peeka-cli sc -p $PID "myapp.*" | \
  jq -r '.classes[] | .name' | \
  while read class; do
    peeka-cli sm -p $PID "$class.*" | \
      jq -r ".methods[] | {class: \"$class\", method: .name, signature: .signature}"
  done | jq -s . > autocomplete_data.json
```

### 6. 监控模块加载

**场景**：实时监控应用加载了哪些新模块/类。

```bash
#!/bin/bash
# monitor_module_loading.sh

PID=12345
INTERVAL=5

# 保存初始状态
peeka-cli sc -p $PID "*" | jq -r '.classes[].name' | sort > initial_classes.txt

while true; do
  sleep $INTERVAL
  
  # 获取当前类列表
  peeka-cli sc -p $PID "*" | jq -r '.classes[].name' | sort > current_classes.txt
  
  # 找出新增的类
  new_classes=$(comm -13 initial_classes.txt current_classes.txt)
  
  if [ -n "$new_classes" ]; then
    echo "[$(date)] New classes loaded:"
    echo "$new_classes"
  fi
  
  cp current_classes.txt initial_classes.txt
done
```

---

## 与 Arthas 对比

### 功能对比

| 功能 | Arthas (Java) | Peeka (Python) | 说明 |
|------|---------------|----------------|------|
| 搜索类 | ✅ `sc` | ✅ `sc` | 一致 |
| 搜索方法 | ✅ `sm` | ✅ `sm` | 一致 |
| 通配符模式 | ✅ `*`, `?` | ✅ `*`, `?` | 一致 |
| 详细信息 | ✅ `-d` | ✅ `-d` | 一致 |
| 结果限制 | ✅ `-n` | ✅ `--limit` | 参数名不同 |
| 正则表达式 | ✅ `-E` | ❌ | Arthas 支持正则 |
| 按接口搜索 | ✅ `-i` | ❌ | Arthas 支持接口匹配 |
| 按注解搜索 | ✅ `-a` | ❌ | Arthas 支持注解匹配 |

### 命令对比

**Arthas (Java)**：
```bash
# 搜索类
sc com.example.*

# 搜索方法
sm com.example.MyClass

# 详细信息
sc -d com.example.MyClass
```

**Peeka (Python)**：
```bash
# 搜索类
peeka-cli sc -p 12345 "myapp.*"

# 搜索方法
peeka-cli sm -p 12345 "myapp.MyClass.*"

# 详细信息
peeka-cli sc -p 12345 "myapp.MyClass" -d
```

### 输出格式对比

**Arthas (文本)**：
```
com.example.MyClass
  module: example.jar
  classLoaderHash: 6d06d69c
```

**Peeka (JSON)**：
```json
{
  "name": "myapp.MyClass",
  "module": "myapp",
  "file": "/app/myapp.py"
}
```

### 优势对比

**Peeka 优势**：
- JSON 输出，易于程序化处理
- 与 `jq` 等工具无缝集成
- 简洁的命令行接口

**Arthas 优势**：
- 支持正则表达式
- 支持按接口/注解搜索
- 支持按类加载器过滤
- 内置 Web UI

---

## 总结

`sc` 和 `sm` 命令是代码探索和动态分析的强大工具，特别适合：
- 探索未知代码库
- 查找特定功能的实现
- 获取方法签名（用于其他命令）
- 验证模块是否已加载
- 学习第三方库 API

**最佳实践**：
- 使用具体的模式减少搜索范围
- 结合 `-d` 参数获取详细信息
- 使用 `jq` 进行强大的数据处理
- 与 `watch`、`stack` 等命令配合使用
- 导出搜索结果以便后续分析

**下一步**：
- 了解 [`watch`](watch.md) 命令（观测函数调用）
- 了解 [`stack`](stack.md) 命令（追踪调用栈）
- 了解 [`monitor`](monitor.md) 命令（性能监控）
- 参考 [AGENTS.md](../AGENTS.md)（开发者指南）
