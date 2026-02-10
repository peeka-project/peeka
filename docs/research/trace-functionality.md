# Arthas Trace 功能研究与 Peeka 实现方案

## 1. Arthas Trace 功能分析

### 1.1 功能概述

Arthas 的 `trace` 命令是一个强大的方法调用路径追踪工具，主要用于：

- **追踪方法调用链**：显示目标方法内部的所有方法调用（包括子方法调用）
- **测量执行时间**：记录每个方法节点的执行耗时
- **可视化调用树**：以树形结构展示方法调用层次关系
- **性能瓶颈定位**：通过耗时数据快速定位性能问题

### 1.2 核心特性

#### 1.2.1 调用路径追踪
```
`---[0.50ms] com.example.MyClass:myMethod()
    +---[0.20ms] com.example.Helper:doWork()
    |   +---[0.10ms] java.util.List:add()
    +---[0.15ms] com.example.Service:call()
```

#### 1.2.2 条件过滤
支持 OGNL 表达式过滤：
```bash
trace com.example.MyClass myMethod '#cost > 100'  # 只显示耗时超过 100ms 的调用
```

#### 1.2.3 灵活控制
- **匹配多个类/方法**：使用通配符模式
- **限制输出次数**：`-n` 参数控制追踪次数
- **跳过 JDK 方法**：`--skipJDKMethod` 减少输出噪音
- **动态追踪**：运行时添加新的追踪目标（Arthas 3.3.0+）

### 1.3 实现原理

Arthas 在 Java 中使用 **字节码增强（Bytecode Instrumentation）** 技术：

1. **字节码修改**：使用 ASM 库在运行时修改目标类的字节码
2. **Advice 机制**：在方法入口/出口/异常点注入额外代码
3. **调用栈记录**：在方法执行过程中记录调用关系和时间
4. **树形输出**：构建调用树并计算每个节点的耗时

#### 关键技术点：
- **无需重启 JVM**：利用 Java Instrumentation API 动态修改字节码
- **低开销设计**：只在需要时启用追踪，不影响未追踪的代码
- **异常安全**：追踪代码异常不会影响业务逻辑

---

## 2. Python 实现方案对比

### 2.1 方案对比矩阵

| 方案 | 优点 | 缺点 | 性能开销 | 实现复杂度 | Python 版本要求 |
|------|------|------|----------|------------|----------------|
| **sys.settrace** | 简单实现，完整调用信息 | 极高开销（10x+） | 极高 | 低 | All |
| **sys.monitoring (PEP 669)** | 低开销，官方支持 | Python 3.12+ | 低（<5%） | 中 | 3.12+ |
| **Decorator Wrapping** | 精确控制，零干扰 | 需要明确指定函数 | 极低 | 低 | All |
| **eBPF** | 最低开销，系统级 | 复杂，需 Linux 内核支持 | 极低（<1%） | 高 | Linux only |

### 2.2 详细方案分析

#### 2.2.1 sys.settrace（不推荐）

**原理**：Python 解释器级别的钩子，拦截每行代码执行

**示例**：
```python
def trace_calls(frame, event, arg):
    if event == 'call':
        code = frame.f_code
        print(f"Calling {code.co_name} in {code.co_filename}")
    return trace_calls

sys.settrace(trace_calls)
```

**评估**：
- ✅ 可以追踪所有函数调用（包括内置函数）
- ❌ 性能开销极大（10-100x 慢）
- ❌ 不适合生产环境
- ❌ 多线程/asyncio 支持复杂

**结论**：❌ 不适合 Peeka 的生产环境定位

---

#### 2.2.2 sys.monitoring (PEP 669)（推荐用于 Python 3.12+）

**原理**：Python 3.12 引入的低开销监控 API，利用解释器优化机制

**示例**：
```python
import sys

def callback(code, instruction_offset, *args):
    print(f"Event in {code.co_name}")

