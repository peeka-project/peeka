# trace 命令

## 简介

`trace` 命令用于追踪 Python 函数的完整调用链和执行耗时，以树形结构展示方法调用的层次关系。这是一个强大的性能分析和问题诊断工具，可以帮助开发者快速定位性能瓶颈和理解代码执行路径。

**设计灵感**：Peeka 的 `trace` 命令借鉴了 [Arthas](https://arthas.aliyun.com/) 的 trace 功能，但针对 Python 语言特性和运行时环境进行了深度优化。

## 使用场景

- **性能瓶颈定位**：通过耗时数据快速找出慢调用
- **调用链路分析**：理解函数内部的调用关系和执行流程
- **代码执行路径追踪**：观察不同条件下的代码执行路径
- **子函数耗时分析**：分析各个子函数的耗时占比
- **递归调用诊断**：追踪递归调用的深度和耗时分布

## 命令格式

```bash
peeka-cli attach <pid>    # 首先附加到目标进程
peeka-cli trace <pattern> [options]
```

### 参数说明

| 参数                    | 说明                    | 默认值     | 示例                                      |
|-----------------------|-----------------------|---------|-----------------------------------------|
| `pattern`             | 函数匹配模式                | -       | `module.Class.method`                   |
| `-d, --depth`         | 追踪深度（最大调用层数）          | `3`     | `-d 5`                                  |
| `-n, --times`         | 观测次数（-1 表示无限）         | `-1`    | `-n 10`                                 |
| `--condition-express` | 条件表达式（支持 `cost` 变量）   | 无       | `--condition-express "cost > 50"`       |
| `--skip-builtin`      | 跳过内置函数和标准库函数          | `true`  | `--skip-builtin=false`                  |
| `--min-duration`      | 最小耗时过滤（毫秒）            | `0`     | `--min-duration 10`                     |

**注意**：
- 追踪深度建议不超过 5 层，深度过大会显著增加性能开销
- `--skip-builtin` 默认启用，以减少输出噪音
- 条件表达式中的 `cost` 变量表示整个调用的总耗时（毫秒）

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

**注意**：必须使用完整的模块路径（从导入根开始），当前版本不支持通配符匹配。

## 基本用法

### 1. 追踪函数调用链

```bash
# 首先附加到目标进程
peeka-cli attach 12345

# 追踪 5 次调用
peeka-cli trace "calculator.Calculator.calculate" -n 5
```

**输出示例**：

```json
{
  "type": "observation",
  "watch_id": "trace_abc123",
  "timestamp": 1705586200.123,
  "func_name": "calculator.Calculator.calculate",
  "location": "AtExit",
  "call_tree": [
    {
      "depth": 0,
      "function": "calculator.Calculator.calculate",
      "filename": "/app/calculator.py",
      "lineno": 42,
      "duration_ms": 125.3,
      "children": [
        {
          "depth": 1,
          "function": "calculator.Calculator._validate",
          "filename": "/app/calculator.py",
          "lineno": 18,
          "duration_ms": 2.1
        },
        {
          "depth": 1,
          "function": "calculator.Calculator._compute",
          "filename": "/app/calculator.py",
          "lineno": 25,
          "duration_ms": 98.2,
          "children": [
            {
              "depth": 2,
              "function": "math.sqrt",
              "duration_ms": 95.1
            }
          ]
        },
        {
          "depth": 1,
          "function": "calculator.Logger.info",
          "filename": "/app/logger.py",
          "lineno": 10,
          "duration_ms": 15.7
        }
      ]
    }
  ],
  "total_duration_ms": 125.3,
  "node_count": 5
}
```

**字段说明**：

| 字段                 | 说明           | 示例值                       |
|--------------------|--------------|---------------------------|
| `watch_id`         | 观测 ID        | `"trace_abc123"`          |
| `timestamp`        | 时间戳          | `1705586200.123`          |
| `func_name`        | 目标函数名        | `"calculator.calculate"`  |
| `location`         | 观测位置         | `"AtExit"`                |
| `call_tree`        | 调用树（嵌套结构）    | `[...]`                   |
| `total_duration_ms`| 总执行耗时（毫秒）    | `125.3`                   |
| `node_count`       | 调用节点总数       | `5`                       |

**调用树节点字段**：

| 字段            | 说明         | 示例值                    |
|---------------|------------|------------------------|
| `depth`       | 调用深度（从 0 开始）| `0`, `1`, `2`          |
| `function`    | 函数完整名称     | `"module.Class.method"`|
| `filename`    | 文件路径       | `"/app/module.py"`     |
| `lineno`      | 行号         | `42`                   |
| `duration_ms` | 执行耗时（毫秒）   | `10.5`                 |
| `children`    | 子调用列表      | `[...]`                |

### 2. 树形文本输出（TUI）

在 TUI 模式下，调用树以可视化的树形结构展示：

```
`---[125.3ms] calculator.Calculator.calculate()
    +---[2.1ms] calculator.Calculator._validate()
    +---[98.2ms] calculator.Calculator._compute()
    |   `---[95.1ms] math.sqrt()
    `---[15.7ms] calculator.Logger.info()
```

**说明**：
- `---` 表示最后一个子节点
- `+---` 表示中间子节点
- `|` 表示父节点有后续兄弟节点的连接线
- `[Xms]` 显示函数执行耗时

### 3. 调整追踪深度

```bash
# 深度为 1：只追踪直接调用
peeka-cli trace "service.process" -d 1

# 深度为 5：追踪 5 层调用
peeka-cli trace "service.process" -d 5
```

**深度对比示例**：

```python
# 原始调用链
process() → validate() → check_type() → isinstance()
  ├── query_db() → execute() → connect()
  └── format_result() → json.dumps()

# depth=1
process() → validate()
          → query_db()
          → format_result()

# depth=2
process() → validate() → check_type()
          → query_db() → execute()
          → format_result() → json.dumps()

# depth=3（默认）
process() → validate() → check_type() → isinstance()
          → query_db() → execute() → connect()
          → format_result() → json.dumps()
```

### 4. 条件过滤

```bash
# 只追踪耗时超过 50ms 的调用
peeka-cli trace "api.handler" --condition-express "cost > 50"

# 组合参数和耗时条件
peeka-cli trace "service.query" --condition-express "cost > 100 and params[0] > 1000"
```

### 5. 跳过内置函数

```bash
# 默认行为：跳过内置函数（减少输出噪音）
peeka-cli trace "mymodule.func"

# 显示所有调用（包括内置函数）
peeka-cli trace "mymodule.func" --skip-builtin=false
```

**内置函数示例**：
- Python 内置函数：`len()`, `str()`, `isinstance()`, `print()`
- 标准库函数：`json.dumps()`, `os.path.join()`, `datetime.now()`

## 实现方案

Peeka 的 `trace` 命令支持多种实现方案，根据 Python 版本和性能要求自动选择最优策略。

### 方案对比

| 方案                          | Python 版本 | 性能开销   | 优点                | 缺点             |
|-----------------------------|-----------|--------|-------------------|----------------|
| **eBPF (推荐)**               | 3.9+      | < 1%   | 极低开销，系统级追踪        | 实现复杂，需要 Linux  |
| **sys.monitoring (PEP 669)** | 3.12+     | < 5%   | 官方支持，性能优秀         | 仅 Python 3.12+ |
| **Decorator + Local Trace** | 3.9+      | < 20%  | 兼容性好，实现简单         | 性能开销较高         |
| **sys.settrace (不推荐)**      | 3.9+      | 1000%+ | 完整调用信息            | 极高开销，不适合生产环境   |

### eBPF 实现方案（推荐）

#### 技术原理

eBPF (extended Berkeley Packet Filter) 是 Linux 内核级别的追踪技术，通过 uprobes 在用户空间函数入口/出口插入探针。

**架构图**：

```
┌─────────────────────────────────────┐
│      Python Application             │
│  ┌──────────────────────────────┐   │
│  │  User Functions              │   │
│  │  +----------------------+    │   │
│  │  | PyObject_Call()      |◄───┼───┼─── eBPF Uprobe (Entry)
│  │  +----------------------+    │   │
│  │           ▼                  │   │
│  │  +----------------------+    │   │
│  │  | PyEval_EvalFrameEx() |    │   │
│  │  +----------------------+    │   │
│  │           ▼                  │   │
│  │  +----------------------+    │   │
│  │  | Function Return      |◄───┼───┼─── eBPF Uprobe (Exit)
│  │  +----------------------+    │   │
│  └──────────────────────────────┘   │
└─────────────────────────────────────┘
           ▲                 ▲
           │                 │
    ┌──────┴─────┐    ┌─────┴──────┐
    │ BPF Maps   │    │  Perf Ring │
    │ (Call Tree)│    │   Buffer   │
    └──────┬─────┘    └─────┬──────┘
           │                 │
           ▼                 ▼
┌─────────────────────────────────────┐
│      Peeka Agent (eBPF Program)     │
│  - Attach uprobes to Python funcs   │
│  - Collect call tree and timing     │
│  - Filter and format output         │
└─────────────────────────────────────┘
```

#### 实现细节

**1. 探针注入点**：

```python
# 使用 bcc (BPF Compiler Collection) 库
from bcc import BPF

# eBPF 程序（C 代码）
bpf_text = """
#include <uapi/linux/ptrace.h>

// 调用栈存储结构
struct call_data_t {
    u64 pid;
    u64 timestamp_ns;
    u64 function_addr;
    char function_name[64];
};

// 使用 BPF Map 存储调用栈
BPF_HASH(call_stack, u32, struct call_data_t, 10240);
BPF_PERF_OUTPUT(events);

// 函数入口探针
int trace_func_entry(struct pt_regs *ctx) {
    u64 pid_tgid = bpf_get_current_pid_tgid();
    u32 pid = pid_tgid >> 32;
    u32 tid = pid_tgid & 0xFFFFFFFF;

    struct call_data_t data = {};
    data.pid = pid;
    data.timestamp_ns = bpf_ktime_get_ns();
    data.function_addr = PT_REGS_IP(ctx);

    // 存储到调用栈
    call_stack.update(&tid, &data);

    return 0;
}

// 函数退出探针
int trace_func_exit(struct pt_regs *ctx) {
    u64 pid_tgid = bpf_get_current_pid_tgid();
    u32 tid = pid_tgid & 0xFFFFFFFF;

    struct call_data_t *entry_data = call_stack.lookup(&tid);
    if (entry_data == NULL) {
        return 0;
    }

    u64 duration_ns = bpf_ktime_get_ns() - entry_data->timestamp_ns;

    // 发送事件到用户空间
    struct call_data_t exit_data = *entry_data;
    events.perf_submit(ctx, &exit_data, sizeof(exit_data));

    call_stack.delete(&tid);
    return 0;
}
"""

# 加载 eBPF 程序
b = BPF(text=bpf_text)

# 附加 uprobe 到 Python 解释器
b.attach_uprobe(name="/usr/bin/python3.12", sym="PyObject_Call", fn_name="trace_func_entry")
b.attach_uretprobe(name="/usr/bin/python3.12", sym="PyObject_Call", fn_name="trace_func_exit")
```

**2. 数据收集和处理**：

```python
import ctypes as ct

# 定义数据结构（与 C 结构对应）
class CallData(ct.Structure):
    _fields_ = [
        ("pid", ct.c_uint64),
        ("timestamp_ns", ct.c_uint64),
        ("function_addr", ct.c_uint64),
        ("function_name", ct.c_char * 64),
    ]

# 处理 eBPF 事件
def process_event(cpu, data, size):
    event = ct.cast(data, ct.POINTER(CallData)).contents
    duration_ms = (event.timestamp_ns) / 1_000_000

    # 构建调用树
    call_tree_node = {
        "function": event.function_name.decode('utf-8', 'replace'),
        "duration_ms": duration_ms,
        "timestamp": event.timestamp_ns,
    }

    # 发送观测数据
    agent._send_observation({
        "type": "observation",
        "watch_id": watch_id,
        "call_tree": [call_tree_node],
    })

# 注册回调
b["events"].open_perf_buffer(process_event)

# 轮询事件
while True:
    b.perf_buffer_poll()
```

#### 优势

- ✅ **极低性能开销**（< 1%）：在内核态执行，不影响 Python 解释器
- ✅ **无需修改代码**：通过 uprobe 动态注入，不修改 Python 字节码
- ✅ **系统级视角**：可以追踪 C 扩展、Cython 代码
- ✅ **高精度计时**：使用内核时间戳，纳秒级精度
- ✅ **支持多进程**：可以同时追踪多个 Python 进程

#### 限制

- ❌ **仅支持 Linux**：eBPF 是 Linux 内核特性
- ❌ **需要 root 权限或 CAP_BPF**：加载 eBPF 程序需要特权
- ❌ **依赖项较多**：需要安装 bcc、内核头文件
- ⚠️ **Python 函数名提取**：默认只能获取 C 函数名，获取 Python 函数名需要 USDT (User Statically-Defined Tracing) 支持
- ⚠️ **内核版本要求**：需要 Linux 4.7+ (推荐 5.2+)

#### 环境要求

**操作系统**：
- Linux 4.7+ (BPF uprobes 支持)
- Linux 5.2+ (推荐，BPF 功能更完善)

**依赖包**：
```bash
# Ubuntu/Debian
sudo apt-get install -y bpfcc-tools linux-headers-$(uname -r) python3-bpfcc

# RHEL/CentOS
sudo yum install -y bcc-tools kernel-devel python3-bcc

# Fedora
sudo dnf install -y bcc-tools kernel-devel python3-bcc
```

**权限要求**：
```bash
# 方案 1：使用 root 运行（不推荐生产环境）
sudo peeka-cli trace "module.func"

# 方案 2：赋予 CAP_BPF 能力（推荐，Linux 5.8+）
sudo setcap cap_bpf,cap_perfmon=ep $(which python3)
peeka-cli trace "module.func"

# 方案 3：临时放宽限制（测试用）
echo 0 | sudo tee /proc/sys/kernel/unprivileged_bpf_disabled
```

**Docker 容器**：
```bash
# 需要特权模式或添加 BPF 能力
docker run --privileged your-image
# 或
docker run --cap-add=SYS_BPF --cap-add=SYS_ADMIN your-image
```

#### Python USDT 探针

为了获取更精确的 Python 函数信息，可以启用 Python USDT 探针：

```bash
# 使用 USDT 版本的 Python（需要编译时启用）
./configure --with-dtrace
make
sudo make install

# 验证 USDT 探针
sudo bpftrace -l 'usdt:/usr/local/bin/python3*' | grep function
```

**USDT 探针示例**：
- `python:function__entry` - 函数入口
- `python:function__return` - 函数返回
- `python:line` - 代码行执行
- `python:gc__start` - GC 开始
- `python:gc__done` - GC 完成

### sys.monitoring 实现方案（Python 3.12+）

对于 Python 3.12+，使用 PEP 669 引入的 `sys.monitoring` API：

```python
import sys

def trace_callback(code, instruction_offset, *args):
    """监控回调函数"""
    if event == sys.monitoring.events.CALL:
        # 函数调用事件
        frame = sys._getframe(1)
        start_time = time.perf_counter()

    elif event == sys.monitoring.events.RETURN:
        # 函数返回事件
        duration = (time.perf_counter() - start_time) * 1000
        # 记录调用树节点

# 注册监控工具
sys.monitoring.use_tool_id(0, "peeka-tracer")
sys.monitoring.set_events(0, sys.monitoring.events.CALL | sys.monitoring.events.RETURN)
sys.monitoring.register_callback(0, sys.monitoring.events.CALL, trace_callback)
```

**优势**：
- ✅ 官方支持，API 稳定
- ✅ 性能开销低（5-10%）
- ✅ 跨平台支持（Windows/macOS/Linux）

**限制**：
- ❌ 仅支持 Python 3.12+

### Decorator + Local Trace 实现方案（通用）

兼容 Python 3.9-3.14+，基于 Peeka 现有的 `DecoratorInjector`：

```python
def _create_trace_wrapper(self, func, watch_id, config):
    depth_limit = config.get("trace_depth", 3)

    @wraps(func)
    def wrapper(*args, **kwargs):
        call_tree = []
        current_depth = [0]

        def local_trace(frame, event, arg):
            """局部 trace 函数"""
            if current_depth[0] >= depth_limit:
                return None

            if event == 'call':
                current_depth[0] += 1
                code = frame.f_code
                start_time = time.perf_counter()

                call_tree.append({
                    'depth': current_depth[0],
                    'function': f"{code.co_filename}:{code.co_name}",
                    'lineno': frame.f_lineno,
                    'start_time': start_time
                })
                return local_trace

            elif event == 'return':
                if call_tree and call_tree[-1]['depth'] == current_depth[0]:
                    duration = (time.perf_counter() - call_tree[-1]['start_time']) * 1000
                    call_tree[-1]['duration_ms'] = duration
                current_depth[0] -= 1

            return local_trace

        # 仅在执行目标函数时启用 trace
        sys.settrace(local_trace)
        try:
            result = func(*args, **kwargs)
            return result
        finally:
            sys.settrace(None)

            # 发送调用树
            self.agent._send_observation({
                'watch_id': watch_id,
                'type': 'trace',
                'call_tree': call_tree,
            })

    return wrapper
```

**优势**：
- ✅ 兼容所有 Python 版本
- ✅ 基于现有架构，实现简单
- ✅ 局部启用，性能可控

**限制**：
- ⚠️ 性能开销较高（10-20%）
- ⚠️ 深度受限（推荐 ≤ 5 层）

## 性能分析

### 性能对比

| 场景                  | eBPF | sys.monitoring | Local Trace | sys.settrace |
|---------------------|------|----------------|-------------|--------------|
| 简单函数（10 次调用）       | < 1% | 5-10%          | 20-30%      | 1000%+       |
| 复杂函数（100 次子调用）     | < 1% | 10-20%         | 50-100%     | 2000%+       |
| 生产环境适用性             | ✅    | ✅              | ⚠️          | ❌            |

**结论**：
- ✅ **eBPF 是生产环境的最佳选择**（极低开销）
- ✅ **sys.monitoring 适合 Python 3.12+ 的通用场景**
- ⚠️ **Local Trace 适合短时间诊断**（< 1 分钟）
- ❌ **sys.settrace 永远不应在生产环境使用**

### 性能优化建议

1. **限制追踪深度**
   ```bash
   # 只追踪 3 层调用
   peeka-cli trace "func" -d 3
   ```

2. **跳过内置函数**
   ```bash
   # 默认启用，减少 50% 以上的节点
   peeka-cli trace "func" --skip-builtin
   ```

3. **使用条件过滤**
   ```bash
   # 只追踪慢调用
   peeka-cli trace "func" --condition-express "cost > 100"
   ```

4. **限制观测次数**
   ```bash
   # 只观测 10 次
   peeka-cli trace "func" -n 10
   ```

5. **最小耗时过滤**
   ```bash
   # 只记录耗时 > 10ms 的子调用
   peeka-cli trace "func" --min-duration 10
   ```

## 使用示例

### 1. 定位性能瓶颈

```bash
# 追踪慢接口，找出耗时最长的子调用
peeka-cli trace "api.handler.process_request" --condition-express "cost > 100"
```

**输出**：
```
`---[1250ms] api.handler.process_request()
    +---[10ms] api.validator.check_params()
    +---[1200ms] database.query.execute()  ← 瓶颈在这里！
    |   +---[50ms] database.connection.connect()
    |   `---[1150ms] database.cursor.fetch_all()
    `---[20ms] api.formatter.to_json()
```

**结论**：数据库查询占用了 96% 的时间，需要优化 SQL 或添加索引。

### 2. 分析递归调用

```bash
# 追踪递归函数的执行深度和耗时
peeka-cli trace "algorithm.factorial" -d 10
```

**输出**：
```
`---[5.2ms] algorithm.factorial(n=5)
    `---[4.1ms] algorithm.factorial(n=4)
        `---[3.0ms] algorithm.factorial(n=3)
            `---[2.0ms] algorithm.factorial(n=2)
                `---[1.0ms] algorithm.factorial(n=1)
                    `---[0.1ms] algorithm.factorial(n=0)
```

### 3. 理解代码执行路径

```bash
# 追踪条件分支的执行路径
peeka-cli trace "service.business_logic" -n 1
```

**场景 A（正常流程）**：
```
`---[50ms] service.business_logic()
    +---[5ms] service.validate_input()
    +---[30ms] service.process_data()
    `---[10ms] service.save_result()
```

**场景 B（异常流程）**：
```
`---[20ms] service.business_logic()
    +---[5ms] service.validate_input()
    +---[10ms] service.handle_invalid_input()
    `---[3ms] service.log_error()
```

### 4. 对比优化前后性能

```bash
# 优化前
peeka-cli trace "converter.parse_json" -n 10 > before.jsonl

# 优化后
peeka-cli trace "converter.parse_json" -n 10 > after.jsonl

# 分析耗时变化
jq '.total_duration_ms' before.jsonl | awk '{sum+=$1; count++} END {print "Before:", sum/count, "ms"}'
jq '.total_duration_ms' after.jsonl | awk '{sum+=$1; count++} END {print "After:", sum/count, "ms"}'
```

### 5. 集成到 CI/CD

```bash
# 性能回归测试
#!/bin/bash
THRESHOLD=100  # 最大允许耗时 100ms

peeka-cli attach $PID
RESULT=$(peeka-cli trace "critical.function" -n 50 | \
  jq -s 'map(select(.type == "observation")) | map(.total_duration_ms) | add / length')

if (( $(echo "$RESULT > $THRESHOLD" | bc -l) )); then
  echo "Performance regression detected: ${RESULT}ms > ${THRESHOLD}ms"
  exit 1
fi
```

## 数据处理与分析

### 使用 jq 处理 JSON

```bash
# 1. 提取调用树
peeka-cli trace "func" | jq '.call_tree'

# 2. 计算平均耗时
peeka-cli trace "func" -n 100 | jq '.total_duration_ms' | \
  awk '{sum+=$1; count++} END {print "avg:", sum/count, "ms"}'

# 3. 找出最慢的子调用
peeka-cli trace "func" | jq '.call_tree | .. | objects | select(.duration_ms != null) | {function, duration_ms}' | \
  jq -s 'sort_by(.duration_ms) | reverse | .[0]'

# 4. 统计调用频次
peeka-cli trace "func" -n 100 | jq '.call_tree | .. | objects | select(.function != null) | .function' | \
  sort | uniq -c | sort -rn

# 5. 生成火焰图数据
peeka-cli trace "func" -n 1000 | jq -r '.call_tree | .. | objects | select(.function != null) | "\(.function) \(.duration_ms)"' > flamegraph.txt
```

### Python 数据分析

```python
import json
import sys
from collections import defaultdict

# 统计子调用的总耗时和次数
stats = defaultdict(lambda: {"count": 0, "total_ms": 0})

for line in sys.stdin:
    data = json.loads(line)
    if data["type"] == "observation":
        def traverse(node):
            if "function" in node:
                stats[node["function"]]["count"] += 1
                stats[node["function"]]["total_ms"] += node.get("duration_ms", 0)

            for child in node.get("children", []):
                traverse(child)

        for root in data["call_tree"]:
            traverse(root)

# 按总耗时排序
sorted_stats = sorted(stats.items(), key=lambda x: x[1]["total_ms"], reverse=True)

print("Top 10 Time-Consuming Functions:")
print(f"{'Function':<60} {'Count':>10} {'Total (ms)':>15} {'Avg (ms)':>12}")
print("-" * 100)

for func, stat in sorted_stats[:10]:
    avg_ms = stat["total_ms"] / stat["count"]
    print(f"{func:<60} {stat['count']:>10} {stat['total_ms']:>15.2f} {avg_ms:>12.2f}")
```

**运行**：
```bash
peeka-cli trace "module.func" -n 100 | python analyze_trace.py
```

**输出**：
```
Top 10 Time-Consuming Functions:
Function                                                      Count     Total (ms)      Avg (ms)
----------------------------------------------------------------------------------------------------
database.query.execute                                          100       12500.00       125.00
api.handler.process_request                                     100       15000.00       150.00
json.dumps                                                      500        1000.00         2.00
...
```

## 与 Arthas Trace 的对比

| 特性           | Peeka (eBPF)            | Peeka (sys.monitoring) | Arthas (Java)      | 说明                    |
|--------------|-------------------------|------------------------|--------------------|-----------------------|
| **目标语言**     | Python                  | Python                 | Java               | 核心差异                  |
| **实现技术**     | eBPF + uprobes          | PEP 669                | ASM 字节码增强          | Peeka 使用内核级追踪         |
| **调用树展示**    | ✅ 树形结构                 | ✅ 树形结构                | ✅ 树形结构            | 功能一致                  |
| **耗时统计**     | ✅ 纳秒级精度                | ✅ 毫秒级                 | ✅ 毫秒级             | eBPF 精度最高             |
| **深度限制**     | ✅ 支持 (`-d`)            | ✅ 支持 (`-d`)          | ✅ 支持 (`-n`)       | 功能一致                  |
| **跳过内置方法**   | ✅ 支持 (`--skip-builtin`) | ✅ 支持                  | ✅ 支持 (`--skipJDKMethod`) | 功能一致                  |
| **条件过滤**     | ✅ `cost > 100`          | ✅ `cost > 100`         | ✅ `#cost>100` | 语法略有差异，功能一致           |
| **性能开销**     | < 1%                    | 5-10%                  | < 5%               | eBPF 开销最低             |
| **C 扩展追踪**   | ✅ 支持                    | ❌ 不支持                 | ✅ 支持（JNI）         | eBPF 可以追踪 C 代码        |
| **跨平台支持**    | ❌ Linux only           | ✅ All platforms        | ✅ All platforms   | eBPF 受限于 Linux       |
| **权限要求**     | ⚠️ CAP_BPF / root       | ✓ 普通权限                | ✓ 普通权限            | eBPF 需要特殊权限           |
| **正则匹配**     | ⏳ 计划支持                 | ⏳ 计划支持                | ✅ 支持              | Arthas 支持通配符和正则       |
| **动态开启/关闭**  | ✅ 支持                    | ✅ 支持                  | ✅ 支持              | 功能一致                  |

### 核心差异

**1. 追踪粒度**
- **Arthas**：基于字节码增强，追踪 Java 方法调用
- **Peeka (eBPF)**：基于内核探针，追踪 C 函数（包括 Python 解释器内部）
- **Peeka (sys.monitoring)**：基于解释器钩子，追踪 Python 函数

**2. 性能特征**
- **eBPF**：内核态执行，开销极低但需要特权
- **sys.monitoring**：解释器钩子，开销低但仅 Python 3.12+
- **Arthas**：字节码增强，开销低且无需特权

**3. 使用场景**
- **Peeka eBPF**：生产环境性能分析，需要极低开销
- **Peeka sys.monitoring**：Python 3.12+ 通用场景
- **Arthas**：Java 应用全方位诊断

## 常见问题

### 1. eBPF 方案无法使用

**问题**：`Operation not permitted` 或 `BPF program load failed`

**解决方案**：

```bash
# 检查内核版本（需要 4.7+）
uname -r

# 检查 BPF 是否启用
ls /sys/kernel/debug/tracing/events/syscalls/sys_enter_bpf

# 赋予 CAP_BPF 能力（Linux 5.8+）
sudo setcap cap_bpf,cap_perfmon=ep $(which python3)

# 或使用 root 运行
sudo peeka-cli trace "module.func"
```

### 2. 追踪深度不够

**问题**：调用树只显示 3 层，但实际有更多层级

**解决方案**：

```bash
# 增加深度限制
peeka-cli trace "module.func" -d 10

# 注意：深度过大会增加性能开销
```

### 3. 输出数据过多

**问题**：包含大量内置函数调用，输出难以阅读

**解决方案**：

```bash
# 跳过内置函数（默认启用）
peeka-cli trace "module.func" --skip-builtin

# 只记录耗时 > 10ms 的调用
peeka-cli trace "module.func" --min-duration 10

# 使用条件过滤
peeka-cli trace "module.func" --condition-express "cost > 50"
```

### 4. 性能开销过大

**问题**：启用 trace 后应用响应变慢

**解决方案**：

```bash
# 1. 使用 eBPF 方案（需要 Linux + root）
# 2. 减少追踪深度
peeka-cli trace "module.func" -d 2

# 3. 限制观测次数
peeka-cli trace "module.func" -n 10

# 4. 使用条件过滤
peeka-cli trace "module.func" --condition-express "cost > 100"
```

### 5. Docker 容器中无法使用 eBPF

**问题**：容器内运行 eBPF 失败

**解决方案**：

```bash
# 使用特权模式
docker run --privileged your-image

# 或添加 BPF 能力
docker run --cap-add=SYS_BPF --cap-add=SYS_ADMIN --cap-add=SYS_PTRACE your-image

# 挂载内核头文件
docker run -v /usr/src:/usr/src:ro -v /lib/modules:/lib/modules:ro your-image
```

### 6. 无法获取 Python 函数名

**问题**：eBPF 输出只显示 C 函数名（如 `PyObject_Call`）

**解决方案**：

**方案 1：使用 USDT 版本的 Python**
```bash
# 编译支持 USDT 的 Python
./configure --with-dtrace
make && sudo make install
```

**方案 2：使用 sys.monitoring 方案（Python 3.12+）**
```bash
# 自动选择 sys.monitoring 实现
peeka-cli trace "module.func"
```

**方案 3：使用 Local Trace 方案**
```bash
# 通过配置强制使用 Local Trace
export PEEKA_TRACE_METHOD=local
peeka-cli trace "module.func"
```

## 高级技巧

### 1. 生成火焰图

```bash
# 收集追踪数据
peeka-cli trace "module.func" -n 1000 > trace.jsonl

# 转换为火焰图格式
jq -r '.call_tree | .. | objects | select(.function != null) | "\(.function);\(.duration_ms)"' trace.jsonl \
  > folded.txt

# 生成火焰图（需要安装 flamegraph.pl）
flamegraph.pl folded.txt > flamegraph.svg
```

### 2. 对比多个版本的性能

```bash
# 版本 A
git checkout v1.0
peeka-cli trace "module.func" -n 100 > trace_v1.jsonl

# 版本 B
git checkout v2.0
peeka-cli trace "module.func" -n 100 > trace_v2.jsonl

# 对比平均耗时
echo "v1.0: $(jq -s 'map(.total_duration_ms) | add / length' trace_v1.jsonl) ms"
echo "v2.0: $(jq -s 'map(.total_duration_ms) | add / length' trace_v2.jsonl) ms"
```

### 3. 自动化性能监控

```python
#!/usr/bin/env python3
"""性能回归监控脚本"""
import json
import subprocess
import time

THRESHOLD = 100  # 最大允许耗时 (ms)
CHECK_INTERVAL = 3600  # 检查间隔 (秒)

def check_performance(pid, pattern):
    cmd = ["peeka-cli", "trace", pattern, "-n", "50"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True)

    durations = []
    for line in proc.stdout:
        data = json.loads(line)
        if data["type"] == "observation":
            durations.append(data["total_duration_ms"])

    avg_duration = sum(durations) / len(durations) if durations else 0

    if avg_duration > THRESHOLD:
        send_alert(f"Performance regression: {avg_duration:.2f}ms > {THRESHOLD}ms")

    return avg_duration

def send_alert(message):
    # 发送告警（邮件、Slack、钉钉等）
    print(f"ALERT: {message}")

if __name__ == "__main__":
    pid = int(sys.argv[1])
    pattern = sys.argv[2]

    while True:
        duration = check_performance(pid, pattern)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Avg duration: {duration:.2f}ms")
        time.sleep(CHECK_INTERVAL)
```

### 4. 集成到 Prometheus

```python
from prometheus_client import Histogram, start_http_server
import json
import subprocess

# 定义指标
trace_duration = Histogram('trace_duration_ms', 'Function trace duration', ['function'])

# 启动 Prometheus 服务器
start_http_server(8000)

# 收集追踪数据
proc = subprocess.Popen(
    ["peeka-cli", "trace", "module.func"],
    stdout=subprocess.PIPE,
    text=True
)

for line in proc.stdout:
    data = json.loads(line)
    if data["type"] == "observation":
        # 递归处理调用树
        def record_metrics(node):
            if "function" in node and "duration_ms" in node:
                trace_duration.labels(function=node["function"]).observe(node["duration_ms"])
            for child in node.get("children", []):
                record_metrics(child)

        for root in data["call_tree"]:
            record_metrics(root)
```

## 参考资料

- [Arthas Trace 文档](https://arthas.aliyun.com/en/doc/trace.html)
- [eBPF 官方文档](https://ebpf.io/)
- [BCC (BPF Compiler Collection)](https://github.com/iovisor/bcc)
- [PEP 669: Low Impact Monitoring for CPython](https://peps.python.org/pep-0669/)
- [Linux USDT (User Statically-Defined Tracing)](https://www.kernel.org/doc/html/latest/trace/uprobetracer.html)
- [Python USDT Probes](https://docs.python.org/3/howto/instrumentation.html)
- [Peeka 架构设计](../ARCHITECTURE.md)

## 更新日志

| 版本    | 日期         | 更新内容                       |
|-------|------------|----------------------------|
| 0.2.0 | 2026-02    | 添加 trace 命令文档，重点介绍 eBPF 实现 |
| 0.1.0 | 2025-01    | 初始版本                       |
