# Peeka 架构设计

## 概述

Peeka 是基于 Python 3.14 远程调试协议（PEP 768）开发的运行时诊断工具，提供类似 Java Arthas 的非侵入式函数观测能力。

### 核心特性

- **非侵入式**：无需修改目标代码，运行时动态注入观测逻辑
- **实时诊断**：毫秒级数据传输，支持流式观测
- **生产可用**：低开销（<5%），高可靠性设计
- **条件过滤**：支持表达式过滤，减少无关数据干扰

### 技术基础

- **进程附加**：`sys.remote_exec(pid, script_path)` - Python 3.14 标准协议
- **通信机制**：Unix Domain Socket - 高效、安全的本地 IPC
- **消息格式**：长度前缀 + JSON - 结构化、可扩展

## 系统架构

### 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        Peeka CLI (本地)                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐ │
│  │ CLI解析器    │→│ 命令构建器   │→│ AgentClient (Socket)    │ │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘ │
│         ↑                                                       │
│         └─ 结果展示器 (实时流式显示)                             │
└─────────────────────────────────────────────────────────────────┘
                              │ sys.remote_exec(pid, script)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     目标Python进程 (PID: xxx)                    │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │                    Peeka Agent                            │  │
│  │  ┌─────────────┐  ┌─────────────┐  ┌───────────────────┐  │  │
│  │  │ 命令路由器   │→│ 观测管理器   │→│ 装饰器注入器       │  │  │
│  │  └─────────────┘  └─────────────┘  └───────────────────┘  │  │
│  │         ↑                                                  │  │
│  │         └─ 流式数据回传 (Socket)                           │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 核心组件

#### 1. PeekaAgent (核心协调器)

- 初始化功能组件
- 注册命令处理器
- 管理客户端连接
- 协调命令执行

#### 2. DecoratorInjector (装饰器注入器)

- 解析函数模式（module.Class.method）
- 创建观测包装函数
- 动态替换目标函数
- 支持注入恢复（可逆操作）

**核心机制**：

```
原始函数 → 包装函数（捕获参数/返回值/异常/耗时） → 发送观测数据
```

#### 3. ObservationManager (观测管理器)

- 接收观测数据
- 固定大小缓冲（防内存膨胀）
- 统计分析（调用次数、错误率、频率）
- 订阅分发（支持多客户端）

#### 4. 命令处理器

- `WatchCommand`: 启动/停止函数观测
- `ThreadCommand`: 线程诊断（规划中）
- `MemoryCommand`: 内存分析（规划中）

统一接口：`BaseCommand.execute(params) -> result`

## 数据流

### 命令执行流

```
用户输入 → CLI解析 → JSON序列化 → Socket发送 
         ↓
目标进程 → Agent接收 → 命令路由 → 处理器执行
         ↓
执行结果 → JSON序列化 → Socket回传 → CLI展示
```

### 观测数据流

```
目标函数调用 → 包装函数拦截 → 捕获上下文
              ↓
           组装观测数据 → 观测管理器 → 更新统计
              ↓
           通知订阅者 → Socket发送 → CLI实时展示
```

### 条件过滤机制

**安全表达式评估**（基于 simpleeval）：

- AST 白名单：只允许安全操作（比较、算术、逻辑）
- 属性保护：阻止 `__class__`、`__subclasses__` 等反射攻击
- 函数黑名单：禁用 `eval`、`compile`、`open`、`exec`、`__import__`

**支持语法**：

```python
len(params) > 2  # 参数数量过滤
kwargs.get('debug') == True  # 关键字参数过滤
x + y > 10  # 算术表达式
str(x).startswith('prefix')  # 字符串操作
params[0] == 'value'  # 索引访问
```

**阻止攻击**：

```python
__import__('os').system('rm -rf')  # ❌ 代码注入
params.__class__.__subclasses__()  # ❌ 对象反射
eval('malicious_code')  # ❌ 动态执行
```

## 通信协议

### 消息格式

**帧结构**：`[4字节长度][JSON数据]`

**命令消息**：

```json
{
  "type": "watch",
  "action": "start",
  "pattern": "module.Class.method",
  "depth": 2,
  "condition": "len(params) > 2",
  "times": -1
}
```

**响应消息**：

```json
{
  "status": "success",
  "watch_id": "watch_001",
  "message": "Started watching module.Class.method"
}
```