# 注册事件监听
sys.monitoring.use_tool_id(0, "peeka-tracer")
sys.monitoring.set_events(0, sys.monitoring.events.CALL)
sys.monitoring.register_callback(0, sys.monitoring.events.CALL, callback)
```

**评估**：
- ✅ 低开销（~5-10% vs sys.settrace 的 1000%）
- ✅ 官方支持，稳定可靠
- ✅ 支持多种事件（CALL, RETURN, EXCEPTION, LINE 等）
- ✅ 可以全局或局部启用
- ❌ 仅支持 Python 3.12+
- ⚠️ 需要额外代码来构建调用树

**结论**：✅ 作为 Python 3.12+ 的首选方案

---

#### 2.2.3 Decorator Wrapping（当前 Peeka 方案的扩展）

**原理**：基于 Peeka 现有的 `DecoratorInjector`，在包装器中记录子调用

**Peeka 现状**：
- 已有 `DecoratorInjector` 类实现函数包装
- 已有 `watch` 命令观测单个函数的参数/返回值/耗时
- 已有条件过滤机制（`condition_express`）
- 已有线程安全的观测数据传输

**扩展方案**：在包装器内部使用 `sys.settrace` 局部追踪子调用

```python
def _create_trace_wrapper(self, func, watch_id, config):
    depth_limit = config.get("trace_depth", 3)  # 追踪深度

    @wraps(func)
    def wrapper(*args, **kwargs):
        call_tree = []  # 存储调用树
        current_depth = [0]  # 当前深度（可变对象）

        def local_trace(frame, event, arg):
            """局部 trace 函数，只在目标函数执行期间启用"""
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
            sys.settrace(None)  # 关键：立即禁用 trace

            # 发送调用树观测数据
            self.agent._send_observation({
                'watch_id': watch_id,
                'type': 'trace',
                'call_tree': call_tree,
                'total_time': sum(c.get('duration_ms', 0) for c in call_tree)
            })

    return wrapper
```

**优化策略**：
1. **局部启用**：只在目标函数执行期间启用 `sys.settrace`
2. **深度限制**：默认只追踪 3 层调用，避免过深递归
3. **时间窗口**：目标函数执行完毕立即禁用 trace
4. **条件过滤**：继承 `watch` 的条件表达式机制

**评估**：
- ✅ 基于现有代码，实现简单
- ✅ 兼容所有 Python 版本（3.9-3.14+）
- ✅ 性能开销可控（仅目标函数执行期间）
- ✅ 与现有 `watch` 命令架构一致
- ⚠️ 仍有一定性能开销（但局部使用可接受）
- ⚠️ 深度受限（但可配置）

**结论**：✅ 作为通用方案，适配 Peeka 现有架构

---

#### 2.2.4 eBPF（未来方向）

**原理**：Linux 内核级别的追踪技术，使用 uprobes 追踪用户空间函数

**示例**（使用 bcc）：
```python
from bcc import BPF

# eBPF 程序
bpf_text = """
#include <uapi/linux/ptrace.h>
BPF_HASH(start, u32);

int trace_func_entry(struct pt_regs *ctx) {
    u64 ts = bpf_ktime_get_ns();
    u32 pid = bpf_get_current_pid_tgid();
    start.update(&pid, &ts);
    return 0;
}
"""

b = BPF(text=bpf_text)
b.attach_uprobe(name="python3.12", sym="PyObject_Call", fn_name="trace_func_entry")
```

**评估**：
- ✅ 极低开销（<1%）
- ✅ 无需修改目标代码
- ✅ 系统级视角（可追踪 C 扩展）
- ❌ 仅支持 Linux
- ❌ 需要 root 权限或特定 capabilities
- ❌ 实现复杂，需要 BPF 专业知识
- ❌ 获取 Python 函数级别信息需要 USDT probe（默认未启用）

**结论**：⏸️ 作为未来优化方向，暂不实现

---

## 3. Peeka Trace 命令实现方案

### 3.1 推荐方案：混合策略

根据 Peeka 的设计目标和 Python 版本支持情况，采用 **分层实现** 策略：

```
┌─────────────────────────────────────────────┐
│         Peeka Trace Command                 │
└─────────────────────────────────────────────┘
                    │
        ┌───────────┴───────────┐
        │                       │
   Python 3.12+           Python 3.9-3.11
        │                       │
        ▼                       ▼
  sys.monitoring         Decorator Wrapper
    (首选方案)              + Local Trace
                           (降级方案)
```

### 3.2 实现架构

#### 3.2.1 新增命令：`TraceCommand`

**文件位置**：`peeka/commands/trace.py`

**功能**：
- 追踪目标方法的调用链和耗时
- 以树形结构显示调用关系
- 支持深度限制、条件过滤、次数限制

**参数**：
```python
{
    "pattern": "module.Class.method",  # 目标方法
    "depth": 3,                        # 追踪深度（默认 3）
    "times": -1,                       # 观测次数（-1 无限）
    "condition_express": "cost > 50",  # 条件过滤
    "skip_builtin": True,              # 跳过内置方法（默认 True）
}
```

#### 3.2.2 扩展 `DecoratorInjector`

**新增方法**：
```python
class DecoratorInjector:
    def inject_trace(self, pattern: str, trace_config: Dict[str, Any]) -> str:
        """注入 trace 包装器"""

    def _create_trace_wrapper(self, func: Callable, watch_id: str, config: Dict[str, Any]) -> Callable:
        """创建 trace 包装器（根据 Python 版本选择策略）"""

    def _create_trace_wrapper_monitoring(self, ...):
        """使用 sys.monitoring 的实现（Python 3.12+）"""

    def _create_trace_wrapper_settrace(self, ...):
        """使用局部 sys.settrace 的实现（Python 3.9-3.11）"""
