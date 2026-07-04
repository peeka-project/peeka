# DecoratorInjector 注入与 Trace 调用树问题复盘

| 字段 | 值 |
|------|-----|
| **话题** | DecoratorInjector 在实例方法识别、`__main__` 解析与 trace 调用树构建/聚合中的故障 |
| **受影响组件** | core/injector, core/instrumentation/trace_backends, commands/trace |
| **最高严重级别** | SEV-1 (High) |
| **事故次数** | 4 |
| **时间跨度** | 2026-01-29 至 2026-07-04 |

## 案例索引

| # | 事故 | 严重级别 | 日期 |
|---|------|----------|------|
| [#4](#事故-4trace-直接被调函数聚合与-stdlib-跳过栈不变量漂移) | Trace 直接被调函数聚合与 stdlib 跳过栈不变量漂移 | SEV-2 | 2026-07-04 |
| [#3](#事故-3trace-调用树在递归多层调用下被破坏) | Trace 调用树在递归/多层调用下被破坏 | SEV-1 | 2026-02-28 |
| [#2](#事故-2脚本启动目标无法解析到-__main__-模块) | 脚本启动目标无法解析到 `__main__` 模块 | SEV-1 | 2026-02-11 |
| [#1](#事故-1实例方法-self-捕获失败) | 实例方法 `self` 捕获失败 | SEV-1 | 2026-01-29 |

> 索引按时间倒序排列（与事故组块顺序一致），点击编号可跳转到对应事故。

## 话题概述

该话题覆盖 DecoratorInjector 与 trace backend 的四类核心稳定性问题：方法绑定语义理解偏差（`self` 捕获）、脚本启动目标的模块身份解析（`__main__` vs 文件名模块）、递归场景下 trace 调用树状态管理（单变量被覆盖），以及 trace 输出模型从任意深度树迁移为“直接被调函数聚合”时产生的深度、异常退出和公开字段契约漂移。共同特征是“运行时语义与实现假设不一致”，导致注入成功率或观测正确性受损。

2026-07-04 的新增事故说明，trace backend 的 public payload 不能只靠单一路径验证。`children` → `direct_callees`、深度限制、stdlib frame 跳过、`PY_UNWIND` 异常退出、TUI drill-down 的函数名解析和文档中的 `--depth` 残留形成同一条契约链；其中任一层未同步，都会让用户看到错误的调用关系或无法继续追踪。

---

## 事故 #4：Trace 直接被调函数聚合与 stdlib 跳过栈不变量漂移

> **Tag 范围**：`v0.1.19` → `HEAD` | **严重级别**：SEV-2 | **日期**：2026-07-04

### 概要

v0.1.20 开发周期中，trace backend 从嵌套 `children` 调用树迁移到只记录直接被调函数并做聚合的 `direct_callees` 模型。该迁移修复了深层调用噪音和 drill-down pattern 不可解析的问题，但随后暴露出 stdlib frame 跳过时的深度栈不变量缺口：`json.dumps(default=user_cb)` 这类 stdlib 内回调会被误记为根函数的直接 callee；异常退出路径 `PY_UNWIND` 还会留下 skipped marker，影响后续深度判断。

### 根因分析

#### 类别
Logic Error / Public Contract Drift

#### 分析

修复前，多个 trace backend 对“调用树”的语义不一致：wrapper-only、`sys.monitoring` 和 `sys.settrace` 路径仍暴露嵌套 `children`，并依赖 `max_depth`/`call_stack` 在不同层控制深度。`1c2bf92` 将输出契约收敛为每次根调用的直接被调函数聚合：

```python
direct_callees = _aggregate_callees(func_children)
root_node = {
    "function": f"{func.__module__}.{func.__qualname__}",
    "direct_callees": direct_callees,
}
```

该设计要求 backend 在跳过 stdlib/builtin frame 时仍维护真实调用深度。`ebc66a9` 发现仅 `return` 而不入栈会让 stdlib 内调用的用户 callback 看起来像 depth=2：

```python
if skip_builtin and _is_builtin_or_stdlib(code):
    call_stack.append({"_code": code, "_skipped": True})
    return
```

`488f205` 进一步补齐 `PY_UNWIND`：异常退出必须弹出 marker，但不记录不完整调用，否则 skipped frame 会污染后续 observation 的深度状态。

同时，`6329dc9` 将 callee 函数名改为 module-qualified 形式，使 TUI drill-down 能使用 `module.function` 重新发起 trace；`351e260` 删除文档、示例和兼容 shim 中已经失效的 `--depth` 概念，避免 CLI 公开契约继续暗示递归树深度可配。

#### 致因提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| 致因提交无法确定性定位 | - | 2026-06-26 前 | trace backend 输出模型从树形 children 演进到直接 callee 聚合时，缺少跨 backend 的 payload/schema 不变量测试 |

### 复现

#### 前置条件
- Python 3.12+ 可走 `sys.monitoring` backend。
- 目标函数内部调用 stdlib 函数，并由 stdlib 回调用户函数，例如 `json.dumps(obj, default=user_cb)`。

#### 步骤
1. 对根函数执行 `trace`，保持 `skip_builtin=True`。
2. 触发 stdlib 内部调用用户 callback。
3. 检查 trace observation 的 `call_tree` / `direct_callees`。
4. 让 stdlib frame 通过异常路径退出，再触发下一次 trace。

#### 预期行为
只记录根函数的直接用户 callee；stdlib 内部 callback 不应被误判为根函数直接 callee；异常退出后深度栈被恢复。

#### 实际行为
在 marker 修复前，stdlib frame 未入栈导致 callback 深度被低估；在 `PY_UNWIND` 修复前，异常退出可能留下 skipped marker，污染后续深度判断。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| [`1c2bf92`](https://github.com/peeka-project/peeka/commit/1c2bf92623701aeb206e833275d3ffa1224468f2) | lufeihaidao | 2026-06-26 | fix(trace): all backends record only direct callees with aggregation |
| [`6329dc9`](https://github.com/peeka-project/peeka/commit/6329dc9b7083c34be752e716349ee5c4d4686178) | lufeihaidao | 2026-07-01 | fix(trace): emit module-qualified callee names so drill-down patterns resolve |
| [`ebc66a9`](https://github.com/peeka-project/peeka/commit/ebc66a9074002e56c4c39b5f2d7a201f6b678135) | lufeihaidao | 2026-07-04 | fix(trace): keep depth accurate when skipping stdlib frames in monitoring backend |
| [`488f205`](https://github.com/peeka-project/peeka/commit/488f20559f2e7f8bcd2193b5e5e10344d60c8f34) | lufeihaidao | 2026-07-04 | fix(trace): pop skipped stdlib markers on PY_UNWIND |
| [`351e260`](https://github.com/peeka-project/peeka/commit/351e260e9372ddb7bcd236e25654a116f2278023) | lufeihaidao | 2026-07-04 | fix(cli): remove stale trace --depth references and compatibility shim |

#### 变更内容
- `peeka/core/instrumentation/trace_backends.py` 增加 `_aggregate_callees()`，并让 wrapper-only、monitoring、settrace backend 统一输出 `direct_callees`。
- `sys.monitoring` backend 对 skipped stdlib frame 入栈 `_skipped` marker，`PY_RETURN` 和 `PY_UNWIND` 均负责弹出。
- callee name 改为 module-qualified，支持 TUI drill-down 直接复用为 trace pattern。
- `README.zh-CN.md`、`docs/demo-guide.md`、`examples/*`、`peeka/commands/trace.py`、`peeka/core/injector.py` 删除已失效的 `--depth` / max-depth 兼容路径。

#### 验证
修复提交新增或更新 `tests/test_trace.py`，覆盖 direct-callee 聚合、stdlib callback 不被记录、正常直接 callee 仍捕获、`PY_UNWIND` 后 marker 被弹出；`351e260` 通过删除兼容 shim 降低旧参数继续被误用的风险。

### 影响

- **受影响用户**：依赖 trace 调用关系、聚合耗时、drill-down 和 CLI 文档示例的用户。
- **持续时间**：直接 callee 迁移从 2026-06-26 开始，follow-up 修复持续到 2026-07-04。
- **数据影响**：无持久数据损坏；影响为诊断输出错误或公开参数文档误导。

### 时间线

| 时间 | 事件 |
|------|------|
| 2026-06-26 | `1c2bf92` 将 trace payload 收敛为 direct-callee 聚合 |
| 2026-07-01 | `6329dc9` 修复 callee 名称不可用于 drill-down 的问题 |
| 2026-07-04 | `ebc66a9` 修复 skipped stdlib frame 的深度维护 |
| 2026-07-04 | `488f205` 修复异常退出路径 marker 泄漏 |
| 2026-07-04 | `351e260` 清理 stale `--depth` 公开契约 |

### 经验教训

#### 做得好的方面
- 后续修复围绕同一 trace payload 契约持续收敛，没有继续扩展多套输出形状。
- 回归测试覆盖了 stdlib callback 和异常退出这类真实运行时边界。

#### 可以改进的方面
- 输出 schema 迁移时应同步冻结 CLI、TUI、文档和所有 backend 的契约矩阵。
- 跳过 frame 不是“什么都不做”；只要会影响深度判断，就必须进入状态机并在所有退出路径清理。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为 trace payload 增加 backend 参数化 schema 测试，覆盖 wrapper-only/monitoring/settrace | P0 | 待处理 |
| 为 skipped frame 增加 return/unwind 双退出路径的不变量测试 | P0 | 已完成 |
| 在命令文档生成或示例测试中检查已删除参数（如 `--depth`）不再出现 | P1 | 待处理 |

### 预防

- **立即执行**：trace backend 的公开字段迁移必须同步更新 CLI/TUI/文档示例和回归测试。
- **短期**：为 `direct_callees`、module-qualified function、`min_ms/max_ms/count` 建立 JSONL contract fixture。
- **长期**：用共享 schema 描述 trace observation，并从 schema 驱动 TUI rendering 与 CLI 文档示例。

### 参考

- 修复提交：`1c2bf92`, `6329dc9`, `ebc66a9`, `488f205`, `351e260`

---

## 事故 #3：Trace 调用树在递归/多层调用下被破坏

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-1 | **日期**：2026-02-28

### 概要

`trace` 命令输出的调用树父子关系错乱，进入/退出计数与耗时统计失真。问题由 `_trace_with_monitoring` 使用单一进入时间变量导致递归覆盖引起。

### 根因分析

#### 类别
Logic Error

#### 分析
原实现进入函数时直接覆盖 `current_entry_time`，在递归或嵌套调用中父层时间戳被子层覆盖。结果是退出阶段无法匹配正确层级，Arthas 风格树形结构被破坏。

关键修复思想（单变量 → 栈）：

```python
# Before:
current_entry_time = ...  # single global variable

# After:
stack: List[float] = []  # stack of entry times for current call chain

def wrapper(...):
    stack.append(time())  # push our entry time
    try:
        return original(...);
    finally:
        entry_time = stack.pop()  # pop when we exit
        # calculate duration and publish
```

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 原始 trace 命令实现采用单状态变量 |

> 源文件未给出确定性致因 hash。

### 复现

#### 前置条件
- 使用 `trace` 观测递归函数或多层调用链。

#### 步骤
1. 对递归方法执行 trace。
2. 触发多层调用。
3. 查看调用树输出。

#### 预期行为
父子层级与每层耗时准确。

#### 实际行为
父子关系错误，时间统计异常。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `929ca0f` | 未提供 | 2026-02-28 | fix(injector): redesign _trace_with_monitoring for correct Arthas-style call tree |

#### 变更内容
- 以调用栈保存每层进入时间。
- 退出阶段执行对应 `pop`，按层计算耗时并发布观测。

#### 验证
- 递归调用显示正确树结构。
- 父子关系与时间统计恢复正确。

### 影响

- **受影响用户**：使用 trace 进行性能/调用链分析的用户。
- **持续时间**：自原始 trace 实现至 2026-02-28。
- **数据影响**：无持久化数据损坏；诊断结果不可信。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | 原始 trace 实现引入单变量状态管理 |
| 2026-02-28 | 调用树错乱问题被记录 |
| 2026-02-28 | 修复提交：`929ca0f` |
| 2026-02-28 | 验证递归调用树与耗时正常 |

### 经验教训

#### 做得好的方面
- 直接对状态模型重构，而非补丁式修复单分支。

#### 可以改进的方面
- 递归场景测试覆盖在初版缺失。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为 trace 增加递归与深层嵌套回归测试 | P0 | 待处理 |

### 预防

- **立即执行**：涉及嵌套/递归状态均采用栈结构建模。
- **短期**：增加 Arthas 风格输出一致性快照测试。
- **长期**：将 trace 核心状态机文档化并做属性测试。

### 参考

- 修复 PR/提交：`929ca0f`
- 相关 issue：未提供

---

## 事故 #2：脚本启动目标无法解析到 `__main__` 模块

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-1 | **日期**：2026-02-11

### 概要

当目标进程通过 `python script.py` 启动时，注入器按文件名模块路径查找，未能识别对象实际驻留在 `__main__`，导致方法查找失败。

### 根因分析

#### 类别
Integration Error

#### 分析
Python 在脚本直启模式下将模块命名为 `__main__`。原实现仅依赖用户提供的导入路径（如 `demo.Calculator`），不会自动映射到 `__main__`。因此同一代码在“模块导入启动”与“脚本直启”两种运行模式下行为不一致。

修复策略：
1. 枚举当前进程模块并查找 `__main__`。
2. 比较目标模块文件路径与 `__main__.__file__`。
3. 匹配时直接返回 `__main__`；否则走常规导入。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 原始模块解析仅支持常规导入路径 |

> 源文件未给出致因 hash。

### 复现

#### 前置条件
- 目标通过 `python examples/demo.py` 启动。

#### 步骤
1. 执行 `peeka` 注入 `demo.Calculator.add`。
2. 触发注入查找。

#### 预期行为
解析到脚本对应模块并成功注入。

#### 实际行为
报找不到模块/函数。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `321450d` | 未提供 | 2026-02-11 | fix(injector): resolve __main__ module for script-based targets |

#### 变更内容
- 增加 `__main__` 特殊解析分支与文件路径匹配逻辑。
- 保持非脚本导入场景不受影响。

#### 验证
- `python script.py` 场景可成功解析。
- 普通导入与交互式场景保持可用。

### 影响

- **受影响用户**：以脚本形式运行目标程序的用户。
- **持续时间**：自原始解析实现至 2026-02-11。
- **数据影响**：无；表现为注入失败。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | 原始解析实现引入脚本模式盲区 |
| 2026-02-11 | 脚本目标解析失败被确认 |
| 2026-02-11 | 修复提交：`321450d` |
| 2026-02-11 | 脚本/模块双场景验证通过 |

### 经验教训

#### 做得好的方面
- 修复覆盖了脚本、模块、交互三类典型运行入口。

#### 可以改进的方面
- 初期未将运行模式差异纳入测试矩阵。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 新增 `python file.py` 与 `python -m` 双模式注入测试 | P0 | 待处理 |

### 预防

- **立即执行**：注入解析优先检查 `__main__` 映射可能性。
- **短期**：模块解析增加文件路径一致性校验。
- **长期**：建立统一符号解析层，屏蔽启动模式差异。

### 参考

- 修复 PR/提交：`321450d`
- 相关 issue：未提供

---

## 事故 #1：实例方法 `self` 捕获失败

> **Tag 范围**：`未知` → `HEAD` | **严重级别**：SEV-1 | **日期**：2026-01-29

### 概要

`watch` 观测实例方法时无法正确捕获 `self`，导致观测数据缺失或错误，影响核心注入能力。

### 根因分析

#### 类别
Logic Error

#### 分析
原始实现以 `hasattr(func, '__self__')` 判断实例方法。该判断对未装饰场景不可靠，导致绑定语义误判。正确方式是检查父对象是否为类：若不是类，则该可调用属于实例绑定方法。

修复关键片段：

```python
if inspect.isclass(parent):
    # This is an unbound method (on the class itself)
    is_instance_method = False
else:
    # This is a bound instance method (on an instance)
    is_instance_method = True
```

并新增 `_is_instance_method` 标志进入 watch 配置。

#### 致因提交
引入该 bug 的提交：

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `未提供` | 未提供 | 未提供 | 最初 `DecoratorInjector` 实现使用 `__self__` 进行方法类型判断 |

### 复现

#### 前置条件
- 定义实例方法并通过对象调用。

#### 步骤
1. 定义并调用：
   ```python
   class Calculator:
       def add(self, a, b):
           return a + b
   calc = Calculator()
   calc.add(1, 2)
   ```
2. 使用 peeka 观测 `calc.add`。
3. 触发调用并查看观测结果。

#### 预期行为
观测中应包含正确的 `self` 信息。

#### 实际行为
`self` 缺失或不正确。

### 修复

#### 修复提交

| 提交 | 作者 | 日期 | 描述 |
|------|------|------|------|
| `46a5591` | 未提供 | 2026-01-29 | fix(injector): correctly capture self for instance methods |

#### 变更内容
- 以 `inspect.isclass(parent)` 重写实例方法识别逻辑。
- 将识别结果显式写入 `_is_instance_method` 配置。

#### 验证
- 实例方法可正确捕获 `self`。
- 静态方法、类方法、普通函数不受影响。

### 影响

- **受影响用户**：依赖实例方法观测的所有用户。
- **持续时间**：自最初注入器实现至 2026-01-29。
- **数据影响**：无持久化影响；观测数据不完整。

### 时间线

| 时间 | 事件 |
|------|------|
| 未提供 | Injector 初始实现引入错误判断 |
| 2026-01-29 | `self` 捕获问题被报告 |
| 2026-01-29 | 修复提交：`46a5591` |
| 2026-01-29 | 实例/类/静态方法回归验证通过 |

### 经验教训

#### 做得好的方面
- 修复同时明确了 Python 绑定方法语义，提升可维护性。

#### 可以改进的方面
- 初始实现对方法绑定模型理解不足。

#### 行动项

| 行动 | 优先级 | 状态 |
|------|--------|------|
| 为实例方法/类方法/静态方法分别建立注入回归用例 | P0 | 待处理 |

### 预防

- **立即执行**：统一使用 `inspect` 做方法语义判断。
- **短期**：在 watch/trace 的方法分类处添加断言与日志。
- **长期**：沉淀 Python 绑定语义设计说明，减少误判重现。

### 参考

- 修复 PR/提交：`46a5591`
- 相关 issue：未提供