**观测消息**：

```json
{
  "type": "observation",
  "watch_id": "watch_001",
  "data": {
    "timestamp": 1705586200.123,
    "func_name": "module.Class.method",
    "args": [
      42,
      "hello"
    ],
    "kwargs": {
      "key": "value"
    },
    "result": 84,
    "success": true,
    "duration_ms": 0.123,
    "thread_id": 12345
  }
}
```

### 流式通信

**客户端**：生成器模式，惰性迭代观测数据

```python
for observation in client.watch("module.func"):
    print(observation)
```

**服务端**：持续发送观测消息，直到达到次数限制或客户端断开

## 安全设计

### 进程附加权限

- Linux: 需要 `CAP_SYS_PTRACE` 或相同 UID
- Docker: 需要 `--cap-add=SYS_PTRACE`
- 建议：生产环境启用审计日志

### 代码注入安全

- PEP 768 要求文件系统路径传递代码（非网络传输）
- Agent 以目标进程权限执行（继承沙箱限制）
- 建议：严格控制脚本文件权限，使用后立即删除

### 数据传输安全

- Unix Domain Socket 限制本地访问
- 套接字文件权限：仅所有者可读写
- 敏感场景建议：应用层加密或使用私密目录

### 资源限制

- **观测次数**：`--times` 参数防止无限观测
- **数据缓冲**：固定大小队列（默认 10000）防止内存溢出
- **连接超时**：自动关闭空闲连接
- **条件表达式**：simpleeval 资源限制（字符串长度、幂运算、位移）

## 性能优化

### 数据格式化

- **惰性格式化**：需要时才转换
- **深度控制**：默认 2 层，避免深度递归
- **字符串截断**：超长字符串自动截断（1000 字符）

### 内存管理

- **固定缓冲**：双端队列自动淘汰旧数据
- **字符串复用**：intern 高频字符串（函数名、参数名）

### 传输效率

- **紧凑 JSON**：去除空白字符 `separators=(',', ':')`
- **批量传输**：高频场景积攒批量发送（可选）

## 扩展性

### 命令扩展

- 继承 `BaseCommand` 抽象类
- 实现 `execute(params) -> result` 方法
- 在 `_register_handlers()` 注册

### 观测扩展

- 支持多种观测策略（装饰器注入、字节码插桩、sys.settrace）
- 统一通过 `ObservationManager` 接口访问

### 输出格式扩展

- 默认：JSON（结构化，便于程序处理）
- 可扩展：表格、精简、彩色等格式化器

## 使用示例

### 基本观测

```bash
# 1. 附加到目标进程
peeka attach 12345

# 2. 观测函数（限制 5 次）
peeka watch 12345 "demo.Calculator.add" --times 5

# 3. 条件过滤
peeka watch 12345 "demo.Calculator.multiply" --condition "params[0] > 100"
```

### 数据处理

```bash
# 使用 jq 提取字段
peeka watch 12345 "demo.func" | jq '.result'

# 统计调用次数
peeka watch 12345 "demo.func" | wc -l

# 保存到文件
peeka watch 12345 "demo.func" > observations.jsonl

# 筛选慢调用
peeka watch 12345 "demo.func" | jq 'select(.duration_ms > 1)'
```

## 故障排除

**附加失败（权限不足）**：

```bash
# Linux: 临时放宽 ptrace 限制
echo 0 | sudo tee /proc/sys/kernel/yama/ptrace_scope
```

**观测不到数据**：

- 检查函数名是否正确（完整限定名）
- 确认函数是否被调用
- 检查条件表达式是否过于严格

**目标进程行为异常**：

- 停止观测：`peeka watch --action stop <watch_id>`
- 如果持续异常，重启目标进程

## 环境变量

| 变量                  | 说明       | 默认值     |
|---------------------|----------|---------|
| `PEEKA_SOCKET_DIR`  | 套接字文件目录  | `/tmp`  |
| `PEEKA_TIMEOUT`     | 命令超时（秒）  | `30`    |
| `PEEKA_BUFFER_SIZE` | 观测数据缓冲大小 | `10000` |

## 版本历史

| 版本    | 日期      | 说明                 |
|-------|---------|--------------------|
| 0.1.0 | 2025-01 | 初始版本，支持基本 watch 功能 |