```

#### 3.2.3 数据结构

**调用树节点**：
```python
{
    "depth": 1,                          # 调用深度
    "function": "module.Class.method",   # 函数全名
    "filename": "/path/to/file.py",      # 文件路径
    "lineno": 42,                        # 行号
    "start_time": 1705586200.123,        # 开始时间（秒）
    "duration_ms": 10.5,                 # 执行耗时（毫秒）
    "children": [...]                    # 子调用（递归结构）
}
```

**观测数据**：
```python
{
    "type": "observation",
    "watch_id": "trace_001",
    "timestamp": 1705586200.123,
    "location": "AtExit",
    "func_name": "demo.Calculator.add",
    "call_tree": [                       # 调用树（扁平化或嵌套）
        {"depth": 0, "function": "demo.Calculator.add", "duration_ms": 15.2},
        {"depth": 1, "function": "demo.Helper.validate", "duration_ms": 2.1},
        {"depth": 2, "function": "builtins.isinstance", "duration_ms": 0.05},
        {"depth": 1, "function": "demo.Logger.info", "duration_ms": 1.8},
    ],
    "total_duration_ms": 15.2,
    "node_count": 4
}
```

### 3.3 CLI 命令

```bash
# 基本用法
peeka-cli trace "module.Class.method"

# 限制深度和次数
peeka-cli trace "module.func" --depth 5 --times 10

# 条件过滤（只追踪耗时超过 50ms 的调用）
peeka-cli trace "module.func" --condition "cost > 50"

# 跳过内置方法
peeka-cli trace "module.func" --skip-builtin

# 输出格式示例
{
  "type": "observation",
  "watch_id": "trace_abc123",
  "call_tree": [
    {"depth": 0, "function": "myapp.service.process", "duration_ms": 125.3},
    {"depth": 1, "function": "myapp.db.query", "duration_ms": 98.2},
    {"depth": 2, "function": "psycopg2.execute", "duration_ms": 95.1},
    {"depth": 1, "function": "myapp.cache.set", "duration_ms": 15.7}
  ],
  "total_duration_ms": 125.3
}
```

### 3.4 输出格式

#### 3.4.1 树形文本输出（TUI）

```
`---[125.3ms] myapp.service.process()
    +---[98.2ms] myapp.db.query()
    |   `---[95.1ms] psycopg2.execute()
    `---[15.7ms] myapp.cache.set()
```

#### 3.4.2 JSON 输出（CLI）

```json
{
  "type": "observation",
  "watch_id": "trace_abc123",
  "timestamp": 1705586200.123,
  "func_name": "myapp.service.process",
  "call_tree": [
    {
      "depth": 0,
      "function": "myapp.service.process",
      "filename": "/app/myapp/service.py",
      "lineno": 42,
      "duration_ms": 125.3,
      "children": [
        {
          "depth": 1,
          "function": "myapp.db.query",
          "filename": "/app/myapp/db.py",
          "lineno": 15,
          "duration_ms": 98.2,
          "children": [
            {
              "depth": 2,
              "function": "psycopg2.execute",
              "duration_ms": 95.1
            }
          ]
        },
        {
          "depth": 1,
          "function": "myapp.cache.set",
          "duration_ms": 15.7
        }
      ]
    }
  ],
  "total_duration_ms": 125.3,
  "node_count": 4
}
```

---

## 4. 实现计划

### 4.1 第一阶段：核心实现（基于 Decorator Wrapper）

**目标**：实现基本的 trace 功能，兼容 Python 3.9-3.14+

**任务**：
1. 创建 `peeka/commands/trace.py`
2. 扩展 `DecoratorInjector`：
   - 添加 `inject_trace()` 方法
   - 实现 `_create_trace_wrapper_settrace()` (局部 trace)
3. 注册 `trace` 命令到 `PeekaAgent`
4. 添加 CLI 命令：`peeka-cli trace <pattern> [options]`
5. 编写单元测试：`tests/test_trace.py`
6. 编写 E2E 测试：`tests/e2e/test_trace_e2e.py`

**核心挑战**：
- 局部 `sys.settrace` 的线程安全性
- 调用树的构建和序列化
- 性能开销控制（深度限制、内置方法过滤）

