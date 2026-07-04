# ADR 0002: Trace 命令直接子调用（Direct-Callee）语义

- 状态：Accepted（已修订 2026-07-04）
- 日期：2026-06-26
- 决策者：peeka 维护者
- 相关计划：`.sisyphus/plans/trace-single-layer.md`

## 上下文

`trace` 命令最初以递归调用树（call tree）为核心语义，通过 `-d/--depth`（默认值 3）控制展开深度。三条后端均按此约定实现：

- `sys.monitoring`（Python 3.12+）
- `sys.settrace`（Python 3.8–3.11）
- `wrapper_only`（gevent monkey-patched 环境的降级后端）

### 已知问题

随着使用积累，该设计暴露出三类问题：

**1. API 复杂度**：`--depth` 参数影响输出形状，同一命令在不同 depth 下产生结构完全不同的 JSON，给 CLI 客户端和前端解析带来额外负担。

**2. 后端行为不对齐**：gevent 路径在检测到 monkey-patch 时静默降级为 `wrapper_only`，返回 `call_tree = []`，但 `depth` 参数依然被接受，造成"参数存在但无效"的语义缺口。

**3. 心智模型错位**：Arthas（peeka 的主要参照系）默认 `trace` 只显示一层直接子调用；用户期望"trace 一个函数"看到的是它直接调用了哪些函数，而非一棵深度可变的递归树。peeka 的 depth-based 模型与此预期不符，产生持续的认知摩擦。

### 之前的实现（不可持续）

三条后端各自递归跟踪帧，在不同代码路径下拼装 `children` 嵌套结构：

```python
# 旧实现示意（sys.settrace 路径）
def _record_call(frame, event, depth_remaining):
    if depth_remaining <= 0:
        return
    node = {"function": ..., "children": []}
    # 递归追踪子帧 ...
```

这使得三条后端都需要维护帧栈和深度计数器，代码量大且难以测试边界条件。

## 决策

采用**单层直接子调用（single-layer direct-callee）**语义：被 trace 的目标函数执行期间，只记录它直接调用的一层函数，不递归展开。

### 1. 移除 `--depth` 参数

从 CLI argparser（`parsers/observe.py`）的 trace 子命令中完整删除 `-d/--depth`。argparse 遇到未知参数会报错，不保留任何兼容别名，强制调用方更新。

### 2. 保留 `call_tree` 键名，变更值语义

`call_tree` JSON 键名不变（避免破坏已有输出解析的 key-existence 检查），但值从嵌套树变为**扁平聚合列表**：每条记录代表一个 `(function, filename, lineno)` 组合在单次执行中的累计统计。

```json
{
  "type": "observation",
  "call_tree": [
    {
      "function": "module.helper",
      "filename": "app.py",
      "lineno": 42,
      "count": 3,
      "total_ms": 15.0,
      "min_ms": 4.5,
      "max_ms": 6.2
    }
  ],
  "total_duration_ms": 20.0,
  "self_time_ms": 5.0,
  "callee_count": 1,
  "node_count": 2
}
```

### 3. 每次执行内聚合

同一次目标函数执行中，相同的 `(function, filename, lineno)` 三元组合并为一条记录，附带 `count`、`total_ms`、`min_ms`、`max_ms`。这使得循环内被反复调用的同一函数只产生一条聚合条目，输出量有界。

### 4. 新增观测字段

| 字段 | 含义 |
|---|---|
| `self_time_ms` | `total_duration_ms - sum(callee.total_ms)`，向下取整为 0（不允许负值） |
| `callee_count` | `call_tree` 列表长度（去重后的直接子调用种数） |
| `node_count` | `1 + callee_count`（目标函数本身 + 直接子调用数，为兼容性保留） |

### 5. TUI 已完成适配（2026-07-04 修订）

界面端的 `#trace-depth` 输入控件已在后续重构中删除，界面不再向 agent 发送 `depth` 字段。`TraceCommand` 中的 `params.pop("depth", None)` 兼容垫片也已随之移除。当前界面使用 `#trace-obs-table` 展示活跃 trace 列表，并通过 `min_duration` 参数控制过滤阈值。

### 6. Gevent 路径不变

gevent monkey-patch 环境下，`wrapper_only` 后端继续返回 `call_tree = []` 并附加降级元数据，行为与之前一致。`--depth` 移除后，该路径也不再接受无意义的深度参数。

### 实现拆分

| 文件 | 变更说明 |
|---|---|
| `trace_backends.py` | 三条后端统一返回扁平 `direct_callees` 列表，通过共享 `_aggregate_callees()` helper 聚合 |
| `trace.py` | 从 `direct_callees` 构建 observation，计算 `self_time_ms`、`callee_count` |
| `trace_backends.py` | `_is_builtin_or_stdlib()` 共享过滤器，统一 skip-builtin 行为 |
| `parsers/observe.py` | trace 子命令移除 `-d/--depth` 参数声明 |

## 边界（哪些**没**纳入本次变更）

| 范围 | 原因 |
|---|---|
| `watch --depth` / `stack --depth` | 与 trace 无关，语义不同，保持现状 |
| `#trace-depth` 输入控件 | 已在后续重构中删除（2026-07-04），界面改用 `#trace-obs-table` 和 `min_duration` 参数 |
| 观测数据迁移工具 | `call_tree` 值语义为破坏性变更，明确接受；不提供数据迁移 |
| gevent `wrapper_only` 后端实现 | 行为不变，仅移除 depth 参数接受路径 |

## 后果

### 正面

- **心智模型对齐**：与 Arthas 默认 trace 行为一致，用户不需要额外学习 depth 语义
- **跨版本输出一致**：三条后端（`sys.monitoring`、`sys.settrace`、`wrapper_only`）在输出结构上统一，Python 3.8–3.14+ 行为差异缩小
- **API 面收窄**：去掉 `--depth` 后 trace 命令参数简洁，降低使用门槛
- **实现简化**：后端不再需要维护帧栈和深度计数器，递归跟踪逻辑消除

### 负面 / 妥协

- **破坏性变更**：`call_tree` 的值从嵌套树变为扁平列表；消费旧格式（存在 `children` 字段）的代码必须更新
- **多层分析需多次 trace**：需要分析深层调用链时，用户需在不同入口分别执行 trace（这是有意为之的设计边界，而非限制）
- **深度控件已删除**：`#trace-depth` 控件已在后续重构中移除，不再存在"控件可见但无效"的状态。

### 中性

- `call_tree` 键名不变——只有值语义变化，对 key-existence 检查透明
- `node_count` 保留为 `1 + callee_count`，为依赖该字段的现有代码提供平滑过渡

## 后续工作（不在本 ADR 范围）

如果未来需要多层调用树分析，可以考虑：

1. 新增独立命令（如 `calltree`），明确以递归树为一等公民，与 `trace` 的单层语义共存
2. 当前 `min_duration` 参数已在 `#trace-obs-table` 视图中作为过滤阈值生效，`#trace-depth` 控件不再适用。

但目前单层语义已满足主流诊断需求，**不**应预先引入复杂度。

## 参考

- 关键源文件：
  - `peeka/core/instrumentation/trace_backends.py`
  - `peeka/core/instrumentation/trace.py`
  - `peeka/cli/parsers/observe.py`
  - `peeka/commands/trace.py`
- 实现 commits：`1c2bf92`、`a767855`、`7c7688e`、`735a3cf`、`a43acfc`
- 测试 commits：`9b4b088`、`5c29cc5`、`84b1a0f`