### 4.2 第二阶段：优化（Python 3.12+ sys.monitoring）

**目标**：在 Python 3.12+ 上使用 `sys.monitoring` 降低开销

**任务**：
1. 实现 `_create_trace_wrapper_monitoring()`
2. 运行时检测 Python 版本，自动选择实现
3. 性能对比测试（sys.settrace vs sys.monitoring）
4. 更新文档

**预期效果**：
- Python 3.12+ 性能开销 < 5%
- Python 3.9-3.11 性能开销 < 20%（局部 trace）

### 4.3 第三阶段：TUI 集成

**目标**：在 TUI 中添加 trace 视图

**任务**：
1. 创建 `peeka/tui/views/trace.py`
2. 实现树形可视化组件
3. 支持展开/折叠调用树节点
4. 添加耗时高亮（红色 > 100ms，黄色 > 50ms）

---

## 5. 性能对比预估

| 场景 | sys.settrace（全局） | sys.settrace（局部） | sys.monitoring | Decorator Only |
|------|---------------------|---------------------|----------------|----------------|
| 简单函数（10 次调用） | 1000%+ | 20-30% | 5-10% | < 1% |
| 复杂函数（100 次子调用） | 2000%+ | 50-100% | 10-20% | < 1% |
| 生产环境适用性 | ❌ | ⚠️ | ✅ | ✅ |

**结论**：
- ✅ Decorator + 局部 trace 在 **短时间、按需追踪** 场景下可接受
- ✅ sys.monitoring 在 Python 3.12+ 上是最优方案
- ❌ 全局 sys.settrace 永远不应该在生产环境使用

---

## 6. 与 Arthas 的对比

| 功能 | Arthas (Java) | Peeka (Python) |
|------|---------------|----------------|
| 调用树追踪 | ✅ | ✅（计划实现） |
| 耗时统计 | ✅ | ✅ |
| 条件过滤 | ✅（OGNL） | ✅（simpleeval） |
| 深度限制 | ✅ | ✅ |
| 跳过 JDK/内置方法 | ✅ | ✅ |
| 动态字节码增强 | ✅（ASM） | ⚠️（局部 trace / sys.monitoring） |
| 性能开销 | < 5% | < 5% (3.12+) / < 20% (3.9-3.11) |

**差异**：
- Java 字节码增强更成熟，Python 需要依赖解释器钩子
- Python 3.12+ 的 sys.monitoring 提供了接近 Arthas 的能力
- Peeka 的局部 trace 方案在短时间追踪场景下性能可接受

---

## 7. 总结与建议

### 7.1 推荐实现方案

**第一优先级**：基于 Decorator Wrapper + 局部 sys.settrace
- ✅ 与 Peeka 现有架构一致
- ✅ 兼容 Python 3.9-3.14+
- ✅ 实现复杂度低
- ✅ 短时间追踪场景性能可接受

**第二优先级**：Python 3.12+ 支持 sys.monitoring
- ✅ 显著降低性能开销
- ✅ 官方支持，未来趋势
- ⚠️ 仅限 Python 3.12+

**未来方向**：探索 eBPF（长期目标）
- ✅ 极低开销
- ❌ 实现复杂，生态不成熟
- ⏸️ 暂不实现，持续关注

### 7.2 实施建议

1. **MVP 阶段**：实现基于局部 sys.settrace 的基础 trace 功能
2. **优化阶段**：添加 sys.monitoring 支持（Python 3.12+）
3. **测试验证**：在真实应用中测试性能开销和稳定性
4. **文档完善**：编写详细的使用文档和性能调优指南

### 7.3 风险与限制

**性能风险**：
- 局部 sys.settrace 仍有 20-30% 开销
- 深度过大或调用频率过高时可能影响业务

**缓解策略**：
- 默认深度限制为 3 层
- 支持条件过滤减少触发次数
- 文档明确标注性能影响

**使用限制**：
- 不适合追踪高频调用（> 1000 QPS）
- 不适合长时间持续追踪（建议 < 1 分钟）
- 适合问题诊断和性能分析场景

---

## 8. 参考资料

- [Arthas Trace Command Documentation](https://arthas.aliyun.com/en/doc/trace.html)
- [PEP 669: Low Impact Monitoring for CPython](https://peps.python.org/pep-0669/)
- [Python sys.settrace Documentation](https://docs.python.org/3/library/sys.html#sys.settrace)
- [eBPF for Python Tracing](https://github.com/iovisor/bcc/blob/master/docs/reference_guide.md)
- [PyCharm Blog: sys.monitoring API](https://blog.jetbrains.com/pycharm/2024/01/new-low-impact-monitoring-api-in-python-3-12/)
